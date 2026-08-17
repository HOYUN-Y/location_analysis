"""반경 2km 밖 누락 영역 보완 검색 → 위례신도시 데이터셋 완성."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json
import math
import os
import re
import time

import folium
import pandas as pd
import requests
from dotenv import load_dotenv
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as sh_transform


load_dotenv(f"{ROOT}/.env")
KKEY = os.getenv("KAKAO_REST_API_KEY")
VKEY = os.getenv("VWORLD_API_KEY")
VDOM = os.getenv("VWORLD_DOMAIN", "https://devprofessional.xyz")
KH = {"Authorization": f"KakaoAK {KKEY}"}
KBASE = "https://dapi.kakao.com/v2/local"
pd.set_option("display.width", 240)

CX, CY = 127.141834, 37.473023
AEQD = f"+proj=aeqd +lat_0={CY} +lon_0={CX} +datum=WGS84 +units=m +no_defs"
FWD = Transformer.from_crs("EPSG:4326", AEQD, always_xy=True)
INV = Transformer.from_crs(AEQD, "EPSG:4326", always_xy=True)
to_m = lambda g: sh_transform(FWD.transform, g)

zf = json.load(open(f"{PROJ}/위례신도시_지구경계.geojson", encoding="utf-8"))["features"][0]
zone = shape(zf["geometry"])
zm = to_m(zone)
gap = zm.difference(Point(0, 0).buffer(2000))

# ── 1. 누락 영역을 덮는 검색점 ──────────────────────────────────
STEP, SUB_R = 500, 700
minx, miny, maxx, maxy = gap.bounds
pts = []
y = miny
while y <= maxy + STEP:
    x = minx
    while x <= maxx + STEP:
        if gap.buffer(300).contains(Point(x, y)):
            pts.append(INV.transform(x, y))
        x += STEP
    y += STEP
print(f"누락 영역 {gap.area/10000:,.1f} ha  →  보완 검색점 {len(pts)}개 × 반경 {SUB_R}m")


def kw(q, lng, lat, radius, page):
    r = requests.get(f"{KBASE}/search/keyword.json", headers=KH,
                     params={"query": q, "x": lng, "y": lat, "radius": radius,
                             "page": page, "size": 15, "sort": "distance"})
    r.raise_for_status()
    return r.json()


def collect(q, lng, lat, radius):
    out = []
    for p in range(1, 4):
        b = kw(q, lng, lat, radius, p)
        out.extend(b["documents"])
        if b["meta"]["is_end"]:
            break
    return out


DROP = re.compile(r"\s*(제?\d+동|[A-Za-z]?\d+동|상가동|상가|정문|후문|입구|출입구|"
                  r"주차장|경비실|관리사무소)\s*$")
PAREN = re.compile(r"\s*\([^)]*\)\s*")


def norm(n):
    s = PAREN.sub(" ", str(n)).strip()
    for _ in range(3):
        s2 = DROP.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    return s


found = {}
for lng, lat in pts:
    for d in collect("아파트", lng, lat, SUB_R):
        if not d.get("category_name", "").startswith("부동산 > 주거시설 > 아파트"):
            continue
        p = Point(float(d["x"]), float(d["y"]))
        if not zone.contains(p):
            continue
        n = norm(d["place_name"])
        found.setdefault(n, []).append(d)

print(f"지구 안 아파트 POI → 단지 {len(found)}개")

# ── 2. 기존 47개와 대조 ────────────────────────────────────────
cur = pd.read_csv(f"{PROJ}/위례신도시_단지.csv")
have = set(cur["단지명"])
new = {n: v for n, v in found.items() if n not in have}
print(f"이미 있는 것 {len(found) - len(new)}개 / 신규 {len(new)}개")
for n in new:
    print(f"    + {n}")

if not new:
    print("\n신규 단지 없음 — 기존 47개가 완전합니다.")
    raise SystemExit


# ── 3. 신규 단지 필지 수집 ─────────────────────────────────────
def vw(gf, size=10, **ex):
    p = {"service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN",
         "key": VKEY, "domain": VDOM, "geomFilter": gf, "crs": "EPSG:4326",
         "format": "json", "size": size, **ex}
    b = requests.get("https://api.vworld.kr/req/data", params=p, timeout=20).json()
    b = b.get("response", {})
    if b.get("status") != "OK":
        raise RuntimeError(f"{b.get('status')} {b.get('error')}")
    r = b.get("result") or {}
    return (r.get("featureCollection", r)).get("features", [])


def area(g):
    poly = shape(g)
    c = poly.centroid
    t = Transformer.from_crs("EPSG:4326",
                             f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} "
                             f"+datum=WGS84 +units=m +no_defs", always_xy=True)
    return sh_transform(t.transform, poly).area


print("\n필지 수집")
rows, geoms = [], {}
for n, docs in new.items():
    lng = sum(float(d["x"]) for d in docs) / len(docs)
    lat = sum(float(d["y"]) for d in docs) / len(docs)
    try:
        fs = vw(f"POINT({lng} {lat})", size=10)
        pt = Point(lng, lat)
        hit = next((f for f in fs if shape(f["geometry"]).contains(pt)), None) \
            or (fs[0] if fs else None)
        if hit is None:
            raise RuntimeError("필지 0건")
        a = area(hit["geometry"])
        g = shape(hit["geometry"])
        dist = Point(0, 0).distance(to_m(Point(lng, lat)))
        geoms[n] = {"type": "Feature", "geometry": hit["geometry"],
                    "properties": {**hit["properties"], "단지명": n}}
        rows.append({"단지명": n, "지번주소": docs[0].get("address_name", ""),
                     "도로명주소": docs[0].get("road_address_name", ""),
                     "중심거리_m": round(dist), "POI수": len(docs),
                     "lng": lng, "lat": lat,
                     "pnu": hit["properties"].get("pnu"),
                     "필지지번": hit["properties"].get("addr")
                              or hit["properties"].get("jibun"),
                     "면적_m2": round(a), "면적_평": round(a / 3.3058),
                     "도형": hit["geometry"]["type"],
                     "지구겹침_%": round(g.intersection(zone).area / g.area * 100, 1)})
        print(f"  {n:<28} {a:>9,.0f} m2")
    except Exception as e:
        print(f"  {n:<28} 실패 — {str(e)[:50]}")
    time.sleep(0.12)

# ── 4. 병합 저장 ───────────────────────────────────────────────
add = pd.DataFrame(rows)
merged = pd.concat([cur, add], ignore_index=True).sort_values("중심거리_m")
merged = merged.reset_index(drop=True)
merged.to_csv(f"{PROJ}/위례신도시_단지.csv", index=False, encoding="utf-8-sig")

gj = json.load(open(f"{PROJ}/위례신도시_단지.geojson", encoding="utf-8"))
gj["features"].extend(geoms.values())
with open(f"{PROJ}/위례신도시_단지.geojson", "w", encoding="utf-8") as fp:
    json.dump(gj, fp, ensure_ascii=False)

print(f"\n최종 {len(merged)}개 단지  (기존 {len(cur)} + 신규 {len(add)})")
print(f"저장: 위례신도시_단지.csv / .geojson")

# ── 5. 지도 갱신 ───────────────────────────────────────────────
gm = {f["properties"]["단지명"]: f for f in gj["features"]}
m = folium.Map(location=[CY, CX], zoom_start=14, tiles="CartoDB positron")
folium.GeoJson(zf["geometry"], name="위례신도시 지구경계",
               style_function=lambda _: {"color": "#0b0b0b", "weight": 2.5,
                                         "fillColor": "#0b0b0b",
                                         "fillOpacity": 0.05}).add_to(m)
for _, r in merged.iterrows():
    f = gm.get(r["단지명"])
    if not f:
        continue
    folium.GeoJson(f["geometry"], name=r["단지명"],
                   style_function=lambda _: {"color": "#2a78d6", "weight": 1.6,
                                             "fillColor": "#2a78d6",
                                             "fillOpacity": 0.35},
                   tooltip=f"{r['단지명']} — {r['면적_m2']:,}㎡ / {r['면적_평']:,}평"
                   ).add_to(m)
folium.Marker([CY, CX], tooltip="기준점 창곡동 506",
              icon=folium.Icon(color="red", icon="star")).add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
m.save(f"{PROJ}/위례신도시_단지_지도.html")
print("저장: 위례신도시_단지_지도.html")

print("\n면적 분포")
print(merged["면적_m2"].describe().round(0).to_string())
