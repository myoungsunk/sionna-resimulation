# P4 Full MAP numerical FAIL: audited fixed-input LUT/rootcause diagnosis

## 범위·출처
- Source P4 model unchanged: `46d679a32f55cae460d9ed35b4bb944bc48cc4ce`. [P4 complete Run 38658117256](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38658117256), [raw evidence 11937707221](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38658117256/artifacts/11937707221), SHA256 `db1bda22f9fdbb56ba95817ea4c02016bba294c35a4c126daca448284a285ec4`.
- 별도 수치 진단 source `d5bd5bce09e848c81539a538ca04e56b5a8bc2cc`, [Run 38659606838](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38659606838), [artifact 11938581489](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38659606838/artifacts/11938581489), ZIP SHA256 `a1506b148234d530fe39b7fa3a9fbc265ed9588f66044b5e633fc3756cc08af0`. Source audit GO, ZIP CRC PASS, 20 fixed inputs saved status/gradient all reproduced. Original R4 solver, `P2_SPEC`, P3 LUT, RF raw, R/Q and acceptance rules **not modified**.
- Initial D4 Run 38659441385 and subsequent Run 38659530376 failed **only after numerical case replay** due to diagnostic report's NumPy scalar JSON serialization; previous failures preserved, audit and output formatting fixed in new commit. Do not retroactively call either PASS.
- This diagnosis is **20 purposively selected examples**: first invalid example of all 14 case×channel groups, several MAX_ITERATIONS and small-gradient controls. It is not a random subsample for estimating a prevalence over all 4,124 failures.

## 1. Total original failure population
Original P4 accepted gate frames 14,186 and 2 MAP initializations = 28,372 MAP model updates.
- MAP accepted and stationary at original `1e−8` gradient: **24,248**, 85.46%.
- MAP `CASE_RESULT_INVALID_NUMERICAL`: **4,124**, 14.54%.
- `LINE_SEARCH_FAILED`: **3,369**.
- `MAX_ITERATIONS`: **755**.
- Stored one-file-per-failure, full prior x/P, raw observations, original solver history, gradient, cost and exact time/pose. Not replaced by EKF or DR state.

## 2. Independent example fixed inputs: all 20 reproduction PASS

| Example | Failing state | terminal gradient∞ | nearest 2° LUT grid boundary | max discrepancy: analytic vs central `s` derivative | max one-sided derivative jump | GN sampled descent |
|---|---|---:|---:|---:|---:|---|
| R2_aA_m0 Full, t=16.0, M4-P | LINE_SEARCH_FAILED | 0.0082904 | 2.70e−11 ° | 0.05051 | 0.10102 | none |
| R2_aA_m0 LoS, t=12.2, M4-P | LINE_SEARCH_FAILED | 0.0165012 | 1.44e−10 ° | 0.05055 | 0.10111 | none |
| R2_aB_m0 Full, t=17.8, M4-P | LINE_SEARCH_FAILED | 0.0644889 | 2.63e−9 ° | 0.08292 | 0.16584 | none |
| R4_aB_m0 Full, t=1.6, M4-P | LINE_SEARCH_FAILED | 0.0563692 | 1.97e−11 ° | 0.17029 | 0.34058 | none |
| R5_aB_m0 LoS, t=10.2, M4-R | LINE_SEARCH_FAILED | 0.00196868 | 1.25e−10 ° | 0.08290 | 0.16580 | none |
| R2_aA_m0 Full, t=129.6, M4-R | MAX_ITERATIONS | 1.76863e−8 | 0.0133 ° | 1.77e−10 | 7.05e−6 | exists |

Entire 20-case summary: **14/20** terminal states within `0.001°` of some `2°` LUT angular knot; **14/20** analytic vs central derivative discrepancy `>1e−3`; **15/20** one-sided derivative jump `>1e−3`; GN sampled full/backtracked descent in **4/20**. Full raw `DIAGNOSTIC_00..19.json` includes knot distances for theta,phi_tx,phi_rx, one-sided derivatives at 1e−4/1e−5/1e−6 coordinate perturbations, and GN candidate grid.

**Interpretation:** The dominant selected line-search failures are strongly associated with reaching a *piecewise-linear LUT interpolation boundary* where the smooth derivative is discontinuous. The original R4 MAP gradient is a derivative of the active LUT cell, not an everywhere-defined gradient at a kink. An endpoint numerical derivative can change abruptly across a boundary. Hence even a correct Gauss–Newton implementation with a strict `||grad||∞≤1e−8` smooth stationarity requirement can fail at a nonsmooth cusp. At such points, relaxing the numeric floating-point cost threshold would NOT resolve the underlying differentiability issue; a smooth local stationary point need not exist at the kink.

**Important limitation:** 6 of 20 sampled failures are not very near an angular knot, usually `MAX_ITERATIONS` with gradients near `1e−8`–`1e−5`. Thus LUT nonsmoothness is **not proven the sole root cause of all 4,124** and must not be used to hide other numerical issues. Some smooth samples exhibit negative cost GN steps but stop at the 80 iteration budget. Additional separate analysis is necessary if numerical closure is required.

## 3. Consequences and next choices (not executed here)

1. **Keep original LUT** and implement a separate nonsmooth-optimization candidate (piecewise trust-region, bundle/local cell-aware search or Clarke stationarity with directional checks), preregister new **nonsmooth** convergence/covariance interpretation. A `KINK_STATIONARY_CANDIDATE` is **not** equivalent to old `CONVERGED` under original smooth `1e−8` gradient contract; do not promote old cases or reuse their RMSE to claim numerical pass.
2. A differentiable periodic interpolation may offer smoother MAP optimization but **changes the RF forward observation model**. If evaluated it requires new P3 h/H parity and science pre-registration; forbidden to silently replace original LUT in this P4.
3. For the 6 sampled smoother/MAX_ITER cases, separate fixed-input slope/curvature/step acceptance and 80-digit cost controls, model pole, and mode comparison; do not assert all failures are LUT kinks.
4. Until an accepted new optimization contract passes independent fixed-input and full RF re-evaluation, use valid Joint/Sequential results as P4 technology comparison; keep all original MAP invalid results and sample-selection caveat.

## Final

- `P4_FIXED_LINEAR_PARITY_PASS=true`.
- `P4_NONLINEAR_ONE_STEP_EVALUATED=true` but `full_MAP_numerical_PASS=false` due to 4,124 original invalid updates.
- `P4_LUT_KINK_CAUSAL_EVIDENCE_STRONG_IN_SAMPLED_LINE_SEARCH_FAILURES`; not a claim of physical RF model correctness or universal root cause.
- `scientific_PASS=false` (RF calibration, independent scene, P5 G3, P6 recursive untouched).
