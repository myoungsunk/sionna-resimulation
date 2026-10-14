# B 추가 검증 — 실행 전 소스/수식 감사 (2026-10-14)

## 1. 사용자 의도 및 업무 경계

실험은 B에 한정: 보정된 RF Range의 signed residual에 어떤 online-readable error/quality 지표가 존재하는지 조사하고, 이 지표로 RF가 DR보다 거리 오차가 작은 확률을 계산할 수 있는지를 평가한다. C/D/E/F 추정기 수정을 수행하지 않는다. A 검증된 원시 RF 및 DR 행은 GitHub Actions 아티팩트 11875206058 SHA256 56276ccb88605382b801f080cb97b58bc465bcff46c78677bcaf14fcd1b62bd5에서 READ ONLY로 읽는다. RF N=18,603개(모델별 6201); paired DR×RF N=223,236. 동일 RF 장면이 복수 DR seed/조건으로 반복되어 독립 RF 관측으로 간주하지 않는다.

참조 사전 감사 기준: https://github.com/myoungsunk/sionna-resimulation/blob/9beb061f354edef18e1f977f5d462d7e0d8b1f2e/research/EKF4_RANGE_S_STAGED_20261014/PRE_RUN_AUDIT_POLICY_20261014_KO.md
기존 최소 모델: 1e325da186355533fc585ed9d8bffe12d02d0604
이번 B 결과 해석에서는 실행가능 / 계산유효 / 가설지지 / 과학주장 4개 판정을 분리한다.

## 2. 중요 수학 및 충분한 검증 범위

기본:
e_R = z_RF-r_true (signed);
e_D = r_DR-r_true;
delta = r_DR-z_RF = e_D-e_R.

B의 조건부 거리 우위 확률:
P_RFwin = P(|e_R| < |e_D| | delta,u,Q) .
delta > 0일 때 P_RFwin = P(e_R > -delta/2 | delta,u,Q),
delta < 0일 때 P_RFwin = P(e_R < -delta/2 | delta,u,Q).
동일 RF observation에 원래 NIS gate와 별개 chance-bound penalty를 곱하지 않는다.
RF error 분포만으로 P_RFwin을 결정할 수 없고, DR error prior와 관측 delta의 조건부 likelihood가 필요하다.

테스트용 독립 Gaussian error 모델:
e_R~N(mu_R,sigma_R²),
e_D~(1-pF)N(0,sigma_D²)+pF N(0,sigma_D²+sigma_fault²),
joint error independence within the simplified model, which is UNVALIDATED.

For each component, V=var_D+var_R,
posterior mean of e_R given delta = (mu_R*var_D - delta*var_R)/V,
posterior var=var_D*var_R/V.
Mixture posterior weights proportional prior-component-weight*N(delta;-mu_R,V).
P_RFwin from Normal-CDF event, compared against independent direct numerical integration of p(e_R)p(e_D=e_R+delta).

Original sigma innovation²=H P H^T + Rr, so sigma_D²=sigma_innov²-Rr. Rr=0.0068578637 m² must be removed ONCE before the error prior. No truth enters candidate predictions: RF signed errors from *other route* provide training labels; truth in evaluation is used solely for scoring pwin and log/coverage accuracy.

## 3. Calibration/quality feature boundary

Available in frozen A artifact: method/channel, corrected observed Range, t_s, DR geometry, DR predicted radial sigma, RF signed residual truth labels for evaluation. NO raw CIR quality values are in the archived signed data.

Report RF quality indicators:
- signed bias, median and std/RMSE;
- negative/positive q01/q05/q95/q99, P(e_R<0), P(e_R<-0.10m), P(e_R>+0.20m);
- conditional error magnitude and under-range events by observed corrected Range (<5/5–10/>=10m);
- leave-one-route-out heldout signed q05/q01 coverage; Gaussian likelihood log score, PIT KS;
- DR reported sigma vs truth-based tail frequency and |e_D|>0.5m;
- P_RFwin (from method-wide signed Gaussian + DR error prior), Brier, log-loss, ECE, high-probability precision/activation, and negative cases.

Observed Range bin statistics are **only descriptive and risk-score diagnostics**. Fitting f(e_R | z_RF bin) and inserting it directly as a normalized generative likelihood p(z_RF|r,Q) is generally incorrect because the bin is itself a function of z_RF and selection must be normalized. No such insertion is performed.
CIR quality proxies not yet measured; future work may use frozen receiver first/peak power, 30% leading-edge/peak ratio, peak-minus-first-path gap, direct-path SINR, etc, with independent scene/channel calibration, BUT no claim of their predictive power in this run.

## 4. Independent validation and claim boundaries

- Train each method's RF error mean/variance/empirical one-sided bounds on the OTHER TWO routes. Test on heldout route; test truth NEVER enters fit. This is **route-out testing**, NOT the earlier stricter 0.5m spatially independent holdout (R2 and R5 training feasibility 0). 
- RF routes R2/R4/R5 spatially overlap. This is a calibration eligibility limit / CLAIM_BLOCK, **not a hard block of numerical diagnostics**.
- Only three route types, many temporally correlated samples; count of 223,236 is descriptive paired evaluations.
- Compare no-fault DR prior vs earlier SYNTHETIC trial pF=0.05,sigma_fault=2m, with exactly the same heldout RF error fit. Do not use heldout score to tune any model parameter/threshold.
- Numerical math atol 1e-8 on 6 varied delta/sign/prior fixtures. This is algebra verification, not external calibration.
- pWin≥0.95 is **the earlier exploratory threshold**, cannot be called calibrated 95% correctness.
- No online DR fault probability or CIR quality model fitted. scientific_PASS=false.

## 5. Actual findings before cloud experiment

SA-001 **HARD_EXECUTION_BLOCK** (fixed before any scientific execution): b_audit.py initially referenced an undefined fault prior identifier in the second Gaussian-mixture branch. Replace with pfault and skip zero-mass components before taking logarithms. Original draft commit 4ccffcdf240d978645c6d48f81b782923f3ce3d8; corrected source commit 96da3e63ea338293156a002f1bc0072db3932442. The source SHA locked by APPROVAL must be the FIXED blob; original implementation is not executed.

SA-002 **CLAIM_BLOCK**: no separate independent RF calibration world, no CIR features, no online gyro-bias likelihood. Continue descriptive/route-out diagnostics and independent math but do not certify probability calibration.

SA-003 **CLAIM_BLOCK**: Gaussian RF residual may inadequately model Full/E1 tails; PIT/heldout tail coverage must be reported rather than hidden. A failure here limits the likelihood/production claim, not valid numerical calculation.

SA-004 **DIAGNOSTIC_DEFECT_OR_WARNING**: missing optional plots/route table does not retroactively invalidate raw data, math fixture or independently verified pwin algebra; repair scoped diagnostics as needed.

SA-005 **HARD_EXECUTION_BLOCK**: exact input zip SHA, DR covariance variance split, RF duplicate/pose-time/source sign identity mismatch. Stage-specific dependent evaluation stops.

Before each cloud phase, b_gate.py verifies the *approved source Git blob hashes* against actual runner bytes and creates a separate PRE_RUN audit receipt. Approval file creation alone triggers Actions; code pushes do not trigger a science run. If hypothesis fails, report opposite evidence and stop without retuning.

## 6. 첫 클라우드 결과 및 범위 제한형 재감사 (B-REPAIR-01)
- 실패 실행: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38545120474
- 원본 데이터 SHA 확인 PASS, source-bound PRE_RUN fixture/acquire/evaluate PASS, 독립 math fixture B_MATH_AUDIT PASS.
- 실패 발생: RF_HELDOUT_BY_ROUTE.csv의 보고서 한 행을 dict으로 조립할 때 train_n 필드가 직접 정의와 one_sided() 반환값에 중복 포함되어 TypeError를 발생시킴.
- 분류: **DIAGNOSTIC_DEFECT_OR_WARNING**, 영향을 받는 범위는 heldout-route 출력 조립 및 그 뒤의 B data phase. 성공한 독립 math는 보존한다.
- 수정: 오직 중복 선언 train_n 한 개 삭제. sign/Range/DR error 계산식, Gaussian probability 수식, prior, 훈련 범위, threshold, 입력은 그대로 유지.
- 수정 코드 commit: 6ca9b9cf6d1471e9d9e0dddffdc47b14b1c6734f.
- 수정후 Git blob과 amended REVIEW/APPROVAL를 새로 고정한 뒤 cloud에서 전체 B-only 단계만 재실행한다.
- 실패 실행은 남기고 다음 성공을 소급해서 원래 run에 적용하지 않는다.
