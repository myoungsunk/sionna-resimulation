# AMENDMENT-004 — deployable heading multi-start after C1-d failure (pre-freeze of AMENDMENT-003)

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (sha256 `68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34`), not edited |
| Builds on | AMENDMENT-003 (DRAFT rules, commit `2b273ab`). All AMENDMENT-003 rules stay in force except where changed below. |
| Author role | IMPLEMENTER, **SELF_REVIEW_ONLY** |
| Trigger | AMENDMENT-003 C1 verification: DEV field 3 (local technical run) and P0_GEO2 run `40852253296` (Actions, all 10 DEV fields; status FAIL, preserved) |
| Results seen | C1 diagnostics only, all on old-geometry DEV inputs. **No S0V2/S1V2 noise outcome on the v2 geometry exists.** Geometry v2, revisit and plate choices were computed by the registered §B–§D rules and are not changed here. |

## Finding (C1-d failed)

The v2 optimizer run from the prior mean sometimes converges to a **spurious basin**:

- Example: field 3, HIGH window, sensor seed 1. The initial heading is 1.66 prior sd (8.3°) off truth.
- Result from the prior mean: final cost 2966–5239 χ², against 2N = 120 residuals; window-end error ≈ 1 m.
- The same data started at the true θ reaches cost 58–146 χ² with errors of a few cm.
- Local field-3 tally: 11/60 batch runs had |cost(prior start) − cost(true start)| > 1e-3, 8 of them gross (> 1500 χ²).
- Run `40852253296` (600 runs): 7 gross local minima (truth start better by > 10 χ²), all in the HIGH window. The v1 estimator's final cost exceeded χ²₀.₉₉₉(120) in 2.2 % of runs.
- The same run also showed: v1 vs v2 (free tap) cost gap up to 23.3 χ² (v2 never worse beyond 1e-10); free-tap v2 NONCONVERGED 142/600; tap-conditioned v2 NONCONVERGED 3/600, NONSMOOTH 235/600; iteration cap 100 → 300 changes nothing; near-linear exact-posterior test passes (≤ 3e-5 sd, ≤ 3e-6 relative covariance).

This also applies to the frozen v1 estimator. So **the earlier S1 DEV/HOLDOUT batch results (runs `40844896963`, `40845647224`) can contain gross local-minimum outliers**. Their H1/H3/CAL numbers are kept as recorded but must be read as *conditional on that optimizer*. They are superseded for interpretation by the S1V2 runs.

## Change

1. **Batch estimator `batch_map_v2_ms`** (deployable, no truth):
   - Run `batch_map_v2` from the prior mean.
   - If the final cost > χ²₀.₉₉₉(2N) (Wilson–Hilferty, 173.67 for N = 60), re-run from heading offsets k·sd_ψ(P0), k ∈ {−1, +1, −2, +2, −3, +3}, with v = 0.
   - Keep the minimum-cost solution.
   - Recorded per run: trigger, best k, start-0 cost, number of distinct minima (cost gaps > 1 χ²), final misfit flag.
   - Used by every batch arm of S1V2 (IID, ORACLE, XMODEL) and by C1.
2. **C1-d criterion** (replaces the AMENDMENT-003 wording):
   - Pass if cost(estimator) − cost(true-θ start) ≤ 1e-3 in ≥ 99 % of C1 runs, and never > 10 χ².
   - The deployable estimator must reach a minimum at least as good as the one found from the truth, up to the nonsmooth tolerance.
   - Also reported: trigger fraction, final-misfit fraction, and the v1 misfit fraction (contamination estimate for the old runs).
3. **C1-a criterion.** Bitwise reproduction is not achievable across runner hardware. Run `40852253296` regenerated the stored DEV rows with max absolute difference 2.8e-6 (median ≤ 4e-10); a local machine gave 1.7e-2 on POSE cells. The pose-field `eigh` square root of an ill-conditioned kernel and the free-tap discontinuities amplify floating-point differences.
   - New criterion, evaluated on Actions: for all 1500 rows, |Δe|/sd ≤ 1e-3 and |ΔP|/P ≤ 1e-3, using the stored posterior sd and variance.
   - The fraction of bit-identical rows is reported.
   - For S1V2 this is a reproducibility limitation: realisations are tied to the platform, and their distribution is not.
4. **Manifest.** `independence_unit` for P0_GEO2 = `mathematical_deterministic` (schema enum). The P0_GEO2 run `40852253296` aggregate stopped on this schema error; its shard evidence is preserved.
5. **Lock location.** The AMENDMENT_LOCK covering AMENDMENT-003 + 004 is appended **below in this file**. `RUN_REQUEST.amendments` lists both; AMENDMENT-003 carries rules only.

## Not changed

Geometry v2 objective and choice rule, revisit rule, plate rule, decision rules, splits (HOLDOUT2 5000–5059), RT block.

## AMENDMENT_LOCK

Appended after a P0_GEO2 re-run with this estimator reports `PASS`.
