"""위례 지구 전역을 촘촘한 격자로 재탐색 (45건 상한 회피)."""

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
from shapely.ops import transform as sh_transform


load_dotenv(f"{ROOT}/.env")
KH = {"Authorization": f"KakaoAK {os.getenv('KAKAO_REST_API_KEY')}"}
KB = "https://dapi.kakao.com/v2/local"
pd.set_option("display.width", 240)

CX, CY = 127.141834, 37.473023
STEP, SUB_R = 200, 300          # 격자 간격 200m, 검색 반경 300m
CAP = 45                        # 카카오 키워드 검색 상한

zf = json.load(open(f"{PROJ}/위례신도시_지구경계.geojson",
                    encoding="utf-8"))["features"][0]
zone = shape(zf["geometry"])

AEQD = f"+proj=aeqd +lat_0={CY} +lon_0={CX} +datum=WGS84 +units=m +no_defs"
FWD = Transformer.from_crs("EPSG:4326", AEQD, always_xy=True)
INV = Transformer.from_crs(AEQD, "EPSG:4326", always_xy=True)
zm = sh_transform(FWD.transform, zone)

minx, miny, maxx, maxy = zm.bounds
pts, y = [], miny - STEP
while y <= maxy + STEP:
    x = minx - STEP
    while x <= maxx + STEP:
        if zm.buffer(SUB_R).contains(Point(x, y)):
            pts.append(INV.transform(x, y))
        x += STEP
    y += STEP
print(f"지구 {zm.area/10000:,.1f} ha  →  격자점 {len(pts)}개 "
      f"(간격 {STEP}m, 검색반경 {SUB_R}m)")


def collect(q, lng, lat, radius):
    out, cap_hit, total = [], False, 0
    for p in range(1, 4):
        r = requests.get(f"{KB}/search/keyword.json", headers=KH,
                         params={"query": q, "x": lng, "y": lat,
                                 "radius": radius, "page": p, "size": 15,
                                 "sort": "distance"})
        r.raise_for_status()
        b = r.json()
        total = b["meta"]["total_count"]
        out.extend(b["documents"])
        if b["meta"]["is_end"]:
            break
    else:
        cap_hit = total > CAP
    return out, cap_hit, total


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


found, caps, calls = {}, 0, 0
for i, (lng, lat) in enumerate(pts):
    docs, cap_hit, total = collect("아파트", lng, lat, SUB_R)
    calls += 1
    caps += cap_hit
    for d in docs:
        if not d.get("category_name", "").startswith("부동산 > 주거시설 > 아파트"):
            continue
        p = Point(float(d["x"]), float(d["y"]))
        if not zone.contains(p):
            continue
        found.setdefault(norm(d["place_name"]), []).append(d)
    if (i + 1) % 25 == 0:
        print(f"  {i+1}/{len(pts)}  누적 단지 {len(found)}개  상한도달 {caps}회")
    time.sleep(0.03)

print(f"\n검색 완료 — 격자점 {calls}개, 45건 상한 도달 {caps}회")
print(f"지구 안 아파트 단지 {len(found)}개")

cur = pd.read_csv(f"{PROJ}/위례신도시_단지.csv")
have = set(cur["단지명"])
new = sorted(set(found) - have)
gone = sorted(have - set(found))

print(f"\n기존 {len(cur)}개 대비")
print(f"  신규 발견 {len(new)}개:")
for n in new:
    d = found[n][0]
    print(f"    + {n:<32} {d.get('address_name','')}")
print(f"  이번에 안 잡힌 기존 {len(gone)}개: {gone if gone else '없음'}")

json.dump({n: [{"place_name": d["place_name"], "x": d["x"], "y": d["y"],
                "address_name": d.get("address_name", ""),
                "road_address_name": d.get("road_address_name", "")}
               for d in v] for n, v in found.items()},
          open("/private/tmp/claude-501/-Users-hoyun-Documents-GitHub-location-analysis/"
               "39a46c99-18b1-4973-a741-111d6f5c06e5/scratchpad/resweep.json",
               "w", encoding="utf-8"), ensure_ascii=False)
print("\n저장: resweep.json")
