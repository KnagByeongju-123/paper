"""Word 서식 틀(templates/reference.docx) 만들기.

thesis.yaml 의 style 설정(용지, 여백, 글꼴, 줄간격)을 읽어
pandoc 이 논문을 만들 때 쓰는 '서식 틀' Word 파일을 만든다.
build.py 가 매번 자동으로 실행하므로 직접 실행할 일은 거의 없다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thesis_lib import TEMPLATE_DIR, load_config  # noqa: E402

# 표지·목차용으로 추가하는 사용자 스타일 (build.py 에서 이름으로 사용)
CUSTOM_STYLES = ["Cover Degree", "Cover Title", "Cover Subtitle", "Cover English",
                 "Cover Info", "Front Heading", "Center Text", "Signature Line"]


def set_font(style, name: str, size: float | None = None, bold: bool | None = None):
    style.font.name = name
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)


def para(style, *, align=None, before=0, after=0, spacing=None, indent_first=None,
         page_break=False, keep_next=False):
    pf = style.paragraph_format
    if align is not None:
        pf.alignment = align
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if spacing:
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = spacing
    if indent_first is not None:
        pf.first_line_indent = Pt(indent_first)
    pf.page_break_before = page_break
    pf.keep_with_next = keep_next


def set_outline_level(style, level: int):
    ppr = style.element.get_or_add_pPr()
    for old in ppr.findall(qn("w:outlineLvl")):
        ppr.remove(old)
    el = OxmlElement("w:outlineLvl")
    el.set(qn("w:val"), str(level))
    ppr.append(el)


def get_style(doc, name, kind=WD_STYLE_TYPE.PARAGRAPH):
    try:
        return doc.styles[name]
    except KeyError:
        st = doc.styles.add_style(name, kind)
        if kind == WD_STYLE_TYPE.PARAGRAPH:
            st.base_style = doc.styles["Normal"]
        return st


def add_page_number_footer(section):
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for kind, text in (("begin", None), (None, " PAGE "), ("separate", None), (None, "1"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
            run._r.append(el)
        elif text.strip() == "PAGE":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
            run._r.append(el)
        else:
            el = OxmlElement("w:t")
            el.text = text
            run._r.append(el)


def build_reference_docx() -> Path:
    cfg = load_config()
    st = cfg.style
    body_font = st.get("body_font", "NanumMyeongjo")
    head_font = st.get("heading_font", "NanumGothic")
    size = float(st.get("body_size_pt", 11))
    spacing = float(st.get("line_spacing", 1.6))
    margin = st.get("margin_cm", {})

    TEMPLATE_DIR.mkdir(exist_ok=True)
    base = TEMPLATE_DIR / "_pandoc_default.docx"
    with open(base, "wb") as fh:
        from thesis_lib import find_tool
        subprocess.run([find_tool("pandoc") or "pandoc", "--print-default-data-file", "reference.docx"],
                       stdout=fh, check=True)
    doc = Document(str(base))

    # --- 용지와 여백
    sec = doc.sections[0]
    if str(st.get("paper", "A4")).upper() == "A4":
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    elif str(st.get("paper")).upper() in ("B5", "4X6배판"):
        sec.page_width, sec.page_height = Cm(18.2), Cm(25.7)
    sec.top_margin = Cm(margin.get("top", 3.0))
    sec.bottom_margin = Cm(margin.get("bottom", 2.5))
    sec.left_margin = Cm(margin.get("left", 3.0))
    sec.right_margin = Cm(margin.get("right", 2.5))
    sec.footer_distance = Cm(1.2)
    sec.start_type = WD_SECTION.NEW_PAGE
    add_page_number_footer(sec)

    S = lambda n: get_style(doc, n)  # noqa: E731

    # --- 본문
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        s = S(name)
        set_font(s, body_font, size)
    for name in ("Body Text", "First Paragraph"):
        para(S(name), align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=4, spacing=spacing, indent_first=size)
    para(S("Compact"), after=2, spacing=spacing)

    # --- 장/절 제목
    heading_spec = {  # 이름: (크기, 정렬, 앞, 뒤, 새 페이지)
        "Heading 1": (16, WD_ALIGN_PARAGRAPH.CENTER, 0, 24, True),
        "Heading 2": (13, WD_ALIGN_PARAGRAPH.LEFT, 18, 8, False),
        "Heading 3": (12, WD_ALIGN_PARAGRAPH.LEFT, 12, 6, False),
        "Heading 4": (11, WD_ALIGN_PARAGRAPH.LEFT, 8, 4, False),
    }
    for name, (sz, al, b, a, pb) in heading_spec.items():
        s = S(name)
        set_font(s, head_font, sz, bold=True)
        para(s, align=al, before=b, after=a, spacing=1.2, page_break=pb, keep_next=True)
        set_outline_level(s, int(name[-1]) - 1)   # 목차에 잡히도록 '개요 수준' 지정

    # --- 그림/표 캡션, 참고문헌, 인용문, 각주
    for name in ("Image Caption", "Table Caption"):
        s = S(name)
        set_font(s, body_font, size - 1, bold=False)
        s.font.italic = False
        para(s, align=WD_ALIGN_PARAGRAPH.CENTER, before=4, after=10, spacing=1.2)
    para(S("Table Caption"), align=WD_ALIGN_PARAGRAPH.CENTER, before=10, after=4, spacing=1.2, keep_next=True)
    para(S("Captioned Figure"), align=WD_ALIGN_PARAGRAPH.CENTER, before=6, keep_next=True)
    para(S("Figure"), align=WD_ALIGN_PARAGRAPH.CENTER, before=6, keep_next=True)
    s = S("Bibliography")
    set_font(s, body_font, size - 1)
    para(s, after=6, spacing=1.3)
    s.paragraph_format.left_indent = Cm(1.0)
    s.paragraph_format.first_line_indent = Cm(-1.0)
    set_font(S("Block Text"), body_font, size - 1)
    set_font(S("Footnote Text"), body_font, 9)

    # --- 표지·목차용 사용자 스타일
    custom = {  # 이름: (글꼴, 크기, 굵게, 앞, 뒤)
        "Cover Degree": (head_font, 16, True, 0, 0),
        "Cover Title": (head_font, 20, True, 0, 6),
        "Cover Subtitle": (head_font, 14, False, 0, 6),
        "Cover English": (body_font, 13, False, 6, 0),
        "Cover Info": (head_font, 14, False, 0, 4),
        "Front Heading": (head_font, 16, True, 0, 24),
        "Center Text": (body_font, size + 1, False, 0, 6),
        "Signature Line": (body_font, size + 1, False, 18, 0),
    }
    for name, (font, sz, bold, b, a) in custom.items():
        s = S(name)
        set_font(s, font, sz, bold=bold)
        para(s, align=WD_ALIGN_PARAGRAPH.CENTER, before=b, after=a, spacing=1.3)
    S("Signature Line").paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    S("Front Heading").paragraph_format.page_break_before = True

    # 인용·링크는 파란 밑줄 대신 본문과 같은 검은 글씨
    try:
        link = doc.styles["Hyperlink"]
        link.font.color.rgb = RGBColor(0, 0, 0)
        link.font.underline = False
    except KeyError:
        pass

    # 표: 위·아래 굵은 선 (국내 논문 일반 양식)
    try:
        tbl = doc.styles["Table"].element
        tblpr = tbl.find(qn("w:tblPr"))
        if tblpr is None:
            tblpr = OxmlElement("w:tblPr")
            tbl.append(tblpr)
        for old in tblpr.findall(qn("w:tblBorders")):
            tblpr.remove(old)
        borders = OxmlElement("w:tblBorders")
        for side in ("top", "bottom"):
            b = OxmlElement(f"w:{side}")
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), "12")
            b.set(qn("w:color"), "000000")
            borders.append(b)
        tblpr.append(borders)
    except KeyError:
        pass

    # 목차 항목 글꼴
    for i in range(1, 4):
        s = S(f"TOC {i}") if f"TOC {i}" in [x.name for x in doc.styles] else get_style(doc, f"toc {i}")
        set_font(s, body_font, size)
        s.paragraph_format.left_indent = Cm(0.8 * (i - 1))

    out = TEMPLATE_DIR / "reference.docx"
    doc.save(str(out))
    base.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    print("만듦:", build_reference_docx())
