"""T맵 보행자 경로안내 API 응답 구조 확인 (테스트 1~2건)."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json
import os
from collections import Counter

import pandas as pd
import requests
from dotenv import load_dotenv
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform as sh_transform


load_dotenv(f"{ROOT}/.env")
TKEY = os.getenv("TMAP_APP_KEY")
URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"
pd.set_option("display.width", 240)

TX, TY = 127.141834, 37.473023          # 창곡동 506 = 위례중앙역(가정)

gj = json.load(open(f"{PROJ}/위례신도시_단지.geojson", encoding="utf-8"))
geoms = {f["properties"]["단지명"]: shape(f["geometry"]) for f in gj["features"]}
NAME = "위례송파푸르지오아파트"
poly_ll = geoms[NAME]
c = poly_ll.centroid
aeqd = f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m +no_defs"
fwd = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
inv = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True)
poly = sh_transform(fwd.transform, poly_ll)
tpt = sh_transform(fwd.transform, Point(TX, TY))
near, _ = nearest_points(poly.boundary, tpt)
SX, SY = inv.transform(near.x, near.y)
straight = poly.boundary.distance(tpt)

print(f"출발: {NAME} 경계 최근접점 ({SX:.6f}, {SY:.6f})")
print(f"도착: 위례중앙역(가정)     ({TX:.6f}, {TY:.6f})")
print(f"직선거리 {straight:,.1f} m\n")


def call(opt):
    body = {"startX": SX, "startY": SY, "endX": TX, "endY": TY,
            "startName": "출발", "endName": "도착",
            "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
            "searchOption": opt}
    r = requests.post(URL, json=body,
                      headers={"appKey": TKEY, "Content-Type": "application/json"},
                      timeout=20)
    return r


r = call(0)
print(f"HTTP {r.status_code}")
if r.status_code != 200:
    print(r.text[:800])
    raise SystemExit

data = r.json()
print("최상위 키:", list(data.keys()))
feats = data["features"]
print(f"features {len(feats)}개")

kinds = Counter(f["geometry"]["type"] for f in feats)
print("도형 타입:", dict(kinds))

p0 = feats[0]["properties"]
print("\n첫 feature properties 키:")
for k, v in p0.items():
    print(f"  {k:<18} = {v}")

pt_keys, ln_keys = set(), set()
for f in feats:
    (pt_keys if f["geometry"]["type"] == "Point" else ln_keys).update(f["properties"])
print("\nPoint properties 키 합집합:     ", sorted(pt_keys))
print("LineString properties 키 합집합:", sorted(ln_keys))

# 총거리 / 총시간
tot_d = p0.get("totalDistance")
tot_t = p0.get("totalTime")
print(f"\n총거리 {tot_d:,} m / 총시간 {tot_t:,} 초 ({tot_t/60:.1f} 분)")
print(f"우회계수 = {tot_d/straight:.3f}")
print(f"T맵 내부 보행속도 = {tot_d/tot_t*3.6:.2f} km/h")

# turnType 집계
tt = Counter(f["properties"].get("turnType") for f in feats
             if f["geometry"]["type"] == "Point"
             and f["properties"].get("turnType") is not None)
print("\nturnType 분포:")
LBL = {200: "출발", 201: "도착", 211: "횡단보도", 212: "좌측횡단보도",
       213: "우측횡단보도", 214: "8시방향횡단보도", 215: "10시방향횡단보도",
       216: "2시방향횡단보도", 217: "4시방향횡단보도", 125: "육교",
       126: "지하보도", 127: "계단진입", 128: "경사로진입", 218: "엘리베이터"}
for k, v in sorted(tt.items()):
    print(f"  {k:>4} {LBL.get(k,'(방향지시)'):<14} {v}회")

print("\n안내 문구 (앞 12개):")
for f in feats:
    if f["geometry"]["type"] != "Point":
        continue
    pr = f["properties"]
    print(f"  [{pr.get('turnType'):>4}] {pr.get('description','')[:60]}")

# 계단 제외 옵션과 비교
print("\n" + "=" * 80)
print("searchOption 비교 (0=추천 / 10=최단 / 30=최단+계단제외)")
print("=" * 80)
for opt in (0, 10, 30):
    rr = call(opt)
    if rr.status_code != 200:
        print(f"  옵션 {opt:>2}: HTTP {rr.status_code}")
        continue
    pp = rr.json()["features"][0]["properties"]
    print(f"  옵션 {opt:>2}: {pp['totalDistance']:>6,} m / "
          f"{pp['totalTime']:>5,} 초 / 우회 {pp['totalDistance']/straight:.3f}")
