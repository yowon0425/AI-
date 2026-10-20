"""1단계 A: KTX 역 주소 → 좌표 변환 (카카오 로컬 API)
입력: KTX 노선별 역정보 CSV (CP949)
출력: station_coords.csv

실행 전 터미널에서 키를 환경변수로 넣어두기 (코드에 키를 직접 쓰지 않음)
  Windows (PowerShell):  $env:KAKAO_REST_KEY="발급받은_REST_API_키"
  Mac/Linux:             export KAKAO_REST_KEY="발급받은_REST_API_키"
실행:
  python step2_geocode.py "한국철도공사_KTX 노선별 역정보_20251121.csv"
"""
import os
import sys
import time

import pandas as pd
import requests

SRC = sys.argv[1] if len(sys.argv) > 1 else "한국철도공사_KTX 노선별 역정보_20251121.csv"
KEY = os.environ.get("KAKAO_REST_KEY")
if not KEY:
    sys.exit("KAKAO_REST_KEY 환경변수가 없습니다. 파일 맨 위 설명대로 먼저 설정하세요.")

HEADERS = {"Authorization": f"KakaoAK {KEY}"}
ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 승하차 파일과 역명이 다른 경우 승하차 파일 이름으로 통일
NAME_MAP = {"울산(통도사)": "울산", "여수EXPO": "여수엑스포"}


def by_address(addr):
    r = requests.get(ADDR_URL, headers=HEADERS, params={"query": addr}, timeout=10)
    r.raise_for_status()
    docs = r.json()["documents"]
    if not docs:
        return None
    d = docs[0]
    a = d.get("address") or d.get("road_address") or {}
    return float(d["x"]), float(d["y"]), a.get("region_1depth_name"), a.get("region_2depth_name")


def by_keyword(name):
    # 주소 검색이 실패하면 "OO역" 키워드로 다시 검색
    r = requests.get(KEYWORD_URL, headers=HEADERS, params={"query": f"{name}역"}, timeout=10)
    r.raise_for_status()
    docs = r.json()["documents"]
    if not docs:
        return None
    d = docs[0]
    parts = d["address_name"].split()
    return float(d["x"]), float(d["y"]), parts[0] if parts else None, parts[1] if len(parts) > 1 else None


info = pd.read_csv(SRC, encoding="cp949")
info["역명"] = info["역명"].str.strip()
info["주소"] = info["주소"].str.strip()
lines = info.groupby("역명")["노선명"].apply(lambda s: ",".join(sorted(set(s)))).rename("노선")
stations = info.drop_duplicates("역명").set_index("역명")[["주소"]].join(lines).reset_index()

rows = []
for _, s in stations.iterrows():
    res, how = by_address(s["주소"]), "주소"
    if res is None:
        res, how = by_keyword(s["역명"].split("(")[0]), "키워드"
    if res is None:
        res, how = (None, None, None, None), "실패"
    lon, lat, sido, sigungu = res
    rows.append({"역명": NAME_MAP.get(s["역명"], s["역명"]), "원래역명": s["역명"], "노선": s["노선"],
                 "주소": s["주소"], "경도": lon, "위도": lat, "시도": sido, "시군구": sigungu, "변환방법": how})
    time.sleep(0.1)

out = pd.DataFrame(rows)
out.to_csv("station_coords.csv", index=False, encoding="utf-8-sig")

print(f"전체 {len(out)}개 역  /  주소 {sum(out['변환방법']=='주소')}  키워드 {sum(out['변환방법']=='키워드')}  실패 {sum(out['변환방법']=='실패')}")
check = out[out["변환방법"] != "주소"]
if len(check):
    print("\n[주소 검색이 안 돼서 확인이 필요한 역]")
    print(check[["역명", "주소", "시도", "시군구", "변환방법"]].to_string(index=False))
