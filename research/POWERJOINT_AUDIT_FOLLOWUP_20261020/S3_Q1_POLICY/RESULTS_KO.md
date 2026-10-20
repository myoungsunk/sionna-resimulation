# S3 Q1 v3 결과

TECHNICAL: TECHNICAL_PASS. 과학 판정: NOT_ESTABLISHED / NO_GO.

주 판정: Full 32/64, Native LoS 0/8. 주 평가는 seed 0, 전체 motion clock t≥30 s다. NO_MARGIN은 같은 모델에서 margin만 0으로 적용한 대조이며 Full 28/64, LoS 1/8이다. v3 판정을 NO_MARGIN으로 대체하지 않는다.

독립 scalar/Cholesky scorer의 공통 11지표 최대 차이는 2.415845301584341e-13이다. historical POWER 재현과 항상 POWER callback, all-frame SPD/finite, nonradio update, 저장·재로딩 검사는 CHECKS.csv와 각 실행 manifest에 보존한다. 행동 선택 비율과 gate 수락은 ACTION_RATES.csv의 별도 열이다. POWER 선택을 갱신 수락으로 세지 않는다.

역사적 POWER 72셀의 Heading 최대 차이는 1.3877787807814457e-13°, gate 불일치는 0이다. 항상 POWER callback 72셀의 상태/공분산 최대 차이는 0.0 / 0.0, gate 불일치는 0, 비RF 갱신은 0이다. 기존 KEY_B0 7셀 최대 차이는 3.26405569239796e-14°다.

## 모든 v3 위반 셀

| case | channel | bias | 기준 RMSE° | v3 RMSE° | 비율 |
|---|---|---|---:|---:|---:|
| C01_A_M45_FULL | full | L2 | 4.137750425 | 5.235030712 | 1.265188 |
| C02_B_M45_FULL | full | B0 | 1.220517378 | 1.768122775 | 1.448667 |
| C02_B_M45_FULL | full | L0 | 1.219028442 | 1.762655847 | 1.445951 |
| C02_B_M45_FULL | full | L1 | 1.211295968 | 2.390708621 | 1.973678 |
| C02_B_M45_FULL | full | L2 | 1.187266945 | 2.078161950 | 1.750375 |
| C03_B_M45_FULL | full | B0 | 0.801080719 | 1.134233651 | 1.415879 |
| C03_B_M45_FULL | full | L0 | 0.800790673 | 1.147478540 | 1.432932 |
| C03_B_M45_FULL | full | L1 | 0.802005569 | 1.043378059 | 1.300961 |
| C03_B_M45_FULL | full | L2 | 0.893947249 | 1.263884129 | 1.413824 |
| O01_O0_M45_FULL | full | B0 | 0.455959814 | 0.626202825 | 1.373373 |
| O01_O0_M45_FULL | full | L0 | 0.454411993 | 0.643531140 | 1.416184 |
| O01_O0_M45_FULL | full | L1 | 0.449309718 | 0.626369575 | 1.394071 |
| O01_O0_M45_FULL | full | L2 | 0.452925726 | 0.609166208 | 1.344958 |
| O02_O0_M45_FULL | full | B0 | 2.220133963 | 5.626952217 | 2.534510 |
| O02_O0_M45_FULL | full | L0 | 2.210473357 | 5.545397147 | 2.508692 |
| O02_O0_M45_FULL | full | L1 | 2.180503365 | 5.470227767 | 2.508700 |
| O02_O0_M45_FULL | full | L2 | 2.072784554 | 2.503973369 | 1.208024 |
| R2_aA_m0 | full | B0 | 1.798910046 | 6.416551579 | 3.566911 |
| R2_aA_m0 | full | L0 | 1.796572619 | 6.382360615 | 3.552520 |
| R2_aA_m0 | full | L1 | 1.795002512 | 6.383976527 | 3.556528 |
| R2_aA_m0 | full | L2 | 1.558987658 | 6.368348976 | 4.084926 |
| R2_aA_m0 | los | B0 | 0.502160096 | 0.931470601 | 1.854928 |
| R2_aA_m0 | los | L0 | 0.478239559 | 0.921185578 | 1.926201 |
| R2_aA_m0 | los | L1 | 0.399067068 | 0.847675357 | 2.124143 |
| R2_aA_m0 | los | L2 | 0.298943071 | 0.683844417 | 2.287541 |
| R2_aA_m45 | full | B0 | 0.982633936 | 1.381260626 | 1.405672 |
| R2_aA_m45 | full | L0 | 0.979989888 | 1.380398943 | 1.408585 |
| R2_aA_m45 | full | L1 | 0.974160949 | 1.373146700 | 1.409569 |
| R2_aA_m45 | full | L2 | 0.941907031 | 1.380742367 | 1.465901 |
| R2_aA_m45 | los | B0 | 0.153262317 | 0.491726449 | 3.208398 |
| R2_aA_m45 | los | L0 | 0.153761544 | 0.488477111 | 3.176848 |
| R2_aA_m45 | los | L1 | 0.156536600 | 0.475349650 | 3.036668 |
| R2_aA_m45 | los | L2 | 0.180166191 | 0.445949633 | 2.475213 |
| R2_aB_m0 | full | B0 | 1.515858347 | 1.699931390 | 1.121432 |
| R2_aB_m0 | full | L0 | 1.499817297 | 1.688149737 | 1.125570 |
| R2_aB_m0 | full | L1 | 1.453750410 | 1.611741418 | 1.108678 |
| R4_aA_m0 | full | L2 | 0.656658329 | 0.728111676 | 1.108814 |
| R5_aB_m0 | full | B0 | 1.056234383 | 1.708676201 | 1.617706 |
| R5_aB_m0 | full | L0 | 1.029308263 | 1.605750138 | 1.560028 |
| R5_aB_m0 | full | L1 | 0.921693491 | 1.273639337 | 1.381847 |

## 선택 조건부 margin

| outer | action | delta (deg²) | OOF 선택 행 | 상태 |
|---|---|---:|---:|---|
| R2 | R0 | 0.10920470153773562 | 51531 | CALIBRATED_SELECTED_OOF |
| R2 | INFLATE4 | 0.058282543918534636 | 8184 | CALIBRATED_SELECTED_OOF |
| R2 | SKIP | 0.13950662162675215 | 10565 | CALIBRATED_SELECTED_OOF |
| R4 | R0 | 0.3098282903902245 | 53727 | CALIBRATED_SELECTED_OOF |
| R4 | INFLATE4 | 0.07907821310441866 | 22047 | CALIBRATED_SELECTED_OOF |
| R4 | SKIP | 0.11559369610810949 | 19566 | CALIBRATED_SELECTED_OOF |
| R5 | R0 | 0.1473175273636818 | 24415 | CALIBRATED_SELECTED_OOF |
| R5 | INFLATE4 | 0.09517701839480874 | 19479 | CALIBRATED_SELECTED_OOF |
| R5 | SKIP | 0.17331846289360617 | 24526 | CALIBRATED_SELECTED_OOF |
| ALL_OLD | R0 | 0.3964278962590081 | 45714 | CALIBRATED_SELECTED_OOF |
| ALL_OLD | INFLATE4 | 0.039146184289087144 | 44414 | CALIBRATED_SELECTED_OOF |
| ALL_OLD | SKIP | 0.1418947894345743 | 26892 | CALIBRATED_SELECTED_OOF |

## 행동 선택과 gate 수락 (t≥30 s RF)

| 입력 | arm | RF 결정 수 | 행동 선택 비율 | 전체 gate 수락 비율 |
|---|---|---:|---|---:|
| full | POLICY_NO_MARGIN | 34240 | POWER 15.6016% / R0 29.0362% / INFLATE4 19.2377% / SKIP 36.1244% | 59.7897% |
| full | POLICY_V3 | 34240 | POWER 79.6525% / R0 8.9574% / INFLATE4 4.5999% / SKIP 6.7903% | 88.7909% |
| los | POLICY_NO_MARGIN | 6632 | POWER 9.3637% / R0 72.0899% / INFLATE4 8.5645% / SKIP 9.9819% | 90.0181% |
| los | POLICY_V3 | 6632 | POWER 69.9186% / R0 26.0404% / INFLATE4 0.3619% / SKIP 3.6791% | 96.3209% |

RF 결정 수는 동일 RF의 조건·bias 반복을 포함한 처리 횟수이며 독립 표본 수가 아니다. 자세한 셀별 수치는 ACTION_RATES.csv다. 선택과 수락을 구분한다.

## 해석 범위

학습은 전수 RF×4 bias×5 seed이며 105개 분할의 포함 label 351,060행을 사용한다. 고정 index의 후보 435,060행 중 t<30s 63,000행과 불완전 horizon 21,000행은 제외 명단에 보존한다. 이 수치는 fold·bias·seed 반복을 포함한다. label loss는 현재 시점 제외 (t,t+10s]의 단발 개입 후 POWER 복귀다. 반면 평가 정책은 매 패킷 다시 행동을 선택한다. 이 단발 label과 지속 재귀 정책의 상태·목적함수 차이를 해소했다고 주장하지 않는다.

R2-heldout은 학습에 M45 mount가 없는 OUT_OF_TRAINING_RANGE_MOUNT 평가를 포함한다. q 기반 모델과 gate는 기존 기준을 유지했으며 S2 GEOM은 채택하지 않았다.

OOF는 고정 v2 prior-label에서 HGB 단계 route-heldout이다. ROUTE_DEPENDENCIES.csv에 상위 P1의 검증 route 의존성을 기록했다. 전체 pipeline OOF나 독립 보정·coverage 보장은 없다. 중첩 창과 동일 RF의 bias/seed 및 fold 중복은 독립 정보가 아니다. ALL_OLD 기준 고유 eligible RF 5,851개, greedy 비겹침 10초 창 120개는 조건별 합계이며 독립 장면 수가 아니다.

기존 복도와 신규 C01–C03은 같은 복도 장면이며 O01–O03은 하나의 오피스 장면이다. 조건 수·seed 수를 독립 표본으로 쓰거나 p-value를 보고하지 않는다. 모든 실패와 불리한 효용을 보존하며, S0/S1/S2와 v2 NO-GO를 변경하지 않는다. S3 후 새 정책 변형이나 다음 단계를 시작하지 않는다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, margin의 coverage 보장, q의 인과적 독립 정보는 주장하지 않는다.

## 실행과 보존 증거

사전 등록 commit: 17274785e30a033dd242088e57bc9ff197b3fca1. label 코드 commit: 1e092428b178d2f5ab2ac1c022f6956d01373363. 최종 학습·평가 run: 39390153193, head: 3617e2aea23f2ac49b13ea6486391951b76a48cb. 원본 archive 118개의 전체 SHA256·CRC·멤버 SHA와 release 재다운로드 SHA를 MANIFEST.json에 기록했다. 요약 release asset: https://github.com/myoungsunk/sionna-resimulation/releases/download/audit-traces-20261020-r01/powerjoint-s3-results-39390280480.zip, SHA256: 74fe1fb291a6bbcfa7bf0279134120e75543eeda76b7ef6792ce8162b6558e95.

최초 학습 대기 run 39378550447의 연결 오류, 최초 보존 run 39380336271의 경로 오류, 학습 retry1 run 39380603592의 불필요한 P1 pickle 바이트 동일성 검사 오류를 보존했다. P1 전체 fitted 수치의 최대 차이는 1.1102230246251565e-16이었으며, 기존 ScalarPower의 1e-12 fitter-parity 기준으로 검증 코드를 수정했다. label·학습 설정·OOF/δ·판정 계약은 바꾸지 않았고 원 label을 재사용했다. 원본 P1 hash와 수치 대조는 P1_NUMERICAL_EQUIVALENCE.csv에 남긴다. 당시 존재한 107개 archive의 보존 run 39380765996은 성공했고, 로컬 회수기의 이전 기대 수 116과 달라 생긴 count 오류도 보존했다. 최종 재시도 run은 39390153193, 최종 보존 run은 39390280480다. 이전 실패 자료와 수정·재시도 관계는 IMPLEMENTATION_REPAIR_01.md, ERRORS.json 및 preparation_failures/에 남긴다. 결과 파일의 최종 git commit과 전체 hash index는 MANIFEST.json 및 OUTPUT_INDEX.json을 따른다.
