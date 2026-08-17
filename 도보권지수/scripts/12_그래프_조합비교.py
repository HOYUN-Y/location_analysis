"""d0 × β 조합 비교 — 소형 다중(small multiples)."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

for c in ["AppleGothic", "Malgun Gothic", "NanumGothic"]:
    if any(f.name == c for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = c
        break
plt.rcParams["axes.unicode_minus"] = False
pd.set_option("display.width", 250)

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, ACCENT = "#e1e0d9", "#c3c2b7", "#eb6834"
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#184f95"]     # 검증 통과한 순차 램프

D0S = [500, 750, 1000, 1500]
BETAS = [1.2, 1.5, 2.0, 3.0]
SITES = [("위례중앙", 112.7), ("래미안", 298.1),
         ("플로리체", 434.8), ("위례송파", 723.6)]
MPM, XMAX = 75.0, 2000


def S(d, d0, b):
    return 100.0 / (1.0 + (np.clip(np.asarray(d, float), 0, None) / d0) ** b)


def peak_of(d0, b):
    """가장 가파른 지점(m)과 그때의 100m 당 낙폭."""
    p = d0 * (((b - 1) / (b + 1)) ** (1 / b))
    v = float(-np.gradient(S(np.array([p - 1, p, p + 1]), d0, b))[1]) * 100
    return p, v


x = np.linspace(0, XMAX, 1400)
SLOPE_MAX = max(np.max(-np.gradient(S(x, d0, b), x) * 100)
                for d0 in D0S for b in BETAS)

fig, axes = plt.subplots(2, len(D0S), figsize=(17.5, 8.4), sharex=True,
                         gridspec_kw={"height_ratios": [1.25, 1],
                                      "hspace": 0.14, "wspace": 0.09})
fig.patch.set_facecolor(SURFACE)

for j, d0 in enumerate(D0S):
    top, bot = axes[0, j], axes[1, j]

    for b, col in zip(BETAS, RAMP):
        top.plot(x, S(x, d0, b), color=col, lw=2.1,
                 solid_capstyle="round", label=f"β = {b}", zorder=3)

        sl = -np.gradient(S(x, d0, b), x) * 100
        bot.plot(x, sl, color=col, lw=2.0, solid_capstyle="round", zorder=3)

        p, v = peak_of(d0, b)
        bot.plot([p], [v], "o", ms=7, color=col, mec=SURFACE, mew=1.6, zorder=5)

    # 반환점 — 모든 β 가 만나는 점
    top.plot([0, d0], [50, 50], color=AXIS, lw=1, ls=(0, (4, 4)), zorder=1)
    top.plot([d0], [50], "o", ms=9, mfc=SURFACE, mec=INK, mew=1.8, zorder=6)

    for _, dist in SITES:
        for a in (top, bot):
            a.axvline(dist, color=ACCENT, lw=0.9, ls=(0, (2, 3)),
                      alpha=0.55, zorder=1)

    top.set_title(f"$d_0$ = {d0:,}m   (도보 {d0/MPM:.0f}분)",
                  fontsize=12.5, color=INK, pad=10)
    top.set_ylim(0, 106)
    bot.set_ylim(0, SLOPE_MAX * 1.12)

    for a in (top, bot):
        a.set_xlim(0, XMAX)
        a.set_facecolor(SURFACE)
        a.grid(True, color=GRID, lw=0.8)
        a.set_axisbelow(True)
        a.tick_params(colors=MUTED, labelsize=9)
        a.set_xticks([0, 500, 1000, 1500, 2000])
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(AXIS)

    if j:
        top.set_yticklabels([])
        bot.set_yticklabels([])
    bot.set_xlabel("거리 (m)", fontsize=10, color=INK2)

axes[0, 0].set_ylabel("도보권 지수", fontsize=11, color=INK2)
axes[1, 0].set_ylabel("100m 당 점수 하락\n(= 그 구간의 변별력)",
                      fontsize=11, color=INK2, linespacing=1.5)
axes[0, 0].legend(loc="lower left", frameon=False, fontsize=9.5,
                  labelcolor=INK2, handlelength=1.6)

fig.suptitle("반환점 $d_0$ × 날카로움 β — 기울기 비교        "
             "세로 점선 = 위례 4개 단지(113 · 298 · 435 · 724m)   ·   "
             "○ = 반환점(모든 β 가 50점으로 만남)   ·   ● = 가장 가파른 지점",
             fontsize=13, color=INK, x=0.008, ha="left", y=0.995)
fig.tight_layout(rect=(0, 0, 1, 0.965))
fig.savefig(f"{PROJ}/도보권지수_조합비교.png",
            dpi=150, facecolor=SURFACE, bbox_inches="tight")
print("저장 완료: 도보권지수_조합비교.png")

# ── 같은 내용의 수치 요약 ────────────────────────────────────────
print()
print("=" * 118)
print("가장 가파른 지점 (m)  —  해상도가 어디에 몰리는가")
print("=" * 118)
print(pd.DataFrame({f"β={b}": {f"d0={d0}": round(peak_of(d0, b)[0])
                               for d0 in D0S} for b in BETAS}).to_string())
print()
print("그때의 100m 당 낙폭 (점)  —  얼마나 가파른가")
print("-" * 118)
print(pd.DataFrame({f"β={b}": {f"d0={d0}": round(peak_of(d0, b)[1], 1)
                               for d0 in D0S} for b in BETAS}).to_string())
print()
print("위례 4개 단지 구간(113~435m)의 상위3폭  —  근거리 변별력")
print("-" * 118)
print(pd.DataFrame({f"β={b}": {f"d0={d0}": round(float(S(112.7, d0, b)
                                                      - S(434.8, d0, b)), 1)
                               for d0 in D0S} for b in BETAS}).to_string())
print()
print("위례송파푸르지오(724m) 점수")
print("-" * 118)
print(pd.DataFrame({f"β={b}": {f"d0={d0}": round(float(S(723.6, d0, b)), 1)
                               for d0 in D0S} for b in BETAS}).to_string())
