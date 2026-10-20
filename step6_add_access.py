"""2단계 A (추가): 승용차 시간비 + 역-도심 거리 붙이기

입력: station_features.csv (step4 결과), station_coords.csv,
      station_car_seoul.csv, sigungu_access.csv, sigungu_base.csv (B 파일 3개)
출력: station_features.csv 에 열 3개 추가 (덮어씀)
      - 서울까지_승용차분 : 역 소재 시군 중심 → 서울 승용차 시간 (B 계산)
      - 시간비            : 서울까지 KTX 최단 시간 / 승용차 시간 (작을수록 KTX가 유리)
      - 도심거리_km       : 역 ↔ 배후권역 인구가중 중심 직선거리
                            (특별·광역시는 구별 중심을 인구로 가중평균한 시 전체 중심)
실행 순서: step4_merge_pop.py → step6_add_access.py → step5_regression.py
"""
import numpy as np
import pandas as pd

METRO = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"}
AREA_OVERRIDE = {"구례구": ("전남", "구례군")}  # step4와 동일


def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


st = pd.read_csv("station_features.csv")
st = st.drop(columns=[c for c in ["서울까지_승용차분", "시간비", "도심거리_km"] if c in st.columns])
coords = pd.read_csv("station_coords.csv")[["역명", "경도", "위도"]]
car = pd.read_csv("station_car_seoul.csv")
acc = pd.read_csv("sigungu_access.csv")
pop = pd.read_csv("sigungu_base.csv")[["시군코드", "인구_2022"]]

# ---------- 서울까지 승용차 시간 ----------
car_map = car.set_index("역명")["시군_서울_승용차시간_분"].to_dict()
acc_idx = acc.set_index(["시도", "시군"])
for name, key in AREA_OVERRIDE.items():
    car_map[name] = acc_idx.loc[key, "서울_승용차시간_분"]
st["서울까지_승용차분"] = st["역명"].map(car_map)
st["시간비"] = (st["서울까지_최단분"] / st["서울까지_승용차분"]).round(3)

# ---------- 배후권역 중심 ----------
acc = acc.merge(pop, on="시군코드", how="left")
acc["권역"] = acc.apply(lambda r: r["시도"] if r["시도"] in METRO else r["시군"], axis=1)
center = (acc.groupby("권역")
             .apply(lambda g: pd.Series({
                 "중심_경도": np.average(g["중심_경도"], weights=g["인구_2022"]),
                 "중심_위도": np.average(g["중심_위도"], weights=g["인구_2022"])}))
             .reset_index())

if "경도" in st.columns:
    st = st.drop(columns=["경도", "위도"])
st = st.merge(coords, on="역명", how="left").merge(center, on="권역", how="left")
st["도심거리_km"] = haversine(st["경도"], st["위도"], st["중심_경도"], st["중심_위도"]).round(1)
st = st.drop(columns=["중심_경도", "중심_위도"])

st.to_csv("station_features.csv", index=False, encoding="utf-8-sig")

miss = st[st[["서울까지_승용차분", "도심거리_km"]].isna().any(axis=1)]
print(f"완료: {len(st)}개 역")
if len(miss):
    print("[값이 비어 있는 역]")
    print(miss[["역명", "권역", "서울까지_승용차분", "도심거리_km"]].to_string(index=False))
print("\n" + st[["역명", "권역", "서울까지_최단분", "서울까지_승용차분", "시간비", "도심거리_km"]]
      .sort_values("도심거리_km", ascending=False).to_string(index=False))
