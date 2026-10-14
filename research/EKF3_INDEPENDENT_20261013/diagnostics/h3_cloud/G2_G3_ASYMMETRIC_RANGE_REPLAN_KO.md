# G2/G3 비대칭 RF Range 관측 및 DR Fault 모델 — 실험 재계획
Date: 2026-10-14

## Status and provenance
- Numerical source and RF calibration are immutable: H3 32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20.
- New descriptive sign audit: branch research/rf-range-sign-audit-g2g3-20261014.
- Verified GitHub Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38523237789
- Audit artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38523237789/artifacts/11875206058
- Paired DR prior and original Range parity: D0 84/84 condition/case/seed; all original D4 RF residual bins reproduced within 1e-8.
- Unique RF observations = 18,603 = 6,201 observations per calibration model, shared RF scenes across 4 gyro/noise settings and 3 DR sensor seeds.
- Paired DR/RF evaluations = 223,236 records. These frames and seeds are NOT independent RF scenes.
- scientific_PASS=false. G2/G3 revised filter is NOT_IMPLEMENTED. G3 numerical FAIL_CLOSED remains valid.

## 1. Signed residual evidence
Define eps_RF=z_RF-r_true. For each method, the table uses 6,201 unique case/pose observations.

Method | mean eps (m) | RF RMSE (m) | P(eps<0) | q05 eps (m) | q01 eps (m)
--- | ---: | ---: | ---: | ---: | ---:
LoS/B_OLD | -0.00259 | 0.04592 | 51.70% | -0.07370 | -0.09152
Full/B_OLD | +0.05032 | 0.13721 | 34.27% | -0.08648 | -0.13276
Full/E1 | -0.00489 | 0.10674 | 59.15% | -0.13067 | -0.19434

The *physical uncorrected path* length may be >= the geometrical line-of-sight, but corrected RF outputs are NOT guaranteed to exceed true distance: z_RF=h_r(x)+(b_NLoS - b_calibration)+noise. E1 reduces overall Full RMSE while increasing its negative residual tail.

Descriptive one-sided margins tau_95=max(0,-q05 eps), tau_99=max(0,-q01 eps):
LoS/B_OLD 0.07370m / 0.09152m;
Full/B_OLD 0.08648m / 0.13276m;
Full/E1 0.13067m / 0.19434m.
The suggested P(r_true <= z_RF + tau_alpha(Q)) >= 1-alpha is a *future heldout-calibrated chance constraint*, not an externally validated probability guarantee. In previous 0.5m spatial-buffer training, R2 and R5 had no eligible training samples. Separate independent RF scenes remain required.

## 2. Actual DR vs RF win rates and non-universal exceptions
Definitions:
h_r(x,y)=sqrt((x-a_x)^2+(y-a_y)^2+delta_h^2).
r_DR=h_r(mu_DR), delta=r_DR-z_RF; positive delta means RF shorter.
Score using truth ONLY after inference:
I_RF=1{|z_RF-r_true|<|r_DR-r_true|}.
NIS=(z_RF-r_DR)^2/(H_r P_DR H_r^T+Rr); frozen chi-square 99% gate=6.634896601.

At gyro_bias L2:
Method | RF win if delta>0 | RF win if delta<0 | RF shorter and rejected n | rejected RF win | RF MAE | DR MAE
--- | ---: | ---: | ---: | ---: | ---: | ---:
LoS/B_OLD | 91.8% | 81.5% | 3,308 | 100.0% | 0.042m | 1.618m
Full/B_OLD | 92.6% | 47.6% | 3,138 | 99.94% | 0.050m | 1.686m
Full/E1 | 88.0% | 73.4% | 3,513 | 99.17% | 0.044m | 1.537m

Counterexamples: Full/E1 when RF shorter and original NIS rejected, noise_pair L1 n=10 RF win 0%, gyro_bias L0 n=11 RF win 0%. In R4_aA_m0, E1 can underestimate true distance by approximately 0.47–0.52m while DR radial error is only 0.03–0.05m. Even under L2, R4's 13 eligible records gave RF win 0%. Therefore delta>0 and high NIS alone cannot authorize unconditional RF trust.
True gyro_bias level is a simulation stress label, not an observable online classifier.

Frozen failure sample (R2_aA_m0, L2, seed0, 195.6s):
r_true=3.608730597m, RF LoS/B_OLD=3.672195826m, DR=6.414651253m.
RF signed error=+0.063465229m; DR signed error=+2.805920656m; delta=+2.742455427m; NIS=112.189372.
Original gate rejected a useful RF observation, but the gate is mathematically a prior/measurement incompatibility test, not a test proving RF is wrong.

The sufficient inequality r_true<=z_RF<r_DR guarantees RF better in **one-dimensional distance**; this is not guaranteed for corrected RF outputs. One Anchor Range does NOT give exact position/heading.

## 3. Mathematical changes: replace blind sign gate with two failure hypotheses

Let pose xi=(x,y,psi). M_D in {N=nominal DR, F=DR fault}, M_R in {I=RF inlier, O=RF outlier}.
The model must retain p(x,y,psi) cross-covariance and circular yaw; no truth leakage.

(a) Model the signed corrected RF residual:
L_I(z_r | xi,Q) = f_e|Q(z_r-h_r(xi)).
Use an asymmetric signed, heavy-tail candidate (split normal / t mixture) with negative residual mass. RF outlier branch L_O is broad with proper normalization. Parameters and quality feature Q (CIR etc.) must be trained using non-heldout data only.
Physical path bias b_NLoS>=0 applies before calibration; **do not impose z_corrected>=h_r(xi)**.

(b) Model the DR probability of catastrophic drift:
p_DR^-(xi |u) = pi_N(u)*p_N^-(xi)+pi_F(u)*p_F^-(xi).
Normal branch p_N is the original frozen DR prior; fault branch p_F is a broad/multimodal prior physically propagated from uncertain gyro bias/motion, not inflated retrospectively to match heldout truth.
Prior weights pi_D(u) use DR gyro/motion history before current RF observation, not the same Range measurement twice.
RF inlier/outlier weights pi_R(Q) use online RF-quality features, not oracle errors.

(c) Proper single-use joint posterior with latent hypotheses:
p(xi,M_D,M_R | z_r,z_s,u,Q)
  proportional to
pi_D(M_D|u) pi_R(M_R|Q) p^-(xi|M_D)
* L_r(z_r|xi,M_R,Q)
* L_s(z_s|z_r,xi,M_R,Q).
The model posterior weights are the normalized evidence integrals over xi.
When delta>0 and NIS is very large, **do not hard-switch**; ask whether DR-fault/RF-inlier evidence exceeds DR-normal/RF-outlier evidence. A decision threshold (e.g. P(M_D=F,M_R=I|data)>=0.95) is an example engineering criterion only and must be preregistered before testing.
The RF Range measurement enters the posterior ONCE. Do not multiply an additional one-sided penalty onto the same signed RF likelihood; that would count the same observation twice.

## 4. G2/G3 mathematical equivalence and approximation controls
**Exact G2 (sequential)**:
p(xi,m | z_r) proportional to p_DR^-(xi,m) * L_r(z_r|xi,m);
p_G2(xi,m | z_r,z_s) proportional to p(xi,m|z_r) * L_s(z_s|z_r,xi,m).
Preserve component weights, full pose–heading covariance and multimodality; do not use the original rejecting NIS gate as an unconditional reason to discard an RF-inlier hypothesis.

**Exact G3 (joint)**:
p_G3(xi,m | z_r,z_s) proportional to
 p_DR^-(xi,m)*L_r(z_r|xi,m)*L_s(z_s|z_r,xi,m).
For identical likelihoods, priors and accurate integrals, G2-exact must equal G3-exact by Bayes factorization. Any disagreement requires code/numerical/gate/mixture-collapse audit, NOT an ungrounded assertion that one is statistically better.
**Approximate G2**: Range EKF / Gaussian approximation followed by S conditional likelihood, explicitly separate from G2-exact. Any performance difference vs G3 may reflect EKF linearization/gating/Gaussian collapse rather than sequential vs joint Bayesian inference.
S/r correlated noise requires valid p(z_s|z_r,xi), with retained full RF noise covariance, not S independence by assumption. R0 R_sr=0 remains an explicit frozen comparison arm.

## 5. Numerical reference and stopping rules
Historical:
- Original GH order 41→65 joint-TV 0.387065: FAIL_CLOSED.
- Original 144×96 polar TV 0.209147: FAIL_CLOSED.
- Frozen range-only adaptive RQMC at n=65536 independent-seed TV 0.628746 / posterior-weighted effective samples around 1: FAIL_CLOSED.
No prior numerical fail is relabelled as success.

New fault+signed RF model is a NEW probability distribution and needs NEW independent numerical convergence.
Use defensive multimodal proposal:
q(x|psi) = eta_N q_nominal + eta_F q_DR-fault + eta_R q_range-shell + eta_U q_full-support,
with exact target/proposal ratio and no duplicate likelihood.
Require independent scrambled QMC and a separate reference integrator agreement (posterior TV<=0.001, MAP<=0.1deg, HPD width<=1deg), evidence/ESS/modes/tails audited. If reference itself fails, numerical FAIL_CLOSED before ranking any pose RMSE.

## 6. Stepwise experiments, frozen gates, falsification
Stage A = current signed RF & directional audit **completed**. No accepted new estimator.

Stage B = fit and independently audit signed RF residual/tau margins and online CIR quality, plus DR fault prior from gyro/motion. No cross-scene certification under only R2/R4/R5 overlapping paths. Original 0.5m spatial buffer must not be loosened after looking at evaluation results.

Stage C = synthetic verification with four predeclared contrasts:
C1 nominal accurate DR + accurate RF (low-bias guardrail);
C2 large DR radial over-prediction + reliable RF (rescue required);
C3 nominal accurate DR + negatively overcorrected RF E1 (must NOT force RF);
C4 NLoS RF too long + accurate DR (must avoid RF error).
Add wrapped psi, nonzero XY-psi cross covariance, multi-mode, R_sr!=0, near-pole.
No truth is used by online estimator. Under C3, a proposed unconditional RF priority is explicitly **refuted**.

Stage D = paired one-step 7 case × 4 DR conditions × 3 sensor seeds × 3 channel/model arms.
Arms: DR-only, G0, original frozen G2H/G2X/G3 when numerically defined, new G2-exact, new G2-approx, new G3-joint, blindly-RF-shorter control, gate-matched control.
Report signed radial errors, 2D/heading RMSE, P95, posterior model branch weights, coverage & NEES, NIS sign bins, numerical TV and fail count. Use route/case blocks as analysis units; repeated Seed are not independent RF scenes.
Stage D must isolate large-bias rescue and no-bias false-rescue cost. Do not infer calibrated trust from raw pooled frame win rates.

Stage E = recursive full-route pose posterior and 3×3 covariance (including Pxy_psi), only if Stage C/D and numerical gates pass. External scene independent confirmation is still necessary for scientific_PASS.

**STOP RULES**:
- Frozen input SHA, P0/P3, D0 or D4 parity FAIL => STOP.
- Signed RF tail fails heldout empirical one-sided coverage => no hard RF upper bound.
- C3 false RF rescue cannot be stopped => reject model.
- Posterior reference TV/evidence fails => STOP before G2/G3 accuracy comparison.
- G2 exact vs G3 exact disagree => identify factorization/double counting, no performance claims.
- If hypotheses are contradicted, run at most a bounded diagnostic and report confirmed/refuted/unresolved. Do not retune frozen gates retroactively.

**FINAL THESIS:** In large positive DR–RF conflict, RF may be a much better radial measurement, but dominant trust should be a posterior conclusion of DR-fault vs RF-outlier model selection, not a deterministic inequality based solely on shorter corrected Range and NIS.
