"""논문 원고 검사기.

실행:  python scripts/check.py

- 오류(❌): 이대로 빌드하면 논문이 깨지는 문제 → 빌드가 멈춤
    · thesis.yaml 에 적힌 장 파일이 없음
    · 그림 파일이 없음
    · 없는 그림/표 번호를 참조함 (@fig:없는것)
    · references.bib 에 없는 문헌을 인용함
    · 그림/표 id 중복
- 경고(⚠️): 빌드는 되지만 확인이 필요한 것
    · 아직 [TODO] 가 남아 있음
    · sources/ 에 넣었는데 SOURCES.md 에 기록되지 않은 자료
    · thesis.yaml 에 빠져 있는 장 파일
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thesis_lib import (  # noqa: E402
    CHAPTER_DIR, CITE_RE, FIG_ID_RE, FIG_RE, ROOT, SOURCE_DIR, TBL_CAP_RE,
    TODO_RE, XREF_RE, iter_body_lines, load_bib_keys, load_config, strip_comments,
)


def run_checks(verbose: bool = True) -> tuple[list[str], list[str]]:
    cfg = load_config()
    errors: list[str] = []
    warnings: list[str] = []
    bib_keys = load_bib_keys(ROOT / cfg.fmt.get("bibliography", "references.bib"))

    fig_ids: Counter = Counter()
    tbl_ids: Counter = Counter()
    xrefs: list[tuple[str, str, str]] = []      # (위치, 종류, id)
    stats: list[tuple[str, int, int]] = []      # (파일, 글자수, TODO 수)

    for part in cfg.parts:
        if not part.path.exists():
            errors.append(f"thesis.yaml 에 적힌 파일이 없습니다: chapters/{part.file}")
            continue
        text = strip_comments(part.path.read_text(encoding="utf-8"))
        todos = 0
        chars = 0
        for ln, line in iter_body_lines(text):
            where = f"chapters/{part.file}:{ln}"
            todos += len(TODO_RE.findall(line))
            chars += len(TODO_RE.sub("", line).replace(" ", "").lstrip("#"))

            for m in FIG_RE.finditer(line):
                img = ROOT / m.group("path")
                if not m.group("path").startswith(("http://", "https://")) and not img.exists():
                    errors.append(f"{where}  그림 파일 없음: {m.group('path')}")
                idm = FIG_ID_RE.search(m.group("attr") or "")
                if idm:
                    fig_ids[idm.group("id")] += 1
                elif m.group("cap").strip():
                    warnings.append(f"{where}  그림에 id가 없습니다 → {{#fig:이름}} 을 붙이면 번호 참조가 가능합니다")
                if not m.group("cap").strip():
                    warnings.append(f"{where}  그림 캡션(설명)이 비어 있습니다")

            tm = TBL_CAP_RE.match(line.strip())
            if tm:
                tbl_ids[tm.group("id")] += 1

            for m in XREF_RE.finditer(line):
                xrefs.append((where, m.group("kind"), m.group("id")))

            for m in CITE_RE.finditer(line):
                key = m.group("key")
                if key.startswith(("fig:", "tbl:")):
                    continue
                if key not in bib_keys:
                    errors.append(f"{where}  references.bib 에 없는 인용: @{key}")
        stats.append((part.file, chars, todos))
        if todos:
            warnings.append(f"chapters/{part.file}  미완성 [TODO] {todos}곳")

    for kind, ids in (("그림", fig_ids), ("표", tbl_ids)):
        for i, n in ids.items():
            if n > 1:
                errors.append(f"{kind} id 중복: {i} ({n}번 사용)")
    for where, kind, i in xrefs:
        if i not in (fig_ids if kind == "fig" else tbl_ids):
            errors.append(f"{where}  없는 {'그림' if kind == 'fig' else '표'}를 참조: @{kind}:{i}")

    # thesis.yaml 에 등록 안 된 장 파일
    listed = {p.file for p in cfg.parts}
    for f in sorted(CHAPTER_DIR.glob("*.md")):
        if f.name not in listed:
            warnings.append(f"chapters/{f.name} 이(가) thesis.yaml 에 없어 논문에 포함되지 않습니다")

    # SOURCES.md 에 기록되지 않은 자료
    manifest = (SOURCE_DIR / "SOURCES.md")
    manifest_text = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
    for f in sorted(SOURCE_DIR.rglob("*")):
        if f.is_file() and f.name not in {".gitkeep", "SOURCES.md", "README.md"}:
            rel = f.relative_to(SOURCE_DIR).as_posix()
            if rel not in manifest_text and f.name not in manifest_text:
                warnings.append(f"sources/{rel} 이(가) SOURCES.md 에 기록되지 않았습니다 (아직 반영 안 된 자료?)")

    if verbose:
        print("\n📄 원고 현황")
        print(f"  {'파일':<24}{'글자수':>8}{'TODO':>6}")
        for name, chars, todos in stats:
            print(f"  {name:<24}{chars:>8,}{todos:>6}")
        print(f"  {'합계':<24}{sum(s[1] for s in stats):>8,}{sum(s[2] for s in stats):>6}")
        print(f"  그림 {len(fig_ids)}개 · 표 {len(tbl_ids)}개 · 참고문헌 {len(bib_keys)}건\n")
        for w in warnings:
            print(f"⚠️  {w}")
        for e in errors:
            print(f"❌ {e}")
        if not errors:
            print("✅ 빌드를 막는 오류가 없습니다." if not warnings else "\n✅ 오류 없음 (경고만 있음)")
    return errors, warnings


if __name__ == "__main__":
    errs, _ = run_checks()
    sys.exit(1 if errs else 0)
