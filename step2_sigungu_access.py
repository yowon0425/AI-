"""2단계 B: 시군 중심점 → 최근접 고속철역·서울·대도시 승용차 시간 (카카오모빌리티 길찾기)

입력:
  raw/sgis/.../bnd_sigungu_00_2025_2Q.shp  SGIS 시군구 경계 (2025년 2분기, EPSG:5179)
  sigungu_base.csv                          10/14 산출물 (시군 목록·코드)
  ../A/station_coords.csv                   A의 10/14 산출물 (KTX역 69개 좌표) — 덕소 뺀 68개를 시군별 최근접 KTX역 후보로
  ../A/station_features.csv                 A의 10/15 산출물 (학습용 KTX역 39개) — 역 소재 시군 → 서울 (station_car_seoul)
출력:
  sigungu_boundary.gpkg   시군 단위로 합친 경계 (지도용)
  sigungu_access.csv      시군별 중심점, 최근접 KTX역 접근시간, 서울·대도시 승용차 시간
  station_car_seoul.csv   역 소재 시군 → 서울 승용차 시간 (A의 열차/승용차 시간비용)

카카오 키: B/.env 의 kakao_rest_api_key
실행:
  python step2_sigungu_access.py               (출발시각 = 다가오는 화요일 10:00)
  python step2_sigungu_access.py 202610201000  (출발시각 직접 지정, YYYYMMDDHHMM)
같은 요청은 raw/kakao_route_cache.json 에 저장해 두고 재실행 시 다시 부르지 않음
"""
import datetime as dt
import glob
import json
import os
import sys
import time

import geopandas as gpd
import pandas as pd
import requests
from dotenv import dotenv_values
from shapely.geometry import Point

KEY = dotenv_values(".env").get("kakao_rest_api_key", "").strip()
if not KEY:
    sys.exit("B/.env 에 kakao_rest_api_key 가 없습니다.")
HEADERS = {"Authorization": f"KakaoAK {KEY}"}
URL = "https://apis-navi.kakaomobility.com/v1/future/directions"


def next_tuesday_10():
    d = dt.date.today() + dt.timedelta(days=1)
    while d.weekday() != 1:
        d += dt.timedelta(days=1)
    return d.strftime("%Y%m%d") + "1000"


DEPART = sys.argv[1] if len(sys.argv) > 1 else next_tuesday_10()
N_STATION = 3  # 직선거리 가까운 역 3개를 길찾기로 비교
N_METRO = 2

SGIS_SIDO = {"11": "서울", "21": "부산", "22": "대구", "23": "인천", "24": "광주", "25": "대전", "26": "울산",
             "29": "세종", "31": "경기", "32": "강원", "33": "충북", "34": "충남", "35": "전북", "36": "전남",
             "37": "경북", "38": "경남", "39": "제주"}
SHORT = {"서울특별시": "서울", "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
         "전북특별자치도": "전북", "전남광주통합특별시": "전남", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남"}
# 대도시 = 특별·광역시청 (OpenStreetMap 좌표)
METRO = {"서울": (126.9784204, 37.5667893), "부산": (129.0752054, 35.1799421), "대구": (128.6019174, 35.8715082),
         "인천": (126.7052408, 37.4561224), "광주": (126.8514, 35.1601), "대전": (127.3849608, 36.3505508),
         "울산": (129.3112519, 35.5395077)}

# ---------- 카카오 길찾기 (캐시) ----------
CACHE_F = "raw/kakao_route_cache.json"
cache = json.load(open(CACHE_F, encoding="utf-8")) if os.path.exists(CACHE_F) else {}
n_call = 0


SHIFTS = [(0, 0), (0.003, 0), (-0.003, 0), (0, 0.003), (0, -0.003), (0.006, 0.006), (-0.006, -0.006),
          (0.006, -0.006), (-0.006, 0.006), (0.012, 0), (-0.012, 0), (0, 0.012), (0, -0.012)]  # 약 0.3~1.2km
FROM_ORIGIN = {102, 105}  # 출발지 주변 도로 없음 / 출발지 주변 교통 장애
FROM_DEST = {103, 106}    # 도착지 주변 도로 없음 / 도착지 주변 교통 장애


def route(o, d):
    """o, d = (경도, 위도) → (분, km). 출발·도착점 주변 도로 문제(102,103,105,106)면
    문제 쪽 점을 조금씩 옮겨 다시 시도. 끝내 실패하면 (None, None)"""
    res = route1(o, d)
    for dx, dy in SHIFTS[1:]:
        if res[0] is not None or len(res) < 3:
            break
        if res[2] in FROM_ORIGIN:
            res = route1((o[0] + dx, o[1] + dy), d)
        elif res[2] in FROM_DEST:
            res = route1(o, (d[0] + dx, d[1] + dy))
        else:
            break
    return res[0], res[1]


def route1(o, d):
    global n_call
    k = f"{o[0]:.6f},{o[1]:.6f}|{d[0]:.6f},{d[1]:.6f}|{DEPART}"
    if k not in cache:
        for attempt in range(3):
            try:
                r = requests.get(URL, headers=HEADERS, timeout=15, params={
                    "origin": f"{o[0]},{o[1]}", "destination": f"{d[0]},{d[1]}",
                    "departure_time": DEPART, "summary": "true"})
                r.raise_for_status()
                rt = r.json()["routes"][0]
                break
            except (requests.RequestException, KeyError) as e:
                if attempt == 2:
                    raise
                time.sleep(2)
        n_call += 1
        if rt["result_code"] == 0:
            cache[k] = [rt["summary"]["duration"] / 60, rt["summary"]["distance"] / 1000]
        elif rt["result_code"] == 104:  # 출발지·도착지 5m 이내
            cache[k] = [0.0, 0.0]
        else:
            cache[k] = [None, None, rt["result_code"], rt["result_msg"]]
        if n_call % 50 == 0:
            json.dump(cache, open(CACHE_F, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"  ... API {n_call}회")
        time.sleep(0.05)
    return cache[k]


# ---------- 1. 경계 → 시군 단위 중심점 ----------
shp = glob.glob("raw/sgis/**/bnd_sigungu_*.shp", recursive=True)[0]
g = gpd.read_file(shp)
g["시도"] = g["SIGUNGU_CD"].str[:2].map(SGIS_SIDO)
g["시군"] = g["SIGUNGU_NM"].str.split(" ").str[0]  # '수원시 장안구' → '수원시'
g.loc[g["시도"] == "세종", "시군"] = "세종특별자치시"  # SGIS 표기 '세종시'
sg = g.dissolve(by=["시도", "시군"], as_index=False)[["시도", "시군", "geometry"]]

base = pd.read_csv("sigungu_base.csv", dtype={"시군코드": str})[["시군코드", "시도", "시군"]]
sg = base.merge(sg, on=["시도", "시군"], how="left", validate="1:1")
assert sg["geometry"].notna().all(), f"경계 매칭 실패: {sg[sg.geometry.isna()][['시도', '시군']].values.tolist()}"
sg = gpd.GeoDataFrame(sg, geometry="geometry", crs=g.crs)


# 중심점 = 행정동 인구가중 중심 (도형 무게중심은 산·바다에 떨어져 길찾기가 실패하고, 주민 기준 접근성도 못 나타냄)
#   행정동 경계(2025.2Q) × SGIS 2024 행정동 총인구(to_in_001)
#   가중 중심이 시군 경계 밖이면(섬 지역) 인구 최다 행정동 내부점 사용
dong = gpd.read_file(glob.glob("raw/sgis/**/bnd_dong_*.shp", recursive=True)[0])
pop_f = glob.glob("raw/sgis/**/*인구총괄(총인구).csv", recursive=True)[0]
dpop = pd.read_csv(pop_f, encoding="cp949", dtype={"행정구역코드": str})
dpop = dpop[(dpop["통계항목"] == "to_in_001") & (dpop["행정구역코드"].str.len() == 8)]
dong = dong.merge(dpop[["행정구역코드", "통계값"]], left_on="ADM_CD", right_on="행정구역코드", how="left")
print(f"행정동 {len(dong)}개 중 인구 매칭 {dong['통계값'].notna().sum()}개")
dong["인구"] = dong["통계값"].fillna(0)
rp = dong.geometry.representative_point()
dong["px"], dong["py"] = rp.x, rp.y
dong["SIGUNGU_CD"] = dong["ADM_CD"].str[:5]
dong = pd.DataFrame(dong.drop(columns="geometry")).merge(g[["SIGUNGU_CD", "시도", "시군"]], on="SIGUNGU_CD")


def center(grp, geom):
    w = grp["인구"].sum()
    t = grp.loc[grp["인구"].idxmax()]
    top = Point(t["px"], t["py"])
    c = Point((grp["px"] * grp["인구"]).sum() / w, (grp["py"] * grp["인구"]).sum() / w) if w > 0 else geom.centroid
    if geom.contains(c):
        return c, top, "인구가중 중심"
    return top, top, "인구 최다 행정동"


pts = {k: center(grp, sg.set_index(["시도", "시군"]).geometry[k]) for k, grp in dong.groupby(["시도", "시군"])}
keys = list(zip(sg["시도"], sg["시군"]))
sg["중심점_방법"] = [pts[k][2] for k in keys]
for col, idx in (("", 0), ("대체_", 1)):
    p = gpd.GeoSeries([pts[k][idx] for k in keys], crs=g.crs)
    sg[f"{col}x5179"], sg[f"{col}y5179"] = p.x.values, p.y.values
    w = p.to_crs(4326)
    sg[f"{col}경도"], sg[f"{col}위도"] = w.x.round(6).values, w.y.round(6).values
sg[["시군코드", "시도", "시군", "geometry"]].to_file("sigungu_boundary.gpkg", driver="GPKG")

# ---------- 2. KTX역 목록: A의 10/15 산출물 station_features.csv (학습용 역) ----------
a = pd.read_csv("../A/station_features.csv")
METRO_SIDO = {"서울", "부산", "대구", "인천", "광주", "대전", "울산"}


def sido_short(full, sgg):
    if full == "전남광주통합특별시":  # 2026 통합 — 자치구는 광주, 나머지는 전남
        return "광주" if str(sgg).endswith("구") else "전남"
    return SHORT.get(full, full[:2])


a["시도"] = [sido_short(s, g_) for s, g_ in zip(a["시도_전체"], a["시군구"])]
# 역 소재 시군: 광역시는 자치구·군, 세종은 세종특별자치시, 그 외는 시·군 ('창원시 의창구' → '창원시')
a["시군"] = [g_ if s in METRO_SIDO else ("세종특별자치시" if s == "세종" else g_.split(" ")[0])
            for s, g_ in zip(a["시도"], a["시군구"])]
st = a[["역명", "시도", "시군"]].drop_duplicates("역명").reset_index(drop=True)  # 역 소재 시군 → 서울 (4번)

# 최근접 KTX역 후보: A station_coords.csv 69개 역 중 덕소 제외 → 68개 역 (10/17 사용자 결정)
EXCLUDE_STATIONS = {"덕소"}
c = pd.read_csv("../A/station_coords.csv")
c = c[~c["역명"].isin(EXCLUDE_STATIONS)]
st_all = c[["역명", "경도", "위도"]].drop_duplicates("역명").reset_index(drop=True)
st_xy = gpd.GeoSeries(gpd.points_from_xy(st_all["경도"], st_all["위도"]), crs=4326).to_crs(g.crs)
st_all["x5179"], st_all["y5179"] = st_xy.x.values, st_xy.y.values
print(f"시군 {len(sg)}개, 최근접 후보 KTX역 {len(st_all)}개 (A station_coords), "
      f"역 소재 시군 {len(st)}개 역 (A station_features), 출발시각 {DEPART}")

metro = pd.DataFrame([(k, *v) for k, v in METRO.items()], columns=["도시", "경도", "위도"])
m_xy = gpd.GeoSeries(gpd.points_from_xy(metro["경도"], metro["위도"]), crs=4326).to_crs(g.crs)
metro["x5179"], metro["y5179"] = m_xy.x.values, m_xy.y.values


def nearest(row, cand, n):
    d = ((cand["x5179"] - row["x5179"]) ** 2 + (cand["y5179"] - row["y5179"]) ** 2) ** 0.5 / 1000
    return cand.assign(직선km=d).nsmallest(n, "직선km")


# ---------- 3. 시군별 접근시간 ----------
def measure(r, pre=""):
    o = (r[f"{pre}경도"], r[f"{pre}위도"])
    xy = {"x5179": r[f"{pre}x5179"], "y5179": r[f"{pre}y5179"]}
    best = None
    for _, s in nearest(xy, st_all, N_STATION).iterrows():
        t, km = route(o, (s["경도"], s["위도"]))
        if t is not None and (best is None or t < best[1]):
            best = (s["역명"], t, km, s["직선km"])
    seoul = route(o, METRO["서울"])
    bm = None
    for _, m in nearest(xy, metro, N_METRO).iterrows():
        t, km = route(o, (m["경도"], m["위도"]))
        if t is not None and (bm is None or t < bm[1]):
            bm = (m["도시"], t, km)
    return o, best, seoul, bm


rows = []
for _, r in sg.iterrows():
    method = r["중심점_방법"]
    o, best, (seoul_t, seoul_km), bm = measure(r)
    if seoul_t is None and method == "인구가중 중심":  # 가중 중심 주변에 도로가 없으면 인구 최다 행정동으로
        o, best, (seoul_t, seoul_km), bm = measure(r, "대체_")
        method = "인구 최다 행정동 (가중 중심 도로 없음)"
    rows.append({
        "시군코드": r["시군코드"], "시도": r["시도"], "시군": r["시군"],
        "중심_경도": o[0], "중심_위도": o[1], "중심점_방법": method,
        "최근접KTX역": best[0] if best else None,
        "KTX역_직선거리_km": best[3] if best else None,
        "KTX역_접근시간_분": best[1] if best else None,
        "KTX역_도로거리_km": best[2] if best else None,
        "서울_승용차시간_분": seoul_t, "서울_도로거리_km": seoul_km,
        "최근접대도시": bm[0] if bm else None,
        "대도시_승용차시간_분": bm[1] if bm else None, "대도시_도로거리_km": bm[2] if bm else None,
    })
json.dump(cache, open(CACHE_F, "w", encoding="utf-8"), ensure_ascii=False)

out = pd.DataFrame(rows)
out["비고"] = ""
out.loc[out["KTX역_접근시간_분"].isna(), "비고"] = "길찾기 실패"
# 본토와 도로로 이어지지 않아 카카오 경로에 카페리 구간이 들어감 → 철도 공백 지수에서 제외 권장
ISLAND = {("제주", "제주시"), ("제주", "서귀포시"), ("경북", "울릉군")}
out.loc[[(s, g_) in ISLAND for s, g_ in zip(out["시도"], out["시군"])], "비고"] = "섬: 카페리 포함 경로, 공백 지수 제외 권장"
out.loc[out["중심점_방법"] != "인구가중 중심", "비고"] = (out["비고"] + " 중심점=인구 최다 행정동(가중 중심이 경계 밖·도로 없음)").str.strip()
num = [c for c in out.columns if c.endswith(("_분", "_km"))]
out[num] = out[num].astype(float).round(1)
out.to_csv("sigungu_access.csv", index=False, encoding="utf-8-sig")

# ---------- 4. 역 소재 시군 → 서울 승용차 시간 (노션 2단계 B, A의 열차/승용차 시간비용) ----------
scs = st[["역명", "시도", "시군"]].merge(
    out[["시군코드", "시도", "시군", "서울_승용차시간_분", "서울_도로거리_km"]], on=["시도", "시군"], how="left", validate="m:1")
assert scs["시군코드"].notna().all(), f"역 소재 시군 매칭 실패: {scs[scs['시군코드'].isna()][['역명', '시도', '시군']].values.tolist()}"
scs = scs.rename(columns={"서울_승용차시간_분": "시군_서울_승용차시간_분", "서울_도로거리_km": "시군_서울_도로거리_km"})
scs.to_csv("station_car_seoul.csv", index=False, encoding="utf-8-sig")

print(f"완료: API 호출 {n_call}회 (나머지는 캐시)")
print(out.describe().T[["mean", "min", "max"]].round(1).to_string())
print("\n[KTX역 접근시간 상위 15]")
print(out.nlargest(15, "KTX역_접근시간_분")[["시도", "시군", "최근접KTX역", "KTX역_접근시간_분", "서울_승용차시간_분"]].to_string(index=False))
print("\n[비고]")
print(out[out["비고"] != ""][["시도", "시군", "최근접KTX역", "KTX역_접근시간_분", "비고"]].to_string(index=False))
