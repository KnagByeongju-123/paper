"""2장의 식으로 펀치·다이 치수와 전단 하중을 계산해 마크다운 표로 출력한다.

실행:  python scripts/figures/calc_tool_dimensions.py
- 간극 비율 k 는 2장 표(재질별 일반 범위)의 중간값을 쓴다.
- 인장강도는 규격 최소값(확인 필요)을 쓴다. 값을 바꾸면 표가 다시 계산된다.
"""
import math

T = 1.0            # 판 두께 (mm)
BLANK_D = 40.0     # 블랭크(제품) 지름 (mm)
HOLE_D = 10.0      # 피어싱 구멍 지름 (mm)
MATERIALS = [      # 이름, 간극 비율 k(범위 중간값), 인장강도 σUTS (MPa, 규격 최소값 — 확인 필요)
    ("Al 5052-H32", (0.03 + 0.06) / 2, 215),
    ("SPCC", (0.05 + 0.08) / 2, 270),
    ("SUS304", (0.07 + 0.10) / 2, 520),
]

print("| 재질 | $k$ (%) | 편측 간극 $c$ (mm) | 블랭킹 다이 $D_d$ | 블랭킹 펀치 $D_p$ | 피어싱 펀치 $d_p$ | 피어싱 다이 $d_d$ |")
print("|------|---:|---:|---:|---:|---:|---:|")
for name, k, _ in MATERIALS:
    c = k * T
    print(f"| {name} | {k*100:.1f} | {c:.3f} | {BLANK_D:.3f} | {BLANK_D-2*c:.3f} | {HOLE_D:.3f} | {HOLE_D+2*c:.3f} |")
print()
print("| 재질 | $\\sigma_{UTS}$ (MPa) | 블랭킹 하중 (kN) | 피어싱 하중 (kN) |")
print("|------|---:|---:|---:|")
for name, _, uts in MATERIALS:
    fb = 0.8 * math.pi * BLANK_D * T * uts / 1000
    fh = 0.8 * math.pi * HOLE_D * T * uts / 1000
    print(f"| {name} | {uts} | {fb:.1f} | {fh:.1f} |")
