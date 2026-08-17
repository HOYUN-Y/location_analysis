"""위례신도시 52개 단지 × 위례중앙역 도보권 지수 (L1)."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json
import os

import folium
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform as sh_transform


load_dotenv(f"{ROOT}/.env")
KH = {"Authorization": f"KakaoAK {os.getenv('KAKAO_REST_API_KEY')}"}
VKEY = os.getenv("VWORLD_API_KEY")
VDOM = os.getenv("VWORLD_DOMAIN", "https://devprofessional.xyz")
pd.set_option("display.width", 250)

TARGET_ADDR = "경기 성남시 수정구 창곡동 506"
TARGET_NAME = "위례중앙역(가정)"
PARAM = {"d0": 1000, "beta": 2.0}          # 확정
ALT = {"d0": 750, "beta": 2.0}             # 검토안


def walk_index_ll(d, d0=1000.0, beta=2.0):
    d = np.clip(np.asarray(d, float), 0, None)
    return 100.0 / (1.0 + (d / d0) ** beta)


def projector(lat0, lng0):
    aeqd = f"+proj=aeqd +lat_0={lat0} +lon_0={lng0} +datum=WGS84 +units=m +no_defs"
    f = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    i = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True)
    return (lambda g: sh_transform(f.transform, g),
            lambda g: sh_transform(i.transform, g))


# ── 목적지 ─────────────────────────────────────────────────────
r = requests.get("https://dapi.kakao.com/v2/local/search/address.json",
                 headers=KH, params={"query": TARGET_ADDR, "size": 1})
d = r.json()["documents"][0]
TX, TY = float(d["x"]), float(d["y"])
print(f"{TARGET_NAME}  {d['address_name']}  ({TX:.6f}, {TY:.6f})")

p = {"service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN",
     "key": VKEY, "domain": VDOM, "geomFilter": f"POINT({TX} {TY})",
     "crs": "EPSG:4326", "format": "json", "size": 10}
b = requests.get("https://api.vworld.kr/req/data", params=p, timeout=20).json()
fs = (b["response"]["result"].get("featureCollection",
                                  b["response"]["result"]))["features"]
tgt_poly = next((shape(f["geometry"]) for f in fs
                 if shape(f["geometry"]).contains(Point(TX, TY))), None)
print(f"목적지 필지: {'확보' if tgt_poly else '없음'}")

# ── 단지 ───────────────────────────────────────────────────────
df = pd.read_csv(f"{PROJ}/위례신도시_단지.csv")
gj = json.load(open(f"{PROJ}/위례신도시_단지.geojson", encoding="utf-8"))
geoms = {f["properties"]["단지명"]: shape(f["geometry"]) for f in gj["features"]}
print(f"단지 {len(df)}개\n")

rows = []
for _, r0 in df.iterrows():
    poly_ll = geoms[r0["단지명"]]
    c = poly_ll.centroid
    to_m, to_ll = projector(c.y, c.x)

    poly = to_m(poly_ll)
    tpt = to_m(Point(TX, TY))
    near, _ = nearest_points(poly.boundary, tpt)
    near_ll = to_ll(near)

    b2b = np.nan
    if tgt_poly is not None:
        b2b = poly.boundary.distance(to_m(tgt_poly).boundary)

    rows.append({
        "단지명": r0["단지명"], "지번주소": r0["지번주소"],
        "면적_m2": r0["면적_m2"],
        "중심→역_m": round(poly.centroid.distance(tpt), 1),
        "경계→역_m": round(poly.boundary.distance(tpt), 1),
        "경계→역경계_m": round(b2b, 1),
        "near_lng": near_ll.x, "near_lat": near_ll.y,
    })

res = pd.DataFrame(rows)
res["도보_분"] = (res["경계→역_m"] / 75).round(1)
res["지수"] = walk_index_ll(res["경계→역_m"].to_numpy(), **PARAM).round(1)
res["중심기준_지수"] = walk_index_ll(res["중심→역_m"].to_numpy(), **PARAM).round(1)
res["경계보정"] = (res["지수"] - res["중심기준_지수"]).round(1)
res["지수_d750"] = walk_index_ll(res["경계→역_m"].to_numpy(), **ALT).round(1)

res = res.sort_values("경계→역_m").reset_index(drop=True)
res.insert(0, "순위", res.index + 1)
res["상대지수"] = (res["지수"] / res["지수"].max() * 100).round(1)

# 우회계수 민감도
for f in (1.2, 1.35, 1.5):
    res[f"×{f}"] = walk_index_ll(res["경계→역_m"].to_numpy() * f, **PARAM).round(1)
res["낙폭"] = (res["지수"] - res["×1.5"]).round(1)

show = ["순위", "단지명", "지번주소", "경계→역_m", "도보_분", "지수",
        "상대지수", "지수_d750", "중심기준_지수", "경계보정", "낙폭"]
print("=" * 130)
print(f"위례신도시 52개 단지 × {TARGET_NAME}   (L1 직선거리, 로그로지스틱 "
      f"d0={PARAM['d0']} β={PARAM['beta']}, 앵커 없음)")
print("=" * 130)
print(res[show].to_string(index=False))

out = res.drop(columns=["near_lng", "near_lat"])
out.to_csv(f"{PROJ}/위례신도시_도보권지수.csv", index=False, encoding="utf-8-sig")
print(f"\n저장: 위례신도시_도보권지수.csv")

print("\n" + "=" * 90)
print("요약")
print("=" * 90)
print(res["지수"].describe().round(1).to_string())
print(f"\n1위 {res.iloc[0]['단지명']} {res.iloc[0]['지수']}점 "
      f"({res.iloc[0]['경계→역_m']:.0f}m)")
print(f"52위 {res.iloc[-1]['단지명']} {res.iloc[-1]['지수']}점 "
      f"({res.iloc[-1]['경계→역_m']:.0f}m)")
print(f"\n낙폭(우회 ×1.5) 최대 {res['낙폭'].max():.1f}점 "
      f"— {res.loc[res['낙폭'].idxmax(), '단지명']}")
print(f"경계보정 최대 {res['경계보정'].max():.1f}점 "
      f"— {res.loc[res['경계보정'].idxmax(), '단지명']}")

# ── 지도 ───────────────────────────────────────────────────────
zf = json.load(open(f"{PROJ}/위례신도시_지구경계.geojson",
                    encoding="utf-8"))["features"][0]
m = folium.Map(location=[TY, TX], zoom_start=14, tiles="CartoDB positron")
folium.GeoJson(zf["geometry"], name="지구경계",
               style_function=lambda _: {"color": "#0b0b0b", "weight": 2,
                                         "fill": False}).add_to(m)


def col(v):
    return ("#184f95" if v >= 90 else "#2a78d6" if v >= 75 else
            "#5598e7" if v >= 60 else "#86b6ef" if v >= 45 else "#c9dcf7")


for _, r0 in res.iterrows():
    lab = (f"{r0['순위']}위 {r0['단지명']} — 지수 {r0['지수']} "
           f"/ {r0['경계→역_m']:.0f}m / 도보 {r0['도보_분']}분")
    folium.GeoJson(geoms[r0["단지명"]].__geo_interface__, name=r0["단지명"],
                   style_function=lambda _, c=col(r0["지수"]): {
                       "color": c, "weight": 1.4, "fillColor": c,
                       "fillOpacity": 0.7},
                   tooltip=lab).add_to(m)
    folium.PolyLine([[r0["near_lat"], r0["near_lng"]], [TY, TX]],
                    color="#898781", weight=1, opacity=0.45,
                    dash_array="4", tooltip=lab).add_to(m)

if tgt_poly is not None:
    folium.GeoJson(tgt_poly.__geo_interface__, name=TARGET_NAME,
                   style_function=lambda _: {"color": "#eb6834", "weight": 3,
                                             "fillColor": "#eb6834",
                                             "fillOpacity": 0.6}).add_to(m)
folium.Marker([TY, TX], tooltip=TARGET_NAME,
              icon=folium.Icon(color="orange", icon="star")).add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
m.save(f"{PROJ}/위례신도시_도보권지수_지도.html")
print("저장: 위례신도시_도보권지수_지도.html")
