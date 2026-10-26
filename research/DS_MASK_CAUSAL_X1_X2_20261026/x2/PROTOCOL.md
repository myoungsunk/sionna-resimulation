# X2 preregistered execution protocol

Authorization: user requested X2 after X0a/X1 completion, 2026-10-26. Local isolated outputs only. Preserve X1 and all source/input files. No retraining, R calibration, X3-X8, or robot operation.

Inputs: all 14 X1 traces, archived original sources/inputs and hashes. Use BB and MM (BASE and MU_R_EXDS). Simulate no new controls: regenerate original seed-0 controls and verify their prediction against archived prior. Read actual truth only for offline error attribution, not estimator inference.

X2 prerequisite: frozen linear error replay, not X0a nonlinear identity. For each arm freeze its own accepted K and H from its verified nonlinear trace. Rejected K is zero. Propagation Jacobian F is original transition evaluated at that arm's previous posterior. Define error estimate-minus-truth, truth includes the known constant gyro bias. At each k:

u = z - h(truth) - mu
w = f(truth_previous, control) - truth_current
A = I - K H; T = A F
e_linear[k] = T e_linear[k-1] + A w + K u

At k=0, use actual initial prior error and identity F, w=0. Wrap angle differences in the original local chart. Keep the initial-state and motion-forcing component; do not pretend all Heading error comes from RF.

Gate per condition and arm: correlation >=0.9 AND abs(RMSE_linear/RMSE_actual - 1)<=0.05. Evaluate both full sequence (original time-series criterion) and t>=30s (scoring interval), require both. Zero-variance correlation is undefined and fails, not silently replaced by 1. Need all 28 condition-arm checks to pass before publishing linear channel/packet attribution. Numerical implementation assertions also required. Stop attribution if any gate fails; retain full diagnostics. No changing criteria after seeing outputs.

Independent closure check: add actual nonlinear transition and observation remainders to the linear recurrence; require actual state-error reconstruction atol 1e-9 SI. This is only an algebraic implementation check. The remainders MUST NOT enter the approximation gate or be reassigned to range/polarization contributions.

If gate passes: propagate separate r/s packet injections through frozen T; c[t,j,ch] = heading row of T_t...T_(j+1) K_j[:,ch] u_j,ch. Save exact packet contributions, signed time sums, common/new/lost accepted groups, initial+motion term, and remainder diagnostic. Compare sum and mean normalized cross term 2*sum_t(r_t*s_t) for BB/MM after30. Check packet sum equals independently propagated aggregate channel components. Keep units deg and deg^2 explicit.

Interpretation: own-arm K/H/F differences remain in BB/MM comparison. This is local linear bookkeeping conditional on recorded trajectories, not a causal unique allocation or BASE-common-gain/Shapley result. Do not infer d0-gate C6 from BB/MM only: B_GATE5 is not in X1 trace inputs. No independent-14-scene inference or CI-containing-1 equivalence claims. End after X2 status/report; preserve failed gates as valid findings.
