"""2단계 A: 역별 서울까지 최단 열차 소요시간 + 평일 정차 횟수 (TAGO 열차정보 API)
         + 역 → 시군(배후권역) 매칭

입력: station_ridership.csv, station_coords.csv (어제 만든 파일, 같은 폴더)
출력: tago_train.csv          역별 열차 변수
      station_features_base.csv  학습용 39개 역: 이용객 + 좌표 + 시군 + 열차 변수

실행 전 공공데이터포털 인증키를 환경변수로 넣기 (마이페이지 > 활용신청 현황 > 일반 인증키 "Decoding")
  cmd:         set TAGO_KEY=발급받은_Decoding_키
  PowerShell:  $env:TAGO_KEY="발급받은_Decoding_키"
실행:
  python step3_tago.py              (조회일 = 다가오는 화요일)
  python step3_tago.py 20261020     (조회일 직접 지정, YYYYMMDD)
"""
import datetime as dt
import json
import os
import re
import sys
import time

import pandas as pd
import requests

KEY = os.environ.get("TAGO_KEY")
if not KEY:
    sys.exit("TAGO_KEY 환경변수가 없습니다. 파일 맨 위 설명대로 먼저 설정하세요.")

BASE = "https://apis.data.go.kr/1613000/TrainInfo"  # 2026년 변경된 주소 (구 TrainInfoService 폐기)
# TAGO 열차정보 도시코드 (시·도 단위)
CITY_CODES = [11, 12, 21, 22, 23, 24, 25, 26, 31, 32, 33, 34, 35, 36, 37, 38]
SEOUL = ["서울", "용산"]           # 서울 도착은 두 역 중 빠른 쪽
HUBS_FOR_SEOUL = ["광명", "오송", "대전"]  # 서울·용산역 자체의 정차 횟수 계산용

# TAGO 역명과 우리 파일 역명이 다를 때 후보 이름 (자동 매칭이 안 되면 여기에 추가)
ALIASES = {
    "김천구미": ["김천(구미)", "김천구미"],
    "울산": ["울산(통도사)", "울산"],
    "여수엑스포": ["여수EXPO", "여수엑스포"],
    "경주": ["경주", "신경주"],
}


def query_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    d = dt.date.today()
    d += dt.timedelta(days=(1 - d.weekday()) % 7 or 7)  # 다음 화요일
    return d.strftime("%Y%m%d")


def call(op, **params):
    params.update(serviceKey=KEY, _type="json", numOfRows=params.get("numOfRows", 500), pageNo=1)
    r = requests.get(f"{BASE}/{op}", params=params, timeout=15)
    try:
        data = r.json()
    except ValueError:
        sys.exit(f"[{op}] JSON이 아닌 응답이 왔습니다 (HTTP {r.status_code}). 인증키를 확인하세요.\n{r.text[:500]}")
    if "response" not in data:
        sys.exit(f"[{op}] 예상과 다른 응답 (HTTP {r.status_code}):\n{json.dumps(data, ensure_ascii=False)[:500]}")
    head = data.get("response", {}).get("header", {})
    if head.get("resultCode") not in ("00", None):
        sys.exit(f"[{op}] API 오류: {head}")
    items = data["response"]["body"].get("items")
    if not items:
        return []
    item = items["item"]
    return item if isinstance(item, list) else [item]


def norm(name):
    return re.sub(r"[\s()역]", "", str(name)).upper()


# ---------- 1. TAGO 역 목록 (nodeid) ----------
CACHE = "tago_stations.json"
if os.path.exists(CACHE):
    nodes = json.load(open(CACHE, encoding="utf-8"))
else:
    nodes = {}
    for code in CITY_CODES:
        for s in call("GetCtyAcctoTrainSttnList", cityCode=code):
            nodes[s["nodename"]] = s["nodeid"]
        time.sleep(0.05)
    json.dump(nodes, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"TAGO 역 목록 {len(nodes)}개")

by_norm = {norm(k): v for k, v in nodes.items()}


def node_id(name):
    for cand in ALIASES.get(name, []) + [name]:
        if cand in nodes:
            return nodes[cand]
        if norm(cand) in by_norm:
            return by_norm[norm(cand)]
    return None


# ---------- 2. 열차 조회 ----------
DATE = query_date()
print(f"조회일: {DATE}")


def trains(dep_id, arr_id):
    rows = call("GetStrtpntAlocFndTrainInfo", depPlaceId=dep_id, arrPlaceId=arr_id, depPlandTime=DATE)
    time.sleep(0.05)
    return [t for t in rows if "KTX" in str(t.get("traingradename", ""))]


def minutes(t):
    dep = dt.datetime.strptime(str(t["depplandtime"]), "%Y%m%d%H%M%S")
    arr = dt.datetime.strptime(str(t["arrplandtime"]), "%Y%m%d%H%M%S")
    return (arr - dep).total_seconds() / 60


ridership = pd.read_csv("station_ridership.csv")
coords = pd.read_csv("station_coords.csv")
target = ridership[ridership["학습사용"]]["역명"].tolist()

seoul_ids = {s: node_id(s) for s in SEOUL}
missing_hub = [s for s in SEOUL + HUBS_FOR_SEOUL if node_id(s) is None]
if missing_hub:
    sys.exit(f"TAGO 역 목록에서 기준역을 못 찾았습니다: {missing_hub} (tago_stations.json에서 실제 이름 확인)")
rows, unmatched = [], []
for name in target:
    nid = node_id(name)
    if nid is None:
        unmatched.append(name)
        continue
    if name in SEOUL:
        nos = set()
        for h in HUBS_FOR_SEOUL:
            hid = node_id(h)
            nos |= {t["trainno"] for t in trains(nid, hid)} | {t["trainno"] for t in trains(hid, nid)}
        rows.append({"역명": name, "nodeid": nid, "서울까지_최단분": 0, "일일_정차횟수": len(nos)})
        continue
    up, down = [], []
    for sid in seoul_ids.values():
        up += trains(nid, sid)
        down += trains(sid, nid)
    rows.append({
        "역명": name, "nodeid": nid,
        "서울까지_최단분": round(min(map(minutes, up))) if up else None,
        "일일_정차횟수": len({t["trainno"] for t in up} | {t["trainno"] for t in down}),
    })
    print(f"  {name}: 최단 {rows[-1]['서울까지_최단분']}분, 정차 {rows[-1]['일일_정차횟수']}회")

tago = pd.DataFrame(rows)
tago.to_csv("tago_train.csv", index=False, encoding="utf-8-sig")

# ---------- 3. 역 → 시군(배후권역) 매칭 ----------
SIDO = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
        "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
        "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
        "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
        "제주": "제주특별자치도"}
METRO = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"}

coords["시도_전체"] = coords["시도"].map(lambda s: SIDO.get(s, s))
# 배후권역: 특별·광역시는 시 전체, 그 외는 시·군 단위 (예: "창원시 의창구" → "창원시")
coords["배후권역"] = coords.apply(
    lambda r: r["시도_전체"] if r["시도_전체"] in METRO else str(r["시군구"]).split()[0], axis=1)

base = (ridership[ridership["학습사용"]]
        .merge(coords[["역명", "경도", "위도", "시도_전체", "시군구", "배후권역"]], on="역명", how="left")
        .merge(tago[["역명", "서울까지_최단분", "일일_정차횟수"]], on="역명", how="left"))
base.to_csv("station_features_base.csv", index=False, encoding="utf-8-sig")

print(f"\n완료: 열차 변수 {len(tago)}개 역 / 학습용 {len(base)}개 역")
if unmatched:
    print("[TAGO에서 역을 못 찾음 → ALIASES에 이름 추가 필요]", unmatched)
miss = base[base["서울까지_최단분"].isna()]["역명"].tolist()
if miss:
    print("[서울 직통 KTX가 조회되지 않은 역]", miss)
