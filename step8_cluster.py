"""3단계 A: 시군 클러스터링 — 철도 공백 지역 유형화

입력: sigungu_base.csv (인구·고령화·승용차), sigungu_access.csv (B의 69개 역 기준 수정본)
      tago_train_all.csv (선택: 69개 역 정차 횟수, 있으면 '최근접역 하루 정차' 변수 추가)
출력: sigungu_cluster.csv     시군별 유형
      cluster_profile.csv     유형별 평균 특성
      cluster_scatter.png     KTX 접근시간 × 고령화율 산점도 (유형별 색)

변수 (표준화 후 K-means)
  - ln(KTX역 접근시간)          접근성
  - ln(대도시 승용차 시간)       대도시 접근성
  - 고령화율                     교통약자
  - 인구증감률(2013→2022)       지역 쇠퇴 (−30 ~ +50% 로 잘라 신도시 이상치 완화)
  - 1인당 자가용 승용차          승용차 의존 (0.6 상한: 법인 등록 많은 도심 구 보정)
  - ln(최근접역 하루 정차 횟수)  철도 서비스 수준 (선택)
제외: 제주시, 서귀포시, 울릉군 (섬)

실행: python step8_cluster.py          (군집 수 자동: 실루엣 기준 3~6 중 선택)
      python step8_cluster.py 4        (군집 수 직접 지정)
"""
import os
import sys

import matplotlib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ISLANDS = ["제주시", "서귀포시", "울릉군"]
K_FIXED = int(sys.argv[1]) if len(sys.argv) > 1 else None

base = pd.read_csv("sigungu_base.csv")
acc = pd.read_csv("sigungu_access.csv")
df = base.merge(acc[["시군코드", "최근접KTX역", "KTX역_접근시간_분", "대도시_승용차시간_분", "중심_경도", "중심_위도"]],
                on="시군코드", how="inner")
df = df[~df["시군"].isin(ISLANDS)].copy()

df["f_접근"] = np.log1p(df["KTX역_접근시간_분"])
df["f_대도시"] = np.log1p(df["대도시_승용차시간_분"])
df["f_고령화"] = df["고령화율_2022"]
df["f_인구증감"] = df["인구증감률_2013_2022"].clip(-30, 50)
df["f_승용차"] = df["1인당자가용승용차_2022"].clip(upper=0.6)
F = ["f_접근", "f_대도시", "f_고령화", "f_인구증감", "f_승용차"]

if os.path.exists("tago_train_all.csv"):
    stops = pd.read_csv("tago_train_all.csv").set_index("역명")["일일_정차횟수"]
    stops.index = stops.index.str.replace(r"\(.*\)", "", regex=True)
    df["최근접역_하루정차"] = df["최근접KTX역"].str.replace(r"\(.*\)", "", regex=True).map(stops)
    if df["최근접역_하루정차"].notna().all():
        df["f_정차"] = np.log1p(df["최근접역_하루정차"])
        F.append("f_정차")
    else:
        print("[정차 횟수가 없는 최근접역 → 정차 변수 제외]", df.loc[df["최근접역_하루정차"].isna(), "최근접KTX역"].unique())

X = StandardScaler().fit_transform(df[F])

# ---------- 군집 수 선택 ----------
scores = {}
for k in range(3, 7):
    lab = KMeans(n_clusters=k, n_init=50, random_state=42).fit_predict(X)
    scores[k] = silhouette_score(X, lab)
print("실루엣 점수:", {k: round(v, 3) for k, v in scores.items()})
K = K_FIXED or max(scores, key=scores.get)
print(f"선택한 군집 수: {K}")

km = KMeans(n_clusters=K, n_init=50, random_state=42).fit(X)
df["유형"] = km.labels_

# 유형 번호를 'KTX 접근시간이 긴 순'으로 다시 매김 (1 = 가장 소외)
order = df.groupby("유형")["KTX역_접근시간_분"].mean().sort_values(ascending=False).index
df["유형"] = df["유형"].map({old: i + 1 for i, old in enumerate(order)})

# ---------- 유형별 프로필 ----------
SHOW = ["KTX역_접근시간_분", "대도시_승용차시간_분", "고령화율_2022", "인구증감률_2013_2022", "1인당자가용승용차_2022"]
if "f_정차" in F:
    SHOW.append("최근접역_하루정차")
prof = df.groupby("유형")[SHOW].mean().round(2)
prof.insert(0, "시군수", df.groupby("유형").size())
prof.insert(1, "인구_2022", df.groupby("유형")["인구_2022"].sum())
prof.insert(2, "고령인구_2022", df.groupby("유형")["고령인구_2022"].sum())
prof["대표 시군"] = df.sort_values("KTX역_접근시간_분", ascending=False).groupby("유형")["시군"].apply(
    lambda s: ", ".join(s.head(6)))
prof.to_csv("cluster_profile.csv", encoding="utf-8-sig")

out_cols = ["시군코드", "시도", "시군", "유형", "최근접KTX역"] + SHOW + ["인구_2022", "고령인구_2022", "중심_경도", "중심_위도"]
df[list(dict.fromkeys(out_cols))].sort_values(["유형", "KTX역_접근시간_분"], ascending=[True, False]) \
    .to_csv("sigungu_cluster.csv", index=False, encoding="utf-8-sig")

# ---------- 그림 ----------
for f in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]:
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

colors = ["#c0392b", "#e67e22", "#2a6fb0", "#27ae60", "#8e44ad", "#7f8c8d"]
fig, ax = plt.subplots(figsize=(9, 6.5))
for k in sorted(df["유형"].unique()):
    d = df[df["유형"] == k]
    ax.scatter(d["KTX역_접근시간_분"], d["고령화율_2022"], s=np.sqrt(d["인구_2022"]) / 6,
               color=colors[(k - 1) % len(colors)], alpha=0.75, edgecolor="white", lw=0.5,
               label=f"유형 {k} ({len(d)}개 시군)")
for _, r in df.nlargest(12, "KTX역_접근시간_분").iterrows():
    ax.annotate(r["시군"], (r["KTX역_접근시간_분"], r["고령화율_2022"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
ax.set(xlabel="최근접 KTX역 접근시간 (분, 승용차)", ylabel="고령화율 (%, 2022)",
       title=f"시군 철도 접근성 유형 (K-means, k={K}, 원 크기 = 인구)")
ax.legend(frameon=False, fontsize=8)
ax.grid(True, lw=0.3, alpha=0.5)
fig.tight_layout()
fig.savefig("cluster_scatter.png", dpi=200)

pd.set_option("display.width", 200)
print("\n[유형별 평균]")
print(prof.drop(columns="대표 시군").to_string())
print("\n[유형별 대표 시군 (접근시간 긴 순)]")
for k, v in prof["대표 시군"].items():
    print(f"  유형 {k}: {v}")
