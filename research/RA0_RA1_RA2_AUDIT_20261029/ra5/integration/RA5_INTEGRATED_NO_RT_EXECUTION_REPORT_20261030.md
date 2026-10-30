# RA5 통합 비-RT 실제 실행 보고 — 2026-10-30

**판정:** `TECHNICAL_NO_RT_METHOD_PASS / SOURCE_PHYSICS_CONDITIONAL / FULL_FILTER_BLOCKED / NEW_PHYSICAL_SCENE_NOT_TESTED`.
원본 R2/R4/R5 및 MBVAR-INFO·POL-XCORR 소스·동결 계약 수정 없음. 본 통합은 구현자 자체 QA이며 독립 감사 및 신규 RT 없음.

## 1. 재현 원장

| 실행 | GitHub Actions | 검증 |
|---|---|---|
| 원본 Full H + 복소 수신 잡음; SourceFFD 3x4 추가 tap Jacobian; 공간/시간 known generator | [40986273213](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40986273213) | SUCCESS, 저장 SHA self-reference 결함 수정 뒤 재실행 |
| 같은 FFD scene에서 Js0/Js1와 잡음 covariance의 조건부 정보량 | [40985784668](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40985784668) | SUCCESS. 최초 40985619574 Python 변수명 오류로 실패, 기록 보존 |
| 새로운 SourceFFD 기하·합성 지연 echo | [40986462306](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40986462306) | SUCCESS, 실제 RT 없음 |
| 세 source-run 원장 검증 및 조건별 통계 집계 | [40986709714](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40986709714) | SUCCESS, 과학 주장 한계 별도 기록 |

머지 완료된 결과의 증거 파일은 위 Action artifact를 다운로드하거나 각 실행 RUN_LOG, QA.json, CSV, 원본/source hash로 확인한다. 40986709714는 별도의 source hash를 확인한 재집계이며 독립 물리 실험이 아니다.

## 2. 추가 tap 관측모델 — 실제 계산

| 항목 | 실행 결과 |
|---|---|
| 기존 MBVAR SourceFFD LoS fixed-tap h/J 확장 | 6/6 선정 pose에서 3x4 Jacobian 파생 |
| SourceFFD 원 첫 tap 관측 parity | 0 difference |
| 독립 finite difference 대비 최대 Jacobian 절대차 | 3.537808102e-9 |
| Original Full H source noise 조건 | 2 original cases ×2 pose ×3 SNR ×2 jitter ×2 RX noise corr = 48 |
| Monte Carlo 원시 CFR 복소 noise | 512/cell, 총 24,576 |
| 원 [r,s0,s1] full R 특이 조건 | 8/48 |
| 잡음 아래 first-path tap 변경 조건 | 40/48 |
| [r,s0,s1] → [r,s0,s1-s0] covariance | 전 조건 정식 T R Tᵀ 동등성 PASS |

특이행렬은 오류로 지우지 않고 명시했다. 이산 first-edge 거리 측정에서는 r의 표본 분산이 0일 수 있으나, SourceFFD 예측거리 h_r는 연속 거리+bias이다. **이 둘을 하나의 full-rank Gaussian raw 3x3 observation likelihood로 결합하지 않는다.**

### Source-matched conditional information

별도 소스-동일 시험에서 6 pose × 3 per-bin SNR × 2 jitter = 36조건, 768 raw complex-noise realizations/cell = 27,648. 같은 SourceFFD LoS spectrum으로 h_s0/h_s1의 Jacobian과 empirical covariance를 계산했다.

- [s0,s1] **2×2** R sub-block은 36/36 가역. 완전한 3×3 r/s0/s1가 가역이라는 의미가 아니다.
- [s0,s1] ↔ [s0,s1−s0] 정보행렬의 최대 상대 계산 차이 4.74e−14 이하.
- 동일 packet의 |corr(s0,s1)| 중앙값은 SNR=-5/5/20dB 및 jitter=0ps에서 각각 **0.9618 / 0.9723 / 0.9740**. 150ps jitter에서는 각각 0.9633 / 0.9840 / 0.9983.
- 조건부 추가 Heading 데이터 Fisher는 모든 36개 가역 subset에서 양수로 계산됨. 0ps 기준 중앙값은 -5dB 19.08, +5dB 330.35, +20dB 10707.65 rad^-2이다. 이는 **주어진 LoS/잡음/pose nuisance 고정의 국소 데이터 정보량**으로, state marginalisation, 실제 측정 잡음, multipath calibration, EKF heading RMSE 개선은 전혀 포함하지 않는다. 큰 SNR 조건에서 정보량이 급증하는 것은 합성 Gaussian 잡음의 축소가 반영된 결과이며 물리 시스템 성능 약속이 아니다.

## 3. 공간 field와 시간 오차

기존 info_core.k_pose, k_time, obs_covariance를 pinned MBVAR-INFO commit에서 변경 없이 호출했다. REV60과 FWD60의 600 독립 field realizations/scenario, 60 samples/field, 3 scenarios = 108,000 synthetic time observations.

| 시나리오 | true (pose,time,white) | empirical weights |
|---|---|---|
| REV60 | (.50,.30,.20) | (.515,.282,.211) |
| FWD60 | (.50,.30,.20) | (.557,.219,.223) |
| REV60 no-time negative | (.70,0,.30) | (.670,.001,.309) |

REV60 동일 pose 29쌍의 공간 성분이 정확히 같고, 서로 다른 시간의 시간·독립 잡음이 차분에 남는 구조를 검증했다. REV60 pair differencing만의 시간 추정은 0.347(참 0.30), 독립 잡음은 0.160(참 0.20). 통계적 오차를 보유한 실험 결과로 인정하되 독립 field simulation 외 물리 시간 과정까지 입증하지 않는다.

## 4. 신규 검증 환경

기존 Corridor/Office/HOLDOUT2와 다른 사전 정의 6개 pose, anchor A/C와 4가지 합성 파형(직접 + 0.35ns/1.5ns/3ns 복소 echo)으로 48 configurations ×256 noise trials = 12,288 observations.
- source h_s0 parity 불일치 0.
- 합성 echo 추가에 의한 first-path tap 변경 6/48.
- noise에 의한 tap switching은 48/48 조건에서 발생.
- 독립 반사점·물성·Sionna RT가 계산된 것 아님. 이 결과는 NEW SYNTHETIC VALIDATION CONDITION, NOT A NEW PHYSICAL ENVIRONMENT. 독립 장면 일반화 주장에는 사용할 수 없음.

실제 새로운 물리 환경은 기존 unsigned PRE-P3 canary C00/C01/C10에서 8 direct parity → 최대 76 configs 순으로 검증할 수 있다. 아직 signed numeric budget, independent audit, scene adapter, reproducible solver matching이 확인되지 않아 실제 RT 실행 0.

## 5. 최종 코드 감사 판단 및 수정 우선순위

1. **완료:** source/observer contract parity, 추가 tap J_s0/J_s1 fixed-tap, 2-port CFR noise Monte Carlo + full covariance transform, spatial/time known-generative revisit, same-scene conditional polarization Fisher, novel no-RT synthetic echo.
2. **P0 blocking (첫 번째):** continuous SourceFFD range mean vs quantized first-edge range observer의 probability likelihood 정합성. Raw full R의 singularity/first-tap mixture를 임의 regularization으로 감추지 말 것. 필요시 sub-tap timing ToA 또는 원시 CIR likelihood와 수치/정책 QA.
3. **P0 blocking (두 번째):** 복소 H에 주입된 thermal noise assumptions, sample/port time-jitter, frequency correlation, receiver gain/phase, weak-port and tap switching calibration. 실제 하드웨어 원시 두 수신편파 tap 동시 제공 여부 미확정.
4. **P1:** 위 두 조건에 맞는 3관측 full model 및 R_3 PSD, Schur conditional ΔI with pose/nuisance marginalization. Candidate G5 baseline, prior innovation d0 duplicate control and original full mask fixed, SELF_NIS separately. No truth leakage.
5. **P2:** state b_s time/space nuisance prior and white/colored split trained on truly independent scene/time, independent pose revisit; only thereafter compare 4 vs 5 state RMSE/NEES/95% coverage and matched-prior policy. Original static H cannot supply this independently.
6. **P3:** separately approved new RT canary and new unseen physical environment. Office already analysed and original MBVAR HOLDOUT2 is governed by another contract: neither should be silently reclassified as fresh external TEST.
7. **Audit gate:** require independent reviewer and negative fixtures to validate entire code/claim package. This branch has no independent science audit and not all unrelated repository CI is green.

**Scientific limits:** Extra adjacent tap has nonredundant local numerical information within the assumed LoS model and correlated noise, but it has NOT yet demonstrated a physically calibrated reduction in full multipath heading RMSE. Known synthetic pose/time source separation is successful, but no physical independent temporal drift is established. Truly unseen new RT scene generalization NOT TESTED.
