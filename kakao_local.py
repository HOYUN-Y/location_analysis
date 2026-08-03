"""카카오 로컬(Local) API 예시 클라이언트.

지원 기능
  - 주소 검색      : /v2/local/search/address.json
  - 지오코딩       : 주소 검색 결과에서 좌표만 추출
  - 역지오코딩     : /v2/local/geo/coord2address.json
  - 행정구역 조회  : /v2/local/geo/coord2regioncode.json
  - 키워드 검색    : /v2/local/search/keyword.json
  - 카테고리 검색  : /v2/local/search/category.json

인증: REST API 키를 환경변수 KAKAO_REST_API_KEY 로 전달한다.
      프로젝트 루트의 .env 파일도 자동으로 읽는다(python-dotenv).
      (키를 코드에 하드코딩하지 말 것)

좌표계 주의: 카카오 API는 x=경도(longitude), y=위도(latitude) 순서다.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import requests

try:  # python-dotenv 는 없어도 환경변수만으로 동작하도록 선택 의존성 처리
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_URL = "https://dapi.kakao.com/v2/local"

_env_loaded = False


def _ensure_env_loaded() -> None:
    """.env 를 환경변수로 로드한다(최초 1회, 이미 설정된 값은 덮어쓰지 않음)."""
    global _env_loaded
    if _env_loaded or load_dotenv is None:
        return

    local_env = Path(__file__).with_name(".env")
    if local_env.is_file():
        load_dotenv(local_env)
    else:
        load_dotenv()  # 현재 위치에서 상위 디렉토리로 올라가며 탐색
    _env_loaded = True

# 카테고리 그룹 코드 (키워드/카테고리 검색에서 사용)
CATEGORY_GROUP = {
    "대형마트": "MT1",
    "편의점": "CS2",
    "어린이집·유치원": "PS3",
    "학교": "SC4",
    "학원": "AC5",
    "주차장": "PK6",
    "주유소·충전소": "OL7",
    "지하철역": "SW8",
    "은행": "BK9",
    "문화시설": "CT1",
    "중개업소": "AG2",
    "공공기관": "PO3",
    "관광명소": "AT4",
    "숙박": "AD5",
    "음식점": "FD6",
    "카페": "CE7",
    "병원": "HP8",
    "약국": "PM9",
}


class KakaoAPIError(RuntimeError):
    """카카오 API가 2xx 이외 응답을 돌려줬을 때."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code


@dataclass
class Place:
    """검색 결과 1건을 다루기 쉽게 정리한 형태."""

    name: str
    address: str          # 지번 주소
    road_address: str     # 도로명 주소
    lng: float            # 경도 (x)
    lat: float            # 위도 (y)
    category: str = ""
    phone: str = ""
    url: str = ""
    distance_m: int | None = None  # 중심 좌표를 준 경우에만 채워진다

    @classmethod
    def from_keyword_doc(cls, doc: dict[str, Any]) -> "Place":
        distance = doc.get("distance")
        return cls(
            name=doc.get("place_name", ""),
            address=doc.get("address_name", ""),
            road_address=doc.get("road_address_name", ""),
            lng=float(doc["x"]),
            lat=float(doc["y"]),
            category=doc.get("category_name", ""),
            phone=doc.get("phone", ""),
            url=doc.get("place_url", ""),
            distance_m=int(distance) if distance else None,
        )


class KakaoLocalClient:
    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 5.0,
        max_retries: int = 2,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key:
            _ensure_env_loaded()
        key = api_key or os.getenv("KAKAO_REST_API_KEY")
        if not key:
            raise ValueError(
                "REST API 키가 없습니다. .env 에 KAKAO_REST_API_KEY 를 넣거나 "
                "환경변수로 설정하세요. (.env.example 참고)"
            )
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"KakaoAK {key}"})

    # ------------------------------------------------------------------
    # 내부 공통 요청
    # ------------------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        # None 값은 쿼리스트링에서 제외
        params = {k: v for k, v in params.items() if v is not None}
        url = f"{BASE_URL}{path}"

        for attempt in range(self.max_retries + 1):
            try:
                res = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
                if attempt == self.max_retries:
                    raise
                time.sleep(0.5 * (attempt + 1))
                continue

            # 429(쿼터 초과)·5xx 는 잠깐 쉬고 재시도
            if res.status_code == 429 or res.status_code >= 500:
                if attempt == self.max_retries:
                    raise KakaoAPIError(res.status_code, res.text)
                time.sleep(1.0 * (attempt + 1))
                continue

            if res.status_code != 200:
                raise KakaoAPIError(res.status_code, res.text)

            return res.json()

        raise KakaoAPIError(0, "요청 실패")  # 도달하지 않음

    # ------------------------------------------------------------------
    # 1) 주소 검색
    # ------------------------------------------------------------------
    def search_address(
        self,
        query: str,
        page: int = 1,
        size: int = 10,          # 1~30
        analyze_type: str | None = None,  # "similar"(기본) | "exact"
    ) -> dict[str, Any]:
        """주소 문자열로 검색한다. 원본 응답(meta + documents)을 그대로 반환."""
        return self._get(
            "/search/address.json",
            {"query": query, "page": page, "size": size, "analyze_type": analyze_type},
        )

    # ------------------------------------------------------------------
    # 2) 지오코딩 (주소 -> 좌표)
    # ------------------------------------------------------------------
    def geocode(self, address: str) -> dict[str, Any] | None:
        """주소를 좌표로 변환한다. 결과가 없으면 None."""
        data = self.search_address(address, size=1)
        docs = data.get("documents", [])
        if not docs:
            return None

        doc = docs[0]
        road = doc.get("road_address") or {}
        jibun = doc.get("address") or {}
        return {
            "input": address,
            "lng": float(doc["x"]),
            "lat": float(doc["y"]),
            "address_name": doc.get("address_name", ""),
            "road_address": road.get("address_name", ""),
            "jibun_address": jibun.get("address_name", ""),
            "zone_no": road.get("zone_no", ""),        # 우편번호
            "region_1depth": jibun.get("region_1depth_name") or road.get("region_1depth_name", ""),
            "region_2depth": jibun.get("region_2depth_name") or road.get("region_2depth_name", ""),
            "region_3depth": jibun.get("region_3depth_name") or road.get("region_3depth_name", ""),
            "building_name": road.get("building_name", ""),
        }

    def geocode_many(self, addresses: list[str], delay: float = 0.05) -> list[dict[str, Any] | None]:
        """여러 주소를 순차 지오코딩. delay 로 호출 간격을 준다(쿼터 보호)."""
        results: list[dict[str, Any] | None] = []
        for addr in addresses:
            results.append(self.geocode(addr))
            if delay:
                time.sleep(delay)
        return results

    # ------------------------------------------------------------------
    # 3) 역지오코딩 (좌표 -> 주소 / 행정구역)
    # ------------------------------------------------------------------
    def reverse_geocode(self, lng: float, lat: float) -> dict[str, Any] | None:
        """좌표를 주소로 변환한다."""
        data = self._get("/geo/coord2address.json", {"x": lng, "y": lat})
        docs = data.get("documents", [])
        if not docs:
            return None

        doc = docs[0]
        road = doc.get("road_address") or {}
        jibun = doc.get("address") or {}
        return {
            "road_address": road.get("address_name", ""),
            "jibun_address": jibun.get("address_name", ""),
            "zone_no": road.get("zone_no", ""),
            "building_name": road.get("building_name", ""),
        }

    def coord_to_region(self, lng: float, lat: float) -> list[dict[str, Any]]:
        """좌표의 행정동/법정동 정보를 반환한다(행정코드 포함)."""
        data = self._get("/geo/coord2regioncode.json", {"x": lng, "y": lat})
        return data.get("documents", [])

    # ------------------------------------------------------------------
    # 4) 키워드 검색
    # ------------------------------------------------------------------
    def search_keyword(
        self,
        query: str,
        lng: float | None = None,
        lat: float | None = None,
        radius: int | None = None,        # 중심 좌표 기준 반경(m), 0~20000
        page: int = 1,                    # 1~45
        size: int = 15,                   # 1~15
        category_group_code: str | None = None,
        sort: str | None = None,          # "accuracy"(기본) | "distance"
    ) -> dict[str, Any]:
        """키워드로 장소를 검색한다. 원본 응답을 반환."""
        return self._get(
            "/search/keyword.json",
            {
                "query": query,
                "x": lng,
                "y": lat,
                "radius": radius,
                "page": page,
                "size": size,
                "category_group_code": category_group_code,
                "sort": sort,
            },
        )

    def search_category(
        self,
        category_group_code: str,
        lng: float,
        lat: float,
        radius: int = 1000,
        page: int = 1,
        size: int = 15,
        sort: str = "distance",
    ) -> dict[str, Any]:
        """카테고리 코드로 주변 장소를 검색한다(반경 검색 시 좌표 필수)."""
        return self._get(
            "/search/category.json",
            {
                "category_group_code": category_group_code,
                "x": lng,
                "y": lat,
                "radius": radius,
                "page": page,
                "size": size,
                "sort": sort,
            },
        )

    # ------------------------------------------------------------------
    # 5) 페이지네이션 헬퍼
    # ------------------------------------------------------------------
    def iter_keyword(
        self,
        query: str,
        max_results: int = 45,
        delay: float = 0.05,
        **kwargs: Any,
    ) -> Iterator[Place]:
        """키워드 검색 결과를 Place 로 변환해 순회한다.

        주의: 카카오 키워드/카테고리 검색은 조건당 최대 45건까지만 노출된다.
              더 많이 모으려면 반경을 쪼개거나 키워드를 나눠야 한다.
        """
        kwargs.pop("page", None)
        size = min(int(kwargs.pop("size", 15)), 15)

        count = 0
        for page in range(1, 46):
            data = self.search_keyword(query, page=page, size=size, **kwargs)
            for doc in data.get("documents", []):
                yield Place.from_keyword_doc(doc)
                count += 1
                if count >= max_results:
                    return
            if data.get("meta", {}).get("is_end", True):
                return
            if delay:
                time.sleep(delay)


# ----------------------------------------------------------------------
# 실행 예시
# ----------------------------------------------------------------------
def _demo() -> None:
    client = KakaoLocalClient()

    print("=" * 60)
    print("1) 주소 검색")
    print("=" * 60)
    res = client.search_address("판교역로 235", size=3)
    for doc in res["documents"]:
        road = doc.get("road_address") or {}
        print(f"  - {doc['address_name']}  (도로명: {road.get('address_name', '-')})")
        print(f"    좌표: lng={doc['x']}, lat={doc['y']}")

    print()
    print("=" * 60)
    print("2) 지오코딩 (주소 -> 좌표)")
    print("=" * 60)
    geo = client.geocode("경기도 성남시 분당구 판교역로 235")
    if geo:
        print(f"  입력  : {geo['input']}")
        print(f"  좌표  : ({geo['lat']}, {geo['lng']})")
        print(f"  도로명: {geo['road_address']} ({geo['zone_no']})")
        print(f"  건물  : {geo['building_name'] or '-'}")
    else:
        print("  결과 없음")

    print()
    print("=" * 60)
    print("3) 역지오코딩 (좌표 -> 주소)")
    print("=" * 60)
    if geo:
        rev = client.reverse_geocode(geo["lng"], geo["lat"])
        print(f"  도로명: {rev['road_address']}")
        print(f"  지번  : {rev['jibun_address']}")

        region = client.coord_to_region(geo["lng"], geo["lat"])
        for r in region:
            print(f"  {r['region_type']}: {r['address_name']} (code={r['code']})")

    print()
    print("=" * 60)
    print("4) 키워드 검색 (반경 1km 카페)")
    print("=" * 60)
    if geo:
        places = client.iter_keyword(
            "카페",
            lng=geo["lng"],
            lat=geo["lat"],
            radius=1000,
            sort="distance",
            category_group_code=CATEGORY_GROUP["카페"],
            max_results=10,
        )
        for i, p in enumerate(places, 1):
            print(f"  {i:2d}. {p.name} — {p.distance_m}m")
            print(f"      {p.road_address or p.address}")

    print()
    print("=" * 60)
    print("5) 카테고리 검색 (반경 1km 지하철역)")
    print("=" * 60)
    if geo:
        res = client.search_category(
            CATEGORY_GROUP["지하철역"], geo["lng"], geo["lat"], radius=1000
        )
        for doc in res["documents"]:
            print(f"  - {doc['place_name']} ({doc['distance']}m)")


if __name__ == "__main__":
    try:
        _demo()
    except (ValueError, KakaoAPIError) as e:
        print(f"오류: {e}")
