"""학위논문 도우미 — 주제 입력, 자료(텍스트·이미지) 추가, 빌드를 한 곳에서.

사용법 (그냥 `python thesis.py` 만 쳐도 메뉴가 나옵니다)

  python thesis.py gui                      # ★ 입력 화면 열기 (브라우저) — 정보·자료·현황 + 하단 Claude 입력란
  python thesis.py init                     # 논문 주제·기본 정보 입력 (질문에 답하기)
  python thesis.py add                      # 자료 추가 (질문에 답하기)
  python thesis.py add 캡처.png --to 3 --section "연구 설계" --caption "연구 모형"
  python thesis.py add 메모.txt --to 1 --section "연구 배경"
  python thesis.py add --text "본 연구는 …" --to 1 --section "연구 목적"
  python thesis.py add 자료.pdf             # 장을 안 정하면 '대기'로 보관 → Claude 가 정리
  python thesis.py status                   # 장별 진행 현황
  python thesis.py build                    # Word + PDF 만들기

자료 추가 규칙
  · 모든 자료는 원본이 sources/ 에 날짜_이름 으로 보관되고 sources/SOURCES.md 에 기록됩니다.
  · --to(장 번호) 를 주면 바로 원고에 들어갑니다.
      텍스트 → 해당 절의 [TODO] 자리를 채우거나 절 끝에 문단으로 추가
      이미지 → figures/ 로 복사되고 "그림 X-Y" 로 실립니다 (캡션 필요)
  · --to 를 안 주면 '대기' 상태로 보관만 합니다. Claude 에게 "대기 자료 반영해줘" 라고 하면
    CLAUDE.md 규칙대로 알맞은 장에 학술 문체로 써 넣습니다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from thesis_lib import CHAPTER_DIR, HEADING_RE, SOURCE_DIR, load_config  # noqa: E402

YAML_PATH = ROOT / "thesis.yaml"
MANIFEST = SOURCE_DIR / "SOURCES.md"
FIG_DIR = ROOT / "figures"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
TEXT_EXT = {".txt", ".md"}
DOCX_EXT = {".docx"}
PAPER_EXT = {".pdf", ".hwp", ".hwpx", ".ppt", ".pptx"}
DATA_EXT = {".csv", ".xlsx", ".xls", ".sav", ".json"}


# ---------------------------------------------------------------------------
# 입력 도우미
# ---------------------------------------------------------------------------
def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{hint}: ").strip()
    except EOFError:
        val = ""
    return val or default


def ask_multiline(prompt: str) -> str:
    print(f"{prompt}  (여러 줄 입력 가능, 빈 줄에서 Enter 두 번이면 끝)")
    lines, empty = [], 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            empty += 1
            if empty >= 2 or not lines:
                if lines:
                    break
                continue
        else:
            empty = 0
        lines.append(line)
    return "\n".join(lines).strip()


def choose(prompt: str, options: list[str]) -> int:
    print(prompt)
    for i, o in enumerate(options, 1):
        print(f"  {i}) {o}")
    while True:
        v = ask("번호 선택")
        if v.isdigit() and 1 <= int(v) <= len(options):
            return int(v) - 1
        print("  목록의 번호를 입력하세요.")


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return s[:40]


# ---------------------------------------------------------------------------
# init: 주제·기본 정보
# ---------------------------------------------------------------------------
INFO_FIELDS = [
    ("title_ko", "논문 제목 (한글)"),
    ("subtitle_ko", "부제 (없으면 Enter)"),
    ("title_en", "논문 제목 (영문)"),
    ("degree", "학위 (석사/박사)"),
    ("university", "대학원 이름 (예: ○○대학교 대학원)"),
    ("department", "학과"),
    ("major", "전공 (없으면 Enter)"),
    ("author", "이름"),
    ("author_en", "영문 이름"),
    ("advisor", "지도교수 (예: 김○○ 교수)"),
    ("date", "제출 연월 (예: 2027년 2월)"),
]


def yaml_set_info(text: str, key: str, value: str) -> str:
    value = value.replace('"', "'")
    pat = re.compile(rf'^(  {key}:\s*)"[^"\n]*"', re.M)
    if pat.search(text):
        return pat.sub(lambda m: f'{m.group(1)}"{value}"', text, count=1)
    return text.replace("info:\n", f'info:\n  {key}: "{value}"\n', 1)


def yaml_set_topic(text: str, topic: dict) -> str:
    """thesis.yaml 맨 아래 'topic:' 블록을 새로 쓴다 (주석은 보존)."""
    def q(s):
        return '"' + s.replace('"', "'") + '"'
    lines = ["topic:",
             "  # 연구 주제 정보 — Claude 가 원고를 쓸 때 방향을 잡는 기준",
             f"  summary: {q(topic.get('summary', ''))}",
             f"  field: {q(topic.get('field', ''))}",
             f"  method: {q(topic.get('method', ''))}",
             "  research_questions:"]
    lines += [f"    - {q(r)}" for r in topic.get("research_questions", [])] or ["    []"]
    if not topic.get("research_questions"):
        lines[-2] = "  research_questions: []"
        lines.pop()
    kws = topic.get("keywords", [])
    lines.append("  keywords: [" + ", ".join(q(k) for k in kws) + "]")
    block = "\n".join(lines) + "\n"
    text = re.sub(r"\n# =+\n#  연구 주제.*", "", text, flags=re.S)
    text = re.sub(r"\ntopic:\n(?:[ #].*\n?)*", "\n", text)
    header = "\n# =============================================================\n#  연구 주제 (python thesis.py init 으로 입력)\n# =============================================================\n"
    return text.rstrip() + "\n" + header + block


PLACEHOLDERS = ("○○", "논문 제목을 입력하세요", "Thesis Title in English", "홍길동", "Gildong Hong")


def clean(v) -> str:
    """예시값(○○, 홍길동 등)은 빈칸으로 본다."""
    v = str(v or "")
    return "" if any(p in v for p in PLACEHOLDERS) else v


def yaml_set_committee(text: str, members: list[str]) -> str:
    members = [m.replace('"', "'") for m in members if m.strip()]
    pat = re.compile(r"^  #? ?committee:.*$", re.M)
    if members:
        line = "  committee: [" + ", ".join(f'"{m}"' for m in members) + "]"
    else:
        line = '  # committee: ["위원장 ○○○", "위원 ○○○", "위원 ○○○", "위원 ○○○", "위원 ○○○"]   # 박사: 보통 5인'
    if pat.search(text):
        return pat.sub(lambda _m: line, text, count=1)
    return re.sub(r'^(  date:.*)$', lambda m: m.group(1) + "\n" + line, text, count=1, flags=re.M)


def write_topic(text: str, topic: dict):
    """연구 주제를 thesis.yaml 에 쓰고, 주제어→국문초록, 연구문제→1장에 반영."""
    text = yaml_set_topic(text, topic)
    YAML_PATH.write_text(text, encoding="utf-8")
    if topic.get("keywords"):
        ab = CHAPTER_DIR / "abstract_ko.md"
        if ab.exists():
            s = ab.read_text(encoding="utf-8")
            s = re.sub(r"\*\*주제어:\*\*.*", "**주제어:** " + ", ".join(topic["keywords"]), s)
            ab.write_text(s, encoding="utf-8")
    if topic.get("research_questions"):
        intro = CHAPTER_DIR / "01_introduction.md"
        if intro.exists() and "[TODO: 연구 문제]" in intro.read_text(encoding="utf-8"):
            body = "\n".join(f"연구 문제 {i}. {r}  " for i, r in enumerate(topic["research_questions"], 1))
            insert_text(intro, "연구 문제", body)


def save_setup(info: dict, topic: dict, committee: list[str] | None = None):
    """입력 화면(GUI)에서 받은 값을 한 번에 저장."""
    text = YAML_PATH.read_text(encoding="utf-8")
    for key, _label in INFO_FIELDS + [("university_en", "")]:
        if key in info:
            text = yaml_set_info(text, key, str(info[key]).strip())
    if info.get("degree"):
        text = yaml_set_info(text, "degree_en", "Doctoral Dissertation" if "박" in info["degree"] else "Master's Thesis")
    if committee is not None:
        text = yaml_set_committee(text, committee)
    write_topic(text, topic)


def cmd_init(args):
    cfg = load_config()
    info = cfg.info
    topic = cfg.raw.get("topic") or {}
    text = YAML_PATH.read_text(encoding="utf-8")
    print("\n📘 논문 기본 정보 입력  (Enter = [ ] 안의 기존 값 유지)\n")
    for key, label in INFO_FIELDS:
        cur = str(info.get(key, "") or "")
        if "○○" in cur or cur in ("논문 제목을 입력하세요", "Thesis Title in English", "홍길동", "Gildong Hong"):
            cur_disp = ""
        else:
            cur_disp = cur
        val = ask(label, cur_disp)
        if key == "degree" and val:
            val = val.replace("학위", "")
            text = yaml_set_info(text, "degree_en", "Doctoral Dissertation" if "박" in val else "Master's Thesis")
        if val or key in ("subtitle_ko", "major"):
            text = yaml_set_info(text, key, val)
    uni = re.search(r'^  university:\s*"([^"]*)"', text, re.M)
    if uni and uni.group(1) and "○○" not in uni.group(1):
        name = uni.group(1).replace("대학교 대학원", "").replace("대학원", "").strip()
        en = ask("대학원 영문명", str(info.get("university_en", "")) if "○○" not in str(info.get("university_en", "")) else f"Graduate School, {name} University")
        text = yaml_set_info(text, "university_en", en)

    print("\n🔎 연구 주제 입력\n")
    new_topic = {
        "summary": ask("연구 주제를 한두 문장으로 (무엇을, 왜 연구하나요?)", topic.get("summary", "")),
        "field": ask("연구 분야 (예: 경영학-조직행동, 교육공학)", topic.get("field", "")),
        "method": ask("연구 방법 (예: 설문조사·회귀분석 / 인터뷰·질적분석 / 실험)", topic.get("method", "")),
    }
    rqs = topic.get("research_questions") or []
    print("연구 문제를 하나씩 입력하세요. (빈 줄 Enter = 끝" + (", 바로 Enter 하면 기존 것 유지)" if rqs else ")"))
    new_rqs = []
    while True:
        r = ask(f"  연구 문제 {len(new_rqs) + 1}")
        if not r:
            break
        new_rqs.append(r)
    new_topic["research_questions"] = new_rqs or rqs
    kw = ask("주제어 (쉼표로 구분)", ", ".join(topic.get("keywords", [])))
    new_topic["keywords"] = [k.strip() for k in kw.split(",") if k.strip()]
    write_topic(text, new_topic)
    print("\n✅ thesis.yaml 에 저장했습니다.")
    print("   다음 단계: python thesis.py add  로 자료를 넣거나, Claude 에게 자료를 주세요.")


# ---------------------------------------------------------------------------
# 원고에 끼워 넣기
# ---------------------------------------------------------------------------
def chapter_files() -> list:
    return [p for p in load_config().parts]


def resolve_chapter(token: str):
    """'3', '03', '03_method.md', '연구 방법', 'abstract_ko' 등을 장 파일로 바꾼다."""
    parts = chapter_files()
    token = str(token).strip()
    chapters = [p for p in parts if p.section == "chapter"]
    if token.isdigit() and 1 <= int(token) <= len(chapters):
        return chapters[int(token) - 1]
    for p in parts:
        if token in (p.file, p.file.removesuffix(".md")) or p.file.startswith(token):
            return p
        first = p.path.read_text(encoding="utf-8").splitlines()[0] if p.path.exists() else ""
        if token and token in first:
            return p
    raise SystemExit(f"❌ '{token}' 에 해당하는 장을 찾지 못했습니다. (python thesis.py status 로 목록 확인)")


def headings(path: Path) -> list[tuple[int, int, str]]:
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        m = HEADING_RE.match(line)
        if m:
            out.append((i, len(m.group("hashes")), m.group("text").strip()))
    return out


def insert_text(path: Path, section: str | None, block: str) -> str:
    """section 제목 아래에 block 을 넣는다. 그 절의 [TODO] 줄이 있으면 첫 번째를 대체한다.
    section 이 없으면 장 끝에 넣는다. 넣은 위치 설명을 돌려준다."""
    lines = path.read_text(encoding="utf-8").splitlines()
    hs = headings(path)
    start, end, where = None, len(lines), "장 끝"
    if section:
        for idx, (ln, level, title) in enumerate(hs):
            if level >= 2 and section.replace(" ", "") in title.replace(" ", ""):
                start = ln
                where = title
                for ln2, lv2, _ in hs[idx + 1:]:
                    if lv2 <= level:
                        end = ln2
                        break
                break
        if start is None:
            # 없는 절이면 새로 만든다
            lines += ["", f"## {section}"]
            start, end, where = len(lines) - 1, len(lines), f"{section} (새 절)"
    body = block.strip().splitlines()
    if start is not None:
        for j in range(start + 1, end):
            if re.fullmatch(r"\s*\[TODO[^\]]*\]\s*", lines[j]):
                lines[j:j + 1] = body
                break
        else:
            k = end
            while k > start + 1 and not lines[k - 1].strip():
                k -= 1
            lines[k:k] = [""] + body
    else:
        lines += [""] + body
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return where


# ---------------------------------------------------------------------------
# add: 자료 추가
# ---------------------------------------------------------------------------
def store_source(src: Path | None, text: str | None, name_hint: str) -> Path:
    today = dt.date.today().strftime("%Y%m%d")
    if src is not None:
        ext = src.suffix.lower()
        sub = ("images" if ext in IMAGE_EXT else "notes" if ext in TEXT_EXT | DOCX_EXT
               else "papers" if ext in PAPER_EXT else "data" if ext in DATA_EXT else "notes")
        stem = re.sub(r"[\\/:*?\"<>|\s]+", "_", src.stem)
        base = stem if stem.startswith(today) else f"{today}_{stem}"
        dest = SOURCE_DIR / sub / f"{base}{ext}"
        n = 2
        while dest.exists() and dest.resolve() != src.resolve():
            dest = SOURCE_DIR / sub / f"{base}_{n}{ext}"
            n += 1
        if dest.resolve() != src.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return dest
    label = re.sub(r"[\\/:*?\"<>|\s]+", "_", name_hint)[:30] or "메모"
    dest = SOURCE_DIR / "notes" / f"{today}_{label}.md"
    n = 2
    while dest.exists():
        dest = SOURCE_DIR / "notes" / f"{today}_{label}_{n}.md"
        n += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text or "", encoding="utf-8")
    return dest


def log_source(dest: Path, kind: str, summary: str, where: str, status: str):
    rel = dest.relative_to(SOURCE_DIR).as_posix()
    summary = summary.replace("|", "/").replace("\n", " ")[:60]
    row = f"| {rel} | {kind} | {summary} | {where} | {status} |\n"
    text = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
    if not text.endswith("\n"):
        text += "\n"
    MANIFEST.write_text(text + row, encoding="utf-8")


def read_text_file(path: Path) -> str:
    if path.suffix.lower() in DOCX_EXT:
        from docx import Document
        return "\n\n".join(p.text for p in Document(str(path)).paragraphs if p.text.strip())
    return path.read_text(encoding="utf-8", errors="replace")


def next_fig_id(base: str) -> str:
    used = set()
    for f in CHAPTER_DIR.glob("*.md"):
        used |= set(re.findall(r"#fig:([\w\-]+)", f.read_text(encoding="utf-8")))
    cand = base or "fig"
    n = 2
    while cand in used:
        cand = f"{base}{n}"
        n += 1
    return cand


def interactive_add(args):
    kind = choose("\n무엇을 추가할까요?", ["텍스트 직접 입력 (붙여넣기)", "파일 (이미지·텍스트·워드·PDF 등)"])
    if kind == 0:
        args.text = ask_multiline("내용을 입력하세요")
        if not args.text:
            raise SystemExit("입력된 내용이 없습니다.")
    else:
        p = ask("파일 경로 (파일을 터미널로 끌어다 놓아도 됩니다)").strip("'\" ")
        args.file = p
    parts = chapter_files()
    opts = [f"{p.file}  —  {first_heading(p)}" for p in parts] + ["아직 모르겠음 (대기로 보관 → Claude 가 정리)"]
    idx = choose("\n어느 장에 넣을까요?", opts)
    if idx < len(parts):
        args.to = parts[idx].file
        hs = [t for _, lv, t in headings(parts[idx].path) if lv >= 2]
        if hs:
            sidx = choose("어느 절에 넣을까요?", hs + ["장 끝에 추가"])
            args.section = hs[sidx] if sidx < len(hs) else None
        if args.file and Path(args.file).suffix.lower() in IMAGE_EXT:
            args.caption = ask("그림 캡션 (예: 연구 모형)")
    args.note = ask("메모 (출처·설명 등, 없으면 Enter)")


def first_heading(part) -> str:
    if not part.path.exists():
        return "(파일 없음)"
    for line in part.path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def cmd_add(args):
    if not args.file and args.text is None:
        interactive_add(args)

    src = Path(args.file).expanduser() if args.file else None
    if src is not None and not src.exists():
        raise SystemExit(f"❌ 파일이 없습니다: {src}")
    ext = src.suffix.lower() if src else ".md"
    is_image = ext in IMAGE_EXT
    kind = ("이미지" if is_image else "텍스트" if (src is None or ext in TEXT_EXT | DOCX_EXT)
            else "논문/문서" if ext in PAPER_EXT else "데이터" if ext in DATA_EXT else "기타")

    hint = args.caption or (args.text or "").strip().splitlines()[0][:20] if (args.text or args.caption) else "메모"
    dest = store_source(src, args.text, hint)
    print(f"📥 보관: {dest.relative_to(ROOT)}")
    summary = args.note or args.caption or (args.text or (read_text_file(src) if kind == "텍스트" else src.name)).strip()

    if not args.to:
        log_source(dest, kind, summary, "-", "대기")
        print("⏳ 장을 정하지 않아 '대기'로 기록했습니다. Claude 에게 \"대기 자료 반영해줘\" 라고 하면 정리해 넣습니다.")
        return

    part = resolve_chapter(args.to)
    if is_image:
        caption = args.caption or ask("그림 캡션이 필요합니다")
        if not caption:
            raise SystemExit("❌ 그림에는 캡션이 필요합니다. --caption \"설명\" 을 붙여주세요.")
        base = slug(args.id or src.stem) or "fig"
        fig_id = next_fig_id(args.id or base)
        FIG_DIR.mkdir(exist_ok=True)
        fig_path = FIG_DIR / f"{fig_id}{ext}"
        shutil.copy2(src, fig_path)
        block = f"![{caption}](figures/{fig_path.name}){{#fig:{fig_id} width={args.width}}}"
        if args.lead:
            block = f"{args.lead.replace('@fig', f'@fig:{fig_id}') if '@fig' in args.lead else args.lead}\n\n{block}"
        where = insert_text(part.path, args.section, block)
        print(f"🖼️  그림 추가: figures/{fig_path.name}  (본문에서 @fig:{fig_id} 로 참조)")
    elif kind == "텍스트":
        body = args.text if src is None else read_text_file(src)
        where = insert_text(part.path, args.section, body)
    else:
        raise SystemExit(f"❌ {ext} 파일은 원고에 바로 넣을 수 없습니다. --to 없이 보관한 뒤 Claude 에게 정리를 맡겨주세요.")

    loc = f"{part.file} {where}"
    log_source(dest, kind, summary, loc, "반영")
    print(f"✍️  원고 반영: chapters/{loc}")
    print("   ※ 넣은 글은 원문 그대로입니다. Claude 에게 \"방금 넣은 부분 논문체로 다듬어줘\" 라고 하면 정리합니다.")


# ---------------------------------------------------------------------------
# status / build
# ---------------------------------------------------------------------------
def cmd_status(_args):
    cfg = load_config()
    i, t = cfg.info, cfg.raw.get("topic") or {}
    print(f"\n📘 {i.get('title_ko')}  —  {i.get('author')} ({i.get('university')} {i.get('department')})")
    if t.get("summary"):
        print(f"   주제: {t['summary']}")
    for n, r in enumerate(t.get("research_questions") or [], 1):
        print(f"   연구 문제 {n}: {r}")
    waiting = MANIFEST.read_text(encoding="utf-8").count("| 대기 |") if MANIFEST.exists() else 0
    print(f"   대기 중인 자료: {waiting}건")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "check.py")])


def cmd_build(args):
    cmd = [sys.executable, str(ROOT / "scripts" / "build.py")]
    if args.no_pdf:
        cmd.append("--no-pdf")
    if args.force:
        cmd.append("--force")
    sys.exit(subprocess.run(cmd).returncode)


def cmd_gui(args):
    cmd = [sys.executable, str(ROOT / "scripts" / "gui.py")]
    if getattr(args, "no_browser", False):
        cmd.append("--no-browser")
    if getattr(args, "port", None):
        cmd += ["--port", str(args.port)]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


def menu():
    idx = choose("\n📘 학위논문 도우미 — 무엇을 할까요?",
                 ["입력 화면 열기 (브라우저)", "논문 주제·기본 정보 입력", "자료 추가 (텍스트·이미지·파일)",
                  "진행 현황 보기", "논문 파일 만들기 (Word+PDF)", "끝내기"])
    ns = argparse.Namespace(file=None, text=None, to=None, section=None, caption=None, id=None,
                            width="80%", note=None, lead=None, no_pdf=False, force=False)
    [cmd_gui, cmd_init, cmd_add, cmd_status, cmd_build, lambda a: None][idx](ns)


def main():
    ap = argparse.ArgumentParser(description="학위논문 도우미", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("gui", help="입력 화면 열기 (브라우저)")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--no-browser", action="store_true")
    sub.add_parser("init", help="논문 주제·기본 정보 입력")
    a = sub.add_parser("add", help="자료 추가 (텍스트·이미지·파일)")
    a.add_argument("file", nargs="?", help="추가할 파일 (이미지·txt·md·docx·pdf …)")
    a.add_argument("--text", help="파일 대신 직접 넣을 글")
    a.add_argument("--to", help="넣을 장: 번호(1~5) 또는 파일명(abstract_ko 등). 없으면 '대기'")
    a.add_argument("--section", help="넣을 절 제목 (예: \"연구 배경\"). 없으면 장 끝")
    a.add_argument("--caption", help="그림 캡션 (이미지일 때 필수)")
    a.add_argument("--id", help="그림 참조 이름 (영문, 예: model → @fig:model)")
    a.add_argument("--width", default="80%", help="그림 너비 (기본 80%%)")
    a.add_argument("--lead", help="그림 앞에 넣을 안내 문장 (예: \"연구 모형은 @fig 와 같다.\")")
    a.add_argument("--note", help="SOURCES.md 에 남길 메모 (출처 등)")
    sub.add_parser("status", help="진행 현황")
    b = sub.add_parser("build", help="Word + PDF 만들기")
    b.add_argument("--no-pdf", action="store_true")
    b.add_argument("--force", action="store_true")
    args = ap.parse_args()
    {"gui": cmd_gui, "init": cmd_init, "add": cmd_add, "status": cmd_status, "build": cmd_build,
     None: lambda _a: menu()}[args.cmd](args)


if __name__ == "__main__":
    main()
