"""3단계 B (10/17): 지도 시각화 — 기존 KTX역 + 철도 공백 지수 색칠 + 신규 구간

입력: sigungu_boundary.gpkg, sigungu_gap.csv, ../A/station_coords.csv (덕소 제외 68개), new_lines.csv
출력: map_gap_national.png   전국 — 공백 지수 5단계 색칠 + 기존 KTX역 + 신규 구간 4개
      map_new_lines.png      신규 구간 4개 확대 (2×2) — 경유 시군 공백 순위·신규 역
색: 공백 지수 = 파랑 한 색 단계(연함→진함), 신규 구간 = 주황 한 색 (노선 구분은 이름표로)
    K2는 정부 추진 중 노선(동해북부선)과 겹쳐 점선으로 표시
"""
import geopandas as gpd
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

for f in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"]:
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # 파랑 100·250·400·550·700
LINE = "#eb6834"      # 주황 (신규 구간)
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8984"
EXCL = "#e4e3df"
GOV = {"K2"}          # 정부 추진 중 노선과 겹침
LABEL_OFFSET = {"K6": ((0, -26), "center")}  # 이름표가 노선을 가리는 경우만 위치 조정 (기본: 끝 역 오른쪽)

g = gpd.read_file("sigungu_boundary.gpkg")
g["geometry"] = g.geometry.simplify(300)
gap = pd.read_csv("sigungu_gap.csv", dtype={"시군코드": str})
g = g.merge(gap[["시군코드", "공백지수", "순위", "포함"]], on="시군코드", how="left")
bins = [0, 45, 55, 60, 65, 101]
labels = ["45 미만", "45~55", "55~60", "60~65", "65 이상"]
g["구간"] = pd.cut(g["공백지수"], bins=bins, labels=labels, right=False)
g["color"] = g["구간"].map(dict(zip(labels, SEQ))).astype(object).where(g["포함"] == 1, EXCL)

st = pd.read_csv("../A/station_coords.csv")
st = st[st["역명"] != "덕소"]
st = gpd.GeoDataFrame(st, geometry=gpd.points_from_xy(st["경도"], st["위도"]), crs=4326).to_crs(g.crs)
nl = pd.read_csv("new_lines.csv")
nl = gpd.GeoDataFrame(nl, geometry=gpd.points_from_xy(nl["경도"], nl["위도"]), crs=4326).to_crs(g.crs)


def draw_lines(ax, label=True, fs=9):
    for lid, d in nl.sort_values("순서").groupby("노선ID"):
        ls = (0, (3, 2)) if lid in GOV else "-"
        ax.plot(d.geometry.x, d.geometry.y, color="white", lw=4.5, zorder=4, solid_capstyle="round")
        ax.plot(d.geometry.x, d.geometry.y, color=LINE, lw=2.4, ls=ls, zorder=5, solid_capstyle="round")
        new = d[d["구분"] == "신규"]
        ax.scatter(new.geometry.x, new.geometry.y, s=46, facecolor="white", edgecolor=LINE, lw=2, zorder=6)
        if label:
            end = d.iloc[-1]
            name = d["노선명"].iloc[0] + (" *" if lid in GOV else "")
            off, ha = LABEL_OFFSET.get(lid, ((8, -2), "left"))
            ax.annotate(f"{lid} {name}", (end.geometry.x, end.geometry.y), xytext=off, textcoords="offset points",
                        fontsize=fs, color=INK, weight="bold", zorder=7, ha=ha,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))


def base(ax):
    g.plot(ax=ax, color=g["color"], edgecolor="white", linewidth=0.3)
    ax.scatter(st.geometry.x, st.geometry.y, s=12, color=INK2, edgecolor="white", lw=0.6, zorder=3)
    ax.set_axis_off()


legend_items = [Patch(facecolor=c, edgecolor="none", label=l) for c, l in zip(SEQ, labels)] + [
    Patch(facecolor=EXCL, edgecolor="none", label="분석 제외 (섬·이상치)"),
    Line2D([], [], marker="o", ls="", color=INK2, markersize=4, label="기존 KTX역 (68개)"),
    Line2D([], [], color=LINE, lw=2.4, marker="o", markerfacecolor="white", label="신규 구간·신규 역"),
    Line2D([], [], color=LINE, lw=2.4, ls=(0, (3, 2)), label="* 정부 추진 중 노선과 겹침"),
]

# ---------- 1) 전국 ----------
fig, ax = plt.subplots(figsize=(8.5, 10.5))
base(ax)
draw_lines(ax)
mainland = g[~g["시군"].isin(["제주시", "서귀포시"])].total_bounds
ax.set_xlim(mainland[0] - 20000, mainland[2] + 60000)
ax.set_ylim(mainland[1] - 10000, mainland[3] + 10000)
ax.set_title("철도 공백 지수와 신규 KTX 구간 제안", fontsize=15, color=INK, loc="left", pad=12)
ax.text(0, 1.0, f"시군별 철도 공백 지수(0~100) · 기존 KTX역 {len(st)}개",
        transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")
ax.legend(handles=legend_items, title="공백 지수", loc="lower right", fontsize=8.5, title_fontsize=9,
          frameon=True, facecolor="white", edgecolor="none")
fig.savefig("map_gap_national.png", dpi=220, bbox_inches="tight", facecolor="white")
plt.close(fig)

# ---------- 2) 노선별 확대 ----------
gap_k = gap.set_index(["시도", "시군"])
fig, axes = plt.subplots(2, 2, figsize=(12, 12))
for ax, (lid, d) in zip(axes.ravel(), nl.sort_values(["노선ID", "순서"]).groupby("노선ID")):
    base(ax)
    draw_lines(ax, label=False)
    x0, y0, x1, y1 = d.total_bounds
    pad = max(x1 - x0, y1 - y0) * 0.35 + 15000
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = max(x1 - x0, y1 - y0) / 2 + pad
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    # 이름표 위치: 가로로 뻗은 노선은 위·아래, 세로로 뻗은 노선은 오른쪽·왼쪽을 번갈아 (겹침 방지)
    horizontal = (x1 - x0) > (y1 - y0)
    for _, r in d.iterrows():
        if r["구분"] == "신규":
            rk = int(gap_k.loc[(r["시도"], r["시군"]), "순위"])
            txt = f"{r['역명']}\n공백 {rk}위"
        else:
            txt = f"{r['역명']} (기존)"
        side = r["순서"] % 2 == 0
        if horizontal:
            off, ha, va = ((0, 12), "center", "bottom") if side else ((0, -12), "center", "top")
        else:
            off, ha, va = ((10, 0), "left", "center") if side else ((-10, 0), "right", "center")
        ax.annotate(txt, (r.geometry.x, r.geometry.y), xytext=off, textcoords="offset points", fontsize=9,
                    ha=ha, va=va, color=INK, zorder=7,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
    tot = d["누적연장_km"].max()
    name = d["노선명"].iloc[0]
    ax.set_title(f"{lid} {name}{' *' if lid in GOV else ''}  ·  약 {tot:.0f}km, 신규 역 {(d['구분'] == '신규').sum()}개",
                 fontsize=11.5, color=INK, loc="left")
fig.legend(handles=legend_items, loc="lower center", ncol=5, fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
fig.suptitle("신규 KTX 구간 4개 (* K2는 정부 추진 중인 동해북부선과 겹침)", fontsize=14, color=INK, x=0.02, ha="left")
fig.tight_layout(rect=(0, 0.04, 1, 0.97))
fig.savefig("map_new_lines.png", dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("saved: map_gap_national.png, map_new_lines.png")
