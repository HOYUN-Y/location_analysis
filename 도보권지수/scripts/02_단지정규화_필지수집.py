"""아파트 POI 정규화 → 단지 단위 병합 → VWorld 필지 경계 수집."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json
import os
import re
import time

import pandas as pd
import requests
from dotenv import load_dotenv
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as sh_transform, unary_union

SCRATCH = ("/private/tmp/claude-501/-Users-hoyun-Documents-GitHub-location-analysis/"
           "39a46c99-18b1-4973-a741-111d6f5c06e5/scratchpad")

load_dotenv(f"{ROOT}/.env")
VKEY = os.getenv("VWORLD_API_KEY")
VDOMAIN = os.getenv("VWORLD_DOMAIN", "https://devprofessional.xyz")
VURL = "https://api.vworld.kr/req/data"
pd.set_option("display.width", 240)

raw = pd.read_csv(f"{SCRATCH}/apts_raw.csv")
print(f"원본 POI {len(raw)}건")

# ── 1. 단지 단위로 정규화 ───────────────────────────────────────
DROP_SUFFIX = re.compile(
    r"\s*(제?\d+동|[A-Za-z]?\d+동|상가동|상가|정문|후문|입구|출입구|"
    r"주차장|경비실|관리사무소)\s*$")
PAREN = re.compile(r"\s*\([^)]*\)\s*")


def normalize(name):
    s = PAREN.sub(" ", str(name)).strip()
    for _ in range(3):                       # "…아파트 6109동" 같은 중첩 접미 제거
        s2 = DROP_SUFFIX.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    return s


# 주거시설 아파트만 (아파트상가·입출구·주차장 제외)
apt = raw[raw["category"].str.startswith("부동산 > 주거시설 > 아파트", na=False)].copy()
apt["단지명"] = apt["단지명"].map(normalize)
print(f"주거 아파트 POI {len(apt)}건 → 정규화")

# 같은 단지명은 하나로 합치고, 좌표는 동들의 평균, 거리는 최솟값
g = apt.groupby("단지명", as_index=False).agg(
    지번주소=("지번주소", "first"), 도로명주소=("도로명주소", "first"),
    lng=("lng", "mean"), lat=("lat", "mean"),
    중심거리_m=("중심거리_m", "min"), POI수=("id", "size"))
g = g.sort_values("중심거리_m").reset_index(drop=True)
print(f"→ 단지 {len(g)}개\n")
print(g[["단지명", "지번주소", "중심거리_m", "POI수"]].to_string())

# ── 2. VWorld 필지 경계 수집 ────────────────────────────────────
def vworld(data, geom_filter, size=10, **extra):
    p = {"service": "data", "request": "GetFeature", "data": data,
         "key": VKEY, "domain": VDOMAIN, "geomFilter": geom_filter,
         "crs": "EPSG:4326", "format": "json", "size": size, **extra}
    r = requests.get(VURL, params=p, timeout=20)
    r.raise_for_status()
    b = r.json().get("response", {})
    if b.get("status") != "OK":
        raise RuntimeError(f"status={b.get('status')} {b.get('error')}")
    res = b.get("result") or {}
    return (res.get("featureCollection", res)).get("features", [])


def area_m2(geom):
    poly = shape(geom)
    c = poly.centroid
    aeqd = f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m +no_defs"
    fwd = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    return sh_transform(fwd.transform, poly).area


print("\n" + "=" * 100)
print("[2] VWorld 필지 경계 수집")
print("=" * 100)

feats, rows, fails = {}, [], []
for i, r in g.iterrows():
    name, lng, lat = r["단지명"], r["lng"], r["lat"]
    try:
        fs = vworld("LP_PA_CBND_BUBUN", f"POINT({lng} {lat})", size=10)
        pt = Point(lng, lat)
        hit = next((f for f in fs if shape(f["geometry"]).contains(pt)), None)
        note = ""
        if hit is None:
            if not fs:
                raise RuntimeError("필지 0건")
            hit = fs[0]
            note = "점 미포함 → 첫 필지"

        a = area_m2(hit["geometry"])
        feats[name] = hit
        rows.append({"단지명": name, "지번주소": r["지번주소"],
                     "중심거리_m": r["중심거리_m"], "POI수": r["POI수"],
                     "lng": lng, "lat": lat,
                     "pnu": hit["properties"].get("pnu"),
                     "필지지번": hit["properties"].get("addr")
                                or hit["properties"].get("jibun"),
                     "면적_m2": round(a), "면적_평": round(a / 3.3058),
                     "도형": hit["geometry"]["type"], "비고": note})
        print(f"  [{i+1:>3}/{len(g)}] {name:<28} {a:>9,.0f} m2  {note}")
    except Exception as e:
        fails.append({"단지명": name, "사유": str(e)[:70]})
        print(f"  [{i+1:>3}/{len(g)}] {name:<28} 실패 — {str(e)[:60]}")
    time.sleep(0.12)

df = pd.DataFrame(rows)
print(f"\n성공 {len(df)}개 / 실패 {len(fails)}개")
if fails:
    print(pd.DataFrame(fails).to_string(index=False))

# ── 3. 저장 ────────────────────────────────────────────────────
df.to_csv(f"{PROJ}/위례_후보단지_필지.csv", index=False, encoding="utf-8-sig")

fc = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": f["geometry"],
     "properties": {**f["properties"], "단지명": n}}
    for n, f in feats.items()]}
with open(f"{PROJ}/위례_후보단지_필지.geojson", "w", encoding="utf-8") as fp:
    json.dump(fc, fp, ensure_ascii=False)

print(f"\n저장: 위례_후보단지_필지.csv  ({len(df)}행)")
print(f"저장: 위례_후보단지_필지.geojson  ({len(fc['features'])} features)")

print("\n" + "=" * 100)
print("면적 분포 — 단지 전체를 덮었는지 확인용")
print("=" * 100)
print(df["면적_m2"].describe().round(0).to_string())
small = df[df["면적_m2"] < 10000].sort_values("면적_m2")
print(f"\n1만 m2 미만 {len(small)}개 — 단지 일부만 잡혔을 가능성:")
print(small[["단지명", "지번주소", "면적_m2", "면적_평"]].to_string(index=False))
