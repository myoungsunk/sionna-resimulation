# S2 N2 기하 특징 검증

기술적 상태: **TECHNICAL_PASS**. GEOM q 대체 후보: **NOT_ESTABLISHED**.

승인된 확장으로 GEOM/GEOM_Q 평균 회귀는 10/11차원, 잔차 평균·공분산은 같은 학습 3D 거리 삼분위다. 검증된 실행 기준 엔진 @034e57a 본문과 SourceFFD 관측, B_OLD, H·gate·update를 보존했다. 주 평가는 전체 motion clock의 t≥30 s, seed 0이다.

| 사전 고정 기준 | 통과 | 필요한 통과 |
|---|---:|---:|
| 신규 seed 0 GEOM ≤ 1.10 Q | 13/36 | 36/36 |
| 기존 M0 GEOM ≤ 1.10 DIST_ONLY | 4/12 | 12/12 |
| 신규 seed 0 GEOM_Q < 0.95 GEOM | 16/36 | 19/36 |

위반 셀과 실제 Heading RMSE는 VIOLATIONS.csv, 전체 네 arm 비교는 GAIN_COMPARISON.csv에 보존했다. 계산 실패/누락을 삭제하여 분모를 줄이지 않았다. 공통 11개 지표는 RESULTS.csv의 792/792행과 별도 Native LoS R0 4/4행에 있다. 독립 scalar/Cholesky scorer 최대 차이는 3.637978807091713e-12다.

Native LoS 각 arm의 R0 대비 절대·상대 변화는 LOS_SAFETY.csv에 별도로 기록했다. 안전성은 GEOM 지지식과 분리한다. 같은 RF의 motion noise 반복은 SEED_SUMMARY.csv에서 셀별 min/median/max·최악 seed·위반 seed 수로 보고한다. seed 평균으로 seed 0 실패를 상쇄하지 않는다. 그룹별 q 추가 개선 분모는 GROUP_COMPARISON.csv에 분리했다.

## 재현과 제한

Q 기준선은 기존 Full의 역사적 POWER1 trace/KEY_B0, Native LoS의 T9 Q trace, 신규 seed 0의 T2 trace와 대조했다. 신규 seed 1–4는 동결 T2 코드/μ/C로 재생성한 reference이며 역사적 gate trace 일치를 주장하지 않는다. 같은 seed/bias/motion의 T2 Heading 지표도 대조했다. DIST_ONLY–T9 차이는 CHECKS.csv의 행별 기록을 참조한다. 입력 SHA, 학습 key/site 분할, 모델 파라미터, 실패는 삭제하지 않았다.

R2 A M45 heldout은 **OUT_OF_TRAINING_RANGE_MOUNT**다. mount 특징을 추가해도 학습에 M45가 없는 한계가 해결되었다고 주장하지 않는다. 미확보 입력/실패는 ERRORS.json 및 technical 상태에 따른다.

## 주장하지 않는 것

독립 장면 일반화, 조건 수·seed 수를 독립 표본 수로 해석한 유의성, q의 물리 기전 또는 인과적 독립 정보 증명, 정규화 Bayesian posterior, 실측 하드웨어 실증을 주장하지 않는다. S0 OPEN/NOT_ESTABLISHED, 원래 77개 BLOCKED_SOURCE_UNAVAILABLE 및 S1 개정 79개/실패 기록을 보존했다. S3는 시작하지 않았다.

## 고정 기준 위반 셀

| 기준 | case | bias | GEOM ° | 기준 arm ° |
|---|---|---|---:|---:|
| NEW_SEED0_36 | C01_A_M45_FULL | B0 | 4.426419745 | 3.966128959 |
| NEW_SEED0_36 | C01_A_M45_FULL | L0 | 4.438315212 | 3.974988074 |
| NEW_SEED0_36 | C01_A_M45_FULL | L1 | 4.484382647 | 4.014458139 |
| NEW_SEED0_36 | C01_A_M45_FULL | L2 | 4.633492945 | 4.137750425 |
| NEW_SEED0_36 | C02_B_M45_FULL | B0 | 1.391314833 | 1.220517378 |
| NEW_SEED0_36 | C02_B_M45_FULL | L0 | 1.392221787 | 1.219028442 |
| NEW_SEED0_36 | C02_B_M45_FULL | L1 | 1.398683479 | 1.211295968 |
| NEW_SEED0_36 | C02_B_M45_FULL | L2 | 1.425124428 | 1.187266945 |
| NEW_SEED0_36 | C03_A_M45_FULL | B0 | 0.762291437 | 0.610194273 |
| NEW_SEED0_36 | C03_A_M45_FULL | L0 | 0.752156809 | 0.605210059 |
| NEW_SEED0_36 | C03_A_M45_FULL | L1 | 0.718607618 | 0.599460339 |
| NEW_SEED0_36 | C03_B_M45_FULL | B0 | 1.340604819 | 0.801080719 |
| NEW_SEED0_36 | C03_B_M45_FULL | L0 | 1.341783203 | 0.800790673 |
| NEW_SEED0_36 | C03_B_M45_FULL | L1 | 1.369189730 | 0.802005569 |
| NEW_SEED0_36 | C03_B_M45_FULL | L2 | 1.444980925 | 0.893947249 |
| NEW_SEED0_36 | O01_O0_M45_FULL | B0 | 1.367884838 | 0.455959814 |
| NEW_SEED0_36 | O01_O0_M45_FULL | L0 | 1.373119179 | 0.454411993 |
| NEW_SEED0_36 | O01_O0_M45_FULL | L1 | 1.394432387 | 0.449309718 |
| NEW_SEED0_36 | O01_O0_M45_FULL | L2 | 1.466233200 | 0.452925726 |
| NEW_SEED0_36 | O03_O0_M45_FULL | B0 | 31.989709008 | 6.868341041 |
| NEW_SEED0_36 | O03_O0_M45_FULL | L0 | 31.864184566 | 6.794545631 |
| NEW_SEED0_36 | O03_O0_M45_FULL | L1 | 32.127165752 | 6.666134936 |
| NEW_SEED0_36 | O03_O0_M45_FULL | L2 | 6.847695540 | 5.625802206 |
| LEGACY_M0_12 | R2_aA_m0 | B0 | 5.406339092 | 1.187833088 |
| LEGACY_M0_12 | R2_aA_m0 | L2 | 4.656983295 | 1.456657410 |
| LEGACY_M0_12 | R2_aB_m0 | B0 | 2.122840585 | 1.197936907 |
| LEGACY_M0_12 | R2_aB_m0 | L2 | 1.762801635 | 1.095292374 |
| LEGACY_M0_12 | R4_aA_m0 | B0 | 0.663189898 | 0.582918711 |
| LEGACY_M0_12 | R4_aA_m0 | L2 | 0.654314985 | 0.574289067 |
| LEGACY_M0_12 | R5_aB_m0 | B0 | 11.053606082 | 0.723721798 |
| LEGACY_M0_12 | R5_aB_m0 | L2 | 10.191919404 | 0.569894930 |

## Native LoS 안전성 수치

아래는 네 LoS 셀 각각을 R0와 비교한 절대·상대 변화의 범위다. 양수는 악화다. 전체 16행은 LOS_SAFETY.csv에 보존했다.

| arm | 최소 변화 ° | 최대 변화 ° | 최소 상대 변화 | 최대 상대 변화 |
|---|---:|---:|---:|---:|
| Q_POWER1 | 1.115989609 | 1.606046106 | 319.828% | 785.378% |
| DIST_ONLY | 0.912504193 | 2.026253617 | 403.507% | 660.965% |
| GEOM | 1.117591986 | 5.121477321 | 620.312% | 1561.540% |
| GEOM_Q | 0.758508876 | 2.011499158 | 400.569% | 635.827% |

## 같은 RF의 motion noise 반복

각 arm에서 5개 seed의 셀 내 Heading 범위(max−min)가 가장 큰 셀이다. 모든 case×bias별 min/median/max·최악 seed·위반 seed 수는 SEED_SUMMARY.csv에 있다. 조건/seed를 독립 표본으로 세지 않는다.

| arm | case / bias | min ° | median ° | max ° | 최악 seed |
|---|---|---:|---:|---:|---:|
| DIST_ONLY | O03_O0_M45_FULL / B0 | 7.460960293 | 32.496041634 | 34.501485779 | 4 |
| GEOM | O03_O0_M45_FULL / L0 | 7.249361121 | 33.105808433 | 36.180209675 | 4 |
| GEOM_Q | O03_O0_M45_FULL / L2 | 34.137105309 | 34.843931007 | 36.807831936 | 4 |
| Q_POWER1 | O03_O0_M45_FULL / L2 | 5.466056942 | 5.625802206 | 6.466404617 | 4 |

역사적 trace 재현 54셀의 최대 Heading 차이 1.092459456231154e-13°, gate 불일치 합 0. 재생성 T2 reference 144셀은 역사적 gate 확인과 구분한다. 기존 DIST_ONLY–T9 최대 절대 차이는 4.307665335545608e-14°다.

## 실행·증거 보존

lock `2f1b21b9f984ba0d5d3768f9a84a8f5b7d263683`, 모델/adapter `481c249e04164ffc5deccaaefbcc84c16a5779f3`. 학습 run39374401047, 기존/LoS run39374960558, 신규 성공 run39375649673. 입력 준비 중단 18개 route-job와 보존 단계의 GitHub 연결 중단을 원래 로그·artifact·SHA와 함께 보존했다. 판정·모델·엔진을 바꾸지 않았으며 성공 계산만을 재귀 재실행하지 않았다. MANIFEST.json에 모든 원본 artifact의 digest/bytes, release asset ID/URL, 전체 재다운로드 SHA, run/head를 기록했다.

미해결 입력: 없음(현재 S2 계약 범위). 원래77개 명단 및 구현2·3 원본 소스 미확보는 S0/S1의 제한으로 그대로 남는다.

## 최종 게시 영수증


결과/원본 요약 498개 파일(101,231,274 bytes)은 18개 분할 커밋으로 게시했고 마지막 결과 커밋은 `4a0ec61cabbf73a028ca8096f57dd46374398f4e`다. 최종 metadata/검증 커밋은 이 결과 커밋의 후속이다. 전체 파일 hash는 OUTPUT_INDEX.json, 게시 내역은 PUBLICATION_RECEIPT.json이다.

신규 Q 180셀의 T2 **공통 11지표 전체**를 같은 seed/bias/motion scope로 다시 대조했으며 최대 차이는 3.858247055177344e-12다(T2_METRIC_PARITY.csv). 역사적 gate는 seed 0에 한해 확인했고 seed 1–4는 명시된 재생성 reference다. 증거 보존 성공 run39376022836은 29개 원본 archive의 SHA/CRC 및 release 전체 readback을 확인했다. 최종 독립 검증은 provenance_tools/verify_local.py로 재현한다.

최종 검증 영수증(FINAL_VERIFICATION.json): 게시 파일 532개 byte 일치, S0/S1/기존 감사 tree와 S1 요약 prefix 보존. 추론 특징 285,432행을 저장된 prior 좌표로 독립 재계산한 최대 차이는 3.8302694349567901e-15, μ/C 재계산 최대 차이는 1.6653345369377348e-16다. 최초 root summary 개행 정규화 오류는 정확한 pinned 원문 bytes 복구 후 재검증했고 ERRORS.json에 보존했다.
