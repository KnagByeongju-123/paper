"""원형 컵 성형해석 결과(summary.csv) → 비교 그래프 + 마크다운 표.

실행:  python scripts/forming/plot_round_cup.py
결과:  figures/fa_round_cup_compare.png  (재질별 간극–최대 두께감소 / 간극–성형 하중)
       figures/fa_round_cup_contour.png  (대표 사례의 변형률 분포 그림, 해석기 출력)
"""
import csv
import shutil
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "sources" / "data" / "fa_round_cup"
STYLE = {"Al5052": ("#2a78d6", "o", "Al 5052"), "SPCC": ("#eb6834", "s", "SPCC"), "SUS304": ("#1baf7a", "^", "SUS304")}
INK, MUTED, GRID = "#1f2328", "#5f6670", "#e3e5e8"
REPRESENTATIVE = "SUS304_k10"


def main():
    rows = list(csv.DictReader((DATA / "summary.csv").open(encoding="utf-8")))
    by = defaultdict(list)
    for r in rows:
        by[r["material"]].append((float(r["k"]) * 100, float(r["max_thinning_percent"]), float(r["forming_load_kN"])))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), dpi=200)
    for ax, col, title, ylab in ((axes[0], 1, "(a) Maximum thinning", "Max. thinning (%)"),
                                 (axes[1], 2, "(b) Forming load", "Forming load (kN)")):
        for mat in ("Al5052", "SPCC", "SUS304"):
            pts = sorted(by[mat])
            c, m, lab = STYLE[mat]
            ax.plot([p[0] for p in pts], [p[col] for p in pts], color=c, marker=m, lw=2, ms=8,
                    mec="white", mew=1.5, label=lab)
        ax.set_title(title, loc="left", color=INK, fontsize=12, pad=10)
        ax.set_xlabel("Wall clearance ratio k (%),  gap = t (1 + k)", color=MUTED)
        ax.set_ylabel(ylab, color=MUTED)
        ax.set_xticks([5, 10, 20])
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#c9cdd2")
        ax.tick_params(colors=MUTED)
    axes[0].legend(frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(ROOT / "figures" / "fa_round_cup_compare.png", facecolor="white")
    shutil.copy2(DATA / REPRESENTATIVE / "1_forming_summary.png", ROOT / "figures" / "fa_round_cup_contour.png")
    print("✅ figures/fa_round_cup_compare.png, figures/fa_round_cup_contour.png\n")
    print("| 재질 | 간극 비율 $k$ (%) | 최대 두께감소 (%) | 발생 위치 $r$ (mm) | 성형 하중 (kN) | 부피 오차 (%) |")
    print("|------|---:|---:|---:|---:|---:|")
    for mat in ("Al5052", "SPCC", "SUS304"):
        for r in sorted((r for r in rows if r["material"] == mat), key=lambda r: float(r["k"])):
            print(f"| {STYLE[mat][2]} | {float(r['k'])*100:g} | {r['max_thinning_percent']} | {r['r_at_max_thinning_mm']} | "
                  f"{r['forming_load_kN']} | {r['volume_error_percent']} |")


if __name__ == "__main__":
    main()
