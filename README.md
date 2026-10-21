# KTX 공백 지도: 교통약자와 탄소로 본 신규 구간 우선순위

**AI와 함께하는 교통문제 해결을 위한 데이터 분석 공모전** · 팀 ITZ (채요원, 박세희)

KTX 접근성이 낮고 고령자가 많으며 승용차 의존이 큰 시군을 공공데이터로 찾았습니다. 그 지역을 기존 KTX 노선에 잇는 신규 구간 4개를 이용객, 탄소 감축, 교통약자 수혜, 사업비로 비교해 우선순위를 제안합니다.

---

## 주요 결과

| 구분 | 결과 |
|---|---|
| 철도 공백 진단 | 공백 지수 1위 강원 고성, 2위 충남 태안, 4위 경북 영양. 가중치를 1,000번 무작위로 바꿔도 상위 20위 안에 들 확률 88~96% |
| 공백 상위 15개 시군 | KTX역까지 승용차 평균 78분(전국 중앙값 28분), 고령화율 31.4%, 65세 이상 18.3만 명 |
| 시군 유형화 (K-means) | 접근 공백형 80개 시군(역까지 평균 52분), 서비스 공백형 49개 시군(역은 16분 거리지만 하루 정차 25회) |
| KTX 역 수요 모형 | 로그 선형회귀, Leave-One-Out R² 0.88, 오차율 중앙값 26.5% (XGBoost·랜덤포레스트보다 우수) |
| 신규 구간 평가 | K6 충남 서해안선(천안아산~예산~서산~태안)이 이용객 72.6만 명, 수혜 고령자 9.3만 명, 고령자 1인당 사업비 3,207만 원으로 1위. 민감도 24개 조합 중 22번 1위 |
| 정책 제안 | 공백 상위 15곳 중 국가철도망 사업·건의에 없는 곳은 태안·영양뿐. 서산~태안 약 19km 연장, 영양 연계교통, 예타에 교통약자 접근성 지표 반영 |

---

## 실행 환경

- Python 3.10 이상
- 패키지

```bash
pip install pandas numpy statsmodels scikit-learn xgboost matplotlib geopandas shapely openpyxl requests python-dotenv
```

- 지도와 그림의 한글 글꼴: Windows는 맑은 고딕을 자동으로 씁니다. Mac은 AppleGothic, Linux는 NanumGothic 또는 Noto Sans CJK KR을 설치하세요.

### API 키

| 키 | 쓰는 곳 | 넣는 방법 |
|---|---|---|
| 카카오 REST API 키 (로컬 API) | `step2_geocode.py` | 환경변수 `KAKAO_REST_KEY` |
| 카카오 REST API 키 (카카오모빌리티 길찾기) | `step2_sigungu_access.py` | 같은 폴더 `.env` 파일에 `kakao_rest_api_key=발급받은_키` |
| 공공데이터포털 인증키 (TAGO 열차정보, Decoding 키) | `step3_tago.py`, `step3b_tago_all.py` | 환경변수 `TAGO_KEY` |

```powershell
# Windows PowerShell 예시
$env:KAKAO_REST_KEY="발급받은_REST_API_키"
$env:TAGO_KEY="발급받은_Decoding_키"
```

---

## 데이터 준비

원자료는 용량과 이용 조건 때문에 저장소에 넣지 않았습니다. 아래에서 받아 지정한 위치에 두세요.

| 데이터 | 출처 | 둘 곳 |
|---|---|---|
| 한국철도공사_KTX 월별 역별 승하차 | [공공데이터포털](https://www.data.go.kr/data/15134123/fileData.do) | 실행 폴더 (`step1_ridership.py` 인자) |
| 한국철도공사_KTX 노선별 역정보 | [공공데이터포털](https://www.data.go.kr/data/15127571/fileData.do) | 실행 폴더 (`step2_geocode.py` 인자) |
| 국토교통부_(TAGO)_열차정보 API | [공공데이터포털](https://www.data.go.kr/data/15098552/openapi.do) | API 키만 필요 |
| 국가데이터처_SGIS 행정구역 통계 및 경계 (2025.06.30) | [공공데이터포털](https://www.data.go.kr/data/15129688/fileData.do) | `raw/sgis/` 에 압축 해제 (시군구·행정동 경계 shp, 2024 인구총괄 CSV) |
| 행정구역(읍면동)별/5세별 주민등록인구 | [KOSIS DT_1B04005N](https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B04005N) | `raw/kosis_pop_sigungu_agg.csv` (2013·2019·2022·2025년, 시군구별 총인구·65세 이상·75세 이상) |
| 자동차등록대수현황 (시군구별) | [KOSIS DT_MLTM_5498](https://kosis.kr/statHtml/statHtml.do?orgId=116&tblId=DT_MLTM_5498) | `raw/molit_car_sigungu.csv` (2019·2022·2025년 12월) |
| 건설투자 디플레이터 / 소비자물가지수 | [KOSIS DT_200Y112](https://kosis.kr/statHtml/statHtml.do?orgId=301&tblId=DT_200Y112) / [DT_1J22003](https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1J22003) | 값을 `step6_assumptions.py` 상수로 옮김 |
| KDI 철도 예타 보고서 5건 + 세부지침(2021) | [KDI 공공투자관리센터](https://pimac.kdi.re.kr) | 값을 `step6_assumptions.py` 상수로 옮김 (쪽수 주석 표기) |

---

## 실행 순서

앞 단계 산출물을 다음 단계가 읽습니다. 위에서부터 차례로 실행하세요.

| 순서 | 스크립트 | 하는 일 | 주요 산출물 |
|---|---|---|---|
| 1 | `step1_ridership.py` | KTX 역별 연간 이용객(2019·2022), 학습용 역 선별 | `station_ridership.csv` |
| 2 | `step2_geocode.py` | 역 주소 → 좌표 (카카오 로컬 API), 69개 역 | `station_coords.csv` |
| 3 | `step1_sigungu_base.py` | 시군별 인구·고령화율·인구 증감률·1인당 승용차 | `sigungu_base.csv` |
| 4 | `step3_tago.py` | 학습용 역의 수도권까지 최단 열차시간·평일 정차 횟수 (TAGO) | `tago_train.csv`, `station_features_base.csv` |
| 5 | `step3b_tago_all.py` | 69개 역 전부의 하루 정차 횟수 | `tago_train_all.csv` |
| 6 | `step4_merge_pop.py` | 역 배후권역 인구 변수 결합 | `station_features.csv` |
| 7 | `step2_sigungu_access.py` | 시군 인구가중 중심 → 최근접 KTX역·서울·대도시 승용차 시간 (카카오모빌리티 길찾기) | `sigungu_access.csv`, `station_car_seoul.csv`, `sigungu_boundary.gpkg` |
| 8 | `step6_add_access.py` | 열차/승용차 시간비, 역-도심 거리 추가 | `station_features.csv` (덮어씀) |
| 9 | `step5_regression.py` | 로그 선형회귀 + LOOCV | `reg_coefficients.csv`, `reg_loocv.png` |
| 10 | `step7_xgboost.py` | 회귀 vs XGBoost vs 랜덤포레스트 비교 | `model_compare.csv`, `model_importance.png` |
| 11 | `step3_gap_index.py` | 철도 공백 지수·시군 순위 (수식으로 다시 계산되는 엑셀 포함) | `sigungu_gap.csv`, `rail_gap.xlsx` |
| 12 | `step8_cluster.py` | 시군 유형화 (K-means, 실루엣 계수로 k 선택) | `sigungu_cluster.csv`, `cluster_scatter.png` |
| 13 | `step4_new_lines.py` | 신규 구간 후보 비교 → 4개 선정, 신규 역 변수 | `new_lines.csv`, `new_station_features.csv` |
| 14 | `step5_maps.py` | 공백 지수 지도 + 신규 구간 | `map_gap_national.png`, `map_new_lines.png` |
| 15 | `step6_assumptions.py 2025` | KDI 건설 단가·배출 원단위, 노선별 사업비 (2025년 가격) | `new_line_cost_2025기준.csv`, `rail_gap_2025기준.xlsx` |
| 16 | `step9_predict_2025.py` | 신규 역 연간 이용객 예측 (정차 10/20/34회, 90% 예측구간) | `new_station_forecast_pop2025.csv` |
| 17 | `step10_carbon_2025.py` | 탄소 감축·교통약자 수혜·효율 지표 | `new_line_evaluation_pop2025.csv` |
| 18 | `step11_sensitivity.py` | 공백 지수 가중치·노선 순위 민감도 | `gap_sensitivity.csv`, `line_sensitivity_summary.csv` |

- `step6_assumptions.py`는 인자 없이 실행하면 2021년 가격으로 계산합니다. 15단계처럼 `2025`를 붙이면 2025년 가격 파일을 따로 만듭니다.
- 16·17단계는 인자 `2022`를 주면 신규 역 인구를 2022년 값으로 계산합니다. 강건성 확인용이며, 노선 순위는 같고 이용객은 11~15% 많습니다.
- 카카오 길찾기 응답은 `raw/kakao_route_cache.json`에 저장되어, 다시 실행하면 API를 부르지 않습니다.

---

## 보고서 그림과 스크립트

| 그림 | 내용 | 스크립트 |
|---|---|---|
| 그림 1 | 시군별 철도 공백 지수와 신규 KTX 구간 4개 | `step5_maps.py` |
| 그림 2 | K-means 시군 유형 | `step8_cluster.py` |
| 그림 3 | KTX 역 수요 모형 교차검증 (실제 vs 예측) | `step5_regression.py` |
| 그림 4 | 신규 역 11개 예상 연간 이용객 | `step9_predict_2025.py` |
| 그림 5 | 노선별 CO2 감축량·탄소 1톤당 사업비·고령자 1인당 사업비 | `step10_carbon_2025.py` |

---

## 주요 가정

- 분석 단위: 시군구 226개 (섬 지역인 제주시·서귀포시·울릉군 제외)
- 공백 지수: 지표 5개를 최소-최대 정규화(0~100) 후 같은 가중치(0.2)로 합산
- 신규 역 위치: 그 시군에서 인구가 가장 많은 행정동. 노선 연장은 직선거리 × 1.3, 표정속도는 120km/h
- 사업비: KDI 단선전철 예타 단가(2025년 가격 311억 원/km) × 연장. 차량비 제외, 개략치
- 탄소: 승용차 전환율 30/50/70%, 서울까지 도로거리 기준. CO2 54,088원/t, 40년, 할인율 4.5%(31년차부터 3.5%)
- 수요 예측 중 청송·영양·양양·속초는 일부 변수가 학습 범위 밖이라 불확실성이 큽니다.

---

## AI 활용

분석 설계 검토, 공공데이터 API 수집·전처리 코드 작성, 오류 수정, 다중공선성 점검, 민감도 분석 설계에 Claude(Anthropic)를 사용했습니다. AI가 작성한 코드는 팀원이 직접 실행해 원자료와 대조했습니다.
