"""논문 만들기 (Word + PDF).

실행:  python scripts/build.py          # 검사 → Word → PDF
       python scripts/build.py --no-pdf # Word 만
       python scripts/build.py --force  # 검사 오류가 있어도 강제로 만들기

처리 순서
  1) check.py 로 원고 검사 (오류 있으면 멈춤)
  2) thesis.yaml 의 순서대로 표지 → 제출지/인준지 → 국문초록 → 목차 → 본문 → 참고문헌 → 영문초록 을 이어 붙임
  3) 장·절 번호(제1장, 1.1, 1.1.1), 그림·표 번호(그림 1-1, 표 2-3)를 자동으로 매기고
     본문의 @fig:이름 / @tbl:이름 을 실제 번호로 바꿈
  4) pandoc 으로 Word 파일 생성 (서식은 templates/reference.docx)
  5) LibreOffice 로 목차 쪽번호를 채우고 PDF 로 저장
결과물: output/<이름>.docx, output/<이름>.pdf, output/<이름>.md(합쳐진 원고)
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import run_checks  # noqa: E402
from make_reference_docx import build_reference_docx  # noqa: E402
from thesis_lib import (  # noqa: E402
    FENCE_RE, FIG_ID_RE, FIG_RE, HEADING_RE, OUTPUT_DIR, ROOT, TBL_CAP_RE,
    TODO_RE, XREF_RE, Config, load_config, strip_comments,
)

PAGE_BREAK = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```'

# 구역(쪽번호 체계) 경계 표시. pandoc 이 Word 를 만든 뒤 split_sections() 가 진짜 '구역 나누기'로 바꾼다.
#   cover : 표지·제출지·인준지 → 쪽번호 없음
#   front : 국문초록·목차      → i, ii, iii (로마 숫자)
#   (나머지) 본문~끝            → 1, 2, 3   (1부터 다시)
SECTION_MARK = "%%SECTION_END:{}%%"


def section_end(name: str) -> str:
    return f'```{{=openxml}}\n<w:p><w:r><w:t>{SECTION_MARK.format(name)}</w:t></w:r></w:p>\n```'


# ---------------------------------------------------------------------------
# 앞부분: 표지, 제출지, 인준지, 목차
# ---------------------------------------------------------------------------
def styled(style: str, text: str) -> str:
    return f'::: {{custom-style="{style}"}}\n{text}\n:::'


def blank(n: int = 1) -> str:
    return "```{=openxml}\n" + "<w:p/>" * n + "\n```"


def cover_page(cfg: Config) -> str:
    i = cfg.info
    parts = [styled("Cover Degree", f"{i.get('degree', '')}학위논문"), blank(5),
             styled("Cover Title", i.get("title_ko", ""))]
    if i.get("subtitle_ko"):
        parts.append(styled("Cover Subtitle", f"― {i['subtitle_ko']} ―"))
    parts += [styled("Cover English", i.get("title_en", "")), blank(10),
              styled("Cover Info", i.get("university", "")),
              styled("Cover Info", f"{i.get('department', '')} {i.get('major', '')}".strip()),
              blank(1), styled("Cover Info", i.get("author", "")), blank(1),
              styled("Cover Info", i.get("date", ""))]
    return "\n\n".join(parts)


def submission_page(cfg: Config) -> str:
    """제출지: '이 논문을 ○○ 석사학위 논문으로 제출함'."""
    i = cfg.info
    major = i.get("major", "") or i.get("department", "")
    return "\n\n".join([
        PAGE_BREAK,
        styled("Cover Title", i.get("title_ko", "")),
        styled("Cover English", i.get("title_en", "")), blank(4),
        styled("Cover Info", f"지도교수  {i.get('advisor', '')}"), blank(2),
        styled("Center Text", f"이 논문을 {major.replace('전공', '')} {i.get('degree', '')}학위 논문으로 제출함"),
        styled("Center Text", i.get("date", "")), blank(4),
        styled("Cover Info", i.get("university", "")),
        styled("Cover Info", f"{i.get('department', '')} {i.get('major', '')}".strip()),
        styled("Cover Info", i.get("author", "")),
    ])


def approval_page(cfg: Config) -> str:
    """인준지: 심사위원 서명란. thesis.yaml 에 committee 가 있을 때만 만든다."""
    i = cfg.info
    committee = i.get("committee") or []
    if not committee:
        return ""
    lines = [PAGE_BREAK,
             styled("Center Text", f"{i.get('author', '')}의 {i.get('degree', '')}학위 논문을 인준함"),
             styled("Center Text", i.get("date", "")), blank(4)]
    for member in committee:
        lines.append(styled("Signature Line", f"{member}  ________________ (인)"))
    lines += [blank(4), styled("Cover Info", i.get("university", ""))]
    return "\n\n".join(lines)


def toc_field(title: str, instr: str, placeholder: str) -> str:
    """Word 목차 필드. LibreOffice/Word 가 열 때 쪽번호를 채운다."""
    return (
        "```{=openxml}\n"
        f'<w:p><w:pPr><w:pStyle w:val="FrontHeading"/></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>'
        '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"<w:r><w:t>{placeholder}</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>\n'
        "```"
    )


def toc_pages(cfg: Config, n_fig: int, n_tbl: int) -> str:
    f = cfg.fmt
    out = []
    if f.get("toc", True):
        out.append(toc_field("목  차", r'TOC \o "1-3" \h \z \u', "(목차: Word에서 F9 로 갱신)"))
    if f.get("list_of_tables", True) and n_tbl:
        out.append(toc_field("표 목차", r'TOC \h \z \t "Table Caption,1"', "(표 목차)"))
    if f.get("list_of_figures", True) and n_fig:
        out.append(toc_field("그림 목차", r'TOC \h \z \t "Image Caption,1"', "(그림 목차)"))
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# 본문 번호 매기기
# ---------------------------------------------------------------------------
class Numberer:
    def __init__(self, cfg: Config):
        f = cfg.fmt
        self.fig_label = f.get("figure_label", "그림 {chapter}-{n}")
        self.tbl_label = f.get("table_label", "표 {chapter}-{n}")
        self.ch_label = f.get("chapter_label", "제{n}장")
        self.chapter = 0
        self.labels: dict[tuple[str, str], str] = {}   # (fig|tbl, id) -> "그림 1-1"
        self.n_fig = self.n_tbl = 0

    # 1단계: 번호 매기기 (제목, 그림, 표 캡션)
    def number_part(self, text: str, numbered: bool) -> str:
        out, in_fence = [], False
        h2 = h3 = fig = tbl = 0
        if numbered:
            self.chapter += 1
        ch = self.chapter if numbered else 0
        for line in text.splitlines():
            if FENCE_RE.match(line.strip()):
                in_fence = not in_fence
                out.append(line)
                continue
            if in_fence:
                out.append(line)
                continue

            hm = HEADING_RE.match(line)
            if hm:
                level, title = len(hm.group("hashes")), hm.group("text")
                skip = re.search(r"\{[^}]*(\.unnumbered|-)[^}]*\}\s*$", title)
                if numbered and not skip:
                    if level == 1:
                        title = f"{self.ch_label.format(n=ch)} {title}"
                    elif level == 2:
                        h2, h3 = h2 + 1, 0
                        title = f"{ch}.{h2} {title}"
                    elif level == 3:
                        h3 += 1
                        title = f"{ch}.{h2}.{h3} {title}"
                out.append(f"{hm.group('hashes')} {title}")
                continue

            def fig_sub(m):
                nonlocal fig
                fig += 1
                self.n_fig += 1
                label = self.fig_label.format(chapter=ch or "", n=fig).replace(" -", " ")
                idm = FIG_ID_RE.search(m.group("attr") or "")
                if idm:
                    self.labels[("fig", idm.group("id"))] = label
                return f"![{label}. {m.group('cap')}]({m.group('path')}){m.group('attr') or ''}"

            if FIG_RE.search(line):
                line = FIG_RE.sub(fig_sub, line)

            tm = TBL_CAP_RE.match(line.strip())
            if tm:
                tbl += 1
                self.n_tbl += 1
                label = self.tbl_label.format(chapter=ch or "", n=tbl).replace(" -", " ")
                self.labels[("tbl", tm.group("id"))] = label
                line = f"Table: {label}. {tm.group('cap')}"
            out.append(line)
        return "\n".join(out)

    # 2단계: @fig:이름 → 그림 1-1
    def resolve_refs(self, text: str) -> str:
        def sub(m):
            return self.labels.get((m.group("kind"), m.group("id")), f"??{m.group('id')}??")
        return XREF_RE.sub(sub, text)


# ---------------------------------------------------------------------------
# 조립
# ---------------------------------------------------------------------------
def assemble(cfg: Config) -> tuple[str, Numberer]:
    num = Numberer(cfg)
    blocks: dict[str, list[str]] = {"front": [], "chapter": [], "back": []}
    for part in cfg.parts:
        text = strip_comments(part.path.read_text(encoding="utf-8"))
        text = TODO_RE.sub(lambda m: f"**{m.group(0)}**", text)   # 미완성 부분은 굵게 표시
        blocks[part.section].append(num.number_part(text, part.numbered))

    references = "# 참고문헌\n\n::: {#refs}\n:::"
    doc = "\n\n".join(filter(None, [
        cover_page(cfg), submission_page(cfg), approval_page(cfg),
        section_end("cover"),
        *blocks["front"],
        toc_pages(cfg, num.n_fig, num.n_tbl),
        section_end("front"),
        *blocks["chapter"],
        references,
        *blocks["back"],
    ]))
    return num.resolve_refs(doc), num


def split_sections(docx_path: Path):
    """표시(%%SECTION_END:…%%) 자리를 Word '구역 나누기'로 바꾸고 구역마다 쪽번호 형식을 정한다."""
    import copy

    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document(str(docx_path))
    body = doc.element.body
    last_sect = body.find(qn("w:sectPr"))           # 문서 끝(본문) 구역 설정

    def page_numbers(sect, fmt: str | None):
        for old in sect.findall(qn("w:pgNumType")):
            sect.remove(old)
        if fmt:
            el = OxmlElement("w:pgNumType")
            el.set(qn("w:fmt"), fmt)
            el.set(qn("w:start"), "1")
            # w:pgNumType 은 w:cols / w:docGrid 등보다 앞에 와야 한다
            anchor = next((c for c in sect if c.tag in (qn("w:cols"), qn("w:formProt"), qn("w:vAlign"),
                           qn("w:noEndnote"), qn("w:titlePg"), qn("w:textDirection"), qn("w:bidi"),
                           qn("w:rtlGutter"), qn("w:docGrid"))), None)
            if anchor is not None:
                anchor.addprevious(el)
            else:
                sect.append(el)

    found = set()
    for p in list(doc.paragraphs):
        text = p.text.strip()
        for name in ("cover", "front"):
            if text == SECTION_MARK.format(name):
                sect = copy.deepcopy(last_sect)
                for r in p._p.findall(qn("w:r")):
                    p._p.remove(r)
                if name == "cover":
                    # 바닥글(쪽번호) 없음
                    for ref in sect.findall(qn("w:footerReference")):
                        sect.remove(ref)
                    page_numbers(sect, None)
                else:
                    page_numbers(sect, "lowerRoman")
                p._p.get_or_add_pPr().append(sect)
                found.add(name)
    page_numbers(last_sect, "decimal")
    doc.save(str(docx_path))
    return found


def run_pandoc(cfg: Config, md_path: Path, docx_path: Path, ref_docx: Path):
    f = cfg.fmt
    cmd = ["pandoc", str(md_path), "-f", "markdown", "-t", "docx",
           "-o", str(docx_path), f"--reference-doc={ref_docx}",
           f"--resource-path={ROOT}", "--metadata", "lang=ko-KR",
           "--metadata", "link-citations=true"]
    bib = ROOT / f.get("bibliography", "references.bib")
    if bib.exists():
        cmd += ["--citeproc", f"--bibliography={bib}"]
        csl = ROOT / f.get("csl", "templates/apa.csl")
        if csl.exists():
            cmd.append(f"--csl={csl}")
    subprocess.run(cmd, check=True, cwd=ROOT)


def finalize_with_libreoffice(docx_path: Path, make_pdf: bool) -> bool:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("⚠️  LibreOffice 가 없어 목차 쪽번호 채우기·PDF 변환을 건너뜁니다.")
        return False
    cmd = [sys.executable, str(Path(__file__).with_name("finalize_lo.py")), str(docx_path)]
    if make_pdf:
        cmd.append("--pdf")
    r = subprocess.run(cmd)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description="논문 빌드")
    ap.add_argument("--no-pdf", action="store_true", help="PDF 는 만들지 않음")
    ap.add_argument("--force", action="store_true", help="검사 오류가 있어도 빌드")
    args = ap.parse_args()

    cfg = load_config()
    errors, _ = run_checks(verbose=True)
    if errors and not args.force:
        print("\n빌드를 멈췄습니다. 위 ❌ 오류를 고치거나 --force 로 강제 실행하세요.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    name = cfg.fmt.get("output_name", "thesis")
    md_path = OUTPUT_DIR / f"{name}.md"
    docx_path = OUTPUT_DIR / f"{name}.docx"

    print("\n🔧 1/3 서식 틀 만드는 중…")
    ref_docx = build_reference_docx()
    print("🔧 2/3 원고 합치고 번호 매기는 중…")
    text, num = assemble(cfg)
    md_path.write_text(text, encoding="utf-8")
    run_pandoc(cfg, md_path, docx_path, ref_docx)
    split_sections(docx_path)
    print("🔧 3/3 목차 쪽번호 채우고 PDF 만드는 중…")
    make_pdf = cfg.fmt.get("pdf", True) and not args.no_pdf
    finalize_with_libreoffice(docx_path, make_pdf)

    print(f"\n✅ 완료  (그림 {num.n_fig}개, 표 {num.n_tbl}개)")
    print(f"   Word : {docx_path.relative_to(ROOT)}")
    if make_pdf and docx_path.with_suffix(".pdf").exists():
        print(f"   PDF  : {docx_path.with_suffix('.pdf').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
