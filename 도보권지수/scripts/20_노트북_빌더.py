"""도보권지수_분석.ipynb 생성 스크립트."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json

C = []


def md(s):
    C.append(("markdown", s.strip("\n")))


def code(s):
    C.append(("code", s.strip("\n")))


# ────────────────────────────────────────────────────────────────
md(r'''
# 도보권 지수 (Walkability Index) — 정의 및 테스트

정의와 논의 배경은 **[`도보권지수_설계노트.md`](도보권지수_설계노트.md)** 에 있습니다.
이 노트북은 그 정의를 **코드로 옮기고 값이 말이 되는지 확인하는** 용도입니다.

## 이 노트북이 계산하는 것

```
WI(대지, 목적지) = S( d_eff(대지, 목적지) )
```

- **단위는 (대지, 목적지) 한 쌍**입니다. 여러 POI 를 합산한 종합 점수는 만들지 않습니다.
- `S` — 거리를 0~100 으로 바꾸는 **감쇠함수**. `d=0 → 100`, `d→∞ → 0`.
- `d_eff` — **유효 보행거리**. 지금(L1)은 대지 경계 기준 직선거리를 그대로 씁니다.

## 현재 단계 = L1

| | 입력 거리 | 필요한 것 | 상태 |
| --- | --- | --- | --- |
| L0 | 중심점 직선거리 | 없음 | — |
| **L1** | **대지 경계 직선거리** | 카카오 + VWorld 키 | **← 지금 여기** |
| L2 | T맵 실경로 거리 | T맵 앱키 | 미발급 |
| L3 | 유효거리 (페널티 반영) | `turnType` 파싱 | — |

L2·L3 으로 올라갈 때 **`effective_distance()` 하나만 갈아끼우면** 되도록 분리해 두었습니다.
감쇠함수와 파라미터는 그대로 둡니다.

> **주의** — 아래 파라미터(`d0`, `k`)는 전부 **근거 없는 임시 초기값**입니다.
> 이 값을 정하는 것이 앞으로의 과제이지, 지금 값이 맞다는 뜻이 아닙니다.
''')

# ── 0. 준비 ─────────────────────────────────────────────────────
md(r'''
## 0. 준비

**1절(감쇠함수)과 2절(파라미터)은 API 키 없이도 그대로 돌아갑니다.**
키가 필요한 것은 3절부터입니다.
''')

code(r'''
# 최초 1회만 실행
# !pip install requests python-dotenv pandas numpy matplotlib folium shapely pyproj
''')

code(r'''
import math
import os

import folium
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

KAKAO_KEY = os.getenv("KAKAO_REST_API_KEY")
VWORLD_KEY = os.getenv("VWORLD_API_KEY")
VWORLD_DOMAIN = os.getenv("VWORLD_DOMAIN", "https://devprofessional.xyz")

KAKAO_BASE = "https://dapi.kakao.com/v2/local"
KAKAO_HEADERS = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
VWORLD_URL = "https://api.vworld.kr/req/data"

# 그래프 한글 깨짐 방지
for _cand in ["AppleGothic", "Malgun Gothic", "NanumGothic", "AppleSDGothicNeo-Regular"]:
    if any(f.name == _cand for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = _cand
        break
plt.rcParams["axes.unicode_minus"] = False

print("카카오 키:", bool(KAKAO_KEY))
print("VWorld 키:", bool(VWORLD_KEY))
print("그래프 폰트:", plt.rcParams["font.family"])
''')

# ── 1. 감쇠함수 ──────────────────────────────────────────────────
md(r'''
## 1. 감쇠함수 — 지수의 심장

거리를 점수로 바꾸는 함수입니다. **여기가 지수의 성격을 전부 결정합니다.**

### 왜 로지스틱인가

`0m → 100`, `∞ → 0` 을 만족하는 함수는 여럿인데, 모양에 따라 뜻이 달라집니다.

| 형태 | 문제 |
| --- | --- |
| 선형 `100(1 − d/D)` | 30m 와 100m 차이를 크게 봄. 실제로는 둘 다 "바로 앞"이라 체감차가 없음 |
| 지수감쇠 `100·e^(−kd)` | `d=0` 에서 기울기 최대. 위와 같은 문제 |
| **로지스틱** | **근거리 포화 O, 임계 부근 급락 O, 원거리 수렴 O** |

사람의 "걸을까 말까"는 실제로 **임계반응**입니다.
300m 와 700m 는 결정이 갈리지만, 50m 와 120m 는 똑같이 "바로 앞"이고
1.5km 와 2.5km 는 똑같이 "안 걸음". 이 모양이 로지스틱입니다.

### 식

$$ S(d) = 100 \cdot \frac{1/(1+e^{k(d-d_0)})}{1/(1+e^{k d_0})} $$

분모는 `S(0)=100` 을 정확히 맞추기 위한 정규화입니다.

- **`d0`** — 반환점. 지수가 **50점**이 되는 거리(m)
- **`k`** — 임계의 날카로움. 클수록 `d0` 부근에서 급하게 떨어짐
''')

md(r'''
### 대안 — 로그로지스틱 (power decay)

첫 실측에서 로지스틱의 문제가 드러났습니다. **꼬리가 지수적으로 얇아서, 근거리를 벌리려고
`d0` 를 줄이면 원거리가 통째로 뭉개집니다.** 해상도의 총량이 고정된 채
어느 구간에 몰아줄지만 정하는 구조인 셈입니다. (자세한 내용은 설계노트 9-2 (1))

$$ S(d) = \frac{100}{1 + (d/d_0)^{\beta}} $$

- `S(0)=100`, `S(∞)=0` 을 **정규화 없이 자동으로** 만족합니다
- 꼬리가 **거듭제곱**이라 두껍습니다 — 근거리를 벌려도 원거리가 죽지 않습니다
- 접근성 연구의 표준 거리감쇠(gravity model 계열)라 **근거를 대기 쉽습니다**

`β` 가 `k` 자리를 대신하며, 클수록 임계가 날카로워집니다. (`β > 1` 이어야 근거리가 포화됩니다)

### 지수의 아래쪽 끝 — 6km 앵커

지금까지는 "거리가 무한대일 때 0점"으로 두었는데, 무한대는 설명할 수 없는 값입니다.
**사람이 빠른 걸음으로 한 시간을 걸으면 대략 6km 를 가므로, 6km 를 0점으로 고정**합니다.

한 시간 넘게 걸어야 하는 곳에 0.3점이니 0.001점이니 하는 값을 매기는 것은 의미 없는 정밀도입니다.
그 구간은 전부 "걸어서 못 간다"는 하나의 상태일 뿐입니다.

```
S(d) = 100 × ( f(d) − f(6000) ) / ( f(0) − f(6000) ),   d > 6000 이면 0
```

**중요한 것은 6km 를 경계조건으로만 쓴다는 점입니다.** 곡선의 모양은 여전히 `d0` 가 지배합니다.
만약 0~6km 를 균등하게 펴면(선형) 800m 에서 86.7점, 2km 에서 66.7점이 나와
**걸어 다닐 만한 거리 전체가 상위에 뭉쳐 버립니다.**
''')

code(r'''
# 6km 앵커는 검토했으나 채택하지 않았다 (설계노트 3-9).
# ZERO_AT 에 ZERO_AT_M 을 넣으면 "6km 에서 정확히 0점" 으로 동작한다.
ZERO_AT = None
ZERO_AT_M = 6000.0      # 빠른 걸음(6.0km/h) 1시간 = 6km. 앵커를 켤 때 쓰는 값.
WALK_SPEED_MPM = 75.0   # 보통 걸음(4.5km/h) = 분당 75m. 분 환산 '표시'에만 쓴다.


def _raw_logistic(d, d0=800.0, k=0.005):
    """로지스틱 원형. 꼬리가 지수적으로 얇다."""
    z = np.clip(k * (np.asarray(d, dtype=float) - d0), -700, 700)
    return 1.0 / (1.0 + np.exp(z))


def _raw_loglog(d, d0=500.0, beta=1.5):
    """로그로지스틱(power decay) 원형. 꼬리가 거듭제곱이라 두껍다."""
    d = np.clip(np.asarray(d, dtype=float), 0, None)
    return 1.0 / (1.0 + (d / d0) ** beta)


def _anchored(raw, d_m, zero_at, **kw):
    """원형 감쇠를 S(0)=100, S(zero_at)=0 이 되도록 재조정한다.

    zero_at 이 None 이면 재조정하지 않고 S(0)=100 만 맞춘다 (원래의 ∞→0 형태).
    zero_at 을 넘어가는 거리는 0 으로 자른다.
    """
    d = np.clip(np.asarray(d_m, dtype=float), 0, None)

    hi = float(raw(0.0, **kw))
    lo = float(raw(zero_at, **kw)) if zero_at else 0.0

    out = np.clip(100.0 * (raw(d, **kw) - lo) / (hi - lo), 0.0, 100.0)
    return out.item() if out.ndim == 0 else out


def walk_index(d_m, d0=800.0, k=0.005, zero_at=ZERO_AT):
    """로지스틱 도보권 지수.

        d0 : 반환점 — 지수가 50점 부근이 되는 거리(m)
        k  : 임계의 날카로움
    """
    return _anchored(_raw_logistic, d_m, zero_at, d0=d0, k=k)


def walk_index_ll(d_m, d0=1000.0, beta=2.0, zero_at=ZERO_AT):
    """로그로지스틱 도보권 지수.

        d0   : 반환점 — 지수가 50점이 되는 거리(m)
        beta : 임계의 날카로움 (1 보다 커야 근거리가 포화된다)
    """
    return _anchored(_raw_loglog, d_m, zero_at, d0=d0, beta=beta)


def to_minutes(d_m, mpm=WALK_SPEED_MPM):
    """거리(m)를 도보 분으로 환산한다. 표시용이며 지수 계산에는 쓰지 않는다."""
    return np.asarray(d_m, dtype=float) / mpm
''')

md(r'''
**6km 앵커가 값을 실제로 얼마나 바꾸는지** 먼저 확인합니다.
로지스틱은 꼬리가 워낙 얇아 6km 지점 값이 이미 사실상 0이라 **변화가 없어야** 정상입니다.
''')

code(r'''
CHK = [0, 100, 200, 400, 600, 800, 1000, 1500, 2000, 3000, 4000, 5000, 6000]


def anchor_effect(fn, label, **kw):
    """앵커 유무를 나란히 놓고 차이를 본다."""
    a = np.asarray(fn(CHK, zero_at=None, **kw), dtype=float)
    b = np.asarray(fn(CHK, zero_at=ZERO_AT_M, **kw), dtype=float)

    return pd.DataFrame({"앵커 없음 (∞→0)": a.round(2),
                         "6km 앵커": b.round(2),
                         "차이": (b - a).round(2)},
                        index=pd.Index(CHK, name=f"거리_m — {label}")).T


display(anchor_effect(walk_index, "로지스틱 d0=800 k=0.005 (현재)",
                      d0=800, k=0.005))
display(anchor_effect(walk_index_ll, "로그로지스틱 d0=500 β=1.5 (유력 후보)",
                      d0=500, beta=1.5))
display(anchor_effect(walk_index_ll, "로그로지스틱 d0=1500 β=1.5 (대형마트처럼 d0 가 큰 경우)",
                      d0=1500, beta=1.5))
''')

md(r'''
**읽는 법이 하나 있습니다.**

`차이` 행의 최댓값은 **"앵커가 없을 때 6km 에서 남아 있던 점수"와 정확히 같습니다.**
로그로지스틱 `d0=500 β=1.5` 는 6km 에서 2.35점이 남아 있었고, 차이도 −2.35 로 수렴합니다.

즉 **앵커를 넣어서 잃는 점수의 최대치 = 원래 6km 에 남아 있던 꼬리의 크기**입니다.
꼬리가 얇은 함수일수록 앵커가 공짜에 가깝고, 두꺼울수록 대가가 큽니다.
`d0=1500` 처럼 반환점을 멀리 잡으면 6km 에서 11.1점이 남아 있어 대가가 커집니다.
''')

md(r'''
### 1-1. 파라미터 읽는 법 — `d0`, `k`, `β` 가 무엇인가

전체 설명은 설계노트 3-8 절에 있습니다. 여기서는 코드를 읽는 데 필요한 만큼만 정리합니다.

#### `d0` 는 얼굴이 둘입니다

첫 번째 얼굴은 **지수가 50점이 되는 거리**입니다.
로그로지스틱은 `(d0/d0)^β = 1` 이므로 `β` 와 무관하게 정확히 50점이 나오고,
로지스틱은 정규화 때문에 50.92점이 나옵니다.

두 번째 얼굴이 중요한데, `d0` 는 **곡선이 가장 가파른 지점, 즉 해상도가 몰리는 곳**이기도 합니다.
지수가 거리 차이를 가장 잘 구분해 내는 구간이 그 주변입니다.

처음에 `d0=800` 을 고른 근거는 "도보 12분이 역세권 경계니까"였는데,
그것은 곧 **"800m 근처에서만 변별이 잘 된다"** 는 뜻이기도 했습니다.
위례 단지 세 곳이 113~435m 에 몰려 있었으니 전부 해상도가 없는 구간에 들어갔던 것입니다.

**그런데 두 함수에서 이 지점이 다릅니다.** 로지스틱은 좌우 대칭이라 `d0` 바로 그 자리가 가장 가파르지만,
로그로지스틱은 비대칭이라 **`d0` 보다 훨씬 앞**에서 가장 가파릅니다.
공식은 `d0 × ((β−1)/(β+1))^(1/β)` 이고, `β=1.5` 면 `d0 × 0.34` 입니다.
**이것이 로그로지스틱의 근거리 변별력이 좋은 진짜 이유입니다.**

#### `k` 와 `β` 는 "얼마나 칼같이 끊기는가"

작으면 완만하고, 크면 된다/안 된다에 가까운 계단이 됩니다.
`β=1` 은 근거리 포화가 없어(0m 에서 기울기 최대) 우리가 피하려던 문제가 생기므로
**`β` 는 반드시 1보다 커야 합니다.**

`β` 가 `k` 보다 나은 점이 하나 있습니다. **`β` 는 무차원입니다.**
`k` 는 단위가 `1/m` 이라 `d0` 를 바꾸면 같이 바꿔야 하고, 그래서 `k·d0` 를 계속 들고 다녀야 했습니다.
`β` 는 `d0` 를 바꿔도 모양이 그대로여서 두 파라미터가 서로 간섭하지 않습니다.

#### 두 함수의 근본 차이 — 뺄셈이냐 나눗셈이냐

```
로지스틱      :  e^( k · (d − d0) )      ←  d 와 d0 의 차이   (뺄셈)
로그로지스틱  :  ( d / d0 )^β            ←  d 와 d0 의 비율   (나눗셈)
```

로지스틱은 "반환점에서 몇 미터 떨어졌나"를 보고,
로그로지스틱은 "반환점의 몇 배인가"를 봅니다.

이름이 "로그"로지스틱인 이유도 문자 그대로입니다.
**거리에 로그를 씌운 뒤 로지스틱을 적용한 것과 완전히 같습니다.**

```
100 / (1 + (d/d0)^β)  ≡  100 / (1 + e^( β·(ln d − ln d0) ))
```

즉 다른 함수가 아니라 **같은 함수를 다른 축에서 보는 것**입니다.

그리고 사람의 거리 감각은 뺄셈보다 나눗셈에 가깝습니다.
100m 와 200m 의 차이는 크게 느껴지지만 1,000m 와 1,100m 는 거의 같게 느껴지고,
둘 다 절대량으로는 같은 100m 입니다. 이것이 베버-페히너 법칙입니다.
''')

code(r'''
# 위 설명을 코드로 확인합니다.
_g = np.linspace(1, 3000, 6000)

print("가장 가파른 지점 (해상도가 몰리는 곳)")
for label, s in [
    ("로지스틱   d0=500 k=0.008", walk_index(_g, 500, 0.008)),
    ("로그로지스틱 d0=500 β=1.5",  walk_index_ll(_g, 500, 1.5)),
    ("로그로지스틱 d0=500 β=2.0",  walk_index_ll(_g, 500, 2.0)),
    ("로그로지스틱 d0=500 β=4.0",  walk_index_ll(_g, 500, 4.0)),
]:
    at = _g[np.argmax(np.abs(np.gradient(s, _g)))]
    print(f"  {label:24} → {at:6.0f}m   (= d0 × {at / 500:.2f})")

print("\n'로그'로지스틱 = ln(d) 에 로지스틱  — 두 식이 같은지 확인")
_d = np.array([100, 250, 500, 1000, 2000], dtype=float)
_direct = 100 / (1 + (_d / 500) ** 1.5)
_vialog = 100 / (1 + np.exp(1.5 * (np.log(_d) - np.log(500))))
print(f"  최대 차이: {np.abs(_direct - _vialog).max():.2e}")

print("\n꼬리 — 멀어질 때 얼마나 빨리 죽는가 (d0=500, 앵커 없음)")
_far = [500, 1000, 1500, 2000, 4000]
display(pd.DataFrame({
    "로지스틱 k=0.008": walk_index(_far, 500, 0.008, zero_at=None).round(4),
    "로그로지스틱 β=1.5": walk_index_ll(_far, 500, 1.5, zero_at=None).round(4),
}, index=pd.Index(_far, name="거리_m")).T)
''')

md(r'''
`β=1.5` 일 때 최대 기울기가 **171m** 로 `d0` 의 3분의 1 지점에 온다는 것이 핵심입니다.
반환점을 500m 에 두고도 해상도는 171m 근처에 몰리므로, 가까운 단지들을 벌려 놓을 수 있습니다.

꼬리 표를 보면 2km 지점에서 로지스틱은 **0.0006점**, 로그로지스틱은 **11.1점**입니다.
5-6 절에서 로지스틱 `d0=500` 을 쓰면 위례송파푸르지오가 14.6점으로 폭락하는 것이 이 꼬리 때문입니다.

### 1-2. 거리별 점수표

`d0=800m, k=0.005` 로 두면 이렇게 나옵니다.
숫자를 보고 **"이 거리에 이 점수가 맞나"** 를 먼저 판단해 보십시오.
''')

code(r'''
DIST_GRID = [0, 100, 200, 300, 400, 500, 600, 800, 1000, 1200, 1600, 2000]

tbl = pd.DataFrame(
    {"지수": walk_index(DIST_GRID, d0=800, k=0.005).round(1)},
    index=pd.Index(DIST_GRID, name="거리_m"),
)
tbl.T
''')

md(r'''
### 1-3. 모양 확인

- **왼쪽** — `d0` 를 바꾸면 곡선이 **거리축으로 스케일**됩니다. (`k` 를 `4/d0` 로 함께 조정)
- **오른쪽** — `k` 를 바꾸면 **임계의 급함**만 달라집니다. `k` 가 크면 "된다/안 된다"에 가까운 계단이 되고,
  작으면 완만한 선형에 가까워집니다.

점선은 반환점(50점)입니다.
''')

code(r'''
d = np.linspace(0, 2500, 600)
fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))

for d0 in [300, 500, 800, 1500]:
    axes[0].plot(d, walk_index(d, d0=d0, k=4.0 / d0), label=f"d0={d0}m")
axes[0].set_title("로지스틱 — 반환점 d0 (k·d0=4 고정)")

for k in [0.002, 0.005, 0.010, 0.030]:
    axes[1].plot(d, walk_index(d, d0=800, k=k), label=f"k={k}")
axes[1].axvline(800, color="gray", lw=0.8, ls=":")
axes[1].set_title("로지스틱 — 날카로움 k (d0=800m 고정)")

# 두 함수형을 같은 반환점에서 직접 비교
axes[2].plot(d, walk_index(d, d0=500, k=0.008), lw=2, label="로지스틱 d0=500")
axes[2].plot(d, walk_index_ll(d, d0=500, beta=1.5), lw=2, ls="--",
             label="로그로지스틱 d0=500 β=1.5")
axes[2].axvline(500, color="gray", lw=0.8, ls=":")
axes[2].set_title("같은 d0 에서 두 함수형 비교")

for ax in axes:
    ax.axhline(50, color="gray", lw=0.8, ls=":")
    ax.set_xlabel("유효 보행거리 (m)")
    ax.set_ylabel("도보권 지수")
    ax.set_ylim(0, 102)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)

plt.tight_layout()
plt.show()
''')

md(r'''
오른쪽 패널이 핵심입니다. 반환점(`d0=500m`)은 같은데 **양쪽 끝의 거동이 다릅니다.**
로그로지스틱은 근거리에서 더 빨리 떨어져 변별력을 만들고, 원거리에서는 더 천천히 떨어져
먼 곳을 완전히 죽이지 않습니다. 로지스틱은 그 반대입니다.
''')

md(r'''
### 1-4. `k·d0` 는 무엇을 뜻하는가

`k·d0` 를 일정하게 두면 **모든 시설이 같은 모양**이 되고 거리축만 늘었다 줄었다 합니다.
즉 `k·d0` 는 **"도보권 경계가 얼마나 칼같은가"** 를 나타내는 하나의 숫자입니다.

| `k·d0` | 성격 | `d0` 의 절반 지점(=`0.5·d0`) 점수 |
| --- | --- | --- |
| 2 | 완만 — 거리에 비례하는 느낌 | 낮음 |
| **4** | **중간 — 현재 기본값** | 약 88 |
| 8 | 날카로움 — 사실상 O/X | 매우 높음 |

아래에서 확인해 보십시오.
''')

code(r'''
rows = []
for kd0 in [2, 3, 4, 6, 8]:
    d0 = 800
    s = walk_index([0, 200, 400, 600, 800, 1000, 1200], d0=d0, k=kd0 / d0)
    rows.append(pd.Series(s.round(1), name=f"k·d0={kd0}",
                          index=[0, 200, 400, 600, 800, 1000, 1200]))

shape_tbl = pd.DataFrame(rows)
shape_tbl.columns.name = "거리_m"
shape_tbl
''')

# ── 2. 파라미터 ──────────────────────────────────────────────────
md(r'''
## 2. 시설별 파라미터 — 이것이 곧 "정의"

`d0` 와 `k` 를 시설마다 다르게 둡니다. **편의점 300m 와 대형마트 1,500m 를 같은 잣대로 잴 수 없기 때문**입니다.

> ### ⚠ 아래 값은 전부 임시 초기값입니다
> 근거가 없습니다. **이 딕셔너리를 확정하는 것이 이 프로젝트의 핵심 과제**입니다.
> 값이 바뀌면 지수가 통째로 바뀝니다. 다른 코드는 건드릴 필요 없이 여기만 고치십시오.
''')

code(r'''
WALK_PARAMS = {
    # ✅ 확정 (2026-08-17) — 근거는 설계노트 9-6
    "지하철역":        {"d0": 1000, "beta": 2.0},

    # ⚠ 미확정 — 아래는 전부 임시값이다.
    #    지하철역처럼 "몇 m 를 50점으로 볼 것인가" 를 시설마다 따로 판단해야 한다.
    #    지금 값은 이전 d0 를 같은 비율(약 1.2배)로 올린 자리표시용이다.
    "초등학교":        {"d0": 600,  "beta": 2.0},
    "어린이집·유치원": {"d0": 500,  "beta": 2.0},
    "편의점":          {"d0": 350,  "beta": 2.0},
    "대형마트":        {"d0": 1800, "beta": 2.0},
    "병원":            {"d0": 1200, "beta": 2.0},
    "공원":            {"d0": 700,  "beta": 2.0},   # 카카오 카테고리 없음 → 키워드 검색 필요
}

DEFAULT_PARAM = {"d0": 1000, "beta": 2.0}

(pd.DataFrame(WALK_PARAMS).T
 .assign(**{"d0_도보분": lambda x: to_minutes(x["d0"]).round(1),
            "최대기울기_m": lambda x: (x["d0"] * ((x["beta"] - 1) / (x["beta"] + 1))
                                    ** (1 / x["beta"])).round(0)}))
''')

md(r'''
**`d0_도보분` 은 참고용으로 붙인 것입니다** (보통 걸음 4.5km/h = 분당 75m 기준).

파라미터를 정할 때 `"지하철역 반환점을 800m 로 할까"` 보다
`"지하철역 반환점을 10분으로 할까"` 가 훨씬 답하기 쉬운 질문입니다.
다만 **지수 계산 자체는 미터로 합니다.** 분으로 정의할지 미터로 정의할지는
설계노트 3-6 에서 다루며, **L2 로 올라갈 때 결정하면 됩니다** (L1 에서는 둘이 수학적으로 동등합니다).
''')

md(r'''
같은 거리라도 시설에 따라 점수가 어떻게 갈리는지 봅니다.
**200m 는 편의점에게는 평범하지만 대형마트에게는 만점에 가깝습니다.**
''')

code(r'''
grid = [100, 200, 300, 500, 800, 1200, 2000]

by_kind = pd.DataFrame(
    {kind: walk_index_ll(grid, **p).round(1) for kind, p in WALK_PARAMS.items()},
    index=pd.Index(grid, name="거리_m"),
).T
by_kind
''')

# ── 3. 거리 재기 ─────────────────────────────────────────────────
md(r'''
## 3. 거리 재기 (L1 — 대지 경계 직선거리)

여기부터 **카카오·VWorld 키가 필요합니다.**
함수는 `vworld_parcel_analysis.ipynb` 에서 가져와 그대로 씁니다.

### 왜 "대지 경계" 기준인가

보통 "역까지 300m"는 **단지 중심점**에서 잰 값입니다. 대지가 넓으면 중심점과 경계선의 차이가
수십~수백 m 납니다. 걷기 시작하는 곳은 중심점이 아니라 **경계(출입구 쪽)** 이므로
경계 기준이 실제에 가깝습니다.
''')

md(r'''
### 3-1. 카카오 — 주소 → 좌표, 주변 POI
''')

code(r'''
CATEGORY_GROUP = {
    "지하철역": "SW8", "학교": "SC4", "병원": "HP8", "대형마트": "MT1",
    "편의점": "CS2", "은행": "BK9", "공공기관": "PO3", "문화시설": "CT1",
    "어린이집·유치원": "PS3", "주차장": "PK6", "약국": "PM9", "카페": "CE7",
}


def geocode(address):
    """주소를 좌표로 변환한다."""
    res = requests.get(f"{KAKAO_BASE}/search/address.json",
                       headers=KAKAO_HEADERS, params={"query": address, "size": 1})
    docs = res.json()["documents"]
    if not docs:
        return None

    d = docs[0]
    road = d.get("road_address") or {}
    return {"input": address, "lng": float(d["x"]), "lat": float(d["y"]),
            "road_address": road.get("address_name", ""),
            "address_name": d.get("address_name", "")}


def search_category(code, lng, lat, radius=1500, max_results=45):
    """업종 코드로 주변 POI 를 모은다 (최대 45건)."""
    out = []
    for page in range(1, 4):
        res = requests.get(
            f"{KAKAO_BASE}/search/category.json",
            headers=KAKAO_HEADERS,
            params={"category_group_code": code, "x": lng, "y": lat,
                    "radius": radius, "page": page, "size": 15, "sort": "distance"},
        )
        body = res.json()
        out.extend(body["documents"])
        if body["meta"]["is_end"] or len(out) >= max_results:
            break

    return out[:max_results]


def search_keyword(query, lng=None, lat=None, radius=20000, size=5):
    """키워드로 장소를 찾는다. 좌표를 주면 가까운 순으로 정렬한다.

    '판교역' 처럼 목적지를 직접 지정할 때 쓴다 (지정 목적지 비교).
    """
    params = {"query": query, "size": size}
    if lng is not None:
        params.update({"x": lng, "y": lat, "radius": radius, "sort": "distance"})

    res = requests.get(f"{KAKAO_BASE}/search/keyword.json",
                       headers=KAKAO_HEADERS, params=params)
    res.raise_for_status()
    return res.json()["documents"]
''')

md(r'''
### 3-2. VWorld — 필지(대지) 경계
''')

code(r'''
def vworld_get_feature(data, geom_filter, crs="EPSG:4326", size=10, **extra):
    """VWorld 데이터 API GetFeature 호출. features 리스트를 반환한다."""
    if not VWORLD_KEY:
        raise ValueError("VWORLD_API_KEY 가 없습니다. .env 를 확인하세요.")

    params = {
        "service": "data", "request": "GetFeature", "data": data,
        "key": VWORLD_KEY, "domain": VWORLD_DOMAIN,
        "geomFilter": geom_filter, "crs": crs,
        "format": "json", "size": size, **extra,
    }
    res = requests.get(VWORLD_URL, params=params, timeout=10)
    res.raise_for_status()

    body = res.json()
    body = body.get("response", body)

    status = body.get("status")
    if status != "OK":
        raise RuntimeError(f"VWorld 응답 status={status} / {body.get('error')}")

    result = body.get("result") or {}
    fc = result.get("featureCollection", result)
    return fc.get("features", [])


def get_parcel(lng, lat, size=10):
    """좌표가 놓인 필지 하나를 반환한다. 없으면 None."""
    feats = vworld_get_feature("LP_PA_CBND_BUBUN", f"POINT({lng} {lat})", size=size)
    if not feats:
        return None

    from shapely.geometry import Point, shape

    pt = Point(lng, lat)
    for f in feats:
        if shape(f["geometry"]).contains(pt):
            return f

    print(f"경고: {len(feats)}건 중 점을 포함하는 필지가 없어 첫 번째를 사용합니다.")
    return feats[0]
''')

md(r'''
### 3-3. 경계선 최소거리 (AEQD 투영)

경위도 상태로는 미터 거리를 잴 수 없으므로, 필지 중심을 원점으로 하는
**AEQD(정거방위도법)** 로 투영한 뒤 계산합니다.
''')

code(r'''
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform as sh_transform


def make_projector(lat0, lng0):
    """필지 중심을 원점으로 하는 미터 좌표계 변환 함수 (정방향, 역방향)."""
    aeqd = f"+proj=aeqd +lat_0={lat0} +lon_0={lng0} +datum=WGS84 +units=m +no_defs"
    fwd = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    inv = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True)
    return (lambda g: sh_transform(fwd.transform, g),
            lambda g: sh_transform(inv.transform, g))


def analyze_shapely(parcel_geojson, pois):
    """필지 경계에서 각 POI 까지의 최소거리를 구한다."""
    poly_ll = shape(parcel_geojson)
    c = poly_ll.centroid
    to_m, to_ll = make_projector(c.y, c.x)

    poly = to_m(poly_ll)
    boundary = poly.boundary

    rows = []
    for p in pois:
        pt_ll = Point(float(p["x"]), float(p["y"]))
        pt = to_m(pt_ll)

        near, _ = nearest_points(boundary, pt)
        near_ll = to_ll(near)

        rows.append({
            "name": p["place_name"],
            "category": p.get("category_name", "").split(" > ")[-1],
            "boundary_m": boundary.distance(pt),
            "center_m": poly.centroid.distance(pt),
            "inside": poly.contains(pt),
            "poi_lng": pt_ll.x, "poi_lat": pt_ll.y,
            "near_lng": near_ll.x, "near_lat": near_ll.y,
        })

    df = pd.DataFrame(rows).sort_values("boundary_m").reset_index(drop=True)
    return df, {"area_m2": poly.area, "perimeter_m": poly.length,
                "centroid": (c.x, c.y)}
''')

md(r'''
### 3-4. 유효 보행거리 — **여기가 L2·L3 교체 지점**

지수 자체는 건드리지 않고 **입력 거리만 바꿔 끼우는** 구조입니다.

```
d_eff = d_기본 × 우회계수 + Σ(장애 요인의 미터 환산 페널티)
```

| 레벨 | `d_기본` | `detour` | `penalties_m` |
| --- | --- | --- | --- |
| **L1 (지금)** | 대지 경계 직선거리 | **1.0** | **0** |
| L2 | T맵 경로거리 | 1.0 (이미 반영됨) | 0 |
| L2′ | 대지 경계 직선거리 | 실측 우회계수 (1.2~1.5) | 0 |
| L3 | T맵 경로거리 | 1.0 | `turnType` 기반 페널티 |

`detour` 를 1.0 이 아닌 값으로 넣어보면 **"우회를 감안하면 점수가 얼마나 떨어지는가"**
를 지금 당장 감을 잡을 수 있습니다.
''')

code(r'''
def effective_distance(d_base_m, detour=1.0, penalties_m=0.0):
    """기본 거리를 유효 보행거리로 바꾼다.

        d_base_m    : L1 이면 대지 경계 직선거리, L2 이면 T맵 경로거리
        detour      : 우회계수. L1 직선거리에 1.2~1.5 를 곱해 실경로를 근사할 수 있다
        penalties_m : 횡단·계단·육교 등을 미터로 환산한 페널티 합 (L3)

    L2 / L3 으로 올라갈 때 **이 함수만 바꾸면** 된다. 감쇠함수와 파라미터는 그대로다.
    """
    return d_base_m * detour + penalties_m
''')

# ── 4. 지수 계산 ─────────────────────────────────────────────────
md(r'''
## 4. 지수 계산

설계노트 3-5 에 따라 **두 가지 비교를 분리**합니다.

| 함수 | 질문 | 용도 |
| --- | --- | --- |
| `wi_to_place()` | **지정 목적지** — 같은 X역에 대해 A vs B | 직주근접, 특정 학교 배정 |
| `wi_nearest()` | **최근접** — A의 최근접역 vs B의 최근접역 | 일상적 역세권 여부 |

그리고 설계노트 3-3 에 따라, 카테고리 안에 POI 가 여러 개여도 **최근접 하나만** 봅니다.
개수·노선 다양성은 도보권이 아니라 교통 편의성이라는 다른 축입니다.
''')

code(r'''
KIND_SOURCE = {
    "지하철역":        {"code": "SW8"},
    "초등학교":        {"code": "SC4", "contains": "초등학교"},
    "어린이집·유치원": {"code": "PS3"},
    "편의점":          {"code": "CS2"},
    "대형마트":        {"code": "MT1"},
    "병원":            {"code": "HP8"},
    # '공원' 은 카카오 카테고리 코드가 없다 → search_keyword("공원") 로 따로 처리해야 한다
}


def fetch_pois(kind, lng, lat, radius=2000):
    """종류 이름으로 주변 POI 를 가져온다. 필요하면 category_name 으로 한 번 더 거른다."""
    src = KIND_SOURCE.get(kind)
    if src is None:
        raise KeyError(f"'{kind}' 는 KIND_SOURCE 에 없습니다. search_keyword() 를 쓰세요.")

    pois = search_category(src["code"], lng, lat, radius=radius)
    if "contains" in src:
        pois = [p for p in pois if src["contains"] in p.get("category_name", "")]
    return pois


def walk_table(parcel_geojson, pois, kind, detour=1.0, penalties_m=0.0):
    """필지 경계 ↔ POI 거리표에 도보권 지수를 붙인다."""
    df, info = analyze_shapely(parcel_geojson, pois)
    if df.empty:
        return df, info

    p = WALK_PARAMS.get(kind, DEFAULT_PARAM)
    df["d_eff_m"] = effective_distance(df["boundary_m"], detour, penalties_m)
    df["지수"] = walk_index_ll(df["d_eff_m"].to_numpy(), **p).round(1)
    df["기준"] = kind
    df["d0"] = p["d0"]

    return df.sort_values("d_eff_m").reset_index(drop=True), info
''')

code(r'''
def wi_to_place(parcel_geojson, center, query, kind, detour=1.0, penalties_m=0.0):
    """지정 목적지 하나에 대한 도보권 지수. (예: '판교역')"""
    pois = search_keyword(query, center["lng"], center["lat"], radius=20000, size=5)
    if not pois:
        raise ValueError(f"'{query}' 검색 결과가 없습니다.")

    df, _ = walk_table(parcel_geojson, pois[:1], kind, detour, penalties_m)
    return df


def wi_nearest(parcel_geojson, center, kinds, radius=2000, detour=1.0, penalties_m=0.0):
    """종류별 '가장 가까운 한 곳' 기준 도보권 지수 요약."""
    rows = []

    for kind in kinds:
        pois = fetch_pois(kind, center["lng"], center["lat"], radius=radius)
        if not pois:
            rows.append({"기준": kind, "대상": f"(반경 {radius}m 내 없음)"})
            continue

        df, _ = walk_table(parcel_geojson, pois, kind, detour, penalties_m)
        r = df.iloc[0]
        rows.append({
            "기준": kind, "대상": r["name"],
            "경계_직선_m": round(r["boundary_m"], 1),
            "중심_직선_m": round(r["center_m"], 1),
            "d_eff_m": round(r["d_eff_m"], 1),
            "d0": int(r["d0"]), "지수": r["지수"],
        })

    return pd.DataFrame(rows)
''')

# ── 5. 다지점 비교 도구 ──────────────────────────────────────────
md(r'''
### 4-1. 지정 목적지가 POI 가 아니라 **주소**일 때

`wi_to_place()` 는 카카오 키워드 검색으로 목적지를 찾습니다.
그런데 **아직 개통하지 않은 역**처럼 POI 가 없는 목적지는 검색되지 않습니다.
이때는 **주소를 지오코딩해서 좌표로 직접 지정**해야 합니다.

또 설계노트 3-4 에서 짚은 **접근점 대칭** 문제 — 출발지만 경계로 잡고
도착지는 점으로 두면 비대칭입니다. 목적지도 필지가 있으면 **경계 대 경계**로 재는 함수를 함께 둡니다.
''')

code(r'''
def parcel_of(address):
    """주소 → (site, parcel). 둘 중 하나라도 실패하면 예외를 던진다."""
    site = geocode(address)
    if site is None:
        raise ValueError(f"주소를 찾지 못했습니다: {address}")

    parcel = get_parcel(site["lng"], site["lat"])
    if parcel is None:
        raise ValueError(f"필지를 찾지 못했습니다: {address}")

    return site, parcel


def parcel_area_m2(parcel):
    """필지 면적(m2)."""
    poly_ll = shape(parcel["geometry"])
    to_m, _ = make_projector(poly_ll.centroid.y, poly_ll.centroid.x)
    return to_m(poly_ll).area


def measure(parcel, tgt_lng, tgt_lat, tgt_parcel=None):
    """대지 ↔ 목적지 거리를 세 가지로 잰다.

        center_m  : 대지 중심점 → 목적지 점      (흔히 쓰는 방식, 비교용)
        boundary_m: 대지 경계   → 목적지 점      (L1 의 기본값)
        b2b_m     : 대지 경계   → 목적지 필지 경계 (접근점 대칭, 목적지 필지가 있을 때만)

    경계선상의 최근접점(near_lng, near_lat)도 함께 준다 — 지도 검증용.
    """
    poly_ll = shape(parcel["geometry"])
    c = poly_ll.centroid
    to_m, to_ll = make_projector(c.y, c.x)

    poly = to_m(poly_ll)
    tgt_pt = to_m(Point(tgt_lng, tgt_lat))
    near, _ = nearest_points(poly.boundary, tgt_pt)
    near_ll = to_ll(near)

    out = {
        "center_m": poly.centroid.distance(tgt_pt),
        "boundary_m": poly.boundary.distance(tgt_pt),
        "b2b_m": np.nan,
        "near_lng": near_ll.x, "near_lat": near_ll.y,
    }
    if tgt_parcel is not None:
        out["b2b_m"] = poly.boundary.distance(to_m(shape(tgt_parcel["geometry"])).boundary)

    return out
''')

md(r'''
---

# 5. 테스트 — 위례 4개 단지 × 위례중앙역

**위례중앙역은 아직 개통하지 않았습니다.** 그래서 POI 검색으로는 잡히지 않습니다.
가장 가까운 건물(**경기 성남시 수정구 창곡동 506**)을 역 위치로 **가정**하고 진행합니다.

> 이 가정 때문에 절대값은 실제 역 출입구 기준과 다를 수 있습니다.
> 다만 **4개 단지 모두에 같은 가정이 적용되므로 상대 비교는 유효**합니다.

이번에는 **지하철역 하나만** 봅니다. 여러 시설을 합치지 않습니다 (설계노트 2-1).
''')

code(r'''
SITES = [
    ("위례송파푸르지오", "서울 송파구 장지동 878"),
    ("위례중앙푸르지오", "서울 송파구 장지동 897"),
    ("래미안위례",       "경기 성남시 수정구 창곡동 528"),
    ("플로리체 위례",    "경기 하남시 학암동 671"),
]

TARGET_NAME = "위례중앙역(가정)"
TARGET_ADDR = "경기 성남시 수정구 창곡동 506"
KIND = "지하철역"

tgt_site, tgt_parcel = parcel_of(TARGET_ADDR)

print(f"{TARGET_NAME}")
print(f"  지번  : {tgt_site['address_name']}")
print(f"  도로명: {tgt_site['road_address']}")
print(f"  좌표  : {tgt_site['lng']:.6f}, {tgt_site['lat']:.6f}")
print(f"  필지  : {parcel_area_m2(tgt_parcel):,.0f} m2")
''')

md(r'''
### 5-1. 단지별 필지 조회 및 거리

**면적을 반드시 확인하십시오.** 아파트 단지인데 면적이 수백 m2 로 나오면
단지 전체가 아니라 일부 필지만 잡힌 것이라 거리가 틀어집니다.
''')

code(r'''
parcels, rows = {}, []

for name, addr in SITES:
    site, parcel = parcel_of(addr)
    parcels[name] = (site, parcel)

    d = measure(parcel, tgt_site["lng"], tgt_site["lat"], tgt_parcel)
    rows.append({"단지": name, "주소": addr,
                 "면적_m2": round(parcel_area_m2(parcel)),
                 "중심→역_m": round(d["center_m"], 1),
                 "경계→역_m": round(d["boundary_m"], 1),
                 "경계→역경계_m": round(d["b2b_m"], 1),
                 "near_lng": d["near_lng"], "near_lat": d["near_lat"]})

df = pd.DataFrame(rows)
df[["단지", "면적_m2", "중심→역_m", "경계→역_m", "경계→역경계_m"]]
''')

md(r'''
### 5-2. 도보권 지수

`경계→역_m` 을 유효 보행거리로 쓰고(L1, `detour=1.0`), 지하철역 파라미터를 적용합니다.

`경계보정_점` = 경계 기준 지수 − 중심 기준 지수.
**중심점 기준은 거리를 과대평가하므로 점수를 깎습니다.** 대지가 넓을수록 이 값이 커집니다.
''')

code(r'''
p = WALK_PARAMS[KIND]

df["d_eff_m"] = effective_distance(df["경계→역_m"])
df["지수"] = walk_index_ll(df["d_eff_m"].to_numpy(), **p).round(1)
df["중심기준_지수"] = walk_index_ll(df["중심→역_m"].to_numpy(), **p).round(1)
df["경계보정_점"] = (df["지수"] - df["중심기준_지수"]).round(1)

main = (df[["단지", "면적_m2", "중심→역_m", "경계→역_m", "경계→역경계_m",
            "지수", "중심기준_지수", "경계보정_점"]]
        .sort_values("지수", ascending=False).reset_index(drop=True))
main
''')

md(r'''
### 5-3. 상대지수 — 어느 단지를 100 으로 둘 것인가

설계노트 2-3 대로, **절대점수에서 상대지수를 유도**합니다.
열이 기준 단지(=100), 행이 비교 대상입니다. 분양가 비교표에 바로 쓰는 형태입니다.
''')

code(r'''
rel = df.set_index("단지")["지수"]

rel_tbl = pd.DataFrame({base: (rel / rel[base] * 100).round(1) for base in rel.index})
rel_tbl.index.name = "대상 \\ 기준(=100)"
rel_tbl
''')

md(r'''
### 5-4. 우회계수 민감도 — L1 을 얼마나 믿을 수 있는가

직선거리는 실제 보행거리보다 짧습니다. 도시부 우회계수는 보통 **1.2~1.5** 입니다.
T맵 키가 없는 지금, **계수를 곱해보는 것만으로 L2 의 영향을 미리 가늠**할 수 있습니다.

**낙폭이 큰 단지일수록 L1 점수를 믿기 어렵습니다.**
''')

code(r'''
sens = df[["단지", "경계→역_m"]].copy()

for r in [1.0, 1.2, 1.35, 1.5]:
    sens[f"×{r}"] = walk_index_ll(
        effective_distance(df["경계→역_m"].to_numpy(), detour=r), **p).round(1)

sens["낙폭"] = (sens["×1.0"] - sens["×1.5"]).round(1)
sens.sort_values("낙폭", ascending=False).reset_index(drop=True)
''')

md(r'''
### 5-5. 순위는 흔들리는가

절대점수가 흔들려도 **순위가 유지된다면 상대 비교는 여전히 쓸 수 있습니다.**
분양가 비교표 용도에서는 이게 절대점수의 정확도보다 중요합니다.
''')

code(r'''
for r in [1.0, 1.2, 1.35, 1.5]:
    order = sens.sort_values(f"×{r}", ascending=False)["단지"].tolist()
    print(f"×{r:<5} : {'  >  '.join(order)}")
''')

md(r'''
### 5-6. 감쇠함수 후보 비교 — **여기서 고르십시오**

첫 실측에서 드러난 가장 큰 문제는 **근거리 변별력이 없다**는 것이었습니다.
상위 세 단지가 87.7~98.7 에 몰려 사실상 구분이 되지 않았습니다.

아래 표의 **`상위3_폭`** 이 그 문제를 재는 지표입니다.
위례중앙푸르지오(113m)와 플로리체 위례(435m)의 점수 차이이며, **클수록 근거리 변별력이 좋습니다.**
동시에 **`위례송파` 열이 너무 낮아지지 않는지**도 함께 봐야 합니다 —
724m 를 걷는 것이 몇 점짜리인지는 별개의 판단입니다.

두 지표는 서로 당깁니다. 어디서 타협할지가 곧 함수 선택입니다.
''')

code(r'''
CANDIDATES = [
    ("로지스틱  d0=800 k=0.005 (현재)", lambda x: walk_index(x, 800, 0.005)),
    ("로지스틱  d0=600 k=0.0067",       lambda x: walk_index(x, 600, 4 / 600)),
    ("로지스틱  d0=500 k=0.008",        lambda x: walk_index(x, 500, 0.008)),
    ("로그로지스틱 d0=800 β=2.0",       lambda x: walk_index_ll(x, 800, 2.0)),
    ("로그로지스틱 d0=600 β=1.8",       lambda x: walk_index_ll(x, 600, 1.8)),
    ("로그로지스틱 d0=500 β=1.5",       lambda x: walk_index_ll(x, 500, 1.5)),
    ("★ 로그로지스틱 d0=1000 β=2.0 (확정)", lambda x: walk_index_ll(x, 1000, 2.0)),
]

_d = df.set_index("단지")["경계→역_m"].reindex(
    ["위례중앙푸르지오", "래미안위례", "플로리체 위례", "위례송파푸르지오"])

cmp_rows = []
for label, fn in CANDIDATES:
    s = np.asarray(fn(_d.to_numpy()), dtype=float)
    cmp_rows.append({"함수": label,
                     **{n: round(float(v), 1) for n, v in zip(_d.index, s)},
                     "상위3_폭": round(float(s[0] - s[2]), 1),
                     "전체_폭": round(float(s[0] - s[3]), 1)})

cmp_fn = pd.DataFrame(cmp_rows)
cmp_fn
''')

md(r'''
같은 내용을 곡선으로 봅니다. 세로 점선이 실제 네 단지의 위치입니다.
**점선들이 곡선의 가파른 부분에 걸쳐 있어야 변별이 됩니다.**
현재 함수(맨 위 실선)는 앞의 세 점선이 전부 평평한 꼭대기에 놓여 있습니다.
''')

code(r'''
d = np.linspace(0, 1600, 700)
fig, ax = plt.subplots(figsize=(11, 5.5))

for i, (label, fn) in enumerate(CANDIDATES):
    style = "-" if "로지스틱 " in label[:6] else "--"
    ax.plot(d, fn(d), style, lw=2.4 if i == 0 else 1.5,
            alpha=1.0 if i == 0 else 0.75, label=label)

for name, dist_m in _d.items():
    ax.axvline(dist_m, color="#555", lw=0.9, ls=":")
    ax.text(dist_m + 8, 3, f"{name}\n{dist_m:.0f}m", fontsize=8,
            rotation=90, va="bottom", color="#333")

ax.set_xlabel("대지 경계 → 역 거리 (m)")
ax.set_ylabel("도보권 지수")
ax.set_ylim(0, 102)
ax.grid(alpha=0.25)
ax.legend(fontsize=9, loc="upper right")
ax.set_title("감쇠함수 후보 × 위례 4개 단지")

plt.tight_layout()
plt.show()
''')

md(r'''
### 5-7. 참고 — 거리를 분으로 보면

지수 계산은 미터로 하지만, 판단할 때는 분이 편할 수 있어 함께 표기합니다.
(보통 걸음 4.5km/h 기준. 빠른 걸음 6.0km/h 로 보면 분 수가 약 1/1.33 로 줄어듭니다)
''')

code(r'''
minute_view = pd.DataFrame({
    "경계→역_m": _d.round(1),
    "도보_분(4.5km/h)": to_minutes(_d.to_numpy()).round(1),
    "도보_분(6.0km/h)": to_minutes(_d.to_numpy(), mpm=100.0).round(1),
    "확정_지수": np.asarray(walk_index_ll(_d.to_numpy(), **WALK_PARAMS[KIND])).round(1),
})
minute_view
''')

md(r'''
### 5-8. 확정안 곡선 — 얼마나 가파르게 떨어지는가

`d0=1000, β=2.0, 앵커 없음` 으로 확정한 곡선입니다.
**위 패널**은 점수, **아래 패널**은 그 기울기(100m 당 몇 점이 떨어지는가)입니다.
아래 패널이 곧 **구간별 변별력**입니다 — 높을수록 그 구간에서 거리 차이를 잘 구분합니다.
''')

code(r'''
_PAL = {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e",
        "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7",
        "curve": "#2a78d6", "mark": "#eb6834"}


def plot_curve(d0, beta, sites, xmax=2000, path=None):
    """감쇠 곡선과 그 기울기를 위아래로 그린다.

    sites : [(이름, 거리m), ...] — 곡선 위에 찍을 실제 대상지
    """
    P = _PAL
    peak = d0 * ((beta - 1) / (beta + 1)) ** (1 / beta)   # 최대 기울기 지점
    x = np.linspace(0, xmax, 1200)
    y = walk_index_ll(x, d0=d0, beta=beta)

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11.5, 8.6), sharex=True,
                                 gridspec_kw={"height_ratios": [2.05, 1],
                                              "hspace": 0.16})
    fig.patch.set_facecolor(P["surface"])

    # 위 — 점수 곡선
    a1.axvspan(0, 200, color=P["muted"], alpha=0.10, lw=0)
    a1.plot(x, y, color=P["curve"], lw=2.4, solid_capstyle="round", zorder=3)

    a1.plot([0, d0], [50, 50], color=P["axis"], lw=1, ls=(0, (4, 4)), zorder=1)
    a1.plot([d0, d0], [0, 50], color=P["axis"], lw=1, ls=(0, (4, 4)), zorder=1)
    a1.plot([d0], [50], "o", ms=8, mfc=P["surface"], mec=P["curve"], mew=2.2, zorder=4)
    a1.annotate(f"반환점  {d0:,.0f}m = 50점\n(도보 {to_minutes(d0):.0f}분)",
                xy=(d0, 50), xytext=(d0 + 90, 56),
                fontsize=9.5, color=P["ink2"], linespacing=1.5)
    a1.plot([peak, peak], [0, walk_index_ll(peak, d0=d0, beta=beta)],
            color=P["mark"], lw=1, ls=(0, (2, 3)), alpha=0.75, zorder=1)

    for name, dist in sites:
        s = walk_index_ll(dist, d0=d0, beta=beta)
        a1.plot([dist], [s], "o", ms=9, color=P["mark"],
                mec=P["surface"], mew=2, zorder=5)
        a1.annotate(f"{name}\n{dist:,.0f}m · {s:.1f}점", xy=(dist, s),
                    xytext=(dist + 42, s + 4.5), fontsize=9,
                    color=P["ink"], linespacing=1.45, zorder=6)

    a1.set_ylim(0, 108)
    a1.set_ylabel("도보권 지수", fontsize=10.5, color=P["ink2"])
    a1.set_title(f"도보권 지수 — 로그로지스틱  d0={d0:,.0f}m,  β={beta}  (앵커 없음)",
                 fontsize=13.5, color=P["ink"], pad=34, loc="left")

    at = a1.secondary_xaxis("top", functions=(lambda v: to_minutes(v),
                                              lambda m: m * WALK_SPEED_MPM))
    at.set_xlabel("도보 분  (보통 걸음 4.5km/h)", fontsize=9.5,
                  color=P["muted"], labelpad=6)
    at.tick_params(colors=P["muted"], labelsize=9)
    for s_ in at.spines.values():
        s_.set_color(P["axis"])

    # 아래 — 기울기
    slope = -np.gradient(y, x) * 100
    a2.fill_between(x, 0, slope, color=P["curve"], alpha=0.14, lw=0)
    a2.plot(x, slope, color=P["curve"], lw=2.2, solid_capstyle="round", zorder=3)

    pv = float(-np.gradient(walk_index_ll(np.array([peak - 1, peak, peak + 1]),
                                          d0=d0, beta=beta))[1]) * 100
    a2.plot([peak], [pv], "o", ms=9, color=P["mark"],
            mec=P["surface"], mew=2, zorder=5)
    a2.annotate(f"가장 가파른 지점\n{peak:,.0f}m · 100m 당 {pv:.1f}점",
                xy=(peak, pv), xytext=(peak + 175, pv + 1.05),
                fontsize=9.5, color=P["ink"], linespacing=1.5,
                arrowprops=dict(arrowstyle="-", color=P["axis"], lw=1,
                                shrinkA=2, shrinkB=6))

    for _, dist in sites:
        v = float(-np.gradient(walk_index_ll(np.array([dist - 1, dist, dist + 1]),
                                             d0=d0, beta=beta))[1]) * 100
        a2.plot([dist], [v], "o", ms=6.5, color=P["mark"],
                mec=P["surface"], mew=1.6, alpha=0.85, zorder=5)

    a2.axvspan(0, 200, color=P["muted"], alpha=0.10, lw=0)
    a2.set_ylim(0, max(slope) * 1.35)
    a2.set_xlabel("대지 경계 → 목적지 거리 (m)", fontsize=10.5, color=P["ink2"])
    a2.set_ylabel("100m 당 점수 하락", fontsize=10.5, color=P["ink2"])
    a2.set_title("얼마나 가파른가 — 구간별 변별력", fontsize=11,
                 color=P["ink2"], loc="left", pad=8)

    for a in (a1, a2):
        a.set_xlim(0, xmax)
        a.set_facecolor(P["surface"])
        a.grid(True, color=P["grid"], lw=0.8)
        a.set_axisbelow(True)
        a.tick_params(colors=P["muted"], labelsize=9.5)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(P["axis"])

    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150, facecolor=P["surface"], bbox_inches="tight")
    return fig
''')

code(r'''
_sites = list(zip(df["단지"], df["경계→역_m"]))

plot_curve(**WALK_PARAMS[KIND], sites=_sites, path="도보권지수_확정곡선.png")
plt.show()
''')

# ── 6. 지도 ─────────────────────────────────────────────────────
md(r'''
## 6. 지도로 확인

선이 엉뚱한 곳에 붙어 있으면 계산이 잘못된 것이라, 눈으로 검증하기 좋습니다.
검은 별이 가정한 역 위치, 점선이 각 단지 경계에서 역까지의 최단선입니다.
''')

code(r'''
PALETTE = ["#d62728", "#1f77b4", "#2ca02c", "#9467bd"]


def make_compare_map(df, parcels, tgt_site, tgt_parcel, tgt_name, zoom=15):
    """여러 대지 + 지정 목적지 + 최단선을 지수와 함께 그린다."""
    m = folium.Map(location=[tgt_site["lat"], tgt_site["lng"]],
                   zoom_start=zoom, tiles="CartoDB positron")

    if tgt_parcel is not None:
        folium.GeoJson(tgt_parcel["geometry"], name=tgt_name,
                       style_function=lambda _: {"color": "#111", "weight": 3,
                                                 "fillColor": "#111",
                                                 "fillOpacity": 0.35}).add_to(m)
    folium.Marker([tgt_site["lat"], tgt_site["lng"]], tooltip=tgt_name,
                  icon=folium.Icon(color="black", icon="star")).add_to(m)

    for i, (_, r) in enumerate(df.iterrows()):
        color = PALETTE[i % len(PALETTE)]
        _, parcel = parcels[r["단지"]]
        label = f"{r['단지']} — 경계→역 {r['경계→역_m']:.0f}m · 지수 {r['지수']}"

        folium.GeoJson(parcel["geometry"], name=r["단지"],
                       style_function=lambda _, c=color: {"color": c, "weight": 2,
                                                          "fillColor": c,
                                                          "fillOpacity": 0.18},
                       tooltip=label).add_to(m)
        folium.PolyLine([[r["near_lat"], r["near_lng"]],
                         [tgt_site["lat"], tgt_site["lng"]]],
                        color=color, weight=2.5, opacity=0.8, dash_array="6",
                        tooltip=label).add_to(m)

    folium.LayerControl().add_to(m)
    return m
''')

code(r'''
m = make_compare_map(df, parcels, tgt_site, tgt_parcel, TARGET_NAME)
m.save("도보권지수_위례_지도.html")
m
''')

code(r'''
main.to_csv("도보권지수_위례_결과.csv", index=False, encoding="utf-8-sig")
print("저장 완료: 도보권지수_위례_결과.csv")
''')

# ── 7. 결과 ─────────────────────────────────────────────────────
md(r'''
---

## 7. 결과 및 다음 단계

이 노트북의 4개 단지 테스트는 **정의를 확정하기 위한 것**이었고, 그 목적은 달성했습니다.
경위와 최종 결론은 **설계노트 2-5절(확정안)과 9절(실행 기록)** 에 기록해 두었습니다.

### 확정된 것

| 항목 | 결정 |
| --- | --- |
| 감쇠함수 | **로그로지스틱** `100/(1+(d/d0)^β)` |
| 지하철역 파라미터 | **`d0`=1,000m, `β`=2.0** |
| 6km 앵커 | **검토 후 철회** (앵커 없음) |
| `β` | **전 시설 공통**, 시설별로는 `d0` 만 정함 |

확정안 기준 4개 단지 결과입니다 (역 위치 = 창곡동 506 가정).

| 단지 | 경계→역 m | 도보 분 | **지수** |
| --- | ---: | ---: | ---: |
| 위례중앙푸르지오 1단지 | 147 | 2.0분 | **97.9** |
| 래미안위례 | 270 | 3.6분 | **93.2** |
| 플로리체 위례 | 523 | 7.0분 | **78.5** |
| 위례송파푸르지오 | 768 | 10.2분 | **62.9** |

### 확정 과정에서 드러난 것

**처음 제안했던 로지스틱은 근거리 변별력이 없었습니다.** 상위 3개가 87~99 에 몰렸습니다.
원인은 `d0` 가 **50점이 되는 거리이자 해상도가 몰리는 지점**이라는 두 얼굴을 갖는데,
`d0=800` 이 대상 분포(113~435m)와 어긋나 있었기 때문입니다.

**그런데 `d0` 만 줄이면 원거리가 죽습니다.** 로지스틱은 꼬리가 지수적으로 얇아,
근거리를 벌리면 724m 단지가 14.6점으로 폭락합니다.
**로그로지스틱은 꼬리가 거듭제곱이라 같은 변별력을 훨씬 적은 대가로 얻습니다.**

**함수형을 바꾸자 우회계수 민감도까지 개선됐습니다.**
위례송파푸르지오의 낙폭이 40.8점에서 19.7점으로 절반이 되었습니다.
곡선이 완만해져 거리 오차가 점수로 덜 증폭되기 때문입니다.

### 이 노트북 다음의 작업

**위례신도시 전체 55개 단지에 대한 산출은 별도 파일에 있습니다.**
카카오 키워드 검색(격자 287점) + VWorld 필지 경계 + 사업지구 경계 필터로 만들었습니다.

| 파일 | 내용 |
| --- | --- |
| `위례신도시_단지.csv` / `.geojson` | 55개 단지와 필지 경계 |
| `위례신도시_도보권지수.csv` | 55개 지수 산출 결과 |
| `위례신도시_도보권지수_지도.html` | 지수별 색상 지도 |

### 남은 한계 (L1)

| 한계 | 영향 | 해소 레벨 |
| --- | --- | --- |
| 직선거리라 실제 보행거리보다 짧다 | 점수 과대평가 (실측 확인됨) | **L2 ← 다음** |
| 8차선 횡단·계단·육교를 반영하지 않는다 | 초등학교 도보권 판단에서 특히 큼 | L3 |
| 역 위치를 건물로 가정 | 실제 출입구 기준과 다름 | 개통 후 |
| 지하철역 외 시설의 `d0` 미확정 | 시설 간 비교 불가 | — |
''')

# ────────────────────────────────────────────────────────────────
nb = {
    "cells": [
        {
            "cell_type": t,
            "metadata": {},
            "source": s.splitlines(keepends=True),
            **({"execution_count": None, "outputs": []} if t == "code" else {}),
        }
        for t, s in C
    ],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.0"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = f"{PROJ}/도보권지수_분석.ipynb"
with open(out, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("생성 완료:", out)
print("셀 수:", len(C), "(markdown", sum(1 for t, _ in C if t == "markdown"),
      "/ code", sum(1 for t, _ in C if t == "code"), ")")
