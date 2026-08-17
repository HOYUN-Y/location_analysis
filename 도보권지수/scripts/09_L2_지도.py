"""L2(T맵 실경로) 기준 지도 — 새 파일로 생성. 기존 지도는 건드리지 않는다."""

# ── 경로 (이 스크립트 위치 기준으로 해결) ──────────────────────
import pathlib as _pl
HERE = _pl.Path(__file__).resolve().parent      # 도보권지수/scripts
PROJ = str(HERE.parent)                         # 도보권지수  — 데이터·산출물
SCRATCH = str(HERE)                             # 중간 파일
ROOT = str(HERE.parent.parent)                  # 저장소 루트 — .env

import json

import folium
import pandas as pd
from folium.plugins import PolyLineTextPath
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform as sh_transform


TX, TY = 127.141834, 37.473023
TARGET = "위례중앙역(가정) — 창곡동 506"

# 검증 통과한 순차 램프 (연함 → 진함 = 지수 낮음 → 높음)
BINS = [(80, "#184f95", "80점 이상"), (60, "#2a78d6", "60 ~ 80"),
        (40, "#5598e7", "40 ~ 60"), (20, "#9ec5f4", "20 ~ 40"),
        (0, "#cde2fb", "20점 미만")]
ROUTE, STRAIGHT, INK, MUTED = "#eb6834", "#898781", "#0b0b0b", "#898781"


def color(v):
    for lo, c, _ in BINS:
        if v >= lo:
            return c
    return BINS[-1][1]


df = pd.read_csv(f"{PROJ}/위례신도시_도보권지수_L2.csv")
gj = json.load(open(f"{PROJ}/위례신도시_단지.geojson", encoding="utf-8"))
geoms = {f["properties"]["단지명"]: shape(f["geometry"]) for f in gj["features"]}
routes = {f["properties"]["단지명"]: f["geometry"]["coordinates"]
          for f in json.load(open(f"{PROJ}/위례신도시_보행경로.geojson",
                                  encoding="utf-8"))["features"]}
zone = json.load(open(f"{PROJ}/위례신도시_지구경계.geojson",
                      encoding="utf-8"))["features"][0]

df = df.sort_values("경로_m").reset_index(drop=True)
df["순위"] = df.index + 1

m = folium.Map(location=[TY, TX], zoom_start=14, tiles="CartoDB positron",
               control_scale=True)

folium.GeoJson(zone["geometry"], name="위례신도시 지구경계",
               style_function=lambda _: {"color": "#0b0b0b", "weight": 2,
                                         "dashArray": "6,4", "fill": False}
               ).add_to(m)

g_lot = folium.FeatureGroup(name="단지 (L2 지수별)", show=True).add_to(m)
g_rt = folium.FeatureGroup(name="T맵 실제 보행경로", show=True).add_to(m)
g_st = folium.FeatureGroup(name="직선거리 (비교용)", show=False).add_to(m)
g_lbl = folium.FeatureGroup(name="우회계수 2배 이상 강조", show=True).add_to(m)

for _, r in df.iterrows():
    name = r["단지명"]
    poly_ll = geoms[name]
    c = poly_ll.centroid
    aeqd = f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m +no_defs"
    fwd = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    inv = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True)
    poly = sh_transform(fwd.transform, poly_ll)
    near, _ = nearest_points(poly.boundary, sh_transform(fwd.transform, Point(TX, TY)))
    nlng, nlat = inv.transform(near.x, near.y)

    tip = (f"<b>{r['순위']}위 · {name}</b><br>"
           f"지수 <b>{r['지수_L2']}</b> (L1 {r['지수_L1']}, {r['지수차']:+.1f})<br>"
           f"경로 {r['경로_m']:,}m · 도보 {r['소요_분']}분<br>"
           f"직선 {r['직선_m']:,.0f}m · 우회 <b>×{r['우회계수']}</b><br>"
           f"횡단보도 {r['횡단보도']}회 · 순위변동 {r['순위변동']:+d}")

    folium.GeoJson(poly_ll.__geo_interface__, name=name,
                   style_function=lambda _, col=color(r["지수_L2"]): {
                       "color": col, "weight": 1.2, "fillColor": col,
                       "fillOpacity": 0.75},
                   tooltip=folium.Tooltip(tip)).add_to(g_lot)

    if name in routes and routes[name]:
        line = folium.PolyLine(
            [[[y, x] for x, y in seg] for seg in routes[name]],
            color=ROUTE, weight=2.4, opacity=0.85,
            tooltip=folium.Tooltip(tip))
        line.add_to(g_rt)

    folium.PolyLine([[nlat, nlng], [TY, TX]], color=STRAIGHT, weight=1.2,
                    opacity=0.6, dash_array="4",
                    tooltip=f"{name} 직선 {r['직선_m']:,.0f}m").add_to(g_st)

    if r["우회계수"] >= 2.0:
        folium.Marker(
            [poly_ll.centroid.y, poly_ll.centroid.x],
            icon=folium.DivIcon(html=(
                f'<div style="font:600 11px system-ui;color:#fff;'
                f'background:{ROUTE};padding:2px 6px;border-radius:9px;'
                f'white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.3)">'
                f'×{r["우회계수"]:.1f}</div>'), icon_anchor=(18, 9)),
            tooltip=tip).add_to(g_lbl)

folium.CircleMarker([TY, TX], radius=9, color="#0b0b0b", weight=2,
                    fill=True, fill_color="#eda100", fill_opacity=1,
                    tooltip=TARGET).add_to(m)

legend = """
<div style="position:fixed;bottom:22px;left:22px;z-index:9999;
     background:#fcfcfb;border:1px solid rgba(11,11,11,.12);border-radius:8px;
     padding:12px 14px;font:13px/1.5 system-ui,-apple-system,sans-serif;
     color:#0b0b0b;box-shadow:0 2px 10px rgba(0,0,0,.10)">
  <div style="font-weight:600;margin-bottom:2px">도보권 지수 (L2)</div>
  <div style="color:#52514e;font-size:11px;margin-bottom:8px">
    T맵 실제 보행경로 기준 · 로그로지스틱 d&#8320;=1,000m, &beta;=2.0</div>
  __ROWS__
  <div style="margin-top:9px;padding-top:8px;
       border-top:1px solid rgba(11,11,11,.10);font-size:11.5px;color:#52514e">
    <span style="display:inline-block;width:22px;height:3px;
      background:#eb6834;vertical-align:middle"></span> T맵 보행경로<br>
    <span style="display:inline-block;width:22px;border-top:2px dashed #898781;
      vertical-align:middle"></span> 직선 (레이어에서 켜기)<br>
    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
      background:#eda100;border:2px solid #0b0b0b;vertical-align:middle"></span>
    위례중앙역(가정)
  </div>
</div>"""
rows = "".join(
    f'<div style="margin:3px 0"><span style="display:inline-block;width:15px;'
    f'height:15px;background:{c};border-radius:3px;vertical-align:-3px;'
    f'margin-right:7px"></span>{lab}</div>' for _, c, lab in BINS)
m.get_root().html.add_child(folium.Element(legend.replace("__ROWS__", rows)))

folium.LayerControl(collapsed=False).add_to(m)
out = f"{PROJ}/위례신도시_도보권지수_L2_지도.html"
m.save(out)
print("저장:", out)
print(f"단지 {len(df)}개 / 경로 {sum(1 for n in df['단지명'] if n in routes)}개")
print(f"우회 2배 이상 강조 {(df['우회계수']>=2.0).sum()}개")
