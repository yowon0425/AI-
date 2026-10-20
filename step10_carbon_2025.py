"""4단계 A: 신규 노선별 탄소 감축량 · 교통약자 수혜 · 효율 지표

입력: new_station_forecast.csv       (step9 결과: 역별 연간 이용객 시나리오)
      new_station_features.csv       (B: 신규 역 변수, 현재 KTX역 접근시간 포함)
      new_line_cost_2025기준.csv     (B: 노선별 사업비·전환 1인km당 감축 g, 2025년 가격)
      sigungu_access.csv             (B: 시군 → 서울 도로거리 = 1회 이동거리)
출력: new_line_evaluation.csv        노선별 최종 평가표 (신규구간평가 시트에 옮길 값)
      new_station_carbon.csv         역별 전환 인km·감축량
      new_line_evaluation.png        노선별 효율 비교 그림

가정 (보고서 '가정' 표에 그대로 기재)
  - 승용차 전환율: 보수 30% / 기준 50% / 낙관 70%  (신규 KTX 이용객 중 원래 승용차 이용 비율)
  - 1회 이동거리: 신규 역 시군 → 서울 도로거리 (모든 승객이 서울행이라 가정 → 상한 추정)
  - 시나리오 묶음: 낮음 = 보수 수요 × 30%, 기준 = 기준 수요 × 50%, 높음 = 낙관 수요 × 70%
  - CO2 비용 54,088원/tCO2 (세부지침 2021 표 V-31, 2025년 가격으로 보정, B '가정' 시트)
  - 운영 40년, 할인율 4.5% (31년차부터 3.5%) — 세부지침 2021 / 개통 전 공사기간은 반영 안 함
  - 신규 역 개통 후 접근시간 = 역-도심 거리 ÷ 시속 30km (+ 대기 5분)
실행: python step10_carbon_2025.py    (기본: step9_predict_2025 결과 사용)
      python step10_carbon_2025.py 2022 (2022년 결과 사용 / 2025 설명: step9 2025 결과 → 결과 파일 이름 끝에 _pop2025)
"""
import sys

import glob

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

SHIFT = {"낮음": ("보수_천명", 0.30), "기준": ("기준_천명", 0.50), "높음": ("낙관_천명", 0.70)}
CO2_COST_WON_PER_T = 54087.981362
YEARS, R1, R2, SWITCH_YEAR = 40, 0.045, 0.035, 30
ACCESS_SPEED_KMH, ACCESS_WAIT_MIN = 30, 5


def pv_factor():
    f = 0.0
    for t in range(1, YEARS + 1):
        if t <= SWITCH_YEAR:
            f += 1 / (1 + R1) ** t
        else:
            f += 1 / ((1 + R1) ** SWITCH_YEAR * (1 + R2) ** (t - SWITCH_YEAR))
    return f


PV = pv_factor()
POP_YEAR = sys.argv[1] if len(sys.argv) > 1 else "2025"  # 이 파일은 기본값 2025
SUF = "" if POP_YEAR == "2022" else f"_pop{POP_YEAR}"

cost_file = (glob.glob("new_line_cost*2025*.csv") or glob.glob("new_line_cost*.csv"))[0]
print(f"사업비 파일: {cost_file}  /  40년 현가계수 {PV:.2f}")

fc = pd.read_csv(f"new_station_forecast{SUF}.csv")
feat = pd.read_csv("new_station_features.csv")
cost = pd.read_csv(cost_file)
acc = pd.read_csv("sigungu_access.csv")[["시도", "시군", "서울_도로거리_km"]]

st = fc.merge(feat[["역명", "시도", "현재_KTX역_접근시간_분"]], on="역명", how="left") \
       .merge(acc, left_on=["시도", "시군구"], right_on=["시도", "시군"], how="left") \
       .merge(cost[["노선ID", "전환1인km당_감축_g"]], on="노선ID", how="left")
if st["서울_도로거리_km"].isna().any():
    print("[서울 도로거리를 못 찾은 역]", st.loc[st["서울_도로거리_km"].isna(), "역명"].tolist())

# ---------- 역별 전환 인km · 감축량 ----------
for tag, (col, share) in SHIFT.items():
    st[f"전환인km_{tag}_백만"] = st[col] * 1000 * share * st["서울_도로거리_km"] / 1e6
    st[f"감축_{tag}_t"] = st[f"전환인km_{tag}_백만"] * 1e6 * st["전환1인km당_감축_g"] / 1e6

# ---------- 교통약자 수혜 ----------
st["고령인구"] = (st["배후인구_2022"] * st["고령화율_2022"] / 100).round(0)
st["개통후_접근시간_분"] = st["도심거리_km"] / ACCESS_SPEED_KMH * 60 + ACCESS_WAIT_MIN
st["접근단축_분"] = (st["현재_KTX역_접근시간_분"] - st["개통후_접근시간_분"]).clip(lower=0)
st["고령자_분"] = st["고령인구"] * st["접근단축_분"]

keep = ["노선ID", "역명", "시군구", "서울_도로거리_km", "기준_천명",
        "전환인km_기준_백만", "감축_낮음_t", "감축_기준_t", "감축_높음_t",
        "고령인구", "현재_KTX역_접근시간_분", "개통후_접근시간_분", "접근단축_분"]
st[keep].round(1).to_csv(f"new_station_carbon{SUF}.csv", index=False, encoding="utf-8-sig")

# ---------- 노선별 집계 ----------
g = st.groupby("노선ID").agg(
    신규역수=("역명", "count"),
    연간이용객_기준_천명=("기준_천명", "sum"),
    전환인km_기준_백만=("전환인km_기준_백만", "sum"),
    감축_낮음_t=("감축_낮음_t", "sum"), 감축_기준_t=("감축_기준_t", "sum"), 감축_높음_t=("감축_높음_t", "sum"),
    수혜고령인구=("고령인구", "sum"),
    고령자_분=("고령자_분", "sum"),
).reset_index()
ev = cost[["노선ID", "노선명", "연장_km", "사업비_기준_억", "사업비_낮음_억", "사업비_높음_억"]].merge(g, on="노선ID")

ev["평균접근단축_분"] = (ev["고령자_분"] / ev["수혜고령인구"]).round(1)
ev["40년누적감축_기준_t"] = ev["감축_기준_t"] * YEARS
ev["탄소편익_연간_억"] = ev["감축_기준_t"] * CO2_COST_WON_PER_T / 1e8
ev["탄소편익_40년현가_억"] = ev["탄소편익_연간_억"] * PV
# 효율 지표 (낮을수록 좋음)
ev["탄소1톤당_사업비_만원"] = ev["사업비_기준_억"] * 1e4 / ev["40년누적감축_기준_t"]
ev["고령자1인당_사업비_만원"] = ev["사업비_기준_억"] * 1e4 / ev["수혜고령인구"]
ev["억원당_연간이용객_명"] = ev["연간이용객_기준_천명"] * 1000 / ev["사업비_기준_억"]

cols = ["노선ID", "노선명", "연장_km", "신규역수", "사업비_기준_억", "사업비_낮음_억", "사업비_높음_억",
        "연간이용객_기준_천명", "전환인km_기준_백만", "감축_낮음_t", "감축_기준_t", "감축_높음_t",
        "40년누적감축_기준_t", "탄소편익_연간_억", "탄소편익_40년현가_억",
        "수혜고령인구", "평균접근단축_분", "탄소1톤당_사업비_만원", "고령자1인당_사업비_만원", "억원당_연간이용객_명"]
ev = ev[cols].sort_values("탄소1톤당_사업비_만원")
ev.round(1).to_csv(f"new_line_evaluation{SUF}.csv", index=False, encoding="utf-8-sig")

# ---------- 그림 ----------
for fnt in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]:
    if any(fnt == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = fnt
        break
plt.rcParams["axes.unicode_minus"] = False

colors = {"K2": "#2a6fb0", "K4": "#e67e22", "K6": "#27ae60", "K7": "#8e44ad"}
fig, axes = plt.subplots(1, 3, figsize=(13, 4))
d = ev.set_index("노선ID")
labels = [f"{k}\n{d.loc[k, '노선명']}" for k in d.index]
c = [colors.get(k, "#7f8c8d") for k in d.index]
axes[0].bar(labels, d["감축_기준_t"], color=c)
axes[0].errorbar(range(len(d)), d["감축_기준_t"],
                 yerr=[d["감축_기준_t"] - d["감축_낮음_t"], d["감축_높음_t"] - d["감축_기준_t"]],
                 fmt="none", ecolor="#333", capsize=4, lw=1)
axes[0].set(title="연간 CO2 감축량 (톤, 낮음~높음)")
axes[1].bar(labels, d["탄소1톤당_사업비_만원"], color=c)
axes[1].set(title="탄소 1톤 감축당 사업비 (만원, 낮을수록 효율)")
axes[2].bar(labels, d["고령자1인당_사업비_만원"], color=c)
axes[2].set(title="수혜 고령자 1인당 사업비 (만원)")
for ax in axes:
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(True, axis="y", lw=0.3, alpha=0.5)
fig.tight_layout()
fig.savefig(f"new_line_evaluation{SUF}.png", dpi=200)

pd.set_option("display.width", 250)
print("\n[노선별 평가 — 탄소 1톤당 사업비 낮은 순]")
show = ["노선ID", "노선명", "사업비_기준_억", "연간이용객_기준_천명", "감축_낮음_t", "감축_기준_t", "감축_높음_t",
        "탄소편익_40년현가_억", "수혜고령인구", "평균접근단축_분", "탄소1톤당_사업비_만원", "고령자1인당_사업비_만원"]
print(ev[show].round(0).to_string(index=False))
