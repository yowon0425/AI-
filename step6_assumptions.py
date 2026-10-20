"""4단계 B (10/18): KDI 예타 보고서·지침에서 건설 단가·배출·환경비용 원단위 정리 → `가정` 시트

입력:
  raw/kdi/*.pdf             KDI 공공투자관리센터 예타 보고서 5개 + 세부지침(2021) — 값은 아래 상수로 옮겨 적고 쪽수 표기
  rail_gap.xlsx             10/16 공백 지수 엑셀 (`가정` 시트를 추가·교체)
  new_lines.csv             10/17 신규 노선 연장
  sigungu_access.csv        신규 역 시군 → 서울 승용차 시간·거리 (평균 주행속도)
출력:
  rail_gap.xlsx `가정` 시트  분석 전제, 보정지수, 건설 단가, 배출·환경비용 원단위, 노선별 적용값·사업비 (수식)
  kdi_unit_cost.csv          예타 5개 사업 km당 단가
  new_line_cost.csv          노선별 사업비·전환 1인km당 CO2 감축 (파이썬 계산, 엑셀과 같은 값)

실행:
  python step6_assumptions.py        2021년 가격 (KDI 보고서 안 보정지수만 사용) → rail_gap.xlsx, kdi_unit_cost.csv, new_line_cost.csv
  python step6_assumptions.py 2025   2025년 가격 (KOSIS 보정지수) → rail_gap_2025기준.xlsx, kdi_unit_cost_2025기준.csv,
                                     new_line_cost_2025기준.csv (rail_gap.xlsx를 복사해 `가정` 시트만 2025년 가격으로)
건설비는 건설투자 GDP 디플레이터, 편익 원단위는 소비자물가지수로 기준연도 가격에 맞춤
※ step3_gap_index.py를 다시 돌리면 rail_gap.xlsx가 새로 만들어지므로 이 스크립트도 다시 돌려야 함
"""
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# ---------- KDI 자료에서 옮긴 값 (출처 쪽수 = 보고서 인쇄 쪽 / PDF 쪽) ----------
# 보정지수: 「동해선 삼척~강릉 고속화사업」 예타(2026) 표 Ⅲ-27·Ⅲ-28 (PDF p190), 원자료 한국은행 ECOS, 2007=100, 2021은 잠정치
INDEX = {  # 연도: (건설투자 GDP 디플레이터, 소비자물가지수)
    2013: (127.7, 119.2), 2015: (129.7, 121.6), 2018: (138.7, 127.0),
    2019: (142.5, 127.5), 2020: (144.1, 128.2), 2021: (156.3, 131.4)}
BASE_YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2021
INDEX_SRC = "삼척~강릉 예타(2026) 표 Ⅲ-27·28 PDF p190, 원자료 한국은행 ECOS, 2007=100 (2021 잠정치)"
if BASE_YEAR == 2025:
    # KOSIS 301/DT_200Y112 국내총생산에 대한 지출 디플레이터(건설투자, 2020=100, 한국은행) /
    # KOSIS 101/DT_1J22003 소비자물가지수(전국 총지수, 2020=100, 통계청) — 2026.10.18 조회, 연간
    INDEX = {2013: (88.4, 93.010), 2015: (89.8, 94.861), 2018: (96.2, 99.086), 2019: (98.8, 99.466),
             2020: (100.0, 100.00), 2021: (108.6, 102.50), 2022: (117.1, 107.72), 2023: (120.4, 111.59),
             2024: (122.1, 114.18), 2025: (122.9, 116.61)}
    INDEX_SRC = ("KOSIS 301/DT_200Y112 건설투자 디플레이터(한국은행) · 101/DT_1J22003 소비자물가지수 전국(통계청), "
                 "2020=100, 2026.10.18 조회")
elif BASE_YEAR != 2021:
    sys.exit("기준연도는 2021(기본) 또는 2025만 지원")
SUFFIX = "" if BASE_YEAR == 2021 else f"_{BASE_YEAR}기준"
SC = f"시설비_{BASE_YEAR}_억"

# 예타 총괄요약표의 '예비타당성조사(본 조사)' 총사업비 (부가세 포함)
PROJECTS = [  # 사업, 보고서번호, 발행, 기준연도, 총사업비(억), 차량구입비(억, 총사업비에 포함된 경우), 총연장, 신설연장, 출처, 단가 대표값 사용
    ("춘천~속초 철도건설", "15000", "2016.07", 2013, 20630.63, 0.00, 93.95, 93.95,
     "요약 <표 25> PDF p57 (차량 1,674억 별도), 2013.12 가격", True),
    ("광주송정~순천 단선전철", "16487", "2020.02", 2018, 17702.80, 258.78, 122.2, 67.6,
     "요약 <표 18> 31쪽(PDF p58), 신설 67.6km는 PDF p158", False),
    ("문경~김천 단선전철", "17842", "2023.01", 2018, 13031.13, 188.60, 69.8, 69.8,
     "<표 9> PDF p52, <표-20> PDF p71", True),
    ("평택~부발 단선전철", "19042", "2025.06", 2020, 20041.00, 1001.00, 59.4, 59.4,
     "요약 53쪽(PDF p80), 비용 내역 PDF p198", True),
    ("동해선 삼척~강릉 고속화", "19162", "2026.04", 2021, 11507.14, 0.00, 45.2, 31.2,
     "요약 <표 51> 59쪽(PDF p89), 차량비 없음, 기존선 활용 14.0km", False),
]
# 노선별 유사 사업 (지역·지형이 비슷한 예타)
SIMILAR = {"K2": "동해선 삼척~강릉 고속화", "K4": "문경~김천 단선전철", "K6": "평택~부발 단선전철", "K7": "광주송정~순천 단선전철"}

# 세부지침 도로·철도부문(KDI, 2021) — 인쇄 쪽 / PDF 쪽
ANALYSIS = [
    ("분석 기준연도(가격)", BASE_YEAR, "년", f"모든 금액을 {BASE_YEAR}년 가격으로 맞춤"),
    ("운영기간(철도)", 40, "년", "세부지침(2021) 319쪽(PDF p346): 철도사업은 운영개시 후 40년"),
    ("사회적 할인율", 0.045, "", "세부지침(2021) 320쪽(PDF p347): 4.5%"),
    ("사회적 할인율(철도 운영 31년차~)", 0.035, "", "세부지침(2021) 320쪽: 운영기간 30년 이상 철도는 30년 이후 3.5%"),
]
CO2_COST_2015 = 44  # 원/kg, 세부지침 표 Ⅴ-31 304쪽(PDF p331), EPA(2013), 2015년 기준
CAR_CO2 = {10: 380.85, 20: 251.48, 30: 197.30, 40: 166.10, 50: 145.34, 60: 130.33, 70: 118.85,
           80: 109.73, 90: 102.27, 100: 96.03}  # g/km, 승용차, 세부지침 표 Ⅴ-30 302쪽(PDF p329)
CAR_AIR_2019 = {  # 원/km, 승용차, 세부지침 표 Ⅴ-32 305쪽(PDF p332), 2019년 기준: CO, NOx, VOC, PM도심, PM교외, PM지방, CO2
    60: (0.05, 3.26, 0.05, 3.18, 0.83, 0.33, 5.96), 70: (0.05, 2.98, 0.04, 2.99, 0.78, 0.31, 5.43),
    80: (0.04, 2.75, 0.04, 2.83, 0.73, 0.29, 5.01), 90: (0.04, 2.57, 0.04, 2.71, 0.70, 0.28, 4.68),
    100: (0.04, 2.41, 0.03, 2.59, 0.67, 0.27, 4.38)}
OCCUPANCY = {"강원": 1.47, "경북": 1.34, "충남": 1.47, "전남": 1.44}  # 인/대, 권역간 승용차 재차인원
OCC_SRC = "한국교통연구원 교통수요 분석 기초자료 배포 설명자료(2021), 평택~부발 예타 <표 Ⅳ-26> 216쪽(PDF p243) — 권역간 값"
RAIL_CO2 = {"기준": 24.0, "낮음": 17.0, "높음": 34.6}  # g CO2/인km, 지침에 없음 → 언론·정부 자료
RAIL_SRC = ("기준 24 = 코레일 자료 '서울~부산 KTX 1인 9.98kg'(아주경제 2014.03.30) ÷ 경부고속선 417.5km (B 계산) / "
            "낮음 17 = 고속철도 17gCO2/인km(뉴데일리 2021.01.05 보도, 원 출처 미확인) / "
            "높음 34.6 = 여객철도 34.6gCO2/인km(국토해양부, 2001년 기준)")
EMU260_SET = 185.11  # 억원/편성(6량), 2021년 가격·부가세 제외, 삼척~강릉 예타 <표 16> PDF p52 (2020 철도통계연보)

# ---------- 파이썬 계산 (CSV·검증용) ----------
d = pd.DataFrame(PROJECTS, columns=["사업", "보고서", "발행", "기준연도", "총사업비_억", "차량포함분_억",
                                    "총연장_km", "신설연장_km", "출처", "대표값사용"])
d["시설비_억"] = d["총사업비_억"] - d["차량포함분_억"]
d[SC] = d["시설비_억"] * INDEX[BASE_YEAR][0] / d["기준연도"].map(lambda y: INDEX[y][0])
d["km당_총연장_억"] = d[SC] / d["총연장_km"]
d["km당_신설_억"] = d[SC] / d["신설연장_km"]
UNIT = {"기준": d.loc[d["대표값사용"], "km당_신설_억"].mean(),
        "낮음": d["km당_신설_억"].min(), "높음": d["km당_신설_억"].max()}
d.round(2).to_csv(f"kdi_unit_cost{SUFFIX}.csv", index=False, encoding="utf-8-sig")

nl = pd.read_csv("new_lines.csv")
acc = pd.read_csv("sigungu_access.csv").set_index(["시도", "시군"])
CO2_BASE = CO2_COST_2015 * INDEX[BASE_YEAR][1] / INDEX[2015][1]
rows = []
for lid, g in nl.groupby("노선ID"):
    st = g[g["구분"] == "신규"]
    sido = st["시도"].iloc[0]
    sp = [acc.loc[(s, t), "서울_도로거리_km"] / acc.loc[(s, t), "서울_승용차시간_분"] * 60 for s, t in zip(st["시도"], st["시군"])]
    speed = sum(sp) / len(sp)
    sp_row = int(min(100, max(10, round(speed / 10) * 10)))
    car_g = CAR_CO2[sp_row] / OCCUPANCY[sido]
    length = g["누적연장_km"].max()
    sim = d.set_index("사업").loc[SIMILAR[lid], "km당_신설_억"]
    rows.append({"노선ID": lid, "노선명": g["노선명"].iloc[0], "시도": sido, "연장_km": length,
                 "승용차_평균속도_kmh": round(speed, 1), "적용속도_kmh": sp_row, "승용차_CO2_g_per_대km": CAR_CO2[sp_row],
                 "재차인원": OCCUPANCY[sido], "승용차_CO2_g_per_인km": round(car_g, 2),
                 "철도_CO2_g_per_인km": RAIL_CO2["기준"], "전환1인km당_감축_g": round(car_g - RAIL_CO2["기준"], 2),
                 **{f"사업비_{k}_억": round(length * v, 0) for k, v in UNIT.items()},
                 "유사사업": SIMILAR[lid], "유사사업_km당_억": round(sim, 1), "사업비_유사사업_억": round(length * sim, 0)})
cost = pd.DataFrame(rows)
cost.to_csv(f"new_line_cost{SUFFIX}.csv", index=False, encoding="utf-8-sig")

# ---------- 엑셀 `가정` 시트 ----------
F = "Arial"
font, bold, blue = Font(name=F, size=10), Font(name=F, size=10, bold=True), Font(name=F, size=10, color="0000FF")
h1 = Font(name=F, size=12, bold=True)
head_fill, input_fill = PatternFill("solid", fgColor="D9E1F2"), PatternFill("solid", fgColor="FFFF00")
thin = Side(style="thin", color="BFBFBF")
box = Border(left=thin, right=thin, top=thin, bottom=thin)

wb = load_workbook("rail_gap.xlsx")
if "가정" in wb.sheetnames:
    del wb["가정"]
ws = wb.create_sheet("가정")
for col, w in zip("ABCDEFGHIJKLMNOP", [30, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 14, 60, 10]):
    ws.column_dimensions[col].width = w


def put(r, c, v, f=font, fmt=None, fill=None, b=True):
    cell = ws.cell(r, c, v)
    cell.font = f
    if fmt: cell.number_format = fmt
    if fill: cell.fill = fill
    if b: cell.border = box
    return cell


def header(r, cols):
    for j, h in enumerate(cols, 1):
        c = put(r, j, h, bold, fill=head_fill)
        c.alignment = Alignment(wrap_text=True, vertical="center")


r = 1
put(r, 1, f"가정 — 건설 단가·배출·환경비용 원단위 (모든 금액 {BASE_YEAR}년 가격)", h1, b=False)
r += 1
put(r, 1, "파란 글자 = KDI 자료에서 옮긴 값·B 가정(노란 칸은 바꿔 볼 수 있음), 검정 = 수식. 출처 열에 보고서 쪽수 표기", font, b=False)

# 1. 분석 전제
r += 2
put(r, 1, "1. 분석 전제", bold, b=False)
r += 1
header(r, ["항목", "값", "단위"] + [""] * 11 + ["출처"])
cell_of = {}
for name, v, unit, src in ANALYSIS:
    r += 1
    put(r, 1, name)
    put(r, 2, v, blue, "0.0%" if isinstance(v, float) else "0", fill=input_fill if isinstance(v, float) else None)
    put(r, 3, unit)
    put(r, 15, src)
    cell_of[name] = f"$B${r}"

# 2. 보정지수
r += 2
put(r, 1, "2. 보정지수 (2007=100)", bold, b=False)
r += 1
header(r, ["연도", "건설투자 디플레이터", "소비자물가지수", f"→{BASE_YEAR} 건설비 배수", f"→{BASE_YEAR} 편익 배수"] + [""] * 9 + ["출처"])
idx_row = {}
first = r + 1
base_r = first + list(INDEX).index(BASE_YEAR)
for y, (dfl, cpi) in INDEX.items():
    r += 1
    idx_row[y] = r
    put(r, 1, y, font, "0")
    put(r, 2, dfl, blue, "0.0")
    put(r, 3, cpi, blue, "0.0")
    put(r, 4, f"=$B${base_r}/B{r}", font, "0.000")
    put(r, 5, f"=$C${base_r}/C{r}", font, "0.000")
    put(r, 15, INDEX_SRC if y == BASE_YEAR else "")

# 3. 건설 단가
r += 2
put(r, 1, "3. 철도 건설 단가 — KDI 예타 '본 조사' 총사업비 (부가세 포함, 차량구입비 제외)", bold, b=False)
r += 1
header(r, ["사업", "보고서 발행", "기준연도", "총사업비(억)", "포함 차량비(억)", "시설비(억)", f"시설비 {BASE_YEAR}(억)",
           "총연장(km)", "신설연장(km)", "km당 총연장(억)", "km당 신설(억)", "대표값 사용", "", "", "출처 (pimac.kdi.re.kr)"])
p_first = r + 1
for p in PROJECTS:
    r += 1
    name, no, pub, yr, tot, veh, L, Lnew, src, use = p
    put(r, 1, name)
    put(r, 2, pub)
    put(r, 3, yr, blue, "0")
    put(r, 4, tot, blue, "#,##0.00")
    put(r, 5, veh, blue, "#,##0.00")
    put(r, 6, f"=D{r}-E{r}", font, "#,##0.0")
    put(r, 7, f"=F{r}*INDEX($D${first}:$D${base_r},MATCH(C{r},$A${first}:$A${base_r},0))", font, "#,##0.0")
    put(r, 8, L, blue, "0.0")
    put(r, 9, Lnew, blue, "0.0")
    put(r, 10, f"=G{r}/H{r}", font, "0.0")
    put(r, 11, f"=G{r}/I{r}", font, "0.0")
    put(r, 12, "O" if use else "", blue)
    put(r, 15, f"보고서 {no}: {src}")
p_last = r
r += 1
put(r, 1, f"단가 기준 (억원/km, {BASE_YEAR})", bold)
put(r, 11, f'=AVERAGEIF(L{p_first}:L{p_last},"O",K{p_first}:K{p_last})', bold, "0.0", input_fill)
put(r, 15, "신설 위주 3개 사업(대표값 O) 평균. 기존선 활용이 섞인 2개는 범위에만 반영")
unit_ref = {"기준": f"$K${r}"}
r += 1
put(r, 1, "단가 낮음")
put(r, 11, f"=MIN(K{p_first}:K{p_last})", font, "0.0")
put(r, 15, "5개 사업 신설 km당 최소")
unit_ref["낮음"] = f"$K${r}"
r += 1
put(r, 1, "단가 높음")
put(r, 11, f"=MAX(K{p_first}:K{p_last})", font, "0.0")
put(r, 15, "5개 사업 신설 km당 최대")
unit_ref["높음"] = f"$K${r}"
r += 1
put(r, 1, "차량 EMU-260 6량 1편성(억원, 참고)")
put(r, 2, EMU260_SET, blue, "0.00")
put(r, 15, "삼척~강릉 예타 <표 16>·<표 17> PDF p52, 2021년 가격·부가세 제외 (2020 철도통계연보)"
    + ("" if BASE_YEAR == 2021 else f" — {BASE_YEAR}년으로 보정 안 함(설비투자 디플레이터 대상)")
    + ". 사업비에 넣지 않음 — 필요하면 편성 수 × 단가 추가")
emu_ref = f"$B${r}"

# 4. 배출·환경비용
r += 2
put(r, 1, "4. 배출·환경비용 원단위", bold, b=False)
r += 1
header(r, ["항목", "값", "단위"] + [""] * 11 + ["출처"])
r += 1
put(r, 1, "CO2 사회적 비용 (2015년)")
put(r, 2, CO2_COST_2015, blue, "0")
put(r, 3, "원/kg")
put(r, 15, "세부지침(2021) 표 Ⅴ-31 304쪽(PDF p331), EPA(2013)")
co2_2015 = f"$B${r}"
r += 1
put(r, 1, f"CO2 사회적 비용 ({BASE_YEAR}년)")
put(r, 2, f"={co2_2015}*$E${idx_row[2015]}", font, "0.00")
put(r, 3, "원/kg")
put(r, 15, f"2015 → {BASE_YEAR} 소비자물가지수 보정")
co2_2021 = f"$B${r}"
r += 1
put(r, 1, f"CO2 사회적 비용 ({BASE_YEAR}년, 톤당)")
put(r, 2, f"={co2_2021}*1000", font, "#,##0")
put(r, 3, "원/tCO2")
for k in ["기준", "낮음", "높음"]:
    r += 1
    put(r, 1, f"철도 CO2 배출 ({k})")
    put(r, 2, RAIL_CO2[k], blue, "0.0", input_fill if k == "기준" else None)
    put(r, 3, "gCO2/인km")
    if k == "기준":
        put(r, 15, "지침에 철도 배출계수 없음 → " + RAIL_SRC)
        rail_ref = f"$B${r}"

r += 2
put(r, 1, "승용차 속도별 CO2 배출계수 (g/대km) — 세부지침(2021) 표 Ⅴ-30 302쪽(PDF p329)", bold, b=False)
r += 1
header(r, ["속도(km/h)"] + [str(s) for s in CAR_CO2])
r += 1
put(r, 1, "CO2 (g/km)")
co2_tab_r = r
for j, v in enumerate(CAR_CO2.values(), 2):
    put(r, j, v, blue, "0.00")
spd_hdr_r = r - 1
for j, s in enumerate(CAR_CO2, 2):  # 속도 머리글을 숫자로 (MATCH용)
    ws.cell(spd_hdr_r, j).value = s

r += 2
put(r, 1, "승용차 속도별 대기오염비용 (원/대km, 2019년) — 세부지침(2021) 표 Ⅴ-32 305쪽(PDF p332)", bold, b=False)
r += 1
header(r, ["속도(km/h)", "CO", "NOx", "VOC", "PM2.5 도심", "PM2.5 교외", "PM2.5 지방", "CO2",
           f"합계(지방, CO2 제외) {BASE_YEAR}"])
for s, vals in CAR_AIR_2019.items():
    r += 1
    put(r, 1, s, font, "0")
    for j, v in enumerate(vals, 2):
        put(r, j, v, blue, "0.00")
    put(r, 9, f"=(B{r}+C{r}+D{r}+G{r})*$E${idx_row[2019]}", font, "0.00")
r += 1
put(r, 1, "※ 탄소 감축은 위 CO2 배출계수 × CO2 비용으로 따로 계산하므로, 대기오염 합계는 CO2를 빼고 지방(인구 150인/㎢ 이하) PM 값을 씀", font, b=False)

# 5. 노선별 적용값·사업비
r += 2
put(r, 1, "5. 신규 노선별 적용값·사업비 (10/19 `신규구간평가` 입력)", bold, b=False)
r += 1
header(r, ["노선", "시도", "연장(km)", "승용차 평균속도", "적용속도", "승용차 CO2 g/대km", "재차인원(인/대)",
           "승용차 CO2 g/인km", "철도 CO2 g/인km", "전환 1인km당 감축 g", "사업비 기준(억)", "사업비 낮음(억)",
           "사업비 높음(억)", "유사사업 사업비(억)", "비고"])
sim_row = {p[0]: p_first + i for i, p in enumerate(PROJECTS)}
for _, c in cost.iterrows():
    r += 1
    put(r, 1, f"{c['노선ID']} {c['노선명']}")
    put(r, 2, c["시도"])
    put(r, 3, c["연장_km"], blue, "0.0")
    put(r, 4, c["승용차_평균속도_kmh"], blue, "0.0")
    put(r, 5, f"=MIN(100,MAX(10,ROUND(D{r}/10,0)*10))", font, "0")
    put(r, 6, f"=INDEX($B${co2_tab_r}:$K${co2_tab_r},MATCH(E{r},$B${spd_hdr_r}:$K${spd_hdr_r},0))", font, "0.00")
    put(r, 7, OCCUPANCY[c["시도"]], blue, "0.00")
    put(r, 8, f"=F{r}/G{r}", font, "0.00")
    put(r, 9, f"={rail_ref}", font, "0.0")
    put(r, 10, f"=H{r}-I{r}", font, "0.00")
    put(r, 11, f"=C{r}*{unit_ref['기준']}", font, "#,##0")
    put(r, 12, f"=C{r}*{unit_ref['낮음']}", font, "#,##0")
    put(r, 13, f"=C{r}*{unit_ref['높음']}", font, "#,##0")
    put(r, 14, f"=C{r}*K{sim_row[c['유사사업']]}", font, "#,##0")
    put(r, 15, f"유사사업 = {c['유사사업']}" + ("  · 정부 추진 중 노선(동해북부선)과 겹침" if c["노선ID"] == "K2" else ""))
r += 1
put(r, 1, "승용차 평균속도 = 신규 역 시군 중심 → 서울시청 카카오 길찾기(평일 10시) 도로거리 ÷ 시간, 신규 역 평균 (sigungu_access.csv)", font, b=False)
r += 1
put(r, 1, "재차인원 출처: " + OCC_SRC, font, b=False)
r += 1
put(r, 1, "탄소 감축량(톤/년) = 승용차 전환 인km × 전환 1인km당 감축 g ÷ 10^6  →  A 10/19 계산", font, b=False)
ws.freeze_panes = "B1"
wb.save(f"rail_gap{SUFFIX}.xlsx")

pd.set_option("display.width", 250)
print(d[["사업", "기준연도", SC, "km당_총연장_억", "km당_신설_억", "대표값사용"]].round(1).to_string(index=False))
print({k: round(v, 1) for k, v in UNIT.items()}, f"CO2 {BASE_YEAR} 원/kg", round(CO2_BASE, 2))
print(cost.to_string(index=False))
