# FP-SC-RECOVERY-001 — B+P 7.5 cm 탐지 고정 후 FP 선택복구 제안서

> **PROPOSER DRAFT / NOT FROZEN / SCIENCE_NOT_RUN / NOT IMPLEMENTED**  
> 사용자가 선택한 정책에서 다음 분석을 설계한다. 현재 기존 selector·B·P·M·EKF 코드를 변경하지 않으며 실제 복구 결과를 주장하지 않는다.

## 1. 기준선 불변

기준 소스 commit: [e9a74d144dfb37ab28799a9d5a702677044c7836](https://github.com/myoungsunk/sionna-resimulation/commit/e9a74d144dfb37ab28799a9d5a702677044c7836). 구현 \`research/FP_SC_B_PONLY_075_20261106/apply_p_only.py\`; 최초 pinned RF/선행결과는 \`cecb38cbaa507ea08f597ae441dbd929c3b8a24e\`.

- **B** = 두 RX별 자기 peak 진폭 30% 최초 유효 crossing 중 앞선 탭. anchor 명칭이 아님.
- **P-only** = 측정 **전** 기존 prior interval의 중점 \`muP=(low+high)/2\`에 대해 \`abs(B*STEP-muP)>0.075+1e-12 m\`일 때 경보. \`STEP=c/(1028*1950000)≈0.14955m/tap\`.
- **M 비활성화**, 과거 B/FP 기반 history 조회 없음, 0번 시점도 평가. P센터·반경·검출기·원본 데이터·S 계산식을 변경하지 않는다.
- 현재 **FLAG-ONLY**. FP 실제 교체, 후단 EKF 갱신 및 생산 배포 없음.
- 원래 자료는 이미 7.5cm 반경 탐색에 사용됨. 현 성능은 **in-sample**이며 모델 prior도 독립적으로 검증된 integrity source로 취급하지 않는다.

| B 오류/정상 분할 | 오류 | 정상 | 합계 |
|---|---:|---:|---:|
| 경보 | TP 678 | FP 11 | 689 |
| 비경보 | FN 321 | TN 2126 | 2447 |
| 합계 | 999 | 2137 | 3136 |

전체 B S MAE/RMSE=0.0473033/0.0798753, 비경보 2447개에서 0.0432963/0.0745778은 **선별된 집단의 S 오차**. 전체 S 정정효과가 아니다. 321 미탐지는 이 gate를 동결하는 동안 복구 대상이 아님. 모든 탐지 오류를 정확히 고치고 정상 11개를 지킨다고 가정해도 exact tap accuracy의 게이트상 상한은 (2137+678)/3136=**89.76%**. 실험/후보상한과 구별.

## 2. 순서 고정

**R0 (최우선: 원본 감사/기준 재현).** GitHub 원본 소스·입력 SHA 고정, 3136 유일 (case,k) 회계, TP678 FP11 FN321 TN2126 S와 경보 판정식 재현. 저장된 P interval이 진짜 측정 전 생성됐는지 코드로 provenance 검증. GT/reference/current-sample 기반 P이면 **즉시 HOLD**. no M, no history 및 첫 시점 보장. 불일치면 후속 단계 실행 금지.

**R1 (최우선 과학 실험: 탐지된 678건에서 참조 FP 후보 존재 여부).** 두 RX의 현재 CIR만으로 기존 VAB 지원 후보 및 각 포트 30% crossing·유효 lobe edge·지원되는 이웃 후보를 생성. 비교는 (a) frozen VAB pool, (b) 별도 shadow 확장 pool로 분리. 정상 오경보 11개와 미탐 321개도 대조. \`reference∈candidate\`, \`reference∈supported\`, \`reference∈P±7.5cm\`, 후보 순위, RX support, 후보 거리/편파비, early/late 1/2tap, 경로/episode를 모두 표기. **참조를 사용한 oracle은 평가 함수 안에서만** 실행하고 온라인 selector에 노출하지 않는다. 참조 후보 부족이면 selector 조정 앞서 후보 생성 누락의 원인부터 조사.

**R2 (R1 이후: 정답 없는 shadow 선택기).** P gate 불변, \`alarm=true\`의 689개만 선택기 평가. 공통 후보 집합의 A0 KEEP_B, A1 P_NEAREST, A2 P+RX_ONSET, A3 P+RF_SUPPORT, A4 P+RF_SUPPORT+ABSTAIN, O* GT_ORACLE (평가 전용) 비교. 정답/LoS S/true pose/route/seed/future/posterior는 어떤 온라인 feature·score 함수에도 입력 금지. 유효 후보가 없거나 P와 충돌하면 강제 교체 없이 \`KEEP_FLAGGED\` 또는 \`ABSTAIN\` 기록; flag를 안전 승인으로 바꾸지 않는다. 각 arm 점수식·동률·선택 조건은 **결과 보기 전** freeze. 기존 점수식에 몰래 덮어쓰기 금지.

**R3 (R2 이후: range/S 공동 검증).** 동일 tap에서 range와 \`S=(|CIR_RX0|²-|CIR_RX1|²)/(양 포트 전력합)\`를 계산한다. B/참조/선택 tap과 S를 동일 행에서 비교. TP 중 exact/corrected-closer/worse/hold, FP11 중 정상보존·훼손·hold, FN321 및 TN2126 **변경 없음**을 확인. 전체 3136 range MAE/RMSE/p95와 S MAE/RMSE, flagged689/unflagged2447/per-route/per-sign/per-1-or-2tap, coverage·보류·위험 episode 평가. **남은 표본의 S만 줄어든 것을 전체 개선이라 주장하지 않는다.**

**R4 (선별 성공 이후: P 민감도).** 고정 7.5cm 정책을 채택상태로 두고, 오직 사후 원인 분석에서 P center에 ±2,±4,±7.5,±15 cm 편차를 부여한 견고성 검사. 문턱 재조정/선택 최적화용 sweep 아님. 원래 예측 중심이 실제 서비스의 DR 오차·지도/방향 편차에 민감한지 확인.

**R5 (후속 별도 GO: EKF paired replay).** R0–R4 통과 및 독립 확인 후에만 동일 초기 상태/seed/관측으로 기존 B, 경보시 보류·R_eff 보수화, 검증된 선택적 교체 arm의 XY/heading RMSE, NIS/NEES, 명목95% coverage, 공분산 과신·악화 사건 비교. FP와 S 관측 변경 여부 분리. 기존 S2/S3 복구 실험과 혼합 금지.

**R6 (새로운 blind RT/RF 증거).** 기존 R2/R4/R5는 이미 노출되어 route-heldout 재분할만으로 독립 검증이라고 주장 불가. 새로운 미노출 seed/경로/기하/편파 민감도/차폐 조건을 고정된 규칙으로 평가; 별도 승인 전 새 RT 실행 안 함.

## 3. 제안 단계게이트 및 보존 규칙

- G0 **반드시 PASS**: 3136/TP678/FP11/FN321/TN2126·원본 SHA·측정 전 P provenance.
- G1 후보집합 존재와 P포괄 여부, oracle 상한. 후보가 없는 케이스를 RF selector 실패로 오판 금지.
- G2 11 정상 경보 전수 검증. 탐색적 최소 기준: **0/11 잘못된 자동 교체**, flagged TP678 중 **≥204건(30%) 정확 복구 제안**. 이는 제안 문턱이며 사전 승인·동결 전 최종 기준이 아님. 0/11은 안전성 증명이 아니며 새로운 자료에서 다시 확인해야 함.
- G3 전체 range·S 비열화, 모든 경로 분리, coverage/hold 포함. 새로운 candidate가 항상 더 정확하거나 S가 더 좋다는 가정 금지.
- G4 원본·신규 SHA, 행별 trace, 실패 목록, 독립 재검산 영수증 보관. 독립감사와 구현자 self-check 혼동 금지.

**필수 산출물:** \`CONTRACT_LOCK.json\`, \`BASELINE_PARITY.json\`, \`CANDIDATE_COVERAGE.csv\`, \`FLAGGED_689.csv\`, \`NORMAL_FALSE_ALARMS_11.csv\`, \`MISSED_321.csv\`, \`ORACLE_BOUND.csv\`, \`SHADOW_SELECTOR_ARMS.csv\`, \`S_RANGE_PAIRWISE.csv\`, \`PER_ROUTE_EPISODES.csv\`, \`INPUT_SHA256.json\`, \`RUN_RECEIPT.json\`, \`NEGATIVE_TESTS.json\`, \`LIMITATIONS_AND_FAILURES.md\`.

## 4. 구현자 실행 지시

**우선 R0→R1까지만 별도 shadow 분석으로 실시한다.** R1에서 왜 참조 후보를 놓치는지와 후보가 있는데도 잘못 고르는지를 분해한 후 R2와 R3를 허가한다. 처음부터 FP 선택기와 EKF를 동시에 변경하지 않는다. 기존 branch의 실패 기록·selector·P/M 계산·입력은 보존하고 새 폴더에서 실험한다. 운영 FP write와 EKF는 현재 단계에서 0건. **현재 문서는 결과나 승인서가 아닌 제안자 설계이다.**
