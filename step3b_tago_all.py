"""2단계 A (추가): KTX 역 69개 전부의 평일 하루 정차 횟수 (TAGO 열차정보 API)
   → 시군 클러스터링·공백 지수에서 '최근접역에 열차가 얼마나 서는지' 반영용

입력: station_coords.csv (69개 역), tago_stations.json (step3에서 만든 캐시, 같은 폴더)
출력: tago_train_all.csv   역명, nodeid, 수도권까지_최단분, 일일_정차횟수

정차 횟수 = 수도권 종착역(서울·용산·청량리·판교)을 오가는 KTX 편수 (상·하행 합)
  - 강릉선·중앙선은 청량리, 중부내륙선은 판교 발착이라 종착역에 포함
  - 종착역 자신은 주요 경유역(광명·오송·대전·양평·원주·충주)과 오가는 편수로 계산

실행 (cmd):
  set TAGO_KEY=발급받은_Decoding_키
  python step3b_tago_all.py
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

BASE = "https://apis.data.go.kr/1613000/TrainInfo"
CITY_CODES = [11, 12, 21, 22, 23, 24, 25, 26, 31, 32, 33, 34, 35, 36, 37, 38]
TERMINALS = ["서울", "용산", "청량리", "판교(경기)"]
PARTNERS = ["광명", "오송", "대전", "양평", "원주", "충주"]
ALIASES = {
    "김천구미": ["김천(구미)", "김천구미"],
    "울산": ["울산(통도사)", "울산"],
    "여수엑스포": ["여수EXPO", "여수엑스포"],
    "경주": ["경주", "신경주"],
    "판교(경기)": ["판교(경기)", "판교"],
    "진부(오대산)": ["진부(오대산)", "진부"],
}


def query_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    d = dt.date.today()
    d += dt.timedelta(days=(1 - d.weekday()) % 7 or 7)  # 다음 화요일
    return d.strftime("%Y%m%d")


def call(op, **params):
    params.update(serviceKey=KEY, _type="json", numOfRows=500, pageNo=1)
    r = requests.get(f"{BASE}/{op}", params=params, timeout=15)
    try:
        data = r.json()
    except ValueError:
        sys.exit(f"[{op}] JSON이 아닌 응답 (HTTP {r.status_code}):\n{r.text[:500]}")
    if "response" not in data:
        sys.exit(f"[{op}] 예상과 다른 응답 (HTTP {r.status_code}):\n{json.dumps(data, ensure_ascii=False)[:500]}")
    head = data["response"].get("header", {})
    if head.get("resultCode") not in ("00", None):
        sys.exit(f"[{op}] API 오류: {head}")
    items = data["response"]["body"].get("items")
    if not items:
        return []
    item = items["item"]
    return item if isinstance(item, list) else [item]


def norm(name):
    return re.sub(r"[\s()역]", "", str(name)).upper()


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
by_norm = {norm(k): v for k, v in nodes.items()}


def node_id(name):
    for cand in ALIASES.get(name, []) + [name, re.sub(r"\(.*\)", "", name)]:
        if cand in nodes:
            return nodes[cand]
        if norm(cand) in by_norm:
            return by_norm[norm(cand)]
    return None


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


coords = pd.read_csv("station_coords.csv")
names = coords["원래역명"].tolist() if "원래역명" in coords.columns else coords["역명"].tolist()
show = dict(zip(names, coords["역명"]))  # 원래역명 → 파일 역명 (울산(통도사) → 울산 등)

term_ids = {t: node_id(t) for t in TERMINALS}
miss = [t for t, v in term_ids.items() if v is None]
if miss:
    sys.exit(f"종착역을 TAGO 목록에서 못 찾음: {miss} (tago_stations.json에서 실제 이름 확인 후 ALIASES에 추가)")

rows, unmatched = [], []
for name in names:
    nid = node_id(name) or node_id(show[name])
    if nid is None:
        unmatched.append(name)
        continue
    if name in TERMINALS:
        others = [t for t in TERMINALS if t != name] + PARTNERS
        nos = set()
        for o in others:
            oid = node_id(o)
            if oid:
                nos |= {t["trainno"] for t in trains(nid, oid)} | {t["trainno"] for t in trains(oid, nid)}
        rows.append({"역명": show[name], "nodeid": nid, "수도권까지_최단분": 0, "일일_정차횟수": len(nos)})
    else:
        up, down = [], []
        for tid in term_ids.values():
            up += trains(nid, tid)
            down += trains(tid, nid)
        rows.append({"역명": show[name], "nodeid": nid,
                     "수도권까지_최단분": round(min(map(minutes, up))) if up else None,
                     "일일_정차횟수": len({t["trainno"] for t in up} | {t["trainno"] for t in down})})
    print(f"  {show[name]}: 정차 {rows[-1]['일일_정차횟수']}회")

out = pd.DataFrame(rows).sort_values("일일_정차횟수")
out.to_csv("tago_train_all.csv", index=False, encoding="utf-8-sig")
print(f"\n완료: {len(out)}개 역")
if unmatched:
    print("[TAGO에서 역을 못 찾음 → ALIASES에 추가 필요]", unmatched)
print("\n[정차가 적은 역 10개]\n" + out.head(10)[["역명", "일일_정차횟수"]].to_string(index=False))
