"""L2 — 위례신도시 55개 단지 × 위례중앙역, T맵 보행자 실경로."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json
import os
import time
from collections import Counter

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform as sh_transform


SC = ("/private/tmp/claude-501/-Users-hoyun-Documents-GitHub-location-analysis/"
      "39a46c99-18b1-4973-a741-111d6f5c06e5/scratchpad")
load_dotenv(f"{ROOT}/.env")
TKEY = os.getenv("TMAP_APP_KEY")
URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"
pd.set_option("display.width", 250)

TX, TY = 127.141834, 37.473023
PARAM = {"d0": 1000, "beta": 2.0}

CROSS = {211, 212, 213, 214, 215, 216, 217}
BRIDGE, UNDER, STAIR, SLOPE, ELEV = 125, 126, 127, 128, 218


def wi(d, d0=1000.0, beta=2.0):
    d = np.clip(np.asarray(d, float), 0, None)
    return 100.0 / (1.0 + (d / d0) ** beta)


def route(sx, sy, opt=0):
    body = {"startX": sx, "startY": sy, "endX": TX, "endY": TY,
            "startName": "출발", "endName": "도착",
            "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
            "searchOption": opt}
    r = requests.post(URL, json=body, timeout=25,
                      headers={"appKey": TKEY, "Content-Type": "application/json"})
    r.raise_for_status()
    return r.json()


gj = json.load(open(f"{PROJ}/위례신도시_단지.geojson", encoding="utf-8"))
geoms = {f["properties"]["단지명"]: shape(f["geometry"]) for f in gj["features"]}
base = pd.read_csv(f"{PROJ}/위례신도시_도보권지수.csv")
print(f"단지 {len(base)}개 — T맵 호출 {len(base)*2}회 예정 (옵션 0 / 30)\n")

rows, geo_routes, fails = [], [], []
for i, r0 in base.iterrows():
    name = r0["단지명"]
    poly_ll = geoms[name]
    c = poly_ll.centroid
    aeqd = f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m +no_defs"
    fwd = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    inv = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True)
    poly = sh_transform(fwd.transform, poly_ll)
    tpt = sh_transform(fwd.transform, Point(TX, TY))
    near, _ = nearest_points(poly.boundary, tpt)
    sx, sy = inv.transform(near.x, near.y)
    straight = poly.boundary.distance(tpt)

    try:
        d0j = route(sx, sy, 0)
        p0 = d0j["features"][0]["properties"]
        tt = Counter(f["properties"].get("turnType") for f in d0j["features"]
                     if f["geometry"]["type"] == "Point")

        time.sleep(0.15)
        d30 = route(sx, sy, 30)
        p30 = d30["features"][0]["properties"]

        rows.append({
            "단지명": name,
            "직선_m": round(straight, 1),
            "경로_m": p0["totalDistance"],
            "소요_초": p0["totalTime"],
            "소요_분": round(p0["totalTime"] / 60, 1),
            "우회계수": round(p0["totalDistance"] / straight, 3),
            "T맵속도_kmh": round(p0["totalDistance"] / p0["totalTime"] * 3.6, 2),
            "횡단보도": sum(v for k, v in tt.items() if k in CROSS),
            "육교": tt.get(BRIDGE, 0), "지하보도": tt.get(UNDER, 0),
            "계단": tt.get(STAIR, 0), "경사로": tt.get(SLOPE, 0),
            "엘리베이터": tt.get(ELEV, 0),
            "계단제외_m": p30["totalDistance"],
            "계단회피비용_m": p30["totalDistance"] - p0["totalDistance"],
        })
        geo_routes.append({"type": "Feature", "properties": {"단지명": name},
                           "geometry": {"type": "MultiLineString", "coordinates": [
                               f["geometry"]["coordinates"] for f in d0j["features"]
                               if f["geometry"]["type"] == "LineString"]}})
        print(f"  [{i+1:>2}/{len(base)}] {name:<28} "
              f"직선 {straight:>6.0f} → 경로 {p0['totalDistance']:>6,}m "
              f"(×{p0['totalDistance']/straight:.2f})  {p0['totalTime']/60:>4.1f}분")
    except Exception as e:
        fails.append({"단지명": name, "사유": str(e)[:70]})
        print(f"  [{i+1:>2}/{len(base)}] {name:<28} 실패 — {str(e)[:50]}")
    time.sleep(0.15)

df = pd.DataFrame(rows)
print(f"\n성공 {len(df)} / 실패 {len(fails)}")
if fails:
    print(pd.DataFrame(fails).to_string(index=False))

# ── 지수 ───────────────────────────────────────────────────────
df["지수_L1"] = wi(df["직선_m"].to_numpy(), **PARAM).round(1)
df["지수_L2"] = wi(df["경로_m"].to_numpy(), **PARAM).round(1)
df["지수차"] = (df["지수_L2"] - df["지수_L1"]).round(1)

df["순위_L1"] = df["직선_m"].rank().astype(int)
df["순위_L2"] = df["경로_m"].rank().astype(int)
df["순위변동"] = df["순위_L1"] - df["순위_L2"]

df = df.sort_values("경로_m").reset_index(drop=True)
df.to_csv(f"{PROJ}/위례신도시_도보권지수_L2.csv", index=False, encoding="utf-8-sig")
json.dump({"type": "FeatureCollection", "features": geo_routes},
          open(f"{PROJ}/위례신도시_보행경로.geojson", "w", encoding="utf-8"),
          ensure_ascii=False)
print("\n저장: 위례신도시_도보권지수_L2.csv / 위례신도시_보행경로.geojson")

show = ["단지명", "직선_m", "경로_m", "우회계수", "소요_분", "T맵속도_kmh",
        "횡단보도", "계단", "지수_L1", "지수_L2", "지수차", "순위변동"]
print("\n" + "=" * 140)
print("L2 결과 (경로거리순)")
print("=" * 140)
print(df[show].to_string(index=False))

print("\n" + "=" * 90)
print("우회계수")
print("=" * 90)
print(df["우회계수"].describe().round(3).to_string())
print(f"\n  중앙값 {df['우회계수'].median():.3f}  "
      f"평균 {df['우회계수'].mean():.3f}  "
      f"최소 {df['우회계수'].min():.3f} ({df.loc[df['우회계수'].idxmin(),'단지명']})  "
      f"최대 {df['우회계수'].max():.3f} ({df.loc[df['우회계수'].idxmax(),'단지명']})")

print("\n" + "=" * 90)
print("T맵 보행속도 — totalTime 이 거리의 단순 환산인가")
print("=" * 90)
print(df["T맵속도_kmh"].describe().round(3).to_string())
corr = np.corrcoef(df["경로_m"], df["소요_초"])[0, 1]
print(f"\n  경로거리↔소요시간 상관 {corr:.4f}")
print(f"  속도 편차: {df['T맵속도_kmh'].min():.2f} ~ {df['T맵속도_kmh'].max():.2f} km/h")

print("\n" + "=" * 90)
print("순위 변동 — L1 이 순위를 맞췄는가")
print("=" * 90)
sp = df[["순위_L1", "순위_L2"]].corr(method="spearman").iloc[0, 1]
print(f"  스피어만 순위상관 {sp:.4f}")
print(f"  순위가 바뀐 단지 {int((df['순위변동'] != 0).sum())}개 / {len(df)}개")
print(f"  최대 변동 {int(df['순위변동'].abs().max())}계단")
big = df[df["순위변동"].abs() >= 3].sort_values("순위변동")
if len(big):
    print("\n  3계단 이상 움직인 단지:")
    print(big[["단지명", "직선_m", "경로_m", "우회계수",
               "순위_L1", "순위_L2", "순위변동"]].to_string(index=False))

print("\n" + "=" * 90)
print("보행 장애물 (turnType 집계)")
print("=" * 90)
for col in ["횡단보도", "육교", "지하보도", "계단", "경사로", "엘리베이터"]:
    print(f"  {col:<8} 총 {df[col].sum():>4}회   평균 {df[col].mean():>5.2f}   "
          f"최대 {df[col].max()}회")
st = df[df["계단"] > 0]
print(f"\n  계단이 있는 경로 {len(st)}개")
if len(st):
    print(st[["단지명", "경로_m", "계단", "계단제외_m", "계단회피비용_m"]]
          .to_string(index=False))
