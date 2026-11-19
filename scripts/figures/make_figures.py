"""논문 그림 만들기 (Blender 3D 렌더 + 한글 라벨).

실행:  python scripts/figures/make_figures.py            # 고품질
       python scripts/figures/make_figures.py --quick    # 빠른 미리보기
결과:  figures/clearance_3d.png   (본문에서 ![…](figures/clearance_3d.png){#fig:clearance3d})

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

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",          # 리눅스
    "C:/Windows/Fonts/malgun.ttf",                              # 윈도우
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",               # 맥
    "/Library/Fonts/NanumGothic.ttf",
]
INK, RED = (25, 30, 40), (190, 40, 35)


def font(size: int, bold: bool = False):
    for f in FONT_CANDIDATES:
        cand = f.replace("NanumGothic.ttf", "NanumGothicBold.ttf") if bold else f
        for path in (cand, f):
            if Path(path).exists():
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def blender_exe() -> str:
    exe = os.environ.get("BLENDER") or shutil.which("blender")
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
    d.line([tuple(anchor), tuple(text_xy)], fill=INK, width=3)
    d.ellipse([anchor[0] - 6, anchor[1] - 6, anchor[0] + 6, anchor[1] + 6], fill=INK)
    d.text((text_xy[0] + 8, text_xy[1] - f.size // 2 - 2), text, font=f, fill=INK)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--punch-d", type=float, default=40.0)
    ap.add_argument("--thick", dest="t", type=float, default=3.0)
    ap.add_argument("--gap", dest="c", type=float, default=4.0)
    a = ap.parse_args()
    a.samples, a.w, a.h = (24, 900, 700) if a.quick else (160, 1400, 1100)
    s = a.w / 900   # 라벨 크기 배율

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        print("🎨 Blender 렌더링 중… (전체 반단면)")
        ov, oa = render("overall", tmp, a)
        print("🎨 Blender 렌더링 중… (간극 확대)")
        dt, da = render("detail", tmp, a)

    f, fb, fsm = font(int(42 * s)), font(int(46 * s), True), font(int(30 * s))
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

    d.text((int(20 * s), int(18 * s)), "(a) 블랭킹 금형 반단면", font=fb, fill=INK)
    d.text((ov.width + int(50 * s), int(18 * s)), "(b) 펀치·다이 간극 부분 확대", font=fb, fill=INK)

    # (a) 라벨
    p = off(oa["punch"], 0); leader(d, p, [p[0] + int(170 * s), p[1] - int(40 * s)], "펀치", f)
    p = off(oa["sheet"], 0); leader(d, p, [p[0] + int(30 * s), p[1] - int(150 * s)], "판재 (두께 t)", f)
    p = off(oa["die"], 0); leader(d, p, [p[0] + int(110 * s), p[1] + int(60 * s)], "다이", f)

    # (b) 간극 표시: 펀치 측면 ~ 다이 측면
    gl, gr = off(da["gap_left"], 1), off(da["gap_right"], 1)
    y = max(gl[1], gr[1]) + int(60 * s)
    for gx in (gl, gr):
        d.line([gx[0], gx[1], gx[0], y + int(10 * s)], fill=RED, width=max(2, int(3 * s)))
    d.line([gl[0], y, gr[0], y], fill=RED, width=max(2, int(4 * s)))
    for x, sgn in ((gl[0], 1), (gr[0], -1)):
        d.polygon([(x, y), (x + sgn * int(16 * s), y - int(8 * s)), (x + sgn * int(16 * s), y + int(8 * s))], fill=RED)
    d.text((gr[0] + int(14 * s), y - int(18 * s)), "간극 c (편측)", font=f, fill=RED)

    note = f"그림용 치수: 펀치 지름 {a.punch_d:g} mm, 판 두께 {a.t:g} mm, 간극 {a.c:g} mm (간극은 보이도록 과장)  ·  Blender 로 연구자 작성"
    d.text((int(20 * s), H - int(45 * s)), note, font=fsm, fill=(110, 115, 125))

    out = ROOT / "figures" / "clearance_3d.png"
    canvas.save(out)
    print(f"✅ 저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
