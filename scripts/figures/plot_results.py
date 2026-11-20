"""해석 결과 CSV → 결과 그래프 + 재질별 적정 간극 표.

실행:  python scripts/figures/plot_results.py [CSV 경로]
기본 CSV: sources/data/ 안에서 이름에 '간극별_해석결과' 가 들어간 가장 최근 파일
결과:   figures/result_clearance.png  (그림)
        화면에 재질별 적정 간극 표(마크다운) 출력 → 4장에 붙여넣기

CSV 형식 (# 로 시작하는 줄은 설명으로 무시):
  material,clearance_pct,burnish_pct,burr_um
적정 간극 정의: 버 높이가 가장 작은 간극 (같으면 전단면 비율이 큰 쪽)
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[2]
# 색: 검증된 범주형 팔레트(파랑·주황·청록) + 재질별 표식 모양 → 흑백 인쇄에서도 구분
STYLE = [("#2a78d6", "o"), ("#eb6834", "s"), ("#1baf7a", "^")]
INK, MUTED, GRID = "#1f2328", "#5f6670", "#e3e5e8"


def korean_font():
    for name in ("NanumGothic", "Malgun Gothic", "AppleGothic", "Noto Sans CJK KR"):
        if any(name == f.name for f in font_manager.fontManager.ttflist):
            return name
    return None


def load(path: Path):
    rows = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    data = defaultdict(list)
    for r in csv.DictReader(rows):
        data[r["material"]].append((float(r["clearance_pct"]), float(r["burnish_pct"]), float(r["burr_um"])))
    for v in data.values():
        v.sort()
    example = "예시" in path.name or "가상" in path.read_text(encoding="utf-8")[:300]
    return data, example


def main():
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        cands = sorted((ROOT / "sources" / "data").glob("*간극별_해석결과*.csv"))
        if not cands:
            raise SystemExit("❌ sources/data/ 에 '간극별_해석결과' CSV 가 없습니다.")
        csv_path = cands[-1]
    data, example = load(csv_path)

    fam = korean_font()
    if fam:
        plt.rcParams["font.family"] = fam
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 11})

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), dpi=200)
    panels = [(1, "(a) 전단면 비율", "전단면 비율 (%)"), (2, "(b) 버 높이", "버 높이 (μm)")]
    for ax, (col, title, ylabel) in zip(axes, panels):
        ends = []
        for (mat, pts), (color, marker) in zip(data.items(), STYLE):
            xs, ys = [p[0] for p in pts], [p[col] for p in pts]
            ax.plot(xs, ys, color=color, lw=2, marker=marker, ms=7, mec="white", mew=1.5, label=mat, zorder=3)
            ends.append([ys[-1], mat, xs[-1]])
        # 끝점 직접 라벨: 서로 겹치지 않게 위아래로 벌림 (글자는 잉크색)
        top = max(p[col] for v in data.values() for p in v)
        gap = top * 0.07
        ends.sort()
        for i in range(1, len(ends)):
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + gap)
        for y, mat, x in ends:
            ax.annotate(mat, (x, y), xytext=(10, 0), textcoords="offset points", va="center", fontsize=10, color=INK)
        ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
        ax.set_xlabel("편측 간극 비율 k (판 두께 대비 %)", color=MUTED)
        ax.set_ylabel(ylabel, color=MUTED)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c9cdd2")
        ax.tick_params(colors=MUTED)
        ax.set_ylim(bottom=0)
        xs_all = sorted({p[0] for v in data.values() for p in v})
        ax.set_xticks(xs_all)
        ax.set_xlim(xs_all[0] - 1, xs_all[-1] * 1.35)
    axes[0].legend(frameon=False, loc="lower left", fontsize=10)
    if example:
        fig.text(0.5, 0.5, "예시 데이터", ha="center", va="center", fontsize=70, color="#d0d4d9",
                 alpha=0.35, rotation=20, zorder=0)
    fig.tight_layout()
    out = ROOT / "figures" / "result_clearance.png"
    fig.savefig(out, facecolor="white")
    print(f"✅ 그림 저장: {out.relative_to(ROOT)}  (데이터: {csv_path.name}{' — 예시 데이터' if example else ''})\n")

    print("| 재질 | 적정 간극 비율 $k$ (%) | 전단면 비율 (%) | 버 높이 (μm) |")
    print("|------|---:|---:|---:|")
    for mat, pts in data.items():
        best = min(pts, key=lambda p: (p[2], -p[1]))
        print(f"| {mat} | {best[0]:g} | {best[1]:g} | {best[2]:g} |")


if __name__ == "__main__":
    main()
