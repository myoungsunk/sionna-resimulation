# DLP-P4-COV-001 — 3-Anchor EKF 신뢰도 과신의 경로 의존성 원인 분석 의뢰서

**2026-11-02 · role=PROPOSER · DRAFT (미동결, 분석 의뢰·실행 명령 아님)**

- 기준 GitHub branch: `research/dual-lp-p4-full-native-c0plus-20261102`, immutable HEAD `e365b2f79eb86a3fd53d0d350f8e2d9364f285fe`.
- 감사·출처: P1 run [41300302082](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41300302082), P4 Full run [41435839892](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41435839892), 12 full traces archive SHA256 `5ecf2a326ec17c8ce4ccc7a42fe76227ecf6ad7ec027df9cdfcd2304dcb0acfe`.
- 기존 `DLP-EKF-GAPS-001`의 P1–P4 증거는 불변. 별도 연구 질문 `DLP-P4-COV-001`로 제안·구현·독립 감사를 분리한다.
- **P0 자료·수학 점검 외 신규 과학 분석, 재귀 실험, R 튜닝, 새 RF 생성은 FROZEN 계약 및 독립 사전 감사 전 실행 금지.** 본문의 예비 숫자는 후향적·탐색적이며 독립 장면 확증이 아니다.

## 질문과 지표 정정

왜 동일 Corridor C0+의 R2/R4/R5 중 **R4 Full 3-anchor의 공분산 포함률이 0%**인가? R2에서는 C 추가가 위치 RMSE를 줄이지만 공분산 포함률을 낮추고, R5에서는 RMSE와 포함률을 모두 악화시킨 이유는 무엇인가?

기존 보고서의 `pose95`는 **위치 XY의 95%가 아니라 [x,y,psi] 3-DOF joint coverage**다. `XY95 = mean(NEES_xy<=chi2_2(.95)=5.991464547)`, `Pose3D95 = mean(NEES_pose<=chi2_3(.95)=7.814727903)`, `Heading95`도 분리해 보고한다. `P_xy` marginal과 `P_x,y,psi` joint를 혼동하지 말 것.

### 기존 trace를 연결한 탐색적 baseline (Full B0, t>=30s)

| Route | AB XY RMSE m | ABC XY RMSE m | AB XY95 | ABC XY95 | ABC Pose3D95 |
|---|---:|---:|---:|---:|---:|
| R2 | 0.186 | 0.122 | 30.52% | 13.75% | 15.08% |
| R4 | 0.386 | 0.179 | 11.32% | **0.00%** | **0.00%** |
| R5 | 0.106 | 0.203 | 50.36% | 7.91% | 9.17% |

같은 R4에서 NativeLoS ABC XY95=**62.5%**, Full ABC XY95=**0%**. C Full 거리잔차의 GT 기준 평균 **+0.0810m**, std **0.1899m**, lag1 **0.784**인 반면, 필터 `Rr=0.0068578637m²`의 가정 std는 **0.0828m**. R4 ABC의 사후 XY 1σ 타원 단/장축 중앙값은 **0.0067m/0.0391m**, GT 대비 평균 오차 y≈−0.1312m. R4 Full B0 ABC batch gate는 **66/742 rejected**이며, **같은 ABC prior에서 AB만 2df gate 검사 시 그 66개 중 44개가 통과**한다.

이 수치들은 원인 후보를 보여주지만 아직 인과 효과나 외부 일반화를 증명하지 않는다.

## 기존 입력 고정

- P1 `contracts/DLP-EKF-GAPS-001/P1_20261101/P1_INPUT_LOCK.json`, `runs/P1_SOURCE_HARMONIZATION_41300302082/P1_MATCHED_SIGNED_ERRORS.csv`.
- P4 `runs/P4_FULL_C0PLUS_NATIVE_41435839892/P4_FULL_12_COMPLETE_4STATE_EKF_TRACES.zip`, 원본 R2/R4/R5 Native C H/tau ZIP 분할과 전체 pose SHA 인덱스, case/pooled/contrast CSV, P4 QA.
- 계산 코드 `p4_full_runtime/p4_full_ekf.py`, 원본 `research/EKF4_RANGE_S_STAGED_20261014/core.py` 및 P4 lock.
- A=(4,0,2.65)m, B=(10,0,2.65)m, C=(16,0.8,2.65)m, Tag z=0.45m; z_r의 예측은 `||p-anchor||-0.5315983906250129m`. RR=0.0068578637m²; chi² gate(df 1/2/3,99%) 6.6348966/9.2103404/11.3448667.
- R2/R4/R5 전체 원시 epoch **979/742/1415**, t>=30s **829/592/1265**. B0와 L2(gyro true bias +0.20°/s), seed=0, Full/NativeLoS. 하나의 RF 장면으로서 route/time/sample은 독립 장면이 아니다.
- `pose_id,t_s,anchor_id,channel,mount,bank SHA,257 frequency bins,FP tap,raw z,source h` 100% 매칭, 원본 H/result SHA 직접 재검증.

## 원인 분리 가설(성능 개선이 목표가 아니라 설명 가능성 검정)

| ID | 잠재 원인 | 핵심 검증 |
|---|---|---|
| H1 C 다중경로의 방향·위치 의존적 signed 거리편향 | A/B Full 불변, **C만 Full ↔ NativeLoS**를 바꾸는 동일 pose/time 경로내 차이. GT 잔차, FP tap, 직접/반사 path ratio와 상관 대조 |
| H2 고정분산 및 관측 시간상관 | A/B/C별 `e_r=z_r-h_r(x_GT)`의 평균·분산/원 R 비·ACF·correlation time; accepted/rejected 분리. 반복 갱신 후 P 축소 시간곡선 |
| H3 비공선 C 기하가 과도한 확신을 생성 | 같은 prior에서 H, S, K, 정보방향, Pxy 고유값/타원 회전, `K_C*nu_C` 방향; route별 앵커 상대거리/방위·yaw·회전구간 대응 |
| H4 공동 gate가 A/B 정보까지 소실 | **ABC의 같은 prior**에서 NIS_AB(df2) vs NIS_ABC(df3); batch 3df와 AB(df2)→C(df1) 독립 gate 비교(동일 prior에서 no-gate sequential affine parity 먼저) |
| H5 Q/gyro·동역학 모델 불일치 | DR4와 NativeLoS 동일 route 비교 후, Q만 바꾸는 민감도 시험(관측 R을 동시에 변경하지 않음) |
| H6 first-path/전파 경로 변화 | full/LoS 동일 pose 원본 H, 직접 지연·FP tap switching·전력·편파 포트, 오류의 시공간 지속 구조 연결 |

### 단계별 의뢰 / GO-NO-GO

**D0: 원본·계산 parity (P0, 재실행 없이 허용).** 정확한 SHA, route pose/time, x/P/state/innovation/NIS, 84 case/28 pooled/48 contrast, 257-bin raw detector를 기존 receipt 및 별도 수식으로 비교. `max |dx|,|dP| <=1e-9`, NIS<=1e-8, row·packet 개수 100% 일치. 원본 불일치 시 즉시 STOP.

**D1: 과신 해부 (FROZEN + 독립 사전 감사 이후).** 3×2 route/mode×2 bias×7 arm **전수**에 대해 XY/Heading/Pose3D coverage 및 NEES, RMSE, signed bias, Pxy eigen/Schur, 10/20/40s 시간창을 생성. 3D pose NEES를 XY 항 + 조건부 heading Schur 항으로 정확하게 분해. R4 0%가 처음 시작하는 시간·위치·yaw, x/y 횡방향 편향과 Pxy 과축소를 지도/시계열로 연결.

**D2: RF 잔차 원인 (FROZEN + 독립 사전 감사 이후).** raw H→CIR→first-path→range/signed s, Full−LoS at identical keys. A/B/C별 e_GT, innov_prior, firsttap, path count/τ, mean/std/R ratio, p95 outlier, ρ₁·ACF·correlation time, anchor crosscov. 서로 다른 route의 총평균만으로 route causality 주장 금지.

**D3: 동일 prior 일회 분기 (FROZEN + 독립 사전 감사 이후).** `(x^-,P^-)`와 물리 z_A,z_B,z_C를 유지해 AB, ABC, C-only 1-step을 각각 독립 계산. `ν,S,K,NIS,gate,∆x,∆P` 비교. batch vs affine sequential은 **동일 선형화**·gate off에서 수치 parity 확보 후 gate만 바꾼다. R4 전수 뒤 R2/R5·Full/LoS·B0/L2 전수. 일회 결과로 full recursion 주장 불가.

**D4: 단일요인 재귀 인과 실험 (FROZEN + 독립 사전 감사 이후).** 매 실험 동일 x0/P0, wheel/gyro/time, 기존 물리 RF 및 SourceFFD, f/F/Q를 사용하고 각 arm 자체 prior를 이어간다.

| 비교 | 유일 변경 변수 | 해석 |
|---|---|---|
| AB Full vs ABC Full | C 관측 추가 | 기존 총효과(정보+오차+gate) |
| A/B Full + C Full vs A/B Full + C NativeLoS | **C의 다중경로만** | C 오염의 영향 |
| ABC batch 3df vs AB(df2) 후 C(df1) gate | **gate 정책만** | 유효 A/B update 손실 |
| ABC Full vs C의 `R_C`만 사전 지정 배율 {1,4,9,16} | **C 관측분산만** | 공분산 고정 과신의 영향 |
| ABC Full vs 동일 평균·주변분포의 합성 잔차 서열 교란 | **시간상관만 (ORACLE/SYNTHETIC)** | 재귀 누적 상관. 물리·배포 모델 아님 |

- 사후 GT 이용한 mean correction/variance fitting은 반드시 `ORACLE_ONLY`; train/test 누출 없는 운용 추정기라고 주장 금지. 이미 결과를 확인한 C0+의 route-heldout 분리는 탐색적 within-scene test이지 새로운 독립 장면의 일반화 시험이 아니다.
- 새 RF/장면/속도 실험은 이 의뢰의 승인 범위 밖. 공간 vs 시간 상관이 현재 원본에서 비식별이면 `NOT_IDENTIFIABLE`로 기록하고 별도 신규 실험/예산·감사 제안.
- 성공 기준은 전 경로 성능 향상이 아니라 어느 후보가 오류/공분산 과신을 설명하고 어떤 반례에서 실패하는지 검증하는 것.

## 제출물

1. `INPUT_SHA_LEDGER.json`, `RUN_MANIFEST.json`, `STAGE_GATE_RECEIPTS.json`: full SHA/버전/코드/시간/명령/scene_n=1.
2. `ROUTE_STATE_COVERAGE.csv`: XY·Pose3D·heading NEES, bias, Pxy axis, Schur, time windows.
3. `RF_RESIDUAL_BY_ANCHOR.csv`, `RF_ACF_CROSSCOV.csv`, `RF_TAP_PATH_GEOMETRY.csv`: 물리 관측오차 분해.
4. `SAME_PRIOR_AB_VS_ABC_GATE.csv`, `ONE_STEP_DELTA_X_P.csv`, `RECURSIVE_SINGLE_FACTOR_ARMS.csv`: 동일 prior/단일변수 대비.
5. `FAILURE_COUNTEREXAMPLE_LEDGER.csv`: R2/R4/R5 모든 Full/LoS/B0/L2, 실패·음성제어 포함.
6. `ROOT_CAUSE_REPORT_KO.md`: 관측편향→innovation/gate/K→posterior 오차/P 과신으로 연결한 수식과 그림 2–3개 및 논문용 최소 주장/제한.
7. `INDEPENDENT_AUDITOR_VERDICT.json`: 다른 실행·수학 경로의 감사 주체가 작성, 구현자가 대신 서명하지 않음.

**원본 불변:** P1–P4 기 연구 데이터, C0/C0+ RF, 연구 결과, source codes, `main`, MBVAR/POL-XCORR를 덮어쓰지 말 것. 새 실험은 별도 브랜치·append-only; 음성 시험(스왑, time shift, pose 중복, port 부호 전도, R PSD 위반) 통과가 필수.

**현재 허가:** D0/P0 source/math/geometry preflight. **D1–D4 새로운 과학 분석·EKF 개입은 FROZEN+독립 사전 감사 후 단계별 승인. 신규 RT 실행 미승인.**
