# Four priority RF/Delta-s experiments — 2026-10-28
Baseline branch: research/ds-x1-x2-results-20261026; parent a95f49d90bae532d386ed169e7d6d01382b2a311.
This branch is ADDITIVE. Never modify original E1 or 28-condition PB outputs.

## P1. Existing MB_VAR mathematical contract
Four-state x=[px,py,psi,b_g]. Prediction x-=f(x+,odom,gyro), P-=FP+F' + GQG'.
Fixed BASE-derived acceptance mask A_B per bias level (not live-gate).
z=[r,s], h=[h_r,h_s], mu_MB=[mu_r_EXDS,mu_s_POWER].
nu=z-h(x-)-mu_MB. R_VAR,k = R_POWER,k + diag(0,sigma_b(rhohat)^2).
sigma_b interpolated knots metres [0,1.5,3,6,10], stdev [0.011,0.02,0.05,0.12,0.24].
S=H P- H'+R_VAR; K=P-H' S^-1; x+=x-+K nu; Joseph P+.
NO extra Delta-s observation and NO bias state in MB_VAR. Delta-s only contributes to existing MB range mean.
Note: A_B is regenerated separately for B0/L0/L1/L2 by frozen BASE.

## P2. Proposed delta-distortion state + joint covariance (DESIGN ONLY)
State q=[px,py,psi,b_g,dDelta], with dDelta a latent multipath distortion, not raw measured Delta-s.
z_r=h_r(x)+mu_r_EXDS+v_r
z_s=h_s(x)+mu_s+f(dDelta,features)+v_s
z_delta=h_delta_LOS(x)+dDelta+v_delta.
H rows = [H_r,0], [H_s,df/ddDelta], [H_delta,1].
R3=[[Vr,Crs,CrDelta],[Crs,Vs,CsDelta],[CrDelta,CsDelta,VDelta]];
Joint covariance MUST be trained on residuals after applying f; do not assume independent derived CIR features.
qDelta prediction qDelta,k=phi(x,u)qDelta,k-1+wDelta.
Where f(dDelta)=a dDelta, beta_s=a dDelta is only a coordinate reparameterization:
it does not add new information unless the separate z_delta channel is actually observed.
Dynamic observability, Fisher/Schur complement and covariance condition checks precede any EKF adoption.

## P3. Actual incremental information experiment
incremental_delta_info.py runs paired FULL/LOS CIR (same original first-path detection) for 7 cases;
forms signed offsets +1,+2,+4,+8 and target residual sFull-sLOS-mu_POWER (GT used only for label).
Online baseline covariates: stored BASE prior polarization innovation, range innovation, mu_s, first-path power.
Train Ridge(alpha=20, fixed) on other TWO routes, evaluate held R2/R4/R5 route.
Compare cross-validated uncentered R2 and RMS. Positive delta-R2 is evidence of additional
predictive information CONDITIONAL ON THE SPECIFIED BASE FEATURES, not proof of EKF information gain.
Hard checks: measured sFull matches frozen E1 z_s; require no file input editing.
Next scientific gate: whitened conditional Fisher of [psi, dDelta] with residual covariance;
7-case binary success must not be treated as statistically independent route replications.

## P4. Failure attribution
audit_pb_scores.py independently calculates 28 paired comparisons with original PB_SCORES.csv:
BB_ORIG, MB_ORIG, MB_VAR; failure axes and magnitude, case clustering,
confidence and XY covariance, heading bias. It is *descriptive* not a packet causal replay.
Observed historical counts: 23/28 Heading improvement, 20/28 XY improvement,
19/28 simultaneous. R2_aA_m45 x 4 fails both; R4_aB_m0 x 4 fails XY only.
R5_aA_m0 L2 is Heading-only failure. Repeated B0/L0/L1/L2 share same RF.
For packet-level cause in follow-up: run matched-prior replay of MB_VAR with saved
Pprior,H,K,nu to split beneficial vs harmful K_s nu_s, radial/tangent first-pass and post60.

## Execution scope and honesty
The workflow can run P1/P4 immediately using committed PB_SCORES; P3 needs fresh RF
channel fetch. P2 at present is a mathematically specified experiment design, not a
completed 5-state replay. No claim of P2 empirical success until implemented and run.
