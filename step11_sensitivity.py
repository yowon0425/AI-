"""5단계 A: 민감도 분석 — 가정을 바꿔도 결론이 유지되는지

[A] 철도 공백 지수 가중치 민감도
    입력: sigungu_base.csv, sigungu_access.csv
    - B 공백 지수 재현: 지표 5개 최소-최대 0~100점, 가중치 0.2씩 (1인당 승용차 0.6 상한, 섬 3곳 제외)
    - 시나리오 6개 (한 지표만 0.4, 나머지 0.15) + 무작위 가중치 1,000회 (Dirichlet)
    - 출력: gap_sensitivity.csv (시군별 기준 순위·시나리오 순위·무작위 순위 범위·상위 20위 확률)
            gap_sensitivity.png (신규 노선 시군의 순위 범위)

[B] 신규 노선 순위 민감도
    입력: new_station_forecast_pop2025.csv (없으면 new_station_forecast.csv), new_station_features.csv,
          new_line_cost_2025기준.csv, sigungu_access.csv
    - 바꿔 보는 가정: 이동거리 (서울 / 가장 가까운 대도시 / 둘 평균) × 사업비 (평균 단가 / 유사사업 단가)
      ※ 수요 시나리오·전환율·단가 낮음~높음은 모든 노선에 같은 비율로 곱해져 노선 '순위'는 바꾸지 못함
    - 종합 점수: 억원당 이용객 · 탄소 1톤당 사업비 · 고령자 1인당 사업비를 노선 간 0~100점으로 바꿔 가중 합
      가중치 시나리오 4개 (균등 / 교통약자 중심 / 탄소 중심 / 수요 중심)
    - 출력: line_sensitivity.csv (조합별 노선 순위), line_sensitivity_summary.csv (노선별 1위 횟수 등)

실행: python step11_sensitivity.py
"""
import glob
import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for fnt in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]:
    if any(fnt == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = fnt
        break
plt.rcParams["axes.unicode_minus"] = False
pd.set_option("display.width", 220)

# ======================================================================
# [A] 공백 지수 가중치
# ======================================================================
IND = {"KTX역_접근시간_분": ("KTX 접근", 1), "고령화율_2022": ("고령화", 1),
       "인구증감률_2013_2022": ("인구 감소", -1), "대도시_승용차시간_분": ("대도시 접근", 1),
       "1인당자가용승용차_2022": ("승용차 의존", 1)}
COLS = list(IND)

base = pd.read_csv("sigungu_base.csv")
acc = pd.read_csv("sigungu_access.csv")
d = base.merge(acc[["시군코드", "KTX역_접근시간_분", "대도시_승용차시간_분"]], on="시군코드")
d = d[~d["시군"].isin(["제주시", "서귀포시", "울릉군"])].reset_index(drop=True)
d["1인당자가용승용차_2022"] = d["1인당자가용승용차_2022"].clip(upper=0.6)  # 법인 등록 많은 도심 구 보정 (B와 동일)

S = pd.DataFrame(index=d.index)
for c, (_, sign) in IND.items():
    z = (d[c] - d[c].min()) / (d[c].max() - d[c].min()) * 100
    S[c] = z if sign == 1 else 100 - z
S = S.values  # (시군 수, 5)


def ranks(w):
    g = S @ (np.asarray(w) / np.sum(w))
    return pd.Series(g).rank(ascending=False, method="min").astype(int).values


SCEN = {"균등(B 기준)": [0.2] * 5}
for i, c in enumerate(COLS):
    w = [0.15] * 5
    w[i] = 0.4
    SCEN[f"{IND[c][0]} 중심"] = w

out = d[["시군코드", "시도", "시군"]].copy()
for name, w in SCEN.items():
    out[name] = ranks(w)

rng = np.random.default_rng(42)
W = rng.dirichlet(np.ones(5), size=1000)
R = np.column_stack([ranks(w) for w in W])
out["무작위_중앙순위"] = np.median(R, axis=1).astype(int)
out["무작위_5%"] = np.percentile(R, 5, axis=1).astype(int)
out["무작위_95%"] = np.percentile(R, 95, axis=1).astype(int)
out["상위20위_확률%"] = ((R <= 20).mean(axis=1) * 100).round(1)
out = out.sort_values("균등(B 기준)")
out.to_csv("gap_sensitivity.csv", index=False, encoding="utf-8-sig")

top20 = set(out.nsmallest(20, "균등(B 기준)")["시군"])
print("[A] 철도 공백 지수 가중치 민감도")
print(f"  시군 {len(out)}개, 기준 상위 20위가 각 시나리오에서도 상위 20위에 남는 수:")
for name in SCEN:
    keep = len(top20 & set(out.nsmallest(20, name)["시군"]))
    print(f"    {name:12s} {keep}/20")
print(f"  무작위 가중치 1,000회에서 상위 20위 확률 80% 이상: {int((out['상위20위_확률%'] >= 80).sum())}개 시군")
print("\n  [기준 상위 15개 시군]")
print(out.head(15)[["시도", "시군", "균등(B 기준)"] + [k for k in SCEN if k != "균등(B 기준)"]
                   + ["무작위_5%", "무작위_95%", "상위20위_확률%"]].to_string(index=False))

# 신규 노선 시군 그림
new = pd.read_csv("new_station_features.csv")
nm = new[["노선ID", "역명", "시도", "시군구"]].merge(out, left_on=["시도", "시군구"], right_on=["시도", "시군"])
nm = nm.sort_values("균등(B 기준)").reset_index(drop=True)
colors = {"K2": "#2a6fb0", "K4": "#e67e22", "K6": "#27ae60", "K7": "#8e44ad"}
fig, ax = plt.subplots(figsize=(9, 5))
for i, r in nm.iterrows():
    c = colors.get(r["노선ID"], "#7f8c8d")
    ax.plot([r["무작위_5%"], r["무작위_95%"]], [i, i], color=c, lw=3, alpha=0.5)
    ax.scatter(r["균등(B 기준)"], i, color=c, s=40, zorder=3)
ax.set_yticks(range(len(nm)), [f"{r['역명'].replace('(신설)', '')} ({r['노선ID']})" for _, r in nm.iterrows()])
ax.invert_yaxis()
ax.axvline(20, color="#c0392b", lw=0.8, ls="--")
ax.set(xlabel=f"철도 공백 순위 (1 = 가장 소외, 전체 {len(out)}개 시군)",
       title="신규 노선 시군의 공백 순위 — 점: 균등 가중치, 선: 무작위 가중치 1,000회 5~95%")
ax.grid(True, axis="x", lw=0.3, alpha=0.5)
fig.tight_layout()
fig.savefig("gap_sensitivity.png", dpi=200)

# ======================================================================
# [B] 신규 노선 순위
# ======================================================================
fc_file = "new_station_forecast_pop2025.csv" if os.path.exists("new_station_forecast_pop2025.csv") else "new_station_forecast.csv"
cost_file = (glob.glob("new_line_cost*2025*.csv") or glob.glob("new_line_cost*.csv"))[0]
fc = pd.read_csv(fc_file)
feat = pd.read_csv("new_station_features.csv")[["역명", "시도", "현재_KTX역_접근시간_분"]]
cost = pd.read_csv(cost_file)
dist = acc[["시도", "시군", "서울_도로거리_km", "대도시_도로거리_km"]]

st = fc.merge(feat, on="역명").merge(dist, left_on=["시도", "시군구"], right_on=["시도", "시군"])
st["고령인구"] = st["배후인구_2022"] * st["고령화율_2022"] / 100
st = st.merge(cost[["노선ID", "전환1인km당_감축_g"]], on="노선ID")
DIST = {"서울": st["서울_도로거리_km"], "대도시": st["대도시_도로거리_km"],
        "평균": (st["서울_도로거리_km"] + st["대도시_도로거리_km"]) / 2}
COST = {"평균단가": "사업비_기준_억", "유사사업": "사업비_유사사업_억"}
WSC = {"균등": (1, 1, 1), "교통약자 중심": (1, 1, 2), "탄소 중심": (1, 2, 1), "수요 중심": (2, 1, 1)}
SHARE = 0.5  # 기준 전환율 (순위에는 영향 없음)


def minmax_good(s, higher_better):
    z = (s - s.min()) / (s.max() - s.min()) * 100 if s.max() > s.min() else s * 0 + 50
    return z if higher_better else 100 - z


rows = []
for dn, dv in DIST.items():
    tmp = st.assign(감축_t=st["기준_천명"] * 1000 * SHARE * dv * st["전환1인km당_감축_g"] / 1e6)
    g = tmp.groupby("노선ID").agg(이용객_천명=("기준_천명", "sum"), 감축_t=("감축_t", "sum"),
                                  고령인구=("고령인구", "sum")).reset_index()
    for cn, ccol in COST.items():
        e = g.merge(cost[["노선ID", "노선명", ccol]].rename(columns={ccol: "사업비_억"}), on="노선ID")
        e["억원당_이용객"] = e["이용객_천명"] * 1000 / e["사업비_억"]
        e["탄소1톤당_사업비_만원"] = e["사업비_억"] * 1e4 / (e["감축_t"] * 40)
        e["고령자1인당_사업비_만원"] = e["사업비_억"] * 1e4 / e["고령인구"]
        sc = pd.DataFrame({"수요": minmax_good(e["억원당_이용객"], True),
                           "탄소": minmax_good(e["탄소1톤당_사업비_만원"], False),
                           "교통약자": minmax_good(e["고령자1인당_사업비_만원"], False)})
        for wn, (wd, wc, we) in WSC.items():
            e["종합점수"] = (wd * sc["수요"] + wc * sc["탄소"] + we * sc["교통약자"]) / (wd + wc + we)
            e["순위"] = e["종합점수"].rank(ascending=False, method="min").astype(int)
            for _, r in e.iterrows():
                rows.append({"이동거리": dn, "사업비": cn, "가중치": wn, "노선ID": r["노선ID"], "노선명": r["노선명"],
                             "순위": r["순위"], "종합점수": round(r["종합점수"], 1),
                             "억원당_이용객": round(r["억원당_이용객"], 1),
                             "탄소1톤당_사업비_만원": round(r["탄소1톤당_사업비_만원"]),
                             "고령자1인당_사업비_만원": round(r["고령자1인당_사업비_만원"])})

ls = pd.DataFrame(rows)
ls.to_csv("line_sensitivity.csv", index=False, encoding="utf-8-sig")
n_comb = ls.groupby(["이동거리", "사업비", "가중치"]).ngroups
summ = ls.groupby(["노선ID", "노선명"]).agg(
    평균순위=("순위", "mean"), 최고순위=("순위", "min"), 최저순위=("순위", "max"),
    **{"1위_횟수": ("순위", lambda s: int((s == 1).sum()))},
    **{"2위이내_횟수": ("순위", lambda s: int((s <= 2).sum()))}).reset_index()
summ["평균순위"] = summ["평균순위"].round(2)
summ = summ.sort_values("평균순위")
summ.to_csv("line_sensitivity_summary.csv", index=False, encoding="utf-8-sig")

print(f"\n[B] 신규 노선 종합 순위 민감도  (수요: {fc_file}, 조합 {n_comb}개 = 이동거리 3 × 사업비 2 × 가중치 4)")
print(summ.to_string(index=False))
print("\n  [가중치별 1위 노선 (이동거리·사업비 6개 조합 중)]")
top = ls[ls["순위"] == 1].groupby(["가중치", "노선ID"]).size().unstack(fill_value=0)
print(top.to_string())
