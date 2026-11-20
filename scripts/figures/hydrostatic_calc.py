"""오일 정압 원형 패드 베어링(모세관 리스트릭터)의 성능 계산 → 표 + 그래프.

실행:  python scripts/figures/hydrostatic_calc.py
결과:  figures/hb_performance.png   (2D 그래프, 영문 라벨)
       화면에 설계점 성능 표(마크다운) 출력 → 4장에 붙여넣기

모델 (비압축성 층류, 원형 리세스 패드, 2장 식):
  유효 면적   Ae = π (R² − R0²) / (2 ln(R/R0))
  막 저항     Rf(h) = 6 μ ln(R/R0) / (π h³)          Q = Pr / Rf
  모세관 저항 Rc = 128 μ lc / (π dc⁴)                Q = (Ps − Pr) / Rc
  압력비      β = Pr/Ps = Rf / (Rf + Rc)
  부하 용량   W = β Ps Ae
  강성        K = −dW/dh = 3 Ae Ps β(1−β) / h       (β = 0.5 에서 최대)
  설계 조건: 설계 막 두께 h0 에서 β = 0.5 가 되도록 Rc = Rf(h0)
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

# ---- 설계 변수 (3장 표와 같게 유지) ----
R, R0 = 40e-3, 20e-3          # 패드 반지름, 리세스 반지름 (m)
MU = 0.028                    # 오일 점도 (Pa·s), ISO VG 32 @ 40 °C 부근 — 확인 필요
H0 = 20e-6                    # 설계 막 두께 (m)
PS_LIST = [2e6, 3e6, 4e6]     # 공급 압력 (Pa)
PS_DESIGN = 3e6

LN = math.log(R / R0)
AE = math.pi * (R**2 - R0**2) / (2 * LN)


def rf(h):
    return 6 * MU * LN / (math.pi * h**3)


RC = rf(H0)   # 설계점에서 β = 0.5


def perf(h, ps):
    beta = rf(h) / (rf(h) + RC)
    w = beta * ps * AE
    k = 3 * AE * ps * beta * (1 - beta) / h
    q = beta * ps / rf(h)
    return beta, w, k, q


INK, MUTED, GRID = "#1f2328", "#5f6670", "#e3e5e8"
STYLE = [("#2a78d6", "o"), ("#eb6834", "s"), ("#1baf7a", "^")]


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.unicode_minus": False})
    hs = [h * 1e-6 for h in range(6, 51)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), dpi=200)

    ax = axes[0]
    ends = []
    for ps, (color, marker) in zip(PS_LIST, STYLE):
        ks = [perf(h, ps)[2] / 1e6 for h in hs]      # N/μm
        ax.plot([h * 1e6 for h in hs], ks, color=color, lw=2, marker=marker, ms=6, markevery=8,
                mec="white", mew=1.2, label=f"Ps = {ps/1e6:g} MPa")
        ends.append((ks[-1], f"{ps/1e6:g} MPa", hs[-1] * 1e6))
    ax.axvline(H0 * 1e6, color="#9aa1a9", lw=1, ls="--")
    ax.text(H0 * 1e6 + 0.8, ax.get_ylim()[1] * 0.95, "design h0", color=MUTED, fontsize=9, va="top")
    ax.set_title("(a) Film stiffness vs. film thickness", loc="left", color=INK, fontsize=12, pad=10)
    ax.set_xlabel("Film thickness h (μm)", color=MUTED)
    ax.set_ylabel("Stiffness K (N/μm)", color=MUTED)
    ax.legend(frameon=False, fontsize=10)

    ax = axes[1]
    betas = [i / 100 for i in range(1, 100)]
    norm = [4 * b * (1 - b) for b in betas]          # K / Kmax
    ax.plot(betas, norm, color=STYLE[0][0], lw=2)
    ax.plot([0.5], [1.0], marker="o", ms=8, color=STYLE[0][0], mec="white", mew=1.5)
    ax.annotate("max at β = 0.5", (0.5, 1.0), xytext=(14, -24), textcoords="offset points", color=INK, fontsize=10)
    ax.set_title("(b) Normalized stiffness vs. pressure ratio", loc="left", color=INK, fontsize=12, pad=10)
    ax.set_xlabel("Pressure ratio β = Pr / Ps", color=MUTED)
    ax.set_ylabel("K / Kmax", color=MUTED)
    ax.set_xlim(0, 1)

    for a in axes:
        a.grid(axis="y", color=GRID, lw=0.8)
        a.set_axisbelow(True)
        a.set_ylim(bottom=0)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color("#c9cdd2")
        a.tick_params(colors=MUTED)
    fig.tight_layout()
    out = ROOT / "figures" / "hb_performance.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, facecolor="white")
    print(f"✅ 그림 저장: {out.relative_to(ROOT)}\n")

    print(f"설계값: R = {R*1e3:g} mm, R0 = {R0*1e3:g} mm, μ = {MU} Pa·s, h0 = {H0*1e6:g} μm, "
          f"Ae = {AE*1e6:,.0f} mm², Rc = {RC:.3e} Pa·s/m³\n")
    print("| 공급 압력 $P_s$ (MPa) | 압력비 $\\beta$ | 부하 용량 $W$ (kN) | 강성 $K$ (N/μm) | 유량 $Q$ (mL/min) | 펌프 동력 $H$ (W) |")
    print("|---:|---:|---:|---:|---:|---:|")
    for ps in PS_LIST:
        b, w, k, q = perf(H0, ps)
        print(f"| {ps/1e6:g} | {b:.2f} | {w/1e3:.2f} | {k/1e6:.0f} | {q*6e7:.1f} | {ps*q:.2f} |")
    print()
    print("| 막 두께 $h$ (μm) | 압력비 $\\beta$ | 부하 용량 $W$ (kN) | 강성 $K$ (N/μm) |")
    print("|---:|---:|---:|---:|")
    for hm in (10, 15, 20, 25, 30, 40):
        b, w, k, _ = perf(hm * 1e-6, PS_DESIGN)
        print(f"| {hm} | {b:.2f} | {w/1e3:.2f} | {k/1e6:.0f} |")


if __name__ == "__main__":
    main()
