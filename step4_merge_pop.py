"""2단계 A: 역 배후권역에 시군 인구·고령화율·인구 증감률·승용차 보유 붙이기

입력: station_features_base.csv (step3 결과), sigungu_base.csv (B가 만든 시군 표)
출력: station_features.csv  학습용 역 × (이용객 + 열차 변수 + 배후권역 인구 변수)

배후권역 규칙
  - 특별·광역·특별자치시(서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종): 시 전체 합계
  - 그 외: 역이 위치한 시·군 (예: 창원시 의창구 → 창원시)
실행:
  python step4_merge_pop.py
"""
import sys

import pandas as pd

BASE = sys.argv[1] if len(sys.argv) > 1 else "station_features_base.csv"
POP = sys.argv[2] if len(sys.argv) > 2 else "sigungu_base.csv"

SHORT = {"충청북도": "충북", "충청남도": "충남", "경상북도": "경북", "경상남도": "경남",
         "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
         "강원도": "강원", "강원특별자치도": "강원", "제주특별자치도": "제주", "세종특별자치시": "세종"}
METRO = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"}
# 역 위치와 실제 이용 권역이 다른 역 (역명: 권역 시군)
AREA_OVERRIDE = {"구례구": "구례군"}  # 구례구역은 순천시에 있지만 구례군 주민이 주로 이용


def short(s):
    s = str(s).strip()
    return SHORT.get(s, s[:2])


# ---------- 시군 표: 배후권역 단위로 집계 ----------
pop = pd.read_csv(POP)
pop["시도"] = pop["시도"].map(short)
pop["권역"] = pop.apply(lambda r: r["시도"] if r["시도"] in METRO else r["시군"], axis=1)

SUM_COLS = ["인구_2013", "인구_2022", "고령인구_2022", "자가용승용차_2022"]
area = pop.groupby(["시도", "권역"], as_index=False)[SUM_COLS].sum()
area["고령화율_2022"] = area["고령인구_2022"] / area["인구_2022"] * 100
area["인구증감률_2013_2022"] = (area["인구_2022"] / area["인구_2013"] - 1) * 100
area["1인당자가용승용차_2022"] = area["자가용승용차_2022"] / area["인구_2022"]
area = area.rename(columns={"인구_2022": "배후인구_2022"})
KEEP = ["시도", "권역", "배후인구_2022", "고령화율_2022", "인구증감률_2013_2022", "1인당자가용승용차_2022"]

# ---------- 역 표: 같은 규칙으로 권역 키 만들기 ----------
st = pd.read_csv(BASE)
sido_col = "시도_전체" if "시도_전체" in st.columns else "시도"
GWANGJU_GU = {"동구", "서구", "남구", "북구", "광산구"}


def sido_key(r):
    # 카카오가 광주·전남을 "전남광주통합특별시"로 돌려주는 경우: 구(區)면 광주, 아니면 전남 (B 파일 기준)
    if "광주" in str(r[sido_col]) and "전남" in str(r[sido_col]):
        return "광주" if str(r["시군구"]).split()[0] in GWANGJU_GU else "전남"
    return short(r[sido_col])


st["시도_키"] = st.apply(sido_key, axis=1)
st["권역"] = st.apply(lambda r: r["시도_키"] if r["시도_키"] in METRO else str(r["시군구"]).split()[0], axis=1)
st["권역"] = st.apply(lambda r: AREA_OVERRIDE.get(r["역명"], r["권역"]), axis=1)

out = st.merge(area[KEEP].rename(columns={"시도": "시도_키"}), on=["시도_키", "권역"], how="left")
out = out.drop(columns=["시도_키"]).round({"고령화율_2022": 2, "인구증감률_2013_2022": 2, "1인당자가용승용차_2022": 4})
out.to_csv("station_features.csv", index=False, encoding="utf-8-sig")

miss = out[out["배후인구_2022"].isna()]
print(f"완료: {len(out)}개 역, 인구 매칭 {len(out) - len(miss)}개")
if len(miss):
    print("[인구가 안 붙은 역 — 시군 이름 확인 필요]")
    print(miss[["역명", sido_col, "시군구", "권역"]].to_string(index=False))
print("\n" + out[["역명", "권역", "배후인구_2022", "고령화율_2022", "인구증감률_2013_2022"]].head(10).to_string(index=False))
