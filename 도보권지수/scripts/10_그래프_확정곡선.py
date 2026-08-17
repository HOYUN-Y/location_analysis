"""확정안(d0=1000, β=2.0, 앵커 없음) 시각화."""

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

# ── 팔레트 (검증 통과: blue↔orange 인접쌍 CVD ΔE 24.7) ──
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
CURVE, MARK = "#2a78d6", "#eb6834"

D0, BETA, MPM = 1000.0, 2.0, 75.0
PEAK = D0 * ((BETA - 1) / (BETA + 1)) ** (1 / BETA)      # 최대 기울기 지점


def S(d):
    d = np.clip(np.asarray(d, float), 0, None)
    return 100.0 / (1.0 + (d / D0) ** BETA)


SITES = [("위례중앙푸르지오", 112.7), ("래미안위례", 298.1),
         ("플로리체 위례", 434.8), ("위례송파푸르지오", 723.6)]

XMAX = 2000
d = np.linspace(0, XMAX, 1200)

fig, (ax, ax2) = plt.subplots(
    2, 1, figsize=(11.5, 8.6), sharex=True,
    gridspec_kw={"height_ratios": [2.05, 1], "hspace": 0.16})
fig.patch.set_facecolor(SURFACE)

# ══ 위: 점수 곡선 ═══════════════════════════════════════════════
ax.set_facecolor(SURFACE)
ax.axvspan(0, 200, color=MUTED, alpha=0.10, lw=0)
ax.text(100, 6, "0~200m\n사실상 동일\n(3.8점 차)", ha="center", va="bottom",
        fontsize=8.5, color=MUTED, linespacing=1.5)

ax.plot(d, S(d), color=CURVE, lw=2.4, solid_capstyle="round", zorder=3)

# 반환점
ax.plot([0, D0], [50, 50], color=AXIS, lw=1, ls=(0, (4, 4)), zorder=1)
ax.plot([D0, D0], [0, 50], color=AXIS, lw=1, ls=(0, (4, 4)), zorder=1)
ax.plot([D0], [50], "o", ms=8, mfc=SURFACE, mec=CURVE, mew=2.2, zorder=4)
ax.annotate("반환점  1,000m = 50점\n(도보 13분)", xy=(D0, 50),
            xytext=(D0 + 90, 56), fontsize=9.5, color=INK2, linespacing=1.5)

# 최대 기울기 지점
ax.plot([PEAK, PEAK], [0, S(PEAK)], color=MARK, lw=1, ls=(0, (2, 3)),
        alpha=0.75, zorder=1)

# 위례 4개 단지
for name, dist in SITES:
    ax.plot([dist], [S(dist)], "o", ms=9, color=MARK,
            mec=SURFACE, mew=2, zorder=5)
    ax.annotate(f"{name}\n{dist:,.0f}m · {S(dist):.1f}점",
                xy=(dist, S(dist)), xytext=(dist + 42, S(dist) + 4.5),
                fontsize=9, color=INK, linespacing=1.45, zorder=6)

ax.set_ylim(0, 108)
ax.set_xlim(0, XMAX)
ax.set_ylabel("도보권 지수", fontsize=10.5, color=INK2)
ax.set_title("지하철역 도보권 지수 — 로그로지스틱  $d_0$=1,000m,  β=2.0  (앵커 없음)",
             fontsize=13.5, color=INK, pad=34, loc="left")
ax.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True)

# 위쪽 보조축 — 도보 분
axt = ax.secondary_xaxis("top", functions=(lambda x: x / MPM, lambda m: m * MPM))
axt.set_xlabel("도보 분  (보통 걸음 4.5km/h)", fontsize=9.5, color=MUTED, labelpad=6)
axt.tick_params(colors=MUTED, labelsize=9)
for s in axt.spines.values():
    s.set_color(AXIS)

# ══ 아래: 기울기 ════════════════════════════════════════════════
ax2.set_facecolor(SURFACE)
slope = -(np.gradient(S(d), d)) * 100          # 100m 당 점수 하락

ax2.fill_between(d, 0, slope, color=CURVE, alpha=0.14, lw=0)
ax2.plot(d, slope, color=CURVE, lw=2.2, solid_capstyle="round", zorder=3)

peak_v = -(S(PEAK + 0.5) - S(PEAK - 0.5)) * 100
ax2.plot([PEAK], [peak_v], "o", ms=9, color=MARK, mec=SURFACE, mew=2, zorder=5)
ax2.annotate(f"가장 가파른 지점\n{PEAK:,.0f}m · 100m 당 {peak_v:.1f}점",
             xy=(PEAK, peak_v), xytext=(PEAK + 175, peak_v + 1.05),
             fontsize=9.5, color=INK, linespacing=1.5,
             arrowprops=dict(arrowstyle="-", color=AXIS, lw=1,
                             shrinkA=2, shrinkB=6))

for name, dist in SITES:
    v = -(S(dist + 0.5) - S(dist - 0.5)) * 100
    ax2.plot([dist], [v], "o", ms=6.5, color=MARK, mec=SURFACE, mew=1.6,
             alpha=0.85, zorder=5)

ax2.axvspan(0, 200, color=MUTED, alpha=0.10, lw=0)
ax2.set_ylim(0, 8.8)
ax2.set_xlim(0, XMAX)
ax2.set_xlabel("대지 경계 → 목적지 거리 (m)", fontsize=10.5, color=INK2)
ax2.set_ylabel("100m 당 점수 하락", fontsize=10.5, color=INK2)
ax2.set_title("얼마나 가파른가 — 구간별 변별력", fontsize=11, color=INK2,
              loc="left", pad=8)
ax2.grid(True, color=GRID, lw=0.8)
ax2.set_axisbelow(True)

for a in (ax, ax2):
    a.tick_params(colors=MUTED, labelsize=9.5)
    for side in ("top", "right"):
        a.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        a.spines[side].set_color(AXIS)

fig.tight_layout()
fig.savefig(f"{PROJ}/도보권지수_확정곡선.png",
            dpi=150, facecolor=SURFACE, bbox_inches="tight")
print("저장 완료: 도보권지수_확정곡선.png")
print(f"최대 기울기 지점 {PEAK:.0f}m, 100m당 {peak_v:.2f}점")
