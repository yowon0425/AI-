"""3단계 B (10/17): 신규 구간 후보 비교 → 2~3개 선정, 신규 역 위치·설명변수

입력:
  sigungu_gap.csv            10/16 공백 지수 (순위·고령인구 등)
  sigungu_base.csv           인구·고령화율·1인당 자가용 승용차
  sigungu_access.csv         시군 인구가중 중심, 서울 승용차 시간
  raw/sgis/**/bnd_dong_*.shp, *인구총괄(총인구).csv   신규 역 위치(인구 최다 행정동) 계산
  ../A/station_coords.csv    기존 KTX역 좌표 (연결역)
  ../A/tago_train_all.csv    연결역의 수도권까지 최단분·일일 정차 횟수
출력:
  new_line_candidates.csv    후보 노선 7개 비교표
  new_lines.csv              선정 노선의 역 목록 (연결역 + 신규 역, 순서·누적 연장)
  new_station_features.csv   신규 역 설명변수 (A 수요 모형 입력 형식)

가정 (모두 B 가정, A 10/18 시나리오에서 조정)
  - 신규 역 위치: 그 시군에서 인구가 가장 많은 행정동의 대표점 (보통 읍·시가지)
  - 노선 연장 = 역 사이 직선거리 × 우회계수 1.3
  - 신규 구간 표정속도 120km/h (KTX-이음급, 정차 포함 평균)
  - 서울까지 KTX 시간 = 연결역의 수도권까지 최단분 + 신규 구간 주행 시간
  - 일일 정차 횟수: 기본 20회(안동·영주 수준) / 보수 10회 / 낙관 34회(강릉 수준) — A tago_train_all.csv 기준
선정 규칙: 후보마다 ① 공백지수 평균(높을수록) ② 고령인구 per km(높을수록) ③ 현재 KTX역 접근시간 평균(길수록)
           순위를 매겨 합이 작은 4개 (동점이면 공백지수 평균 높은 쪽)
"""
import glob
import math

import geopandas as gpd
import numpy as np
import pandas as pd

DETOUR = 1.3
SPEED_KMH = 120
N_SELECT = 4  # 10/17 사용자 결정: 규칙 상위 3개 + K2 포함해 4개 (K2는 정부 추진 중 표시)
STOPS = {"기본": 20, "보수": 10, "낙관": 34}

# 후보: (이름, 연결 기존역, 경유 시군 [(시도, 시군)...], 설명)
CANDIDATES = {
    "K1": ("강원 북부 내륙선", "횡성", [("강원", "홍천군"), ("강원", "화천군"), ("강원", "양구군"), ("강원", "인제군")],
           "강릉선 횡성 분기 → 홍천 → 화천 → 양구 → 인제 (접경 지역)"),
    "K2": ("동해 북부선", "강릉", [("강원", "양양군"), ("강원", "속초시"), ("강원", "고성군")],
           "강릉 → 양양 → 속초 → 고성"),
    "K3": ("경북 북부 동서선", "영주", [("경북", "봉화군"), ("경북", "울진군")],
           "중앙선 영주 → 봉화 → 울진"),
    "K4": ("경북 내륙 동해선", "안동", [("경북", "청송군"), ("경북", "영양군"), ("경북", "울진군")],
           "중앙선 안동 → 청송 → 영양 → 울진"),
    "K5": ("강원 남부 폐광지선", "제천", [("강원", "영월군"), ("강원", "정선군"), ("강원", "태백시")],
           "중앙선 제천 → 영월 → 정선 → 태백 (기존 태백선 축)"),
    "K6": ("충남 서해안선", "천안아산", [("충남", "예산군"), ("충남", "서산시"), ("충남", "태안군")],
           "경부고속선 천안아산 → 예산 → 서산 → 태안"),
    "K7": ("전남 서남해안선", "목포", [("전남", "해남군"), ("전남", "완도군")],
           "호남선 목포 → 해남 → 완도"),
}

# 실제 추진 현황 (10/17 웹 검색, 10/19 제5차 국가철도망 비교 때 다시 확인)
STATUS = {
    "K2": "정부 추진 중 — 동해북부선 강릉~제진 단선전철 (기본계획·타당성 평가 단계, 이르면 2028 완공 보도)",
    "K4": "일부 겹침 — 안동~청송은 지자체 건의 '동서횡단철도(홍성~안동~청송~영덕)'와 겹침, 영양·울진 직결 건의는 못 찾음",
    "K6": "확인된 추진·건의 사업 없음 (서산·태안 철도 검색 결과 없음)",
    "K7": "해남은 남해안철도(보성~임성리, 일반철도) 통과, 해남·완도는 '서울~제주 고속철도' 5차 계획 반영 건의",
}


def hav(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


gap = pd.read_csv("sigungu_gap.csv", dtype={"시군코드": str})
base = pd.read_csv("sigungu_base.csv", dtype={"시군코드": str})
acc = pd.read_csv("sigungu_access.csv", dtype={"시군코드": str})
sc = pd.read_csv("../A/station_coords.csv").set_index("역명")
tago = pd.read_csv("../A/tago_train_all.csv").set_index("역명")
key = gap.set_index(["시도", "시군"])

# ---------- 신규 역 위치: 시군별 인구 최다 행정동 대표점 ----------
SGIS_SIDO = {"11": "서울", "21": "부산", "22": "대구", "23": "인천", "24": "광주", "25": "대전", "26": "울산",
             "29": "세종", "31": "경기", "32": "강원", "33": "충북", "34": "충남", "35": "전북", "36": "전남",
             "37": "경북", "38": "경남", "39": "제주"}
need = {k for c in CANDIDATES.values() for k in c[2]}
dong = gpd.read_file(glob.glob("raw/sgis/**/bnd_dong_*.shp", recursive=True)[0])
sgg = gpd.read_file(glob.glob("raw/sgis/**/bnd_sigungu_*.shp", recursive=True)[0])[["SIGUNGU_CD", "SIGUNGU_NM"]]
dpop = pd.read_csv(glob.glob("raw/sgis/**/*인구총괄(총인구).csv", recursive=True)[0], encoding="cp949", dtype={"행정구역코드": str})
dpop = dpop[(dpop["통계항목"] == "to_in_001") & (dpop["행정구역코드"].str.len() == 8)]
dong = dong.merge(dpop[["행정구역코드", "통계값"]], left_on="ADM_CD", right_on="행정구역코드")
dong["SIGUNGU_CD"] = dong["ADM_CD"].str[:5]
dong = dong.merge(sgg, on="SIGUNGU_CD")
dong["시도"] = dong["SIGUNGU_CD"].str[:2].map(SGIS_SIDO)
dong["시군"] = dong["SIGUNGU_NM"].str.split(" ").str[0]
dong = dong[[(s, g_) in need for s, g_ in zip(dong["시도"], dong["시군"])]]
top = dong.loc[dong.groupby(["시도", "시군"])["통계값"].idxmax()].copy()
rp = gpd.GeoSeries(top.geometry.representative_point(), crs=dong.crs).to_crs(4326)
top["역_경도"], top["역_위도"] = rp.x.round(6).values, rp.y.round(6).values
st_pt = top.set_index(["시도", "시군"])[["ADM_NM", "역_경도", "역_위도"]]
assert len(st_pt) == len(need), set(need) - set(st_pt.index)

# ---------- 후보 비교 ----------
rows, line_rows = [], []
for k, (name, hub, towns, desc) in CANDIDATES.items():
    pts = [(hub, "연결역", sc.loc[hub, "경도"], sc.loc[hub, "위도"], None, None)]
    for t in towns:
        p = st_pt.loc[t]
        pts.append((f"{t[1][:-1]}(신설)", "신규", p["역_경도"], p["역_위도"], t, p["ADM_NM"]))
    cum = 0.0
    for i, (nm, kind, x, y, t, adm) in enumerate(pts):
        if i:
            cum += hav(pts[i - 1][2], pts[i - 1][3], x, y) * DETOUR
        line_rows.append({"노선ID": k, "노선명": name, "순서": i, "역명": nm, "구분": kind,
                          "시도": t[0] if t else None, "시군": t[1] if t else None, "역_행정동": adm,
                          "경도": x, "위도": y, "누적연장_km": round(cum, 1)})
    g = key.loc[towns]
    rows.append({"노선ID": k, "노선명": name, "연결역": hub, "경유시군": "·".join(t[1] for t in towns), "설명": desc,
                 "신설역수": len(towns), "연장_km": round(cum, 1),
                 "공백지수_평균": round(g["공백지수"].mean(), 1), "공백순위_최고": int(g["순위"].min()),
                 "공백상위15_포함": int((g["순위"] <= 15).sum()),
                 "인구_2022": int(g["인구_2022"].sum()), "고령인구_2022": int(g["고령인구_2022"].sum()),
                 "고령인구_per_km": round(g["고령인구_2022"].sum() / cum, 0),
                 "현재_KTX역_접근시간_평균": round(g["KTX역_접근시간_분"].mean(), 1)})
cand = pd.DataFrame(rows)
cand["순위_공백"] = cand["공백지수_평균"].rank(ascending=False, method="min").astype(int)
cand["순위_고령per_km"] = cand["고령인구_per_km"].rank(ascending=False, method="min").astype(int)
cand["순위_접근시간"] = cand["현재_KTX역_접근시간_평균"].rank(ascending=False, method="min").astype(int)
cand["순위합"] = cand[["순위_공백", "순위_고령per_km", "순위_접근시간"]].sum(axis=1)
SELECT = cand.sort_values(["순위합", "공백지수_평균"], ascending=[True, False])["노선ID"].head(N_SELECT).tolist()
cand["선정"] = cand["노선ID"].isin(SELECT).map({True: "O", False: ""})
cand["실제_추진현황"] = cand["노선ID"].map(STATUS).fillna("확인 안 함")
cand.to_csv("new_line_candidates.csv", index=False, encoding="utf-8-sig")
lines = pd.DataFrame(line_rows)
lines = lines[lines["노선ID"].isin(SELECT)]
lines.to_csv("new_lines.csv", index=False, encoding="utf-8-sig")

# ---------- 신규 역 설명변수 (A step5 변수와 같은 이름) ----------
acc_k = acc.set_index(["시도", "시군"])
base_k = base.set_index(["시도", "시군"])
feat = []
for _, r in lines[lines["구분"] == "신규"].iterrows():
    t = (r["시도"], r["시군"])
    hub = CANDIDATES[r["노선ID"]][1]
    hub_min = tago.loc[hub, "수도권까지_최단분"]
    ktx_min = hub_min + r["누적연장_km"] / SPEED_KMH * 60
    car_min = acc_k.loc[t, "서울_승용차시간_분"]
    cx, cy = acc_k.loc[t, "중심_경도"], acc_k.loc[t, "중심_위도"]
    feat.append({
        "역명": r["역명"], "노선ID": r["노선ID"], "노선명": r["노선명"], "연결역": hub,
        "시도": t[0], "시군구": t[1], "권역": t[1], "경도": r["경도"], "위도": r["위도"], "역_행정동": r["역_행정동"],
        "배후인구_2022": int(base_k.loc[t, "인구_2022"]), "권역내역수": 1,
        "고령화율_2022": base_k.loc[t, "고령화율_2022"], "인구증감률_2013_2022": base_k.loc[t, "인구증감률_2013_2022"],
        "1인당자가용승용차_2022": base_k.loc[t, "1인당자가용승용차_2022"],
        "연결역까지_km": r["누적연장_km"], "서울까지_최단분": round(ktx_min, 0), "서울까지_승용차분": car_min,
        "시간비": round(ktx_min / car_min, 3),
        "도심거리_km": round(hav(r["경도"], r["위도"], cx, cy), 1),
        "일일_정차횟수": STOPS["기본"], "일일_정차횟수_보수": STOPS["보수"], "일일_정차횟수_낙관": STOPS["낙관"],
        "현재_KTX역_접근시간_분": acc_k.loc[t, "KTX역_접근시간_분"], "공백순위": int(key.loc[t, "순위"]),
        "비고": "정부 추진 중 노선(동해북부선)과 겹침" if r["노선ID"] == "K2" else "",
    })
feat = pd.DataFrame(feat)
feat.to_csv("new_station_features.csv", index=False, encoding="utf-8-sig")

pd.set_option("display.width", 250)
print(cand.drop(columns=["설명", "실제_추진현황"]).to_string(index=False))
print("선정:", SELECT)
print()
print(feat[["역명", "노선ID", "역_행정동", "배후인구_2022", "고령화율_2022", "연결역까지_km", "서울까지_최단분",
            "서울까지_승용차분", "시간비", "도심거리_km", "일일_정차횟수"]].to_string(index=False))
