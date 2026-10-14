# G2/G3 B–F 단계별 감사·판정 및 다음 분기 (2026-10-14)

## 사용자 요청과 판정 범위
목표는 A→F까지 구현·검증이지만 과학 가설에 반대되는 결과가 나오면 진단 후 다음 가설 방향을 확인하고 진행한다. 따라서 이번 문서는 **기존 검증에서 확인된 C4 반례와 B 학습 불가능성**을 정리하고, 그 다음 실행을 위해 필요한 변경 계약을 등록한다. 이 문서 자체는 새로운 B–F 실험 실행이나 승인 영수증이 아니다.

기준: EKF4 PRE_RUN_AUDIT_POLICY_20261014_KO.md @ 9beb061f354edef18e1f977f5d462d7e0d8b1f2e
원본 H3: 32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20
최소 모델 source: 5dfdea0bdc86706cadc69cc20a3607a482fa02f9
최소 모델 수식 및 합성 run: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526264898
Readout 수정 run: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38527848155
원본 DR/RF signed 감사: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38523237789

## A–F 네 층 판정
| 단계 | 실행 가능? | 계산 유효? | 가설 지지? | 과학적 주장 가능? |
|---|---|---|---|---|
| A. signed/부호별 RF audit | PASS(기존 검증 재사용) | PASS(원본 D0/D4 parity) | 방향별 RF 우위는 특정 사례 지지, 보편적 우위는 반례 | 보관된 시뮬레이터의 기술통계에 한정 |
| B. signed likelihood / gyro fault prior 보정 | 모델 합성 구현 가능, 독립 보정 데이터 적격성 FAIL | 합성 모수로 수학 계산 가능 | 실제 보정·보장 주장은 미검증 | CLAIM_BLOCK_CALIBRATION |
| C. 4종 합성 반례 | 완료(기존 최소 radial 시험) | 검산 PASS | C2 복구 지지, C3/C4 연속상태 보호 **불충분** | 새 estimator 채택 보류 |
| D. G2/G3 수치 적분 | 선형 Gaussian 구성 PASS; full nonlinear 이전 FAIL | 선형 동등성 PASS, full nonlinear TV 0.387065 > 0.001 | exact algebra만 지지 | full nonlinear 성능 CLAIM_BLOCK |
| E. one-step 전체 비교 | 새 estimator 미구현·미실행 | NOT_EVALUATED | NOT_EVALUATED | CLAIM_BLOCK |
| F. recurrent 3-state | 새 estimator 미구현·미실행 | NOT_EVALUATED | NOT_EVALUATED | CLAIM_BLOCK |

## B 사전 감사 — 독립 학습의 적격성
H3 frozen 0.5m holdout spatial feasibility를 다시 확인:
R2 heldout: R4/R5 모든 training case buffer-valid=0.
R5 heldout: R2/R4 모든 training case buffer-valid=0.
R4 heldout: 각 R2 case 267, 각 R5 case 220 buffer-valid observations.
이 수치는 서로 독립 scene 수가 아니며, 경로 공유/시간 상관 및 antenna case 반복이 존재. **R2와 R5에 대한 0.5 m buffered 학습-평가 계약을 만족하는 calibrator를 현 dataset에서 구축할 수 없다.**
따라서 B의 독립 calibrated signed RF likelihood, P(corrected range true<=z+tau|Q), gyro fault prior calibration을 PASS라고 판정하는 것은 금지.
이는 HARD_EXECUTION_BLOCK이 아니라 **CLAIM_BLOCK_CALIBRATION**: 합성 수식·독립 적분·진단 및 별도의 새로운 데이터 구축은 계속 가능하다.

## C 위배: 기계적인 95% RF dominance threshold로는 상태 보호 불가능
C2 truth 3.608730597, DR 6.414651253, RF 3.672195826:
posterior mean 3.695715835; RF distance superiority posterior probability .9978215929, point error .086985238m.
C3 truth5.0, DR5.03, RF4.50: posterior mean error .065532m > DR .03m.
C4 truth5.0, DR5.03, RF7.0: posterior mean error 1.302069m >> DR .03m.
95% dominance boolean 미발동은 continuous posterior mean의 움직임 제한이 아님.
**원래 C의 '잘못된 RF로 정확한 DR 보호' 가설은 완전 지지되지 않는다.** 모델 파라미터를 같은 평가 자료에 fitting하거나 과거 오류를 PASS로 바꾸지 않는다.

## 더 검증해야 할 가설 (수정 방향; 승인 전 미실행)
C2를 회복하면서 C3/C4를 보호하려면 단순 혼합 posterior mean 대신 **사전 고정된 action/readout policy**를 별도 비교할 수 있다:
1. posterior에서 직접 거리 우위 사건 probability pi_better := P(|z-r|<|d-r||z,d,Q,u) 산출. `fault∩inlier` 확률을 필수 gate로 사용하지 않음.
2. 위험 제약을 사전에 정의한 RF-assisted radial action a로 적용. 후보: RF superiority가 높은 경우에만 단일 step radial correction; 애매한 경우 DR 유지; posterior mixture mean을 무조건 state에 내보내지 않음. 이는 기존 Bayesian posterior 자체를 변조하는 조치는 아님.
3. 점추정/갱신 정책은 `DR-only`, `unconditional mixture mean`, `posterior RF-win action`, `blind shorter RF` 대조로 고정하고 C1–C4 및 sign-negative controls에서 DR degradation과 C2 rescue를 동시에 측정.
4. 이용 가능한 입력이 d,z,σ뿐이면 posterior와 다른 실제 truth를 갖는 alias world가 존재해 정확한 신호원 구별을 절대 보장할 수 없다. 따라서 gyro motion history 및 CIR quality feature 추가 여부를 사전 결정해야 하며, 이 입력의 독립 교정 전까지 source attribution claim 금지.
5. 새 policy의 synthetic guards 통과 후 **별도** signed likelihood/DR fault calibration을 검증. 제대로 된 heldout scene가 없으면 실험 결과는 탐색 범위에 머물러야 한다.

## D–F 단계 강행 금지와 향후 실행 조건
D: 동결 G3 GH TV 0.387065, fixed polar TV .209147, adaptive QMC 65k independent seed TV .628746를 재해석해 PASS하지 않는다.
Exact G2 and exact G3 with identical `p(x,y,ψ)` and `p(z_r,z_s|x,y,ψ)` must match; covariance cross-terms and correlation preserved; same RF Range precisely once.
Before comparing RMSE must independently solve numerical reference for actual 195.6s cell to TV<=.001 and diagnose ESS/modes/tails. Nonconverged cell => CASE_RESULT_INVALID, not invalidate unaffected D0/linear checks.
E: case/route/seed paired full one-step evaluation only after C+ D numerical validation; low-bias and R4/E1 overcorrection negative controls mandatory.
F: full recursive (x,y,psi), Pxy,ψ, 95% coverage, NEES and gradual/large gyro bias only after E passes source-appropriate guardrails.

## 감사 및 실행 의사결정
- Input/source SHA, truth leakage, duplicate RF use, covariance PSD, wrong factorization: HARD_EXECUTION_BLOCK, dependent runs stop.
- One nonconverged G3 cell: CASE_RESULT_INVALID only that cell, report fail denominator. Others may proceed if separable.
- B independent calibration missing / E/F external generalization missing: CLAIM_BLOCK only.
- Diagnostic serialization or optional metadata error: DIAGNOSTIC_DEFECT_OR_WARNING; repair and re-audit diagnostic, not scientific model.
- Contradiction: preserved C3/C4 and C2 probability ambiguity. User requirement #2 makes a new action policy/observation-feature model **direction-confirmation dependent**. No automatic scientific retuning or full nonlinear estimator implementation on an unapproved hypothesis.
- Requested continuation: approve **direct RF-distance-win probability as decision target, with DR-preserving radial action and explicit C3/C4 guardrails**; or demand an independent gyro/CIR feature/calibration stage first. Once selected, new contract, source-bound pre-audit, targeted fixture, correction, only then cloud expansion.

Current status: A and minimal radial mathematical subchecks DONE, C contradiction diagnosed, new B–F scientific verification NOT COMPLETED. scientific_PASS=false.