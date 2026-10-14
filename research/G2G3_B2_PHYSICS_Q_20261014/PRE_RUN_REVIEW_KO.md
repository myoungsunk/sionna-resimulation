# B2/C2/D0 사전 감사 — 2026-10-14

## 1. 목적·근거
사용자 승인: 기존 B의 독립 보정 실패를 새 물리 기반 확률모델로 재검증한 다음 C1–C4 및 가능한 후속 G2/G3 단계까지 진행. 수치 계산/가설/과학적 주장 구분. 독립 자료 부족과 이미 확인한 RF 과소보정 C3, 긴 경로 C4 반례를 숨기지 않는다.
감사 기준: 9beb061f354edef18e1f977f5d462d7e0d8b1f2e.
이전 기준: B/C commit 2fa18fbf26b817af2e6591157c8bc05c86fd4904, run 38556968635.
원본 RF Office/Anchor2: b05af070a87981f8712fdd41eac4c1bbb882e9c7; Office 35, A2 15, A2B 14. Office/A2 are two different *synthetic geometrical scene families*, A2B belongs to A2 family. Both previously inspected: no new independent third RF family.
기존 signed Full/E1과 LoS/B_OLD는 원본 detector/antenna calibration과 office TX0 observer가 달라 그대로 같은 physical likelihood로 채택 불가.

## 2. B2 signed error model: pre-specified limitations
- Clean positionwise Office LoS residual mean mu, standard deviation sigma, **Gaussian convolved with independent Uniform[-q/2,q/2]** with frozen tap spacing q=0.1495522588047491m. This is a deliberately conservative noise-broadening hypothesis, **not** an exact 30%-leading-edge detector likelihood: continuous threshold crossings may be biased, and office raw residual sd already includes discretization. Do not claim calibrated sensor generative law solely from this.
- Blocked Office residual Student-t df3 (loc median, scale max(0.06m,1.4826 MAD)).
- **Defensive negative error component** Student-t(df3,loc=-0.5m,scale=.25m,weight=.035) is inherited from *pre-existing* G2G3 synthetic C3 prior BEFORE this test. It has not been calibrated in independent sensor data. It is a conservative risk component, not a physical measurement claim.
- CIR quality Q consists of observable first-to-peak gap, first energy fraction, and first/peak amplitude ratio, *never truth Range, actual geometric LoS label, or injected gyro condition*. In Office TRAIN ONLY, regularized logistic (lambda=5) predicts oracle blocked label from observed Q; mix with office base block fraction using 50% fixed shrinkage. At online inference, no labels are required.
- Model density: f_R(e|Q)=(1-.035)*[(1-w_bad(Q))*f_clean(e)+w_bad(Q)*f_blocked(e)] + .035*f_negative(e).
- Compare 95%/99% one-sided empirical coverage, PIT uniformity KS, NLL and Office leave-one-location-out. Heldout A2 and related A2B are NOT included in fitting or logistic normalization.
- No tail threshold altered from predeclared 95%/99%. 100% observed coverage with n=15/14 is not independent 99% calibration proof.

## 3. DR fault prior limitation
Existing synthetic pFault=.05 and extra2m remain frozen, NOT calibrated with independent dynamic gyro/odom. The external office and anchor RF sweeps have NO time-resolved odometry. Direct P_RFbetter requires joint p(eR,eD|delta,Q,U), not just RF RMSE or CIR quality. This run evaluates only independence surrogate.
Test event: delta=d-z=e_D-e_R. delta>0 iff eR> -delta/2 improves radial absolute error; delta<0 opposite. Source truth only synthetic fixture scoring AFTER infer decisions.
C2 keeps fixed C1–C4, old NIS>6.634896601, pwin>=.95, RF shorter sign guard. Novel signed f_R with prior negative-tail component must not be trained/tuned from C3/C4 outcomes. Need separate check of **pwin C4 false confidence** even when action guarded.
Estimate numerical via interval-split adaptive quad vs separately fixed Simpson grid; invalid if mismatch > 1.5e-5. C protective action PASS is not probability calibration.

## 4. D0 stage scope
D0 only independent source audit plus algebraic factorization of normalized **scalar radial × toy angular** nonlinear likelihood. It does NOT compute physical full 3-state G2/G3 or original S LoS LUT.
Historical D original tilted-GH one-cell independent verification run 38531405523 had numerical PASS, but original physical G3 Heading posterior had error 52.58° vs G2X 24.56° in run 38532581455. Do not reinterpret old R0 or call D0 "G3 whole route PASS".
If B2 or C2 *scientific calibration* fails, D0 purely mathematical checks may continue under CLAIM_BLOCK. Physical E full and F recursive stay NOT_RUN until calibrated DR fault and independent full pose numerical reference.
Stop hypothesis-dependent adoption at first contradiction and report before new tuning.

## 5. Audit logic and findings
- HARD_EXECUTION_BLOCK: Git source hash mismatch against approved Git blobs; original Office receiver parity/source-commit mismatch; any online truth/CIR feature inferred from ground truth; observation double-count or invalid probability density.
- CASE_RESULT_INVALID: B2/C2 numeric nonfinite / quadrature disagreement / invalid model, only dependent numeric cell blocked.
- CLAIM_BLOCK: A2/A2B as independent experiments, signed posterior online calibration from 2 scene families, DR fault prior, Full E1 transfer, full G2/G3 RMSE/covariance/NEES.
- DIAGNOSTIC_DEFECT_OR_WARNING: result export/optional plot errors, fix with new approved source and run receipt preserving previous science calculations.
- No external human reviewer; model code source reviewed by assistant; independent checks are different mathematical paths for C probability and original receiver readout.

## 6. Static pre-run source audit
Reviewed files: CONTRACT.json, run.py, gate.py and workflow B2. Source-BLOCK important potential was **truth leakage through reconstructing observed distance via true range** in a quality feature; removed before approval. Q now uses 3 CIR-only features.
A 4th hidden source of apparent B PASS is external target leakage via heldout labels; this code fits logistic/clean and blocked error components ONLY Office samples. External A2/A2B used for reported scores after freeze and no post-hoc parameter alteration.
Another limitation: clean spread fitted from quantized positional residuals then widened by explicit tap uniform uncertainty **double counts some discretization variance**, deliberately conservative and should be measured as calibration sharpness vs coverage, not framed as physically exact.
The prior defensive -.5m signed component remains *synthetic inherited* and is not a claim of genuine B independent calibration. C4 should be inspected explicitly, do not adopt a probability flag as state safety evidence.
New source SHA validated on actual GitHub runner at BOOTSTRAP, B2, C2, D0. Original Office acquisition and extraction separately audited using unchanged original source and approval.

## 7. Four separate verdicts
(1) EXECUTION: stage code cloud success required, not inferred from push.
(2) CALCULATION: finite/normalized density, source SHA, error formula independent quadrature and algebra identity.
(3) HYPOTHESIS: B2 leave-location-out + A2/A2B external coverage and C1–C4 guards; contradictions reported not retuned.
(4) SCIENTIFIC: calibrated posterior and pose/Heading/G2/G3/generalization remains CLAIM_BLOCK until 3+ independent RF scene families, independent gyro/odom, correct co-observation and pose likelihood; no release/final adoption.
