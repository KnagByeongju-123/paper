"""논문 그림 만들기 (Blender 3D 렌더 + 한글 라벨).

실행:  python scripts/figures/make_figures.py            # 고품질
       python scripts/figures/make_figures.py --quick    # 빠른 미리보기
결과:  figures/sheared_edge_3d.png  전단면 구성 (처짐·전단면·파단면·버)
       figures/clearance_3d.png     블랭킹 금형 반단면 + 간극 확대
       그림 속 글자는 영문 (논문 그림 관례)

필요: Blender (https://www.blender.org, 무료). 명령어 `blender` 가 실행돼야 합니다.
      윈도우는 BLENDER 환경변수에 blender.exe 경로를 넣어도 됩니다.
그림 치수(펀치 지름·판 두께·간극)는 --punch-d / --thick / --gap 로 바꿀 수 있습니다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# 그림 속 글자는 영문 (학위논문 그림 관례) — 영문 글꼴
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",          # 리눅스
    "C:/Windows/Fonts/arial.ttf",                               # 윈도우
    "/System/Library/Fonts/Supplemental/Arial.ttf",             # 맥
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
INK, RED = (25, 30, 40), (190, 40, 35)


def font(size: int, bold: bool = False):
    for path in (BOLD_CANDIDATES if bold else []) + FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def blender_exe() -> str:
    sys.path.insert(0, str(HERE.parent))
    from thesis_lib import find_tool
    exe = find_tool("blender")
    if not exe:
        raise SystemExit("❌ Blender 를 찾지 못했습니다. 설치 후 다시 실행하거나 BLENDER 환경변수에 경로를 넣어 주세요.")
    return exe


def render(view: str, tmp: Path, a) -> tuple[Image.Image, dict]:
    out, anc = tmp / f"{view}.png", tmp / f"{view}.json"
    cmd = [blender_exe(), "-b", "-P", str(HERE / "clearance_3d.py"), "--",
           "--view", view, "--out", str(out), "--anchors", str(anc),
           "--samples", str(a.samples), "--width", str(a.w), "--height", str(a.h),
           "--punch-d", str(a.punch_d), "--thick", str(a.t), "--gap", str(a.c)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not out.exists():
        print(r.stdout[-2000:], r.stderr[-2000:])
        raise SystemExit(f"❌ {view} 렌더 실패")
    return Image.open(out).convert("RGB"), json.loads(anc.read_text(encoding="utf-8"))


def leader(d: ImageDraw.ImageDraw, anchor, text_xy, text, f):
    """점(anchor) → 글자 위치로 지시선. 글자가 점보다 왼쪽이면 오른쪽 정렬해 선과 겹치지 않게 한다."""
    d.line([tuple(anchor), tuple(text_xy)], fill=INK, width=3)
    d.ellipse([anchor[0] - 6, anchor[1] - 6, anchor[0] + 6, anchor[1] + 6], fill=INK)
    w = d.textlength(text, font=f)
    x = text_xy[0] - w - 10 if text_xy[0] < anchor[0] else text_xy[0] + 10
    d.text((x, text_xy[1] - f.size // 2 - 2), text, font=f, fill=INK)


def run_blender(script: str, out: Path, anc: Path, extra: list[str]) -> tuple[Image.Image, dict]:
    cmd = [blender_exe(), "-b", "-P", str(HERE / script), "--", "--out", str(out), "--anchors", str(anc), *extra]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not out.exists():
        print(r.stdout[-2000:], r.stderr[-2000:])
        raise SystemExit(f"❌ {script} 렌더 실패")
    return Image.open(out).convert("RGB"), json.loads(anc.read_text(encoding="utf-8"))


def make_sheared_edge(a):
    """그림: 전단면 구성 (처짐·전단면·파단면·버) 3D."""
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        print("🎨 Blender 렌더링 중… (전단면 구성)")
        img, an = run_blender("sheared_edge_3d.py", tmp / "edge.png", tmp / "edge.json",
                              ["--samples", str(a.samples), "--width", str(a.w), "--height", str(a.h)])
    s = a.w / 900
    # 위·아래 빈 여백 자르기 (라벨 좌표도 함께 이동)
    box = ImageChops.difference(img, Image.new("RGB", img.size, "white")).point(lambda v: 255 if v > 8 else 0).getbbox()
    if box:
        top, bot = max(0, box[1] - int(40 * s)), min(img.height, box[3] + int(70 * s))
        img = img.crop((0, top, img.width, bot))
        an = {k: ([v[0], v[1] - top] if isinstance(v, list) and len(v) == 2 and k != "size" else v) for k, v in an.items()}
    f, fsm = font(int(30 * s)), font(int(22 * s))
    W = int(img.width * 1.35)
    canvas = Image.new("RGB", (W, img.height), "white")
    canvas.paste(img, (0, 0))
    d = ImageDraw.Draw(canvas)
    col_x = int(img.width * 0.98)
    names = [("Rollover", "Rollover"), ("Burnish", "Burnish zone"), ("Fracture", "Fracture zone"), ("Burr", "Burr")]
    ys = sorted([an[k][1] for k, _ in names])
    gap = int(70 * s)
    for i in range(1, len(ys)):          # 라벨이 겹치지 않게 세로 간격 확보
        ys[i] = max(ys[i], ys[i - 1] + gap)
    order = sorted(names, key=lambda kv: an[kv[0]][1])
    for (key, text), y in zip(order, ys):
        leader(d, an[key], [col_x, y], text, f)
    note = "Conceptual illustration; zone proportions are not to scale."
    d.text((int(16 * s), img.height - int(40 * s)), note, font=fsm, fill=(110, 115, 125))
    out = ROOT / "figures" / "sheared_edge_3d.png"
    canvas.save(out)
    print(f"✅ 저장: {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", choices=["clearance", "edge"], help="한 그림만 다시 만들기")
    ap.add_argument("--punch-d", type=float, default=40.0)
    ap.add_argument("--thick", dest="t", type=float, default=3.0)
    ap.add_argument("--gap", dest="c", type=float, default=4.0)
    a = ap.parse_args()
    a.samples, a.w, a.h = (24, 900, 700) if a.quick else (160, 1400, 1100)
    if a.only != "clearance":
        make_sheared_edge(a)
    if a.only == "edge":
        return
    s = a.w / 900   # 라벨 크기 배율

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        print("🎨 Blender 렌더링 중… (전체 반단면)")
        ov, oa = render("overall", tmp, a)
        print("🎨 Blender 렌더링 중… (간극 확대)")
        dt, da = render("detail", tmp, a)

    f, fb, fsm = font(int(34 * s)), font(int(36 * s), True), font(int(24 * s))
    pad_top = int(70 * s)
    W = ov.width + dt.width + int(30 * s)
    H = ov.height + pad_top + int(60 * s)
    canvas = Image.new("RGB", (W, H), "white")
    canvas.paste(ov, (0, pad_top))
    canvas.paste(dt, (ov.width + int(30 * s), pad_top))
    d = ImageDraw.Draw(canvas)

    def off(p, panel):
        x0 = 0 if panel == 0 else ov.width + int(30 * s)
        return [p[0] + x0, p[1] + pad_top]

    d.text((int(20 * s), int(18 * s)), "(a) Blanking die, half section", font=fb, fill=INK)
    d.text((ov.width + int(50 * s), int(18 * s)), "(b) Detail: punch-die clearance", font=fb, fill=INK)

    # (a) 라벨
    p = off(oa["punch"], 0); leader(d, p, [p[0] + int(170 * s), p[1] - int(40 * s)], "Punch", f)
    p = off(oa["sheet"], 0); leader(d, p, [p[0] + int(40 * s), p[1] - int(90 * s)], "Sheet (t)", f)
    p = off(oa["die"], 0); leader(d, p, [p[0] + int(110 * s), p[1] + int(60 * s)], "Die", f)

    # (b) 간극 표시: 펀치 측면 ~ 다이 측면
    gl, gr = off(da["gap_left"], 1), off(da["gap_right"], 1)
    y = max(gl[1], gr[1]) + int(60 * s)
    for gx in (gl, gr):
        d.line([gx[0], gx[1], gx[0], y + int(10 * s)], fill=RED, width=max(2, int(3 * s)))
    d.line([gl[0], y, gr[0], y], fill=RED, width=max(2, int(4 * s)))
    for x, sgn in ((gl[0], 1), (gr[0], -1)):
        d.polygon([(x, y), (x + sgn * int(16 * s), y - int(8 * s)), (x + sgn * int(16 * s), y + int(8 * s))], fill=RED)
    d.text((gl[0] - int(150 * s), y + int(16 * s)), "Clearance c (per side)", font=f, fill=RED)

    note = f"Drawing dimensions: punch dia. {a.punch_d:g} mm, sheet t = {a.t:g} mm, c = {a.c:g} mm (clearance exaggerated for visibility)"
    d.text((int(20 * s), H - int(45 * s)), note, font=fsm, fill=(110, 115, 125))

    out = ROOT / "figures" / "clearance_3d.png"
    canvas.save(out)
    print(f"✅ 저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
