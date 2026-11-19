"""학위논문 작업실 — 브라우저 입력 화면.

실행:  python thesis.py gui          (또는 python scripts/gui.py)
       → 브라우저가 열리고 http://127.0.0.1:8765 에 입력 화면이 뜹니다.
       → 끝낼 때는 터미널에서 Ctrl+C

화면 구성
  ① 기본 정보·주제   : 제목·학교·지도교수·심사위원, 연구 주제·방법·연구 문제·주제어
  ② 자료 넣기       : 글 직접 입력 / 이미지(캡처 Ctrl+V 붙여넣기·끌어놓기) / 파일(txt·docx·pdf·xlsx…)
  ③ 진행 현황       : 장별 글자수·TODO, 검사 결과, Word·PDF 만들기
  하단 Claude 입력란 : 내 컴퓨터의 Claude Code 로 원고 수정 요청 (없으면 API 키로 질문만)

외부 패키지 없이 파이썬 기본 기능만 씁니다. (API 키 방식은 `pip install anthropic` 필요)
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import thesis  # noqa: E402  (루트의 thesis.py: 저장·자료 추가 로직 재사용)
from check import run_checks  # noqa: E402
from thesis_lib import (  # noqa: E402
    OUTPUT_DIR, TODO_RE, iter_body_lines, load_config, strip_comments,
)

SESSION_FILE = OUTPUT_DIR / ".claude_session"
_chat_lock = threading.Lock()
_api_history: list[dict] = []


# ---------------------------------------------------------------------------
# 상태 읽기
# ---------------------------------------------------------------------------
def chapter_state() -> list[dict]:
    out = []
    for p in load_config().parts:
        item = {"file": p.file, "section": p.section, "numbered": p.numbered,
                "title": "", "sections": [], "chars": 0, "todos": 0, "exists": p.path.exists()}
        if p.path.exists():
            text = strip_comments(p.path.read_text(encoding="utf-8"))
            for _, line in iter_body_lines(text):
                if line.startswith("# ") and not item["title"]:
                    item["title"] = line[2:].strip()
                elif line.startswith("## "):
                    item["sections"].append(line[3:].strip())
                elif not line.startswith("#"):
                    item["todos"] += len(TODO_RE.findall(line))
                    item["chars"] += len(TODO_RE.sub("", line).replace(" ", ""))
        out.append(item)
    return out


def sources_rows() -> list[dict]:
    rows = []
    if thesis.MANIFEST.exists():
        for line in thesis.MANIFEST.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 5 and cells[0] not in ("파일",) and not set(cells[0]) <= {"-"}:
                rows.append(dict(zip(["file", "kind", "summary", "where", "status"], cells)))
    return rows


def chat_backend() -> dict:
    if shutil.which("claude"):
        return {"kind": "claude-code", "label": "Claude Code 연결됨 · 원고 수정 가능"}
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
            return {"kind": "api", "label": "API 키 연결됨 · 답변만 (파일 수정 불가)"}
        except ImportError:
            return {"kind": "none", "label": "API 키는 있지만 anthropic 패키지가 없습니다 (pip install anthropic)"}
    return {"kind": "none", "label": "연결 안 됨 · Claude Code 를 설치하거나 ANTHROPIC_API_KEY 를 설정하세요"}


def state() -> dict:
    cfg = load_config()
    info = {k: thesis.clean(v) for k, v in cfg.info.items() if not isinstance(v, list)}
    committee = [m for m in (cfg.info.get("committee") or []) if "○○" not in str(m)]
    with contextlib.redirect_stdout(io.StringIO()):
        errors, warnings = run_checks(verbose=False)
    return {
        "info": info, "committee": committee, "topic": cfg.raw.get("topic") or {},
        "chapters": chapter_state(), "sources": sources_rows(),
        "errors": errors, "warnings": warnings, "backend": chat_backend(),
        "outputs": {ext: (OUTPUT_DIR / f"{cfg.fmt.get('output_name', 'thesis')}.{ext}").exists() for ext in ("docx", "pdf")},
        "output_name": cfg.fmt.get("output_name", "thesis"),
    }


# ---------------------------------------------------------------------------
# 동작
# ---------------------------------------------------------------------------
def do_setup(data: dict) -> dict:
    topic = data.get("topic") or {}
    topic["research_questions"] = [r.strip() for r in topic.get("research_questions", []) if r.strip()]
    topic["keywords"] = [k.strip() for k in topic.get("keywords", []) if k.strip()]
    thesis.save_setup(data.get("info") or {}, topic, data.get("committee"))
    return {"ok": True, "message": "저장했습니다. 연구 문제는 1장, 주제어는 국문 초록에 반영됩니다."}


def do_add(data: dict) -> dict:
    tmp = None
    ns = argparse.Namespace(file=None, text=None, to=data.get("to") or None, section=data.get("section") or None,
                            caption=data.get("caption") or None, id=data.get("id") or None, width="80%",
                            note=data.get("note") or None, lead=None)
    if data.get("mode") == "text":
        ns.text = (data.get("text") or "").strip()
        if not ns.text:
            return {"ok": False, "message": "넣을 글이 비어 있습니다."}
    else:
        if not data.get("data"):
            return {"ok": False, "message": "파일이나 이미지를 먼저 골라 주세요."}
        tmp = Path(tempfile.mkdtemp(prefix="thesis_upload_"))
        name = Path(data.get("filename") or "upload.bin").name
        f = tmp / name
        f.write_bytes(base64.b64decode(data["data"].split(",", 1)[-1]))
        ns.file = str(f)
        if data.get("mode") == "image":
            ns.lead = (data.get("lead") or "").strip() or None   # 그림 앞 안내 문장 (@fig 자리에 그림 번호)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            thesis.cmd_add(ns)
        return {"ok": True, "message": buf.getvalue().strip()}
    except SystemExit as e:
        return {"ok": False, "message": (buf.getvalue() + "\n" + str(e)).strip()}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def do_build() -> dict:
    r = subprocess.run([sys.executable, str(HERE / "build.py")], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"ok": r.returncode == 0, "message": (r.stdout + r.stderr).strip()}


CHAT_GUIDE = (
    "이 요청은 논문 작업실 화면의 Claude 입력란에서 왔다. 사용자는 비전공자일 수 있으니 쉬운 한국어로 짧게 답한다. "
    "CLAUDE.md 규칙을 따르고, 원고를 고쳤다면 무엇을 어디에 고쳤는지 알려준다. 필요하면 python scripts/build.py 로 검사·빌드한다."
)


def chat_claude_code(message: str) -> dict:
    sid = SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else ""
    cmd = ["claude", "-p", message, "--output-format", "json",
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Bash(python:*)", "Bash(python3:*)",
           "--append-system-prompt", CHAT_GUIDE]
    if sid:
        cmd += ["--resume", sid]
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reply": "15분 안에 끝나지 않아 멈췄습니다. 요청을 나눠서 보내 주세요."}
    out = r.stdout.strip()
    try:
        data = json.loads(out)
        if data.get("session_id"):
            OUTPUT_DIR.mkdir(exist_ok=True)
            SESSION_FILE.write_text(data["session_id"])
        reply = data.get("result") or "(답변 없음)"
        return {"ok": not data.get("is_error", False), "reply": reply}
    except json.JSONDecodeError:
        if sid and r.returncode != 0:
            SESSION_FILE.unlink(missing_ok=True)   # 이전 대화를 못 찾으면 새 대화로
        return {"ok": r.returncode == 0, "reply": out or r.stderr.strip() or "Claude Code 실행에 실패했습니다."}


def chat_api(message: str) -> dict:
    """Claude Code 가 없을 때: API 키로 질문·답변만 (파일은 고치지 않음)."""
    import anthropic

    rules = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    yaml_text = (ROOT / "thesis.yaml").read_text(encoding="utf-8")
    outline = "\n".join(f"- {c['file']}: {c['title']} / 절: {', '.join(c['sections'])} / {c['chars']}자, TODO {c['todos']}"
                        for c in chapter_state())
    system = (f"{CHAT_GUIDE}\n이 모드에서는 파일을 직접 고칠 수 없으니, 원고에 넣을 문장은 그대로 복사해 쓸 수 있게 제시한다.\n\n"
              f"<CLAUDE.md>\n{rules}\n</CLAUDE.md>\n\n<thesis.yaml>\n{yaml_text}\n</thesis.yaml>\n\n<현재 원고 개요>\n{outline}\n</현재 원고 개요>")
    _api_history.append({"role": "user", "content": message})
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=16000, system=system, messages=_api_history,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
    except anthropic.APIStatusError as e:
        _api_history.pop()
        return {"ok": False, "reply": f"API 오류 ({e.status_code}): {e.message}"}
    except anthropic.APIConnectionError:
        _api_history.pop()
        return {"ok": False, "reply": "인터넷 연결을 확인해 주세요."}
    if resp.stop_reason == "refusal":
        _api_history.pop()
        return {"ok": False, "reply": "이 요청에는 답할 수 없습니다. 표현을 바꿔 다시 시도해 주세요."}
    text = "".join(b.text for b in resp.content if b.type == "text")
    _api_history.append({"role": "assistant", "content": resp.content})
    return {"ok": True, "reply": text}


def do_chat(data: dict) -> dict:
    message = (data.get("message") or "").strip()
    if data.get("reset"):
        SESSION_FILE.unlink(missing_ok=True)
        _api_history.clear()
        return {"ok": True, "reply": "새 대화를 시작합니다."}
    if not message:
        return {"ok": False, "reply": "메시지를 입력하세요."}
    backend = chat_backend()["kind"]
    with _chat_lock:   # 동시에 두 요청이 원고를 고치지 않도록
        if backend == "claude-code":
            return chat_claude_code(message)
        if backend == "api":
            return chat_api(message)
    return {"ok": False, "reply": chat_backend()["label"]}


# ---------------------------------------------------------------------------
# 웹 서버
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # 터미널을 조용하게
        pass

    def _send(self, code, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, (HERE / "gui.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            self._json(state())
        elif path.startswith("/output/"):
            f = (OUTPUT_DIR / Path(path).name)
            if f.suffix in (".pdf", ".docx") and f.exists():
                ctype = "application/pdf" if f.suffix == ".pdf" else \
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                disp = "inline" if f.suffix == ".pdf" else f'attachment; filename="{f.name}"'
                self._send(200, f.read_bytes(), ctype, {"Content-Disposition": disp})
            else:
                self._send(404, "아직 만들어지지 않았습니다.".encode(), "text/plain; charset=utf-8")
        elif path.startswith("/figures/"):
            f = ROOT / "figures" / Path(path).name
            if f.exists():
                self._send(200, f.read_bytes(), "application/octet-stream")
            else:
                self._send(404, b"", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "message": "잘못된 요청"}, 400)
        routes = {"/api/setup": do_setup, "/api/add": do_add, "/api/chat": do_chat,
                  "/api/build": lambda _d: do_build()}
        fn = routes.get(self.path)
        if not fn:
            return self._json({"ok": False}, 404)
        try:
            self._json(fn(data))
        except Exception as e:  # 화면에 오류를 보여 주기 위해
            self._json({"ok": False, "message": f"오류: {e}", "reply": f"오류: {e}"}, 500)


def main():
    ap = argparse.ArgumentParser(description="학위논문 작업실 (브라우저 입력 화면)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = ap.parse_args()
    server = None
    for port in range(args.port, args.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("사용할 수 있는 포트가 없습니다.")
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"\n📘 학위논문 작업실이 열렸습니다 → {url}")
    print(f"   Claude: {chat_backend()['label']}")
    print("   끝내려면 이 창에서 Ctrl+C\n")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n작업실을 닫았습니다.")


if __name__ == "__main__":
    main()
