"""창곡동 506 반경 2km 아파트 단지 탐색."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import math
import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(f"{ROOT}/.env")
KEY = os.getenv("KAKAO_REST_API_KEY")
BASE = "https://dapi.kakao.com/v2/local"
H = {"Authorization": f"KakaoAK {KEY}"}
pd.set_option("display.width", 240)

CENTER_ADDR = "경기 성남시 수정구 창곡동 506"
RADIUS = 2000


def geocode(addr):
    r = requests.get(f"{BASE}/search/address.json", headers=H,
                     params={"query": addr, "size": 1})
    r.raise_for_status()
    d = r.json()["documents"]
    if not d:
        return None
    return {"lng": float(d[0]["x"]), "lat": float(d[0]["y"]),
            "address_name": d[0]["address_name"]}


def keyword(query, lng, lat, radius, page=1, size=15):
    r = requests.get(f"{BASE}/search/keyword.json", headers=H,
                     params={"query": query, "x": lng, "y": lat,
                             "radius": radius, "page": page, "size": size,
                             "sort": "distance"})
    r.raise_for_status()
    return r.json()


def collect(query, lng, lat, radius):
    """키워드 검색을 페이지 끝까지 모은다 (카카오 상한 45건)."""
    out, meta = [], None
    for p in range(1, 4):
        b = keyword(query, lng, lat, radius, page=p)
        meta = b["meta"]
        out.extend(b["documents"])
        if b["meta"]["is_end"]:
            break
    return out, meta


def haversine(lng1, lat1, lng2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


site = geocode(CENTER_ADDR)
if site is None:
    sys.exit("기준 주소를 찾지 못했습니다.")
print(f"기준점: {site['address_name']}  ({site['lng']:.6f}, {site['lat']:.6f})")
print()

# ── 1. 단일 검색으로 규모 파악 ──────────────────────────────────
docs, meta = collect("아파트", site["lng"], site["lat"], RADIUS)
print("=" * 100)
print("[1] 단일 키워드 검색 — 규모 파악")
print("=" * 100)
print(f"  카카오가 보고한 총 건수 total_count = {meta['total_count']}")
print(f"  실제 받은 건수                      = {len(docs)}  (카카오 상한 45)")
print(f"  → 격자 분할이 필요한가: {'예' if meta['total_count'] > 45 else '아니오'}")

cats = pd.Series([d.get("category_name", "") for d in docs]).value_counts()
print("\n  category_name 분포:")
for k, v in cats.items():
    print(f"    {v:>3}건  {k}")

print("\n  샘플 5건:")
for d in docs[:5]:
    print(f"    {d['place_name']:<28} | {d.get('road_address_name','')} "
          f"| {d.get('address_name','')} | {d['distance']}m")

# ── 2. 격자 분할 검색 ───────────────────────────────────────────
print()
print("=" * 100)
print("[2] 격자 분할 검색 — 상한 우회")
print("=" * 100)

# 중심 + 6방향 링 2겹으로 덮는다 (반경 700m 원들로 2km 를 덮음)
SUB_R = 700
pts = [(site["lng"], site["lat"])]
m_lat = 111320.0
m_lng = 111320.0 * math.cos(math.radians(site["lat"]))
for ring_r in (900, 1600):
    n = 6 if ring_r == 900 else 12
    for i in range(n):
        th = 2 * math.pi * i / n
        pts.append((site["lng"] + ring_r * math.cos(th) / m_lng,
                    site["lat"] + ring_r * math.sin(th) / m_lat))

print(f"  서브 검색점 {len(pts)}개 × 반경 {SUB_R}m")

seen, rows, calls = {}, [], 0
for lng, lat in pts:
    for q in ("아파트",):
        d, mt = collect(q, lng, lat, SUB_R)
        calls += 1
        for x in d:
            if "아파트" not in x.get("category_name", ""):
                continue
            pid = x["id"]
            if pid in seen:
                continue
            dist = haversine(site["lng"], site["lat"],
                             float(x["x"]), float(x["y"]))
            if dist > RADIUS:
                continue
            seen[pid] = True
            rows.append({"단지명": x["place_name"],
                         "지번주소": x.get("address_name", ""),
                         "도로명주소": x.get("road_address_name", ""),
                         "lng": float(x["x"]), "lat": float(x["y"]),
                         "중심거리_m": round(dist), "id": pid,
                         "category": x.get("category_name", "")})

df = pd.DataFrame(rows).sort_values("중심거리_m").reset_index(drop=True)
print(f"  API 호출 {calls}회(페이지 제외) → 중복 제거 후 {len(df)}건")
print()
print(df[["단지명", "지번주소", "중심거리_m"]].to_string())

df.to_csv("/private/tmp/claude-501/-Users-hoyun-Documents-GitHub-location-analysis/"
          "39a46c99-18b1-4973-a741-111d6f5c06e5/scratchpad/apts_raw.csv",
          index=False, encoding="utf-8-sig")
print("\n저장: apts_raw.csv")
