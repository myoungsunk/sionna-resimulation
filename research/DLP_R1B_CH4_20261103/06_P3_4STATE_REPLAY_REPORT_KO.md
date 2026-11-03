# DLP-R1B-CH4-001 — P3 4상태 재귀 비교 상태 보고서

**작성일:** 2026-11-03 KST  
**실제 R1·Anchor B SourceFFD EKF:** `NOT_RUN`  
**실제 Heading·XY RMSE:** `null` — 계산되지 않음  
**중단 원인:** 선행 Native canary의 `HOLD_RF_PARITY`

## 1. 현재 결과의 범위

R1·Anchor B의 B0 및 L2에 대한 Native LoS/Full 4상태 EKF 재귀 비교는 실행하지 않았다. P0에서 생성된 8개 canary의 복소 채널 상대오차 RMS가 `1.0051515145524099e-4`로 동결 기준 `1e-4`를 초과했고, 독립 원시 배열 감사도 같은 HOLD 판정을 재현했다. 따라서 전체 917개 Native 관측쌍을 생성·조립하는 선행 단계가 열리지 않았다. [실제 canary QA](runs/P0_CANARY_V2/03_RF_CANARY_QA.json), [최종 독립 원시 감사](audits/P0_CANARY_RAW_AUDIT_FINAL.json), [P1 실행 상태](04_P1_RF_GENERATION_REPORT_KO.md)

| bias | 관측 채널 | 실제 재귀 실행 | Heading RMSE (°) | XY RMSE (cm) |
|---|---|---|---|---|
| B0 | Native LoS | `NOT_RUN` | `null` | `null` |
| B0 | Native Full | `NOT_RUN` | `null` | `null` |
| L2 | Native LoS | `NOT_RUN` | `null` | `null` |
| L2 | Native Full | `NOT_RUN` | `null` | `null` |

위의 `null`은 계산되지 않은 값을 뜻한다. 0도·0 cm 오차를 뜻하지 않는다. Full−LoS 성능 차이, 증감률, 실제 패킷 수용률, 갱신 이득과 상태오차 분해도 아직 산출되지 않았다. 따라서 R1의 Full 환경에서 Heading 또는 XY 오차가 개선되거나 악화되었다는 결론은 현재 근거로 작성할 수 없다.

## 2. 동결된 재귀 비교 계약

다음 설정은 준비된 V2 계약의 정의이며, 실제 R1 실행 결과가 아니다. [V2 계약의 replay 및 단계 조건](00_REQUEST_CONTRACT_FROZEN_V2.json), [독립 사전 source review](audits/P3_PRE_RUN_AUDIT.json)

| 항목 | 동결 설정 |
|---|---|
| 상태 | `[x,y,ψ,b_g]ᵀ`, 4상태 |
| 관측 | `[r,s]ᵀ`; 각 Native 채널에서 독립적으로 검출한 공통 RX tap |
| 관측모델 | 원본 SourceFFD; `h_r = d_3D − 0.5315983906250129 m` |
| 평균·추가분산 | `μ=[0,0]ᵀ`, 추가분산 0 |
| 고정 R0 | `diag(0.0068578637 m², 0.0081)` |
| NIS gate | `χ²₂(0.99)=9.210340371976184`; 각 arm의 자체 prior·자체 gate |
| 상태 전이 | 원본 `core.predict`, gyro bias를 포함하는 SE(2) 전이 |
| 입력 Q | `diag(2e-5·|ds_odom|, rad(0.015)²·dt, 0)` |
| 초기 P0 | `diag(0.1²,0.1²,rad(5)²,rad(0.1)²)` |
| 입력 생성 | 원본 SensorV2 및 `build_positive_bias_controls`, seed 0, legacy-euler convention |
| bias 범위 | B0 필수; L2 `+0.2°/s` gyro-bias 보조 조건. 다른 결정적 drift는 원본 비교 설정대로 억제 |
| 공통 조건 | LoS/Full에 같은 controls, seed, 초기 상태·P0, f/F/Q, h/H, R0 적용 |
| 공분산 및 각도 | 원본 Joseph 갱신, yaw wrap |
| 평가 | t0부터 각 arm 자체 posterior로 재귀; 주 점수는 `t≥30 s`의 모든 767개 시점. 거절 시점도 포함 |

평가 시점 767개는 원본 궤적에서 정해진 **예정 평가 집합**이다. 현재 767개 posterior가 생성되거나 점수화된 것은 아니다. 참 궤적은 synthetic sensor 입력 생성과 오프라인 진단에만 사용하도록 분리되어 있다.

거리 예측의 고정 offset은 기존 continuous detector bridge이다. `μ=0`은 이 관측모델에 추가 경험적 평균 보정을 적용하지 않는다는 뜻이다. 단일 canary 또는 RF 생성 단계로 거리 검출 오차의 확률분포나 R0의 통계적 적합성을 검증했다고 주장하지 않는다.

## 3. 준비된 replay 코드와 로그 정의

[r1b_replay.py](runtime/r1b_replay.py)의 SHA-256은 `e157573d863847a12da02a392edd6f0a9fdba0a5c4318b4e23b14503edfffd77`이다. 이 adapter는 원본 SourceFFD, `core.predict`, `core.gaussian_update`, 원본 controls 생성기를 호출한다. frozen 계약, canary PASS, 전체 RF manifest PASS, 917개 paired pose, 동일 port schema 및 해시를 선행 조건으로 검사하도록 구현되어 있다. 현재 이 준비 상태를 실제 R1 재귀 실행 완료로 분류하지 않는다. [source review](audits/P3_PRE_RUN_AUDIT.json)

향후 선행 조건을 충족했을 때 저장하도록 구현한 진단은 다음과 같다.

\[
e=z-h(x^{GT}),\quad
\delta h=h(x^{GT})-h(\hat x^-),\quad
\nu=e+\delta h.
\]

\[
\Delta x_{\mathrm{potential}}=K\nu=Ke+K\delta h,\qquad
\Delta x_{\mathrm{applied}}=\mathbb{1}_{\mathrm{accepted}}K\nu.
\]

거절된 관측에도 계산 가능한 pre-gate 이득과 잠재 갱신을 보존하고, 실제 적용 갱신은 0으로 구분한다. yaw의 실제 상태 차이는 wrap을 적용해 검산한다. 패킷 로그는 prior/posterior `x/P`, `h/H`, `z`, 혁신, `S/K/NIS`, accepted, `Ke`, `Kδh`, 거리·편파별 signed heading 기여를 기록하도록 준비했다. **현재 실제 R1 패킷 로그는 생성되지 않았다.**

전체 시점의 관측오차 `e0=FULL−h(GT)`, `Δz=FULL−LOS`, `eLoS=LOS−h(GT)` 및 phase·거리·방위각·`|H_sψ|`별 표도 준비 코드에 포함된다. 이 표들의 실제 917-pose 데이터 역시 아직 계산하지 않았다. `|H_sψ|` bin 자체를 smooth-cell finite-difference 검증의 통과로 해석하지 않도록 명시했다.

## 4. 실제 수행한 계산 QA와 적용 범위

별도 계산 검토자가 수행한 검사는 **인공 입력에 대한 수학·로그 검사**다. R1 궤적과 실제 Native RF를 넣은 재귀 성능시험은 수행하지 않았다. [수학 QA](audits/P3_PRE_RUN_MATH_QA.json), [거절 로그 음성 시험](audits/P3_REJECTED_LOG_QA_e157573d8638.json)

| 근거 | 실제 수행 내용 | 판정과 한계 |
|---|---|---|
| `P3_PRE_RUN_MATH_QA.json` | 인공 motion F 수치미분, 인공 affine accepted/rejected state·Joseph·NIS, 인공 채널 observer parity | 11/11 PASS. R1·SourceFFD Native parity 또는 실제 재귀 점수의 시험이 아님 |
| `P3_REJECTED_LOG_QA_e157573d8638.json` | 인공 단일 REJECT 행의 정상 로그와 S·K를 각각 훼손한 로그 | 3/3 PASS. 정상 로그 통과, 훼손 S/K 각각 예상한 수학 parity HOLD 발생 |
| `P3_PRE_RUN_AUDIT.json` | V2 source와 계약·로그·평가 mask의 독립 검토 | `ACCEPT_PRE_RUN_SOURCE_WITH_BOUNDARIES`; `scientific_release=false` |

수학 QA의 초기 adapter checkpoint는 `ff605b961ff3648603e1ac08537bef51113a9a83fcf65c088f32f80f6a2649e4`이며, V2까지의 source 변경은 별도로 검토했다. V2 거절 로그 시험은 현재 adapter 해시 `e157…fd77`에 직접 연결되어 있다. 수학 QA의 motion F 최대 절대차 `1.1677342426352766e-10`, Joseph 최대 절대차 `2.168404344971009e-19`, NIS 최대 절대차 `2.2737367544323206e-13`는 해당 **인공 시험 입력의 수치**다. R1의 상태오차·RMSE와 섞어 보고하지 않는다. [source review의 numerical evidence](audits/P3_PRE_RUN_AUDIT.json)

검토자는 별도 위임 agent와 별도 계산 provenance를 사용했으며 같은 workspace를 공유했다. 외부 인간 심사나 별도 물리 장비의 독립 재현을 주장하지 않는다. 실제 HOLD canary를 넣어 생산/replay 진입 차단을 실행 시험했다는 주장도 하지 않는다.

## 5. 전체 RF 입력을 준비하는 코드의 별도 제한

준비된 [생산·조립 실행기](runtime/r1b_acquire.py)는 `PREPARED_ONLY_UNEXECUTED`이며, 이를 실행하도록 승인한 생산 계획·감사는 없다. 코드 SHA-256은 `0377a0df44636469d8ce1d1c28fba6e232f33b4b5300240bd9284cf17780ff35`이다. [준비 source review](audits/P1_PRODUCTION_DRIVER_PREPARED_REVIEW.json)

현재 조립 코드의 anchor 비교에는 `np.array_equal`이 들어 있다. 실제 canary 원시 anchor와 상수 `(10,0,2.65)`의 차이는 최대 `4.440892098500626e-16 m`로, 동결 Native 초기화의 허용오차 `1e-12 m` 안에 있다. 준비 코드의 완전일치 검사는 이 표현 차이도 거절할 수 있으므로 **향후 RF 조립·P3를 진행하기 전에 별도 수정과 재검토가 필요하다.** 현재 HOLD에서는 코드와 계약을 변경하지 않았다. 이 미실행 조립 코드의 제한은 실행된 canary의 복소 RMS 실패 원인이 아니다. [원시 감사의 좌표 검산 및 erratum](audits/P0_CANARY_RAW_AUDIT_FINAL.json)

## 6. 다음 단계의 조건과 원고 사용 범위

P3를 시작하려면 기존 실패·동결 문서를 보존한 상태에서 RF 정합 HOLD를 다루는 별도 검토 절차가 먼저 필요하다. 이후 생산 코드의 알려진 제한 수정·검토, 실제 비용·분할 계획과 독립 감사, 전체 917개 Native LoS/Full paired 입력 검증이 충족되어야 한다. 실제 재귀 실행 후에는 별도 검토자가 원시 관측·패킷 항등식·이득·공분산·점수를 다시 계산해야 한다. [V2 단계 조건](00_REQUEST_CONTRACT_FROZEN_V2.json), [사전 검토의 remaining stage conditions](audits/P3_PRE_RUN_AUDIT.json)

현재 제IV장에 인용 가능한 것은 요청 범위, 원본 R1 입력, 동결된 비교 정의, 사전 구현·인공 수학 검토의 범위, 그리고 Native canary HOLD라는 사실이다. R1 LoS–Full Heading·XY 비교표나 관측오차에서 실제 위치·heading 성능으로 이어지는 실증 결과는 아직 제공할 수 없다.

## 7. 핵심 근거 해시

| 근거 | SHA-256 |
|---|---|
| [V2 계약](00_REQUEST_CONTRACT_FROZEN_V2.json) | `a31a537dd35823d10c1d74ee0cf488d439b7ba2c70114309e024b451a9468596` |
| [실제 canary QA](runs/P0_CANARY_V2/03_RF_CANARY_QA.json) | `ac5959437500c480e0b3d93cd6a4c4988d537f76b331eecb1de0a5764062f5d0` |
| [replay 코드](runtime/r1b_replay.py) | `e157573d863847a12da02a392edd6f0a9fdba0a5c4318b4e23b14503edfffd77` |
| [P3 사전 source review](audits/P3_PRE_RUN_AUDIT.json) | `78e4679628a32c221d7063f2395bd5d03be2df554cd9d43c7590562b108d7236` |
| [인공 수학 QA](audits/P3_PRE_RUN_MATH_QA.json) | `c35193e19a5add74743f9695877f24b89bee056af99b8876bbd66706532f5d51` |
| [V2 거절 로그 시험](audits/P3_REJECTED_LOG_QA_e157573d8638.json) | `ec591eb19437ebf15b0ba0f442eca73f083fe5f49c43782c656cac3da3188eaa` |

**최종 상태:** `P3_NOT_RUN / ACTUAL_R1_RMSE_UNAVAILABLE / SCIENTIFIC_HOLD`.
