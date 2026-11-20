"""원형 컵(축대칭) 드로잉 성형해석 — 사내 해석기 mold_sold 를 불러서 실행하고 결과를 논문으로 가져온다.

mold_sold 는 별도(비공개) 저장소이므로 코드는 복사하지 않고 경로로 호출한다.
  해석기 위치: 환경변수 MOLD_SOLD (기본: 이 저장소 옆 폴더 ../mold_sold)

실행 예:
  python scripts/forming/round_cup.py --material SPCC --k 0.10
  python scripts/forming/round_cup.py --all            # 3재질 × 간극 3수준
결과:
  sources/data/fa_round_cup/<재질>_k<간극>/   (mold_sold 원본 결과: summary.json, *_thickness.csv, 그림)
  sources/data/fa_round_cup/summary.csv       (재질·간극별 최대 두께감소, 최대 하중 모음)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sources" / "data" / "fa_round_cup"

# 재질 상수: Swift 경화식 σ̄ = K (ε0 + ε̄)^n [MPa]
# SUS304 는 mold_sold 기본값, SPCC·Al 5052 는 대표값(가정) — 인장시험 값으로 바꿀 것
MATERIALS = {
    "SPCC":   {"K": 550.0,  "n": 0.22, "eps0": 0.010, "m": 0.05},
    "SUS304": {"K": 1275.0, "n": 0.45, "eps0": 0.034, "m": 0.05},
    "Al5052": {"K": 380.0,  "n": 0.20, "eps0": 0.010, "m": 0.05},
}

T = 1.0         # 판 두께 [mm]
RP = 12.0       # 펀치 반지름 [mm]
DEPTH = 6.0     # 컵 깊이 [mm]
R_OUT = 30.0    # 블랭크 바깥 반지름(스트립에 잡힘) [mm]
R_TOOL = 34.0   # 금형 바깥 반지름 [mm]
DRAFT = 0.3     # 벽 빼기구배(반지름 증가량) [mm]


def stages(k: float) -> dict:
    """공정이 끝났을 때의 판재 윗면(펀치)·아랫면(다이). 벽 간극 = t (1 + k)."""
    rd = RP + T * (1 + k)
    top = [[0, -DEPTH], [RP, -DEPTH], [RP + DRAFT, 0.0], [R_TOOL, 0.0]]
    bottom = [[0, -DEPTH - T], [rd, -DEPTH - T], [rd + DRAFT, -T], [R_TOOL, -T]]
    return {"1_forming": {"top": top, "bottom": bottom}}


def run_case(mold: Path, mat: str, k: float, quick: bool) -> dict:
    case = OUT / f"{mat}_k{int(round(k * 100)):02d}"
    case.mkdir(parents=True, exist_ok=True)
    (case / "stages.json").write_text(json.dumps(stages(k), indent=1))
    cfg = {"thickness": T, "r_outer": R_OUT, "r_tool": R_TOOL, "material": MATERIALS[mat],
           "stages": ["1_forming"], "labels": {"1_forming": f"Round cup, {mat}, k = {k:.2f}"},
           "pads": {}, "mesh_by_stage": {}, "mesh_size": 0.33 if quick else 0.25,
           "step": 0.08 if quick else 0.05, "friction": 0.1, "edge": "slide", "min_tool_radius": 2.5}   # 펀치·다이 모서리 R 2.5 mm
    (case / "config.json").write_text(json.dumps(cfg, indent=1))
    print(f"▶ {mat}, k = {k:.2f} 해석 중 …", flush=True)
    r = subprocess.run([sys.executable, str(mold / "sheet_forming.py"), str(case / "stages.json"),
                        "--config", str(case / "config.json"), "--out", str(case)],
                       capture_output=True, text=True, cwd=mold)
    (case / "solver.log").write_text(r.stdout[-20000:] + "\n" + r.stderr[-20000:])
    res = json.loads((case / "1_forming_result.json").read_text(encoding="utf-8")) if (case / "1_forming_result.json").exists() else {}
    if r.returncode != 0 or not res:
        print(f"  ❌ 실패 — {case / 'solver.log'} 확인")
        return {}
    # 성형 하중: 마지막 바닥 닿기(급상승) 직전까지의 최대값 — 행정의 97 % 이내
    import numpy as np
    hist = np.loadtxt(case / "1_forming_load.csv", delimiter=",", skiprows=1)
    form = hist[hist[:, 0] <= 0.97 * hist[:, 0].max(), 1].max()
    res["forming_load_kN"] = round(float(form), 1)
    print(f"  ✅ 최대 두께감소 {res.get('max_thinning_percent')} %, 성형 하중 {res['forming_load_kN']} kN")
    return {"material": mat, "k": k, **{key: res.get(key) for key in
            ("max_thinning_percent", "r_at_max_thinning_mm", "forming_load_kN", "volume_error_percent")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", choices=list(MATERIALS))
    ap.add_argument("--k", type=float, default=0.10)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    mold = Path(os.environ.get("MOLD_SOLD", ROOT.parent / "mold_sold")).resolve()
    if not (mold / "sheet_forming.py").exists():
        raise SystemExit(f"❌ mold_sold 해석기를 찾지 못했습니다: {mold}  (MOLD_SOLD 환경변수로 경로 지정)")
    cases = [(m, k) for m in MATERIALS for k in (0.05, 0.10, 0.20)] if a.all else [(a.material or "SPCC", a.k)]
    rows = [r for r in (run_case(mold, m, k, a.quick) for m, k in cases) if r]
    if rows:
        f = OUT / "summary.csv"
        old = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else []
        keep = {(o["material"], float(o["k"])): o for o in old}
        for r in rows:
            keep[(r["material"], r["k"])] = r
        with f.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["material", "k", "max_thinning_percent", "r_at_max_thinning_mm", "forming_load_kN", "volume_error_percent"])
            w.writeheader()
            for key in sorted(keep):
                w.writerow(keep[key])
        print(f"\n📄 {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
