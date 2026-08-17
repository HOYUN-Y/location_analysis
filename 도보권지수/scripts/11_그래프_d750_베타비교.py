"""d0=750m, β 여러 버전 비교."""

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

for c in ["AppleGothic", "Malgun Gothic", "NanumGothic"]:
    if any(f.name == c for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = c
        break
plt.rcParams["axes.unicode_minus"] = False

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, ACCENT = "#e1e0d9", "#c3c2b7", "#eb6834"
# 순차(ordinal) 램프 — β 가 커질수록 진해진다. 검증 통과.
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#184f95"]

D0, MPM = 750.0, 75.0
BETAS = [1.2, 1.5, 2.0, 3.0]
SITES = [("위례중앙", 112.7), ("래미안", 298.1),
         ("플로리체", 434.8), ("위례송파", 723.6)]


def S(d, b):
    return 100.0 / (1.0 + (np.clip(np.asarray(d, float), 0, None) / D0) ** b)


XMAX, XPAD = 2000, 2320
x = np.linspace(0, XMAX, 1400)

fig, (a1, a2) = plt.subplots(2, 1, figsize=(12.2, 9.0), sharex=True,
                             gridspec_kw={"height_ratios": [2.0, 1], "hspace": 0.16})
fig.patch.set_facecolor(SURFACE)

# ══ 위 — 점수 곡선 ══════════════════════════════════════════════
for b, col in zip(BETAS, RAMP):
    a1.plot(x, S(x, b), color=col, lw=2.3, solid_capstyle="round",
            label=f"β = {b}", zorder=3)
    a1.annotate(f"β={b}", xy=(XMAX, S(XMAX, b)), xytext=(XMAX + 45, S(XMAX, b)),
                fontsize=9.5, color=col, va="center", fontweight="bold")

# 모든 곡선이 만나는 점
a1.plot([0, D0], [50, 50], color=AXIS, lw=1, ls=(0, (4, 4)), zorder=1)
a1.plot([D0], [50], "o", ms=10, mfc=SURFACE, mec=INK, mew=2, zorder=6)
a1.annotate("반환점 750m — β 와 무관하게 모든 곡선이\n여기서 정확히 50점으로 만난다",
            xy=(D0, 50), xytext=(D0 + 95, 62), fontsize=10, color=INK,
            linespacing=1.55,
            arrowprops=dict(arrowstyle="-", color=AXIS, lw=1, shrinkA=2, shrinkB=8))

for name, dist in SITES:
    a1.axvline(dist, color=ACCENT, lw=1, ls=(0, (2, 3)), alpha=0.6, zorder=1)
    a1.text(dist, 103.5, f"{name}\n{dist:,.0f}m", ha="center", va="bottom",
            fontsize=8.5, color=ACCENT, linespacing=1.4)

a1.set_ylim(0, 112)
a1.set_ylabel("도보권 지수", fontsize=10.5, color=INK2)
a1.set_title("반환점 750m 고정, β 를 바꿔가며", fontsize=14, color=INK,
             pad=52, loc="left")
a1.legend(loc="upper right", frameon=False, fontsize=10,
          labelcolor=INK2, title="임계의 날카로움", title_fontsize=9.5)

at = a1.secondary_xaxis("top", functions=(lambda v: v / MPM, lambda m: m * MPM))
at.set_xlabel("도보 분  (보통 걸음 4.5km/h)", fontsize=9.5, color=MUTED, labelpad=6)
at.tick_params(colors=MUTED, labelsize=9)
for s_ in at.spines.values():
    s_.set_color(AXIS)

# ══ 아래 — 기울기 ═══════════════════════════════════════════════
for b, col in zip(BETAS, RAMP):
    sl = -np.gradient(S(x, b), x) * 100
    a2.plot(x, sl, color=col, lw=2.1, solid_capstyle="round", zorder=3)

    peak = D0 * (((b - 1) / (b + 1)) ** (1 / b))
    pv = float(-np.gradient(S(np.array([peak - 1, peak, peak + 1]), b))[1]) * 100
    a2.plot([peak], [pv], "o", ms=8, color=col, mec=SURFACE, mew=1.8, zorder=5)
    a2.annotate(f"{peak:,.0f}m", xy=(peak, pv), xytext=(peak, pv + 0.75),
                ha="center", fontsize=8.5, color=col, fontweight="bold")

for _, dist in SITES:
    a2.axvline(dist, color=ACCENT, lw=1, ls=(0, (2, 3)), alpha=0.6, zorder=1)

a2.set_ylim(0, 14.5)
a2.set_xlabel("대지 경계 → 목적지 거리 (m)", fontsize=10.5, color=INK2)
a2.set_ylabel("100m 당 점수 하락", fontsize=10.5, color=INK2)
a2.set_title("얼마나 가파른가 — 점은 각 β 의 가장 가파른 지점",
             fontsize=11, color=INK2, loc="left", pad=8)

for a in (a1, a2):
    a.set_xlim(0, XPAD)
    a.set_facecolor(SURFACE)
    a.grid(True, color=GRID, lw=0.8)
    a.set_axisbelow(True)
    a.tick_params(colors=MUTED, labelsize=9.5)
    a.set_xticks([0, 250, 500, 750, 1000, 1250, 1500, 1750, 2000])
    for side in ("top", "right"):
        a.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        a.spines[side].set_color(AXIS)

fig.tight_layout()
fig.savefig(f"{PROJ}/도보권지수_d750_베타비교.png",
            dpi=150, facecolor=SURFACE, bbox_inches="tight")
print("저장 완료: 도보권지수_d750_베타비교.png")
