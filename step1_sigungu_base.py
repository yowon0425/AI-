"""1단계 B: 시군별 인구·고령화율·인구 증감률·1인당 자동차 등록대수
입력:
  raw/kosis_pop_sigungu_agg.csv  KOSIS 101/DT_1B04005N 행정구역(읍면동)별/5세별 주민등록인구, 각 연도 12월 기준
                                  (총인구, 65세 이상, 75세 이상 / 2013·2019·2022·2025)
  raw/molit_car_sigungu.csv      KOSIS 116/DT_MLTM_5498 자동차등록대수현황 시도별(시군구), 각 연도 12월
                                  (승용·총계 × 자가용·계 / 2019·2022·2025)
출력: sigungu_base.csv
"""
import pandas as pd

SIDO = {"11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전",
        "31": "울산", "36": "세종", "41": "경기", "43": "충북", "44": "충남", "46": "전남",
        "47": "경북", "48": "경남", "50": "제주", "51": "강원", "52": "전북"}
POP_COLS = [f"{k}_{y}" for k in ("pop", "pop65", "pop75") for y in (2013, 2019, 2022, 2025)]

# ---------- 인구 ----------
pop = pd.read_csv("raw/kosis_pop_sigungu_agg.csv", dtype={"code": str, "parent": str})
sido_tot = pop[pop["lvl"] == 1].set_index("code")
pop = pop[pop["lvl"] == 2].copy()

# 행정구역 변경 이어붙이기 (현재 행정구역 기준)
#  - 인천 남구(28170) → 미추홀구(28177), 2018
#  - 청원군(43710) → 청주시(43110) 통합, 2014
#  - 군위군 경북(47720) → 대구(27720) 편입, 2023
merge_into = {"28170": "28177", "43710": "43110", "47720": "27720"}
names = pop[~pop["code"].isin(merge_into)].set_index("code")["name"]
pop["code"] = pop["code"].replace(merge_into)
pop = pop.groupby("code", as_index=False)[POP_COLS].sum(min_count=1)
pop["name"] = pop["code"].map(names)
pop["parent"] = pop["code"].str[:2]
pop = pop[pop["pop_2022"] > 0]  # 북부출장소·동해출장소(인구 0) 제외

# 검증: 시군 합계 = 시도 합계
for y in (2013, 2022, 2025):
    s = pop.groupby("parent")[f"pop_{y}"].sum()
    t = sido_tot[f"pop_{y}"].reindex(s.index)
    bad = (s - t).abs() > 0
    if y == 2025:  # 군위군 편입 이후 기준이라 2025만 정확히 일치
        assert not bad.any(), f"{y} 시도 합계 불일치: {s[bad].to_dict()}"
    elif bad.any():
        print(f"[참고] {y} 시도 합계 차이(행정구역 변경분): {(s - t)[bad].to_dict()}")

# ---------- 자동차 ----------
car = pd.read_csv("raw/molit_car_sigungu.csv")
car = car[car["sigungu"] != "계"].copy()
car["시군"] = car["sigungu"].str.split(" ").str[0]          # '고양시 덕양구' → '고양시'
car.loc[car["sigungu"] == "군위군", "sido"] = "대구"          # 경북 시절 값도 대구 군위군으로 이어붙임
car = car[car["시군"] != "청원군"]                             # 통합 후 잔존 등록(10대 내외) 제외
num = [c for c in car.columns if c.startswith(("car_", "veh_"))]
car = car.groupby(["sido", "시군"], as_index=False)[num].sum(min_count=1)

pop["sido"] = pop["parent"].map(SIDO)
base = pop.merge(car, left_on=["sido", "name"], right_on=["sido", "시군"], how="left", validate="1:1")
missing = base[base["car_priv_2022"].isna()]
assert missing.empty, f"자동차 매칭 실패: {missing[['sido', 'name']].values.tolist()}"

# ---------- 지표 ----------
out = pd.DataFrame({
    "시군코드": base["code"],
    "시도": base["sido"],
    "시군": base["name"],
    "인구_2013": base["pop_2013"],
    "인구_2022": base["pop_2022"],
    "인구_2025": base["pop_2025"],
    "고령인구_2022": base["pop65_2022"],
    "고령인구_2025": base["pop65_2025"],
    "후기고령인구_2022": base["pop75_2022"],
    "고령화율_2022": base["pop65_2022"] / base["pop_2022"] * 100,
    "고령화율_2025": base["pop65_2025"] / base["pop_2025"] * 100,
    "인구증감률_2013_2022": (base["pop_2022"] / base["pop_2013"] - 1) * 100,
    "인구증감률_2022_2025": (base["pop_2025"] / base["pop_2022"] - 1) * 100,
    "자가용승용차_2022": base["car_priv_2022"],
    "자가용승용차_2025": base["car_priv_2025"],
    "승용차_전체_2022": base["car_all_2022"],
    # 메인 지표: 자가용 승용차 / 인구. 렌터카·리스 법인 등록지(제주시, 인천 계양구, 전남 해남·신안 등)
    # 때문에 '계'(영업용 포함) 기준은 왜곡이 커서 자가용만 사용
    "1인당자가용승용차_2022": base["car_priv_2022"] / base["pop_2022"],
    "1인당자가용승용차_2025": base["car_priv_2025"] / base["pop_2025"],
    "1인당승용차_전체_2022": base["car_all_2022"] / base["pop_2022"],
})
# 2013년 이후 신설(세종)·통합 지역은 증감률 해석 주의
out["비고"] = ""
out.loc[out["시군"] == "세종특별자치시", "비고"] = "2012 출범, 2013 대비 증감률 과대"
out.loc[out["시군"] == "청주시", "비고"] = "2013은 청주시+청원군 합산"
out.loc[out["시군"] == "군위군", "비고"] = "2023 경북→대구 편입, 시계열 이어붙임"
out.loc[out["시군"] == "미추홀구", "비고"] = "2018 인천 남구에서 명칭 변경"
out.loc[out["1인당자가용승용차_2022"] > 0.6, "비고"] = "도심 법인 등록 많아 1인당 등록대수 과대"

out = out.round({c: 2 for c in out.columns if c.endswith(("율", "률"), 0, c.find("_"))})
out = out.round({c: 4 for c in out.columns if c.startswith("1인당")})
cnt = [c for c in out.columns if c.startswith(("인구_", "고령인구", "후기고령", "자가용", "승용차"))]
out[cnt] = out[cnt].astype("Int64")
out.to_csv("sigungu_base.csv", index=False, encoding="utf-8-sig")

print(f"시군 수: {len(out)}")
print(out.describe().T[["mean", "min", "max"]].round(2).to_string())
show = ["시도", "시군", "인구_2022", "고령화율_2022", "인구증감률_2013_2022", "1인당자가용승용차_2022"]
print("\n[고령화율 상위 10]")
print(out.nlargest(10, "고령화율_2022")[show].to_string(index=False))
print("\n[1인당 자가용 승용차 상위 10]")
print(out.nlargest(10, "1인당자가용승용차_2022")[show].to_string(index=False))
