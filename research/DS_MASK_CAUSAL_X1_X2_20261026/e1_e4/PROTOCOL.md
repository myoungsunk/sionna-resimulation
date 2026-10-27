# Nonlinear E1–E4 protocol (2026-10-27 KST)

User authorized the reviewed plan including revised claim language and the additional E4b control. Execute E1 -> E2 -> E3 -> E4, no new training, R calibration, Office extension, or time-varying oracle. Preserve all existing outputs. Source/inputs and X1/X2 trace hashes are frozen before execution. Each stage must pass its controls before advancing.

Common: same 14 corridor Full conditions, original seed-0 controls, initial state/covariance, POWER_DIAG R and polarization mean. Integrate from t=0, score t>=30. Define all packet sets over the ENTIRE sequence (R2_aB new=6, lost=4; R5_aA new=26, lost=0). Recompute physical h/H/P/K on each trajectory. No re-gating after forced mask. Diagnostics use GT only offline; the oracle is explicitly not deployable.

Primary C8/C9 cases: R2_aA_m45, R4_aA_m0, R4_aB_m0, each B0/L2 (6 conditions). Run E1–E3 on all 14 and distinguish primary from additional conditions. E4a R5_aA_m0 B0/L2; E4b R2_aB_m0 B0/L2.

Parity: state, covariance, prior, H/h, mean/R and masks against X1 as applicable; atol=1e-10, rtol=1e-10 in stored SI units. Compare wrapped angles; effective sequential gains need not be compared. Masks exact. Numerical guards: finite states, symmetric P <1e-12, min eigenvalue >=-1e-12, rejected state/P unchanged. R off-diagonal must be exactly zero. Joint-vs-sequential synthetic unit check before replay. Preserve failure and stop dependent stages if any control fails.

Metrics: wrapped Heading error degrees; RMSE; signed mean bias; population std (ddof=0), verify RMSE^2=bias^2+std^2; heading95=95th percentile of absolute Heading error; heading NEES=e_psi^2/P_psi,psi; full-state NEES=e^T P^-1 e (4D, true constant gyro bias); anchor-distance error RMSE in cm from estimated XY and fixed heights. Also record XY RMSE and covariance consistency; do not infer true covariance accuracy from Joseph algebra.

E1: alpha=0,.25,.5,.75,1; mu_r=mu_B+alpha(mu_M-mu_B), fixed A_B. Endpoints reproduce BB and MB before next stage. Monotonic absolute-bias changes use 1e-6 deg numerical slack. Nondecreasing magnitude and nonincreasing std are descriptive dose-response, not C8/C9 identification. Absence of monotonicity is not absence of causation.

E2: m_s=mean(u_s_true[A_B]) over all time, separately per condition, from X2's verified truth-based BB residual (not its invalid linear attribution). Apply same scalar shift z_s-m_s to BB and MB. Include zero-shift BB/MB controls. Test only condition-constant residual-bias contribution. Do not automatically execute 10-second moving oracle.

E3: frozen-prior affine sequential range then polarization, diagonal R, Joseph covariance. Range step uses Kr=P Hr/(Hr P Hr+Rrr). BLOCK sets Kr[psi,bg]=0. Polarization residual subtracts Hs*(x1-xprior); no physical relinearization within the packet, final angle wrapping only. First require all 14 unblocked BB/MB sequential traces to reproduce X1. Then execute blocked BB/MB. This removes immediate range-stage psi/bg updates; later covariance/gain effects remain. It does not isolate a unique mechanism.

E2/E3 gap metrics: G_before=metric(MB)-metric(BB), G_after=metric(intervention_MB)-metric(intervention_BB); report raw G, f_signed=1-G_after/G_before, f_magnitude=1-|G_after|/|G_before|, sign reversal. Minimum |G_before|=0.01 deg for bias and RMSE, else NOT_IDENTIFIABLE. Primary support rubric uses f_magnitude >=.7 STRONG_GAP_REDUCTION; [.3,.7) PARTIAL; <.3 WEAK. This is an operational descriptive rule, not statistical significance or proof/refutation of all C8/C9. Report whether baseline |bias| and RMSE actually worsened.

E4a: BB baseline joint on A_B; at J_new=A_M & ~A_B add proper scalar polarization update, no new gate; keep BASE mu/R. Controls BB and BM reproduce X1. Primary reproduction=(RMSE_BB_NEW_POL-RMSE_BB)/(RMSE_BM-RMSE_BB); require denominator >.01 deg. >=.7 supports substantial reproduction; [.7,1.3] approximate reproduction, >1.3 overshoot. Signed bias ratio secondary with abs denominator >.01. This tests sufficiency of that packet/channel addition, not unique causality.

E4b: M range mean throughout, new packets range-only, existing packets joint. Four cells: no-new/keep-lost=MB; no-new/drop-lost=additional control; add-new/keep-lost=restoration arm; add-new/drop-lost=MM_NEW_RANGE_ONLY. Masks respectively A_B, A_B & A_M, A_B | A_M, A_M. Original MB and MM_NEW_RANGE_ONLY controls must reproduce. Report removal contrasts at both new-packet settings and MSE interaction. Descriptive return-to-MB: absolute RMSE gap <=.02 deg AND signed-bias gap <=.02 deg. Do not claim statistical equivalence or full explanation of the original BB/MB/BM/MM interaction.

Report each condition, group interpretations by route, B0/L2 paired not independent. No bootstrapped significance or linear channel attribution. Save all traces, scores, protocol/input/output hashes, scripts, events and process receipt. End after four stages and report; no implicit commit/push.
