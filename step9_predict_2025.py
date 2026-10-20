"""3단계 A: 신규 KTX 역 연간 이용객 예측 (정차 횟수 시나리오 3개)

입력: station_features.csv      학습용 기존 역 (step4 → step6 결과)
      new_station_features.csv  B가 만든 신규 역 변수
      new_lines.csv             B가 만든 신규 노선 (연장)
출력: new_station_forecast.csv  역별 시나리오별 예측 + 90% 예측구간 + 학습 범위 밖 여부
      new_line_forecast.csv     노선별 합계
      new_station_forecast.png  역별 예측 막대 (기준 시나리오 + 보수~낙관 범위)

모형: step5 최종 모형과 동일 (학습 37개 역, 서울·용산 제외)
  ln(이용객) = b0 + b1 ln(배후인구/권역 내 역 수) + b2 ln(정차) + b3 고령화율 + b4 시간비 + b5 ln(1+도심거리)
시나리오: 하루 정차 보수 / 기준 / 낙관 (B 파일의 일일_정차횟수_보수, 일일_정차횟수, 일일_정차횟수_낙관)
학습 범위 밖 변수: 원래 값 예측과 함께 '학습 범위로 자른 값' 예측도 제시 (민감도 확인)

실행: python step9_predict_2025.py    (기본: 신규 역 인구·고령화율 2025년 값)
      python step9_predict_2025.py 2022 (B 파일 2022년 값으로 되돌릴 때 / 2025 설명: 신규 역 인구·고령화율을 sigungu_base.csv 2025년 값으로 교체
                                       → 결과 파일 이름 끝에 _pop2025)
"""
import sys

import matplotlib
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

EXCLUDE = ["서울", "용산"]
X = ["ln_인구분담", "ln_정차", "고령화율", "시간비", "ln_도심거리"]
SCEN = {"보수": "일일_정차횟수_보수", "기준": "일일_정차횟수", "낙관": "일일_정차횟수_낙관"}
LABEL = {"ln_인구분담": "배후인구", "ln_정차": "정차 횟수", "고령화율": "고령화율",
         "시간비": "시간비", "ln_도심거리": "도심거리"}


def build(df, stops_col="일일_정차횟수"):
    out = pd.DataFrame(index=df.index)
    out["ln_인구분담"] = np.log(df["배후인구_2022"] / df["권역내역수"])
    out["ln_정차"] = np.log(df[stops_col])
    out["고령화율"] = df["고령화율_2022"]
    out["시간비"] = df["시간비"]
    out["ln_도심거리"] = np.log1p(df["도심거리_km"])
    return out


# ---------- 학습 (step5와 동일) ----------
tr = pd.read_csv("station_features.csv")
tr["권역내역수"] = tr.groupby("권역")["역명"].transform("count")
tr = tr[~tr["역명"].isin(EXCLUDE)].copy()
train = build(tr)
train["ln_y"] = np.log(tr["이용객_천명_2019"])
model = smf.ols("ln_y ~ " + " + ".join(X), data=train).fit()
lo_lim, hi_lim = train[X].min(), train[X].max()
print(f"학습: {len(train)}개 역, R² = {model.rsquared:.3f}")

# ---------- 예측 ----------
POP_YEAR = sys.argv[1] if len(sys.argv) > 1 else "2025"  # 이 파일은 기본값 2025
SUF = "" if POP_YEAR == "2022" else f"_pop{POP_YEAR}"
new = pd.read_csv("new_station_features.csv")
if POP_YEAR != "2022":
    # 신규 역은 권역 = 시군, 권역 내 역 1개 → 시군 인구를 그대로 배후인구로 사용
    base = pd.read_csv("sigungu_base.csv")[["시도", "시군", f"인구_{POP_YEAR}", f"고령화율_{POP_YEAR}"]]
    new = new.merge(base, left_on=["시도", "시군구"], right_on=["시도", "시군"], how="left")
    if new[f"인구_{POP_YEAR}"].isna().any():
        sys.exit(f"[{POP_YEAR}년 인구를 못 찾은 역] {new.loc[new[f'인구_{POP_YEAR}'].isna(), '역명'].tolist()}")
    new["배후인구_2022"] = new[f"인구_{POP_YEAR}"] / new["권역내역수"]  # 열 이름은 그대로 두고 값만 교체
    new["고령화율_2022"] = new[f"고령화율_{POP_YEAR}"]
    print(f"신규 역 인구·고령화율: {POP_YEAR}년 값 사용")
res = new[["노선ID", "노선명", "역명", "시군구", "배후인구_2022", "고령화율_2022", "시간비", "도심거리_km"]].copy()

for tag, col in SCEN.items():
    f = build(new, col)
    pr = model.get_prediction(f).summary_frame(alpha=0.10)  # 90% 예측구간
    res[f"{tag}_천명"] = np.exp(pr["mean"]).round(0)
    if tag == "기준":
        res["기준_하한90_천명"] = np.exp(pr["obs_ci_lower"]).round(0)
        res["기준_상한90_천명"] = np.exp(pr["obs_ci_upper"]).round(0)
        # 학습 범위 밖 변수 확인
        out_of = f.apply(lambda r: [LABEL[c] for c in X if r[c] < lo_lim[c] or r[c] > hi_lim[c]], axis=1)
        res["학습범위밖_변수"] = out_of.map(lambda v: ", ".join(v))
        clipped = f.clip(lower=lo_lim, upper=hi_lim, axis=1)
        res["기준_범위보정_천명"] = np.exp(model.predict(clipped)).round(0)

res["기준_하루평균_명"] = (res["기준_천명"] * 1000 / 365).round(0)
res["인구기준연도"] = POP_YEAR
res.to_csv(f"new_station_forecast{SUF}.csv", index=False, encoding="utf-8-sig")

# ---------- 노선별 합계 ----------
lines = pd.read_csv("new_lines.csv")
length = lines.groupby("노선ID")["누적연장_km"].max().rename("연장_km")
agg = res.groupby(["노선ID", "노선명"]).agg(
    신규역수=("역명", "count"),
    배후인구=("배후인구_2022", "sum"),
    보수_천명=("보수_천명", "sum"),
    기준_천명=("기준_천명", "sum"),
    낙관_천명=("낙관_천명", "sum"),
).reset_index().merge(length, on="노선ID")
agg["기준_km당_천명"] = (agg["기준_천명"] / agg["연장_km"]).round(1)
agg = agg.sort_values("기준_천명", ascending=False)
agg.to_csv(f"new_line_forecast{SUF}.csv", index=False, encoding="utf-8-sig")

# ---------- 그림 ----------
for fnt in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]:
    if any(fnt == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = fnt
        break
plt.rcParams["axes.unicode_minus"] = False

colors = {"K2": "#2a6fb0", "K4": "#e67e22", "K6": "#27ae60", "K7": "#8e44ad"}
d = res.reset_index(drop=True)
fig, ax = plt.subplots(figsize=(10, 5))
xs = np.arange(len(d))
ax.bar(xs, d["기준_천명"], color=[colors.get(k, "#7f8c8d") for k in d["노선ID"]], alpha=0.85)
ax.errorbar(xs, d["기준_천명"], yerr=[d["기준_천명"] - d["보수_천명"], d["낙관_천명"] - d["기준_천명"]],
            fmt="none", ecolor="#333", capsize=4, lw=1)
for i, r in d.iterrows():
    if r["학습범위밖_변수"]:
        ax.annotate("*", (i, r["낙관_천명"]), ha="center", va="bottom", fontsize=12, color="#c0392b")
ax.set_xticks(xs, [n.replace("(신설)", "") for n in d["역명"]])
ax.set(ylabel="연간 이용객 (천 명)",
       title=f"신규 KTX 역 예상 연간 이용객 ({POP_YEAR}년 인구, 막대 = 하루 20회 정차, 선 = 10회~34회, * = 학습 범위 밖 변수 있음)")
for k, c in colors.items():
    nm = d.loc[d["노선ID"] == k, "노선명"]
    if len(nm):
        ax.bar(0, 0, color=c, label=f"{k} {nm.iloc[0]}")
ax.legend(frameon=False, fontsize=8)
ax.grid(True, axis="y", lw=0.3, alpha=0.5)
fig.tight_layout()
fig.savefig(f"new_station_forecast{SUF}.png", dpi=200)

pd.set_option("display.width", 220)
print("\n[역별 예측 (천 명/년)]")
print(res[["노선ID", "역명", "보수_천명", "기준_천명", "낙관_천명", "기준_하한90_천명", "기준_상한90_천명",
           "기준_범위보정_천명", "학습범위밖_변수"]].to_string(index=False))
print("\n[노선별 합계 (천 명/년)]")
print(agg.to_string(index=False))
