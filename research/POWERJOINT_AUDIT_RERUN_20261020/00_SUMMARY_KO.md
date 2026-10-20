# POWER_JOINT 감사 후 재실행·신규 검증

2026-10-20 S0 사후 적용성 정정: Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다.

구현1/canonical의 현재 지위는 검증된 실행 기준이다. 구현2·3은 DEFERRED_SOURCE_UNAVAILABLE이며 원본 비교·동등성 검증을 완료한 것으로 간주하지 않는다. 파일명 CANONICAL_RESULTS.csv와 역사적 정본 표기는 원문 식별자로 보존한다.

과거 '요청 9,519점 중 2,268점 미확보이므로 BLOCKED_INPUT'이라는 현재 판정은 철회한다. 7,251점 실행 기록과 원문은 보존하며, 서로 다른 모집단의 대응은 별도 S0 모집단 감사에서 판정한다. 이 정정은 새 모집단 수치나 대응 인증을 주장하지 않는다.

T7B NO_GO는 사전 고정한 v2 정책(특징·label·학습·행동 규칙)의 평가 결과에만 적용한다. 효용 target 접근 전체나 가능한 다른 정책의 기각으로 일반화하지 않는다.

수정 전 원문은 후속 S0_CORRECTIONS/ORIGINALS에 보존했다. 숫자 CSV와 원래 DECISION은 변경하지 않았다.

작업 브랜치 `research/powerjoint-audit-rerun-20261020`, base `5ac914fa0ad53de454278d878962c68c2aebaabb`. 실제 Actions 결과를 아래에 기록한다. 계산 성공과 가설 지지는 구분하며 미확보·인증 실패 범위를 PASS로 승격하지 않는다.

| 과제 | 가설 | TECHNICAL | 과학 판정 | 핵심 수치 | 커밋 / run / artifact |
| --- | --- | --- | --- | --- | --- |
| T0 | 입력 보존 | TECHNICAL_PASS | CONFIRMED_IN_REPLAY | 원본 ZIP 5개 release 보존 후 SHA256 재검증 | run39357262848 / artifact12235433909 |
| T1 | 시간기억 | 구현1·576행 PASS; 구현2/3 DEFERRED_SOURCE_UNAVAILABLE | NOT_ESTABLISHED, 채택 FAIL | MEMORY >10% 악화14/64, coverage 개선60/64; R5 A B0 4.556146→8.764142° | 원본3fc70f2 / run39358085399,39359952488,39361490496 / artifact12236825429 및 manifest |
| T2 | 신규 기준선 | TECHNICAL_PASS | NOT_ESTABLISHED (이전 구현 차이 완전 분해); 검증된 실행 기준 고정 | 108행, seed0–4 motion noise 반복; 독립 scorer 최대1.137e−13 | source8bfdd790 / run39359952488 / 6개 artifact manifest |
| T3 | SourceFFD 통일 | B_OLD 계산 PASS; SRC_TAP 설계 무효 | B_OLD NOT_ESTABLISHED; SRC_TAP INVALID_DESIGN_ZERO_RANGE_JACOBIAN | B_OLD L2 J4 M0 .298943°, M45 .180166°; 구 LUT 변경6칸 | run39358530627,39361112976 / artifact12236606373,12237193562 |
| T4 | F1 흡수 경로 | B_OLD 10이벤트 완료; SRC_TAP 설계 무효 | B_OLD NOT_ESTABLISHED; SRC_TAP INVALID_DESIGN_ZERO_RANGE_JACOBIAN | B_OLD POST30 지지0/5; R5 V1 skip +7.740819° | scope lock52b1212 / run39359599833,39361156858,39361448922 / T4 MANIFEST |
| T5 | 초기화 | TECHNICAL_PASS | NOT_ESTABLISHED | 360행; ≥50% 효과 소거 설정 없음; C03 A GLOBAL_T30 skip+.070670° | run39361156858 / artifact12237836289,12237895894 |
| T6 | 검출 tap Range | 당시 계산 기록 보존; SRC_TAP 설계 무효 | INVALID_DESIGN_ZERO_RANGE_JACOBIAN; 과거 모집단 BLOCKED_INPUT 사유 철회 | 잔차0·안정 tap FD0은 연속 EKF range 교정 증거가 아님; B_OLD/B_REFIT_ONLY 유효 | run39358085714,39359601219 / artifact12236256727,12236414588 |
| T7A | 온라인 특징 회수 | TECHNICAL_PASS | SUPPORTED_BUT_LIMITED | 고정12이벤트 abs_s rank AUC .742857, 포화 .700000 | 원본5ac914f / run39354151551 / artifact12233874874 |
| T7B | 효용 target 정책 | TECHNICAL_PASS | NOT_ESTABLISHED, 고정 v2 정책 NO_GO | Full52/64 및 Native LoS8/8에서10% 악화 한도 초과 | protocol e18dcd04 / source4eb01aa8 / run39361956622 / artifact12238630433 |
| T8 | M45 시간 바인딩 | 입력·행별 감사·정지형 비교 PASS; 재귀 BLOCKED_INPUT | BLOCKED_INPUT | 인증0/4; 정렬 행5,606/5,610 실패; 정지형 pose쌍5,610 | source90c7d752 / run39361554110 / artifact12237048283 |
| T9 | q–거리 교란 | TECHNICAL_PASS | NOT_ESTABLISHED (거리 및 Δq); 채택 안 함 | 72행; pooled 거리 회수1.242830이나 조건별80% 실패 | run39359824661 / artifact12237051901 |

각 task의 MANIFEST와 Actions receipt에 전체 source SHA, run/artifact id, archive digest, 회수 member SHA256 및 byte 수를 기록했다. [Actions 실행 목록](https://github.com/myoungsunk/sionna-resimulation/actions). 큰 NPZ는 Actions에 보존하고 실행 코드·요약 CSV·원본 학습모델의 base64 JSON은 git에 보존한다. 모델은 재학습 없이 SHA256 검증 후 복원할 수 있다. 큰 artifact의 부분 회수는 API immutable archive digest와 member CRC/SHA 검증을 구분해 기록했으며 전체 ZIP을 로컬 재해시했다고 주장하지 않는다.

## 검증된 실행 기준 엔진·센서·검증

- 검증된 실행 기준인 기억 구현1 원본: `3fc70f2280471954f1a0673009812ad75437d9ea`, engine.py SHA256 `d9e20a3082bb6069690f47211995295595e458556255af3bbfcc806458b94ea5`. 500회 선형 Gaussian 시험 NEES1.0886208364, coverage93.4%. 구현2/3 원본 미확보로 세 구현의 완전한 원인 diff는 DEFERRED_SOURCE_UNAVAILABLE이다.
- T2 실제 adapter engine SHA256 `81f275d8697d612418cc4b5759301161ad7973c92d70abc30af0c1891f44ca01`. 온라인 callback을 추가한 버전은 preregistration commit `e18dcd04bd9bb7fb0a0da5f9625116f322a680e5`, 현재 SHA256 `e725f92bd74e6a845b07418d6f3b7a2974a518b2cd03b16969518bf879ee11b8`. 기본 POWER1 수학은 유지하고 상태·공분산·gate parity를 확인했다.
- 신규 센서 검증된 실행 기준: T2 PROTOCOL_LOCK v3 SHA256 `b05e7ead6cf658d20a4830094cec56332ffcc839e7dccf04fd4ce3a1f86ccef0`. 원래 route generator의 .25s motion, Sensor-v2 잡음·초기오차, 실제 radio pose 시점에서만 update한다. RF CSV/pose CSV byte identity를 검사했다. seed0–4는 같은 RF의 motion noise·초기오차 반복이다.
- 기존 POWER1 B0와 KEY_B0 최대 차1.262e−13°, gate 불일치0. 기존 rho0 최대 상태 차3.997e−14·공분산7.772e−16; 신규36 trace 최대 상태 차3.249e−14·공분산5.135e−16·gate 불일치0. 독립 scorer는 해당 실행에서 ≤1e−9를 확인했다. 신규 주로는 T2를 첫 기준선으로 지정한다.
- 공통 재귀 표에는 Heading RMSE·signed mean·sigma RMS·heading95·Heading/Pose/conditional XY NEES·XY RMSE·bias RMSE/시간평균/최종값을 보존했다. 슬라이드 표는 전체 실행 표에서 필요한 열을 발췌한다.
- Range 행 Jacobian = 0으로 직접 Range 감도 제거, C_rs·gate 영향만 남음. Range 교정 근거로 사용 불가
SRC_TAP은 양자화된 정수 검출 tap으로 range를 예측하므로 tap 내부에서 range의 위치 Jacobian이 0이다. 이를 연속 EKF의 range 관측으로 사용하면 range의 직접 위치 관측 정보가 제거되고 range–s joint gain·gate·교차공분산 경로가 달라진다. 따라서 잔차 0과 안정 tap FD 0은 range 관측식 교정의 유효성 증거가 아니며, SRC_TAP 재귀 arm 및 그 파생 표·개입·변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN이다. B_OLD와 B_REFIT_ONLY에는 적용하지 않는다. T3/SRC_TAP, T4/SRC_TAP·POST30_SRC_TAP은 원래 수치·판정을 보존하되 교정·F1 검증 증거에서 제외한다.

## 이전 문서에서 바뀌거나 구분해야 하는 수치

| 항목 | 이전 값·출처 | 새 검증된 실행 기준 값 | 해석 |
|---|---|---|---|
| R2 A M0 B0 MEMORY | 구현2 2.857°, 구현3 3.023° (5d3ffc9/fcf0725) | 구현1 1.986223° | 원본2/3 없이 구현 차이 원인은 확정 불가 |
| C01 A/B B0 POWER1 | Chain F 4.269°/4.910° (3fc70f2) | 3.966129°/5.027763° | T2 검증된 실행 기준 센서·기존3route 전체 학습 |
| C02 A B0 POWER1 | Chain F1.995°, crosscase2.236° | 2.235796° | 행별 비교 T2 PREVIOUS_COMPARISON.csv |
| O02/O03 B0 POWER1 | Chain F O02 2.121°; crosscase2.220°/6.868° | 2.220134°/6.868341° | 공개된 이전 값과 차이를 보존 |
| LoS L2 J4 M0/M45 | 구 LUT .24°/.16° | SourceFFD .298943°/.180166° | 변경 전체6칸 T3 OLD_LUT_CHANGES.csv |
| LoS L2 J3 M0/M45 | 구 LUT17.94°/17.37° | SourceFFD18.264908°/17.453725° | B_OLD SourceFFD 기준 |
| R5 A M0 V1 skip | POST30 +7.751° (fcf0725) | POST30 +7.740819° | GLOBAL_T30 +3.020653°는 별도 범위이며 교체값 아님 |
| C01 A x16–21 V1 skip | POST30 +5.393° | POST30 +5.389283° | endpoint 완전 구현 parity는 미인증 |
| O03 y4–8 V2 skip | POST30 −15.347° | POST30 −15.264760° | 전체 비교 T4 EVENT_SCOPE_COMPARISON.csv |
| C03 A 초기 skip | 과거 이벤트 후 효과+.767° | GLOBAL_T5 +.232010°, T10 +.233160°, T30 +.070670° | 평가 시작 시각 변경은 별도 추정량 |
| R5 A B0 POWER1 range 변경 | B_OLD4.556146° | SRC_TAP17.904643° | SRC_TAP 및 변화량은 INVALID_DESIGN_ZERO_RANGE_JACOBIAN; 교정 증거에서 제외 |

T4 최초 lock의 주 판정은 GLOBAL_T30였으나 원문 skip 효과는 이벤트 종료 후30초였다. 원문 범위를 확인한 뒤 `52b121207b634f21fc6f86e60e75805fc5f3d18d`에 POST30 수정 lock을 먼저 커밋하고 이미 산출된 POST30 행을 재집계했다. 필터·RF·파라미터·이벤트·arm·임계값은 바꾸지 않았다. 최초 GLOBAL_T30 및 수정 POST30 판정 모두 NOT_ESTABLISHED이며 두 결과를 보존했다.

## BLOCKED_INPUT과 필요한 입력

1. T1 구현2 원본 POWERJOINT_A_F_CHAIN_CAUSAL_RESULTS_20261019.zip (지정 SHA256 6c3150b65078ff62dfcebf5aa8aa95741389a085100b3c8a1f1851a2c967cec3), 구현3 POWERJOINT_CROSSCASE_HEADING_CAUSES_20261020 실제 실행 코드. 문서 재구성은 원본 구현 시험을 대신하지 않는다. 현재 분류는 DEFERRED_SOURCE_UNAVAILABLE이며 검증된 구현1 실행 기준의 재현을 무효화하는 전역 차단 사유는 아니다.
2. T6의 과거 2,268점 미확보 BLOCKED_INPUT 주장은 철회했다. 모집단 대응은 후속 S0 감사의 별도 항목이며, 이 문서는 새 대응 인증이나 수치를 주장하지 않는다. SRC_TAP의 현재 제외 사유는 입력 누락이 아니라 0 range Jacobian 설계다.
3. T8 Tnone motion과 행 단위 시간·pose가 인증된 R4/R5 M45 RF. 현재 T10 first-visit은 재귀 대체 입력이 아니다. 이름·CRC·pose 집합 일치만으로 시간 대응을 인증하지 않았다.

T7B는 전체72셀·3arm·2평가시점432행을 완료했으며 오류0건, 기준선 최대Heading 차9.726e−14°·gate 불일치0이다. O01 L2 POWER1 .452926° 대비 POLICY9.363465°로 악화했고, 정책 채택을 하지 않는다.

기존 E1 hybrid ZIP은 확보되지 않았으나 허용된 재실행으로 T3를 완료했다. 감사 배경 Claude artifact는 접근되지 않아 유일한 근거로 사용하지 않았다. 오류·NO-GO·NONSPD 및 재시도 이유는 각 task ERRORS/receipt에 보존했다. 요청 수나 판정 임계값을 결과에 맞춰 바꾸지 않았다.

## 주장하지 않는 것

기존 R2/R4/R5와 C01–C03은 같은 복도 장면, O01–O03은 같은 오피스 장면이다. 조건 수를 독립 표본 수로 쓰지 않고 p-value를 제시하지 않는다. 독립 장면 일반화, 범용 기억 모델 승인, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. GT·Native LoS·미래가 필요한 개입과 utility label은 ORACLE_DIAGNOSTIC 또는 offline training으로 구분했다. 온라인 추론은 현재 Full RF와 해당 필터 prior만 사용한다. 새 단일 원인·새 gate·새 기억 모델 변형을 만들지 않았으며 T10 실험은 실행하지 않았다.

## 최종 산출물 검증

PUBLICATION_QA.json에 코드 구문·출력 SHA256·파일당20MB 한도·8개 재귀 표의 공통11지표 검사를 기록했다. T3 Slide4와 T1 검증된 실행 기준 Heading 차이는0이다. 계산 재실행이 아닌 산출물 무결성 검사다.
