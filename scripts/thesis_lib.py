"""논문 빌드/검사 스크립트가 함께 쓰는 공통 기능.

- 설정 파일(thesis.yaml) 읽기
- 장(章) 파일 목록 만들기
- 본문에서 그림·표·인용·TODO 찾기
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHAPTER_DIR = ROOT / "chapters"
SOURCE_DIR = ROOT / "sources"
OUTPUT_DIR = ROOT / "output"
TEMPLATE_DIR = ROOT / "templates"

# ---- 본문 문법(정규식) -------------------------------------------------
# 그림:  ![캡션](figures/a.png){#fig:a width=80%}
FIG_RE = re.compile(r"!\[(?P<cap>[^\]]*)\]\((?P<path>[^)\s]+)\)(?P<attr>\{[^}]*\})?")
FIG_ID_RE = re.compile(r"#fig:(?P<id>[\w\-]+)")
# 표 캡션:  Table: 캡션 {#tbl:a}   또는   : 캡션 {#tbl:a}
TBL_CAP_RE = re.compile(r"^(?P<lead>Table:|:)\s*(?P<cap>.*?)\s*\{#tbl:(?P<id>[\w\-]+)\}\s*$")
# 그림/표 참조:  @fig:a  /  [@fig:a]
XREF_RE = re.compile(r"\[?(?<![\w@])@(?P<kind>fig|tbl):(?P<id>[\w\-]+)\]?")
# 문헌 인용:  [@kim2020]  [@kim2020, p. 12; @lee2021]  @kim2020
CITE_RE = re.compile(r"(?<![\w@])@(?P<key>[A-Za-z][\w:\-.]*\w)")
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*$")
TODO_RE = re.compile(r"\[TODO[^\]]*\]")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FENCE_RE = re.compile(r"^(```|~~~)")


@dataclass
class Part:
    """논문을 이루는 파일 하나 (초록, 장 등)."""
    file: str
    section: str          # front / chapter / back
    numbered: bool = False
    cite: bool = False    # true 이면 인용 없는 문단을 경고

    @property
    def path(self) -> Path:
        return CHAPTER_DIR / self.file


@dataclass
class Config:
    raw: dict
    parts: list[Part] = field(default_factory=list)

    @property
    def info(self) -> dict:
        return self.raw.get("info", {})

    @property
    def fmt(self) -> dict:
        return self.raw.get("format", {})

    @property
    def style(self) -> dict:
        return self.raw.get("style", {})


def load_config() -> Config:
    raw = yaml.safe_load((ROOT / "thesis.yaml").read_text(encoding="utf-8"))
    cfg = Config(raw=raw)
    for key, section in (("front_matter", "front"), ("chapters", "chapter"), ("back_matter", "back")):
        for item in raw.get(key) or []:
            cfg.parts.append(Part(file=item["file"], section=section,
                                  numbered=bool(item.get("numbered", False)),
                                  cite=bool(item.get("cite", False))))
    return cfg


def iter_body_lines(text: str):
    """코드 블록(``` … ```) 안쪽을 빼고 (줄번호, 줄) 을 돌려준다."""
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield i, line


def strip_comments(text: str) -> str:
    """작성 안내용 HTML 주석(<!-- -->)을 지운다. 줄 수는 유지한다."""
    return COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def load_bib_keys(bib_path: Path) -> set[str]:
    if not bib_path.exists():
        return set()
    text = bib_path.read_text(encoding="utf-8")
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", text))
