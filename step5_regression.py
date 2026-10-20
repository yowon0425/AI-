"""3단계 A: KTX 역 수요 모형 (로그 선형회귀) + Leave-One-Out 교차검증

입력: station_features.csv (step4 결과)
출력: reg_coefficients.csv  계수표 (2019 메인, 2022 강건성)
      reg_loocv.csv         역별 실제값 vs LOOCV 예측값
      reg_loocv.png         실제 vs 예측 산점도
      reg_summary.txt       전체 회귀 결과

모형: ln(연간 이용객) = b0 + b1 ln(권역 인구 / 권역 내 KTX역 수) + b2 서울까지 시간(시간)
                         + b3 ln(일일 정차 횟수) + b4 고령화율 (+ b5 열차/승용차 시간비, 열이 있으면)
학습 제외: 서울·용산 (출발 종착역이라 지방 신규 역과 성격이 다름)

필요 패키지: pip install pandas numpy statsmodels matplotlib
실행: python step5_regression.py
"""
import sys

import matplotlib
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

SRC = sys.argv[1] if len(sys.argv) > 1 else "station_features.csv"
EXCLUDE = ["서울", "용산"]

# ---------- 데이터 준비 ----------
df = pd.read_csv(SRC)
df["권역내역수"] = df.groupby("권역")["역명"].transform("count")
df = df[~df["역명"].isin(EXCLUDE)].copy()

df["ln_y2019"] = np.log(df["이용객_천명_2019"])
df["ln_y2022"] = np.log(df["이용객_천명_2022"])
df["ln_인구분담"] = np.log(df["배후인구_2022"] / df["권역내역수"])
df["서울시간_h"] = df["서울까지_최단분"] / 60
df["ln_정차"] = np.log(df["일일_정차횟수"])
df["고령화율"] = df["고령화율_2022"]

X = ["ln_인구분담", "서울시간_h", "ln_정차", "고령화율"]
if "시간비" in df.columns and df["시간비"].notna().all():
    X.remove("서울시간_h")  # 시간비에 열차 시간이 이미 들어 있어 둘 다 넣으면 공선성 (VIF 5~7)
    X.append("시간비")
if "도심거리_km" in df.columns and df["도심거리_km"].notna().all():
    df["ln_도심거리"] = np.log1p(df["도심거리_km"])
    X.append("ln_도심거리")

missing = df[X + ["ln_y2019"]].isna().any(axis=1)
if missing.any():
    print("[결측치가 있어 제외된 역]", df.loc[missing, "역명"].tolist())
    df = df[~missing]
n = len(df)
formula = lambda y: f"{y} ~ " + " + ".join(X)

# ---------- 전체 적합 ----------
m19 = smf.ols(formula("ln_y2019"), data=df).fit(cov_type="HC1")
m22 = smf.ols(formula("ln_y2022"), data=df).fit(cov_type="HC1")


def coef_table(m, tag):
    return pd.DataFrame({f"계수_{tag}": m.params, f"p값_{tag}": m.pvalues}).round(4)


coefs = coef_table(m19, "2019").join(coef_table(m22, "2022"))
coefs.to_csv("reg_coefficients.csv", encoding="utf-8-sig")

vif = pd.Series([variance_inflation_factor(df[X].assign(c=1).values, i) for i in range(len(X))], index=X).round(2)

# ---------- Leave-One-Out ----------
pred = []
for i in df.index:
    fit = smf.ols(formula("ln_y2019"), data=df.drop(i)).fit()
    pred.append(fit.predict(df.loc[[i]]).iloc[0])
df["예측_ln"] = pred
df["예측_천명"] = np.exp(df["예측_ln"]).round(0)
df["오차율_%"] = ((df["예측_천명"] - df["이용객_천명_2019"]) / df["이용객_천명_2019"] * 100).round(1)

ss_res = ((df["ln_y2019"] - df["예측_ln"]) ** 2).sum()
ss_tot = ((df["ln_y2019"] - df["ln_y2019"].mean()) ** 2).sum()
loo_r2 = 1 - ss_res / ss_tot
mape = df["오차율_%"].abs().mean()
medape = df["오차율_%"].abs().median()

out = df[["역명", "권역", "이용객_천명_2019", "예측_천명", "오차율_%"] + X].sort_values("이용객_천명_2019", ascending=False)
out.to_csv("reg_loocv.csv", index=False, encoding="utf-8-sig")

# ---------- 그림 ----------
for f in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]:
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(7, 7))
ax.scatter(df["이용객_천명_2019"], df["예측_천명"], s=28, color="#2a6fb0")
lo, hi = df[["이용객_천명_2019", "예측_천명"]].min().min() * 0.7, df[["이용객_천명_2019", "예측_천명"]].max().max() * 1.4
ax.plot([lo, hi], [lo, hi], color="#999", lw=1, ls="--")
for _, r in df.iterrows():
    ax.annotate(r["역명"], (r["이용객_천명_2019"], r["예측_천명"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
ax.set(xscale="log", yscale="log", xlim=(lo, hi), ylim=(lo, hi),
       xlabel="실제 연간 이용객 (천 명, 2019)", ylabel="LOOCV 예측 (천 명)",
       title=f"KTX 역 수요 모형 교차검증 (n={n}, LOO R²={loo_r2:.2f}, 오차율 중앙값 {medape:.0f}%)")
ax.grid(True, which="both", lw=0.3, alpha=0.5)
fig.tight_layout()
fig.savefig("reg_loocv.png", dpi=200)

# ---------- 요약 ----------
summary = [
    f"학습 역 수: {n} (제외: {', '.join(EXCLUDE)})",
    f"설명변수: {', '.join(X)}",
    "",
    f"[2019 메인] R² = {m19.rsquared:.3f}, 수정 R² = {m19.rsquared_adj:.3f}",
    f"[2022 강건성] R² = {m22.rsquared:.3f}, 수정 R² = {m22.rsquared_adj:.3f}",
    "",
    "[계수 (HC1 강건 표준오차 기준 p값)]",
    coefs.to_string(),
    "",
    "[다중공선성 VIF — 10 넘으면 주의]",
    vif.to_string(),
    "",
    f"[Leave-One-Out] R²(로그) = {loo_r2:.3f}, 평균 오차율 = {mape:.1f}%, 오차율 중앙값 = {medape:.1f}%",
    "",
    "[오차가 큰 역 Top 5]",
    out.reindex(out["오차율_%"].abs().sort_values(ascending=False).index)[["역명", "이용객_천명_2019", "예측_천명", "오차율_%"]].head(5).to_string(index=False),
    "",
    str(m19.summary()),
]
open("reg_summary.txt", "w", encoding="utf-8").write("\n".join(summary))
print("\n".join(summary[:-1]))
