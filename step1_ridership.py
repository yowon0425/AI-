"""1단계 A: 역별 연간 KTX 이용객 정리
입력: KTX 월별 역별 승하차 CSV (CP949, 단위: 천 명)
출력: station_ridership.csv
"""
import sys
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "한국철도공사_KTX 월별 역별 승하차_20230101.csv"
MIN_ANNUAL = 50  # 연간 5만 명(=50천 명) 미만 역은 학습에서 제외

df = pd.read_csv(SRC, encoding="cp949")
df["연도"] = df["년월"].str[:4].astype(int)
long = df.drop(columns="년월").melt(id_vars="연도", var_name="역명", value_name="이용객_천명")

# 연간 합계 + 해당 연도에 0이 아닌 달 수(개통·운행 여부 확인용)
annual = (long.groupby(["역명", "연도"])
              .agg(이용객_천명=("이용객_천명", "sum"),
                   운행월수=("이용객_천명", lambda s: (s > 0).sum()))
              .reset_index())

wide = annual[annual["연도"].isin([2019, 2022])].pivot(index="역명", columns="연도")
wide.columns = [f"{a}_{b}" for a, b in wide.columns]
wide = wide.reset_index()

# 학습용 조건: 2019년 12개월 모두 운행 + 연간 5만 명 이상
wide["학습사용"] = (wide["운행월수_2019"] == 12) & (wide["이용객_천명_2019"] >= MIN_ANNUAL)
wide = wide.sort_values("이용객_천명_2019", ascending=False)

out = wide[["역명", "이용객_천명_2019", "이용객_천명_2022", "운행월수_2019", "운행월수_2022", "학습사용"]]
out.to_csv("station_ridership.csv", index=False, encoding="utf-8-sig")

print(f"전체 역: {len(out)}  /  학습용: {out['학습사용'].sum()}")
print("\n[제외된 역]")
print(out[~out["학습사용"]][["역명", "이용객_천명_2019", "운행월수_2019"]].to_string(index=False))
