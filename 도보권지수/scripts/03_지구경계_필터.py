"""위례신도시 지구 경계 안의 단지만 골라 별도 데이터셋 생성.

원본(위례_후보단지_필지.*)은 건드리지 않는다.
"""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json
import os

import folium
import pandas as pd
import requests
from dotenv import load_dotenv
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as sh_transform


load_dotenv(f"{ROOT}/.env")
VKEY = os.getenv("VWORLD_API_KEY")
VDOM = os.getenv("VWORLD_DOMAIN", "https://devprofessional.xyz")
pd.set_option("display.width", 240)

CX, CY = 127.141834, 37.473023          # 창곡동 506
ZONE_NAME = "위례 택지개발사업 예정지구"


def vw(layer, gf, size=100, **ex):
    p = {"service": "data", "request": "GetFeature", "data": layer, "key": VKEY,
         "domain": VDOM, "geomFilter": gf, "crs": "EPSG:4326",
         "format": "json", "size": size, **ex}
    b = requests.get("https://api.vworld.kr/req/data", params=p, timeout=25).json()
    b = b.get("response", {})
    if b.get("status") != "OK":
        raise RuntimeError(f"{b.get('status')} {b.get('error')}")
    r = b.get("result") or {}
    return (r.get("featureCollection", r)).get("features", [])


def projector(lat0, lng0):
    aeqd = f"+proj=aeqd +lat_0={lat0} +lon_0={lng0} +datum=WGS84 +units=m +no_defs"
    t = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    return lambda g: sh_transform(t.transform, g)


# ── 1. 지구 경계 ───────────────────────────────────────────────
zones = vw("LT_C_LHZONE", f"POINT({CX} {CY})", buffer=6000)
zf = next(f for f in zones if f["properties"].get("zonename") == ZONE_NAME)
zone = shape(zf["geometry"])

to_m = projector(CY, CX)
print(f"지구: {ZONE_NAME}")
print(f"  면적 {to_m(zone).area / 10000:,.1f} ha   도형 {zf['geometry']['type']}")

# ── 2. 원본 로드 후 판정 ───────────────────────────────────────
df = pd.read_csv(f"{PROJ}/위례_후보단지_필지.csv")
gj = json.load(open(f"{PROJ}/위례_후보단지_필지.geojson", encoding="utf-8"))
geoms = {f["properties"]["단지명"]: f for f in gj["features"]}
print(f"\n원본 단지 {len(df)}개")

rows = []
for _, r in df.iterrows():
    g = shape(geoms[r["단지명"]]["geometry"])
    inter = g.intersection(zone)
    ratio = (inter.area / g.area) if g.area else 0.0
    rows.append({"지구내_중심": zone.contains(g.centroid),
                 "지구겹침_%": round(ratio * 100, 1)})

df = pd.concat([df, pd.DataFrame(rows)], axis=1)

inside = df[df["지구내_중심"]].sort_values("중심거리_m").reset_index(drop=True)
outside = df[~df["지구내_중심"]]

print(f"  지구 안 {len(inside)}개 / 밖 {len(outside)}개")

edge = inside[inside["지구겹침_%"] < 99]
if len(edge):
    print(f"\n  경계에 걸친 단지 {len(edge)}개 (겹침 99% 미만):")
    print(edge[["단지명", "지번주소", "면적_m2", "지구겹침_%"]].to_string(index=False))

# ── 3. 저장 ────────────────────────────────────────────────────
cols = ["단지명", "지번주소", "도로명주소" if "도로명주소" in inside else "지번주소",
        "중심거리_m", "POI수", "lng", "lat", "pnu", "필지지번",
        "면적_m2", "면적_평", "도형", "지구겹침_%"]
cols = [c for c in dict.fromkeys(cols) if c in inside.columns]
inside[cols].to_csv(f"{PROJ}/위례신도시_단지.csv", index=False, encoding="utf-8-sig")

fc = {"type": "FeatureCollection", "features": [
    geoms[n] for n in inside["단지명"] if n in geoms]}
with open(f"{PROJ}/위례신도시_단지.geojson", "w", encoding="utf-8") as fp:
    json.dump(fc, fp, ensure_ascii=False)

with open(f"{PROJ}/위례신도시_지구경계.geojson", "w", encoding="utf-8") as fp:
    json.dump({"type": "FeatureCollection", "features": [zf]}, fp, ensure_ascii=False)

print(f"\n저장: 위례신도시_단지.csv          ({len(inside)}행)")
print(f"저장: 위례신도시_단지.geojson      ({len(fc['features'])} features)")
print(f"저장: 위례신도시_지구경계.geojson")

# ── 4. 목록 ────────────────────────────────────────────────────
print("\n" + "=" * 100)
print("위례신도시 내 단지")
print("=" * 100)
print(inside[["단지명", "지번주소", "중심거리_m", "면적_m2", "면적_평"]].to_string())

print("\n면적 분포")
print(inside["면적_m2"].describe().round(0).to_string())
sm = inside[inside["면적_m2"] < 5000]
print(f"\n5,000m2 미만 {len(sm)}개:")
if len(sm):
    print(sm[["단지명", "지번주소", "면적_m2"]].to_string(index=False))

print("\n제외된 단지 (지구 밖)")
print(outside.sort_values("중심거리_m")[["단지명", "지번주소", "중심거리_m", "면적_m2"]]
      .to_string(index=False))

# ── 5. 지도 ────────────────────────────────────────────────────
m = folium.Map(location=[CY, CX], zoom_start=14, tiles="CartoDB positron")
folium.GeoJson(zf["geometry"], name="위례신도시 지구경계",
               style_function=lambda _: {"color": "#0b0b0b", "weight": 2.5,
                                         "fillColor": "#0b0b0b",
                                         "fillOpacity": 0.05}).add_to(m)
for _, r in inside.iterrows():
    folium.GeoJson(geoms[r["단지명"]]["geometry"], name=r["단지명"],
                   style_function=lambda _: {"color": "#2a78d6", "weight": 1.6,
                                             "fillColor": "#2a78d6",
                                             "fillOpacity": 0.35},
                   tooltip=f"{r['단지명']} — {r['면적_m2']:,}㎡").add_to(m)
for _, r in outside.iterrows():
    if r["단지명"] in geoms:
        folium.GeoJson(geoms[r["단지명"]]["geometry"],
                       style_function=lambda _: {"color": "#898781", "weight": 1.2,
                                                 "fillColor": "#898781",
                                                 "fillOpacity": 0.18},
                       tooltip=f"(제외) {r['단지명']} — {r['면적_m2']:,}㎡").add_to(m)
folium.Marker([CY, CX], tooltip="기준점 창곡동 506",
              icon=folium.Icon(color="red", icon="star")).add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
m.save(f"{PROJ}/위례신도시_단지_지도.html")
print("\n저장: 위례신도시_단지_지도.html")
