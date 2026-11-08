# FP-NATIVE-B-CAUSAL-REPAIR-20261108

Role: IMPLEMENTER / SELF_CHECK_ONLY. Base commit: `89e582703fd9332315664db1afab6fea172f5c16`.
User authorized input acquisition repair, audit corrections, baseline reproduction, then Actions execution.
Repository governance is explicitly MBVAR-INFO-scoped; this package uses the local common/implementer contract hashes recorded in LOCAL_VALIDATION.json. This is not an independent audit or scientific adoption.

## Frozen and amended scope

Original six NPZ, two FFD banks, SourceFFD model, B detector, P radius 0.075 m, K1/K2, Q, controls, initial state/covariance and archived evidence remain unchanged. No RF regeneration. All analysis remains retrospective in the exposed Corridor seed10 sample (R2 979, R4 742, R5 1415).

This amendment was written after the prior results and failed input acquisition were known. The added calibration contrasts are exploratory, not preregistered, fitted, or independently validated detector calibration.

## Audit dispositions

| Finding | Repair / boundary |
|---|---|
| LFS timeout and no alternate NPZ path | Eight Release assets have pinned SHA/size in RELEASE_INPUT_LOCK.json. Acquire into disposable cache; stream, bounded retry, stop nonzero on failure, record failure. No fallback to regeneration. |
| FFD artifact expiration | Preserve original banks as Release assets; same SHA as SOURCE_LOCK.json. No artifact service dependency. |
| One-step K=0 on rejected samples | Preserve actual conditional K effect and separately reconstruct hypothetical all-sample gain from native prior/H/Reff. Record accepted/rejected strata and label potential effects counterfactual. |
| Missing fixed-gate pooled analysis | Include NN in fixed-mask set; sample-weighted MSE and interactions for all four arms under natural and fixed masks. Natural-minus-fixed is a coupled mask/state intervention, not a uniquely identified gate-only effect. |
| Legacy mu/R applied to B | Primary `frozen` estimand is detector substitution in the existing calibrated system. Also run `zero_mean` (muMB=muBASE=0) and `zero_mean_common_R` (zero means, time-constant common base covariance equal to mean archived R within each route). This uses no evaluator truth. Q and original distance-dependent MB variance law remain. These contrasts assess calibration dependence; they do NOT supply B-specific recalibration or prove detector-intrinsic performance. Independent calibration data remain required for that claim. |
| Partial staging cannot be retried | Verified existing destination is reused; mismatched destination fails closed. Partial copies are atomically promoted after SHA check. Run staging twice in CI. |
| Missing detailed traces/checkpoints | Each completed causal arm has atomic input/source-signature checkpoint with every original replay field. Natural/fixed output retains prior, Pprior, h, H, mu, Reff, nu, S, K, masks, observations, time and pose IDs. K replay saves per-route traces/partial metrics. Causal `--resume` only permits identical code/inputs/incomplete run; completed results immutable. Unfinished arm restarts from its beginning. |
| Additional missing archive fields | Input archive lacks trace_x/trace_P. Reconstruct posterior from stored prior, gain, H and Reff using Joseph equation, then compare state/covariance; do not access nonexistent fields. |
| Packed/executed source drift | Execute checked-out Python files directly. Retain old analysis_package.tar.xz as historical evidence; it is no longer executed. |

## Gates and metrics

1. Release SHA validation and original source-lock staging (11 inputs: 6 NPZ + 3 candidate archives + 2 banks).
2. Targeted tests and original synthetic checks.
3. R2 then R4/R5 native and B recursive baseline parity. Relative-scaled max tolerance fixed at 1e-10; masks exact. No evaluator truth in this gate. Independently reconstruct archived native posterior; B against archived R45 trace.
4. Stored comparison and original B/DROP/K1_R/K2_R/K1_RS/K2_RS replay parity, unchanged 7.5 cm.
5. NN/BN/NB/BB in natural/fixed gates for each calibration regime. Evaluator truth read only after recursion per route. Heading uses wrapped angle; XY norm squared; pool MSE by n, then square root. Record 3D NEES (no invented gyro truth).

Per-run source hash file, checkout SHA, input receipts, baseline checkpoints, full traces, contracts, failures and output SHA are uploaded even on failure. Baseline artifacts are uploaded before full experiments. CI green means execution/self-check passed, not independent audit or adoption.

## Local validation before dispatch

See LOCAL_VALIDATION.json: all-route native/B baseline parity, max normalized discrepancy 1.7653e-14; targeted negative/positive tests; real R2 four-arm natural/fixed smoke; 11-file staging repeat. Local NumPy/SciPy versions differ from pinned CI; CI repeats parity and must fail before downstream calculations if platform drift exceeds the frozen threshold.
