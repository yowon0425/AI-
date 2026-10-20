"""3단계 A: 수요 모형 비교 — 로그 선형회귀 vs XGBoost vs 랜덤포레스트 (Leave-One-Out)

입력: station_features.csv (step4 → step6 결과)
출력: model_compare.csv     모형별 LOOCV 성능
      model_compare_pred.csv 역별 모형별 예측
      model_importance.png  XGBoost 변수 중요도 + 회귀 표준화 계수

변수는 step5_regression.py 최종 모형과 동일하게 맞춤.
필요 패키지: pip install xgboost scikit-learn
실행: python step7_xgboost.py
"""
import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from xgboost import XGBRegressor

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

EXCLUDE = ["서울", "용산"]

# ---------- 데이터 (step5와 동일한 변수) ----------
df = pd.read_csv("station_features.csv")
df["권역내역수"] = df.groupby("권역")["역명"].transform("count")
df = df[~df["역명"].isin(EXCLUDE)].copy()
df["ln_y"] = np.log(df["이용객_천명_2019"])
df["ln_인구분담"] = np.log(df["배후인구_2022"] / df["권역내역수"])
df["ln_정차"] = np.log(df["일일_정차횟수"])
df["고령화율"] = df["고령화율_2022"]
X = ["ln_인구분담", "ln_정차", "고령화율"]
if "시간비" in df.columns and df["시간비"].notna().all():
    X.append("시간비")
else:
    df["서울시간_h"] = df["서울까지_최단분"] / 60
    X.append("서울시간_h")
if "도심거리_km" in df.columns and df["도심거리_km"].notna().all():
    df["ln_도심거리"] = np.log1p(df["도심거리_km"])
    X.append("ln_도심거리")
df = df.dropna(subset=X + ["ln_y"]).reset_index(drop=True)
n = len(df)

MODELS = {
    "로그 선형회귀": lambda: LinearRegression(),
    # 표본이 37개뿐이라 얕은 트리 + 강한 규제
    "XGBoost": lambda: XGBRegressor(n_estimators=300, max_depth=2, learning_rate=0.05, subsample=0.8,
                                    colsample_bytree=0.8, min_child_weight=3, reg_lambda=1.0, random_state=42),
    "랜덤포레스트": lambda: RandomForestRegressor(n_estimators=500, min_samples_leaf=3, random_state=42),
}

# ---------- Leave-One-Out ----------
preds = {name: np.zeros(n) for name in MODELS}
for i in range(n):
    tr = df.index != i
    for name, make in MODELS.items():
        m = make().fit(df.loc[tr, X], df.loc[tr, "ln_y"])
        preds[name][i] = m.predict(df.loc[[i], X])[0]

rows = []
y = df["ln_y"].values
for name, p in preds.items():
    ape = np.abs(np.exp(p) - np.exp(y)) / np.exp(y) * 100
    rows.append({"모형": name,
                 "LOO R²(로그)": round(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum(), 3),
                 "RMSE(로그)": round(np.sqrt(((y - p) ** 2).mean()), 3),
                 "평균 오차율 %": round(ape.mean(), 1),
                 "오차율 중앙값 %": round(np.median(ape), 1)})
comp = pd.DataFrame(rows)
comp.to_csv("model_compare.csv", index=False, encoding="utf-8-sig")

pred_df = df[["역명", "이용객_천명_2019"]].copy()
for name, p in preds.items():
    pred_df[f"예측_{name}"] = np.exp(p).round(0)
pred_df.to_csv("model_compare_pred.csv", index=False, encoding="utf-8-sig")

# ---------- 변수 중요도 ----------
xgb = MODELS["XGBoost"]().fit(df[X], df["ln_y"])
gain = pd.Series(xgb.get_booster().get_score(importance_type="gain")).reindex(X).fillna(0)
gain = gain / gain.sum()
ols = LinearRegression().fit(df[X], df["ln_y"])
std_coef = pd.Series(ols.coef_ * df[X].std().values, index=X)  # 표준화 계수 (변수 1 표준편차당 ln 이용객 변화)

for f in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]:
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

LABEL = {"ln_인구분담": "배후 인구(역당)", "ln_정차": "하루 정차 횟수", "고령화율": "고령화율",
         "시간비": "KTX/승용차 시간비", "서울시간_h": "서울까지 시간", "ln_도심거리": "역-도심 거리"}
order = gain.sort_values().index
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
axes[0].barh([LABEL[c] for c in order], gain[order], color="#2a6fb0")
axes[0].set(title="XGBoost 변수 중요도 (gain 비율)", xlabel="비율")
axes[1].barh([LABEL[c] for c in order], std_coef[order],
             color=["#c0392b" if v < 0 else "#2a6fb0" for v in std_coef[order]])
axes[1].axvline(0, color="#999", lw=0.8)
axes[1].set(title="회귀 표준화 계수 (빨강 = 음의 효과)", xlabel="1 표준편차당 ln(이용객) 변화")
for ax in axes:
    ax.grid(True, axis="x", lw=0.3, alpha=0.5)
fig.tight_layout()
fig.savefig("model_importance.png", dpi=200)

print(f"학습 역 수: {n}, 변수: {', '.join(X)}\n")
print(comp.to_string(index=False))
print("\n[XGBoost 중요도]\n" + gain.sort_values(ascending=False).round(3).to_string())
print("\n[회귀 표준화 계수]\n" + std_coef.sort_values(key=abs, ascending=False).round(3).to_string())
