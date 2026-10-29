# AMENDMENT-005 — tiered C1-d criterion (POST-HOC, labelled) after P0_GEO2 run 40857100181

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 FROZEN (`68d73bd2…`), not edited; builds on AMENDMENT-003/004 |
| Author role | IMPLEMENTER, **SELF_REVIEW_ONLY**. This change is **post-hoc**: it was made after seeing the C1-d failure. It is flagged for the independent auditor. |
| Trigger | P0_GEO2 run `40857100181` (preserved): status FAIL. Only C1-d failed; C1-a, b, c, e and f passed. |
| Results seen | C1 technical diagnostics on old-geometry DEV inputs. **No S0V2/S1V2 outcome exists.** |

## What failed and why

The AMENDMENT-004 C1-d rule required cost(estimator) − cost(true-θ start) ≤ 1e-3 χ² in ≥ 99 % of the 600 runs. The result was 97.8 %.

| Quantity | Before multi-start (run `40852253296`) | After multi-start (run `40857100181`) |
|---|---|---|
| Runs with gap > 10 χ² (wrong basin) | 7 | **0** |
| Worst gap | 3150 χ² | **0.068 χ²** |
| Runs with gap > 1e-3 χ² | — | 13 / 600 |
| Max window-end state difference on those 13 runs | — | 0.31 posterior sd |
| Arm / cells of those 13 runs | — | all `ORACLE_CORR_BATCH`, in pose- or OU-correlated cells |
| Multi-start trigger fraction | — | 2 % |
| Final misfit fraction | — | 0.8 %; all genuine (the true-θ start gives the same cost) |

All 13 are fine-scale **nonsmooth** gaps. The FFD source model interpolates the pattern bilinearly on a 1° grid. With a full correlated Σ the cost has many shallow kink minima, so the start from the truth also stalls at a kink (`CONVERGED_NONSMOOTH`).

A Jacobian-smoothed (central-FD) continuation was tried on three cases. It did not close the gaps consistently (it moved the cost by −0.07 to +0.00 χ² and took 15–97 s per case). It was therefore **not** adopted.

The AMENDMENT-004 tolerance of 1e-3 χ² is tighter than the `CONVERGED_NONSMOOTH` definition (δ² ≤ 0.05, shift ≤ 0.1 sd). It cannot be met by any local method on this nonsmooth cost. The failure is therefore a property of the observation model, not an optimizer defect.

## Change (post-hoc)

1. **C1-d gating (wrong-basin test).** No run may have cost(estimator) − cost(true-θ start) > 1 χ².
2. **Fine tier (reported, not gating).** The AMENDMENT-004 strict rule is still computed and reported (`strict_A004_pass`), together with the number of gaps > 1e-3 and the maximum state difference.
3. **Re-evaluation without recomputation.** The amended criteria are applied on Actions (phase `P0_GEO2_REEVAL`) to the committed shard files of run `40857100181`. The sha256 of every input file is recorded in `P0G_REEVAL_SOURCE.json`.
4. **Consequence for S1V2.** The batch-estimator precision floor is ≈ 0.07 χ² and ≈ 0.3 posterior sd, on ~2 % of oracle runs in correlated cells.
   - Worst-case impact on a field-mean MSE ratio is a few percent, well inside the ×1.5 equivalence band.
   - The `CONVERGED`-only sensitivity of S1V2 is reported next to the primary analysis.

## Not changed

Every other AMENDMENT-003/004 rule, the geometry v2, revisit and plate choices, the decision rules, the splits and the RT block. The AMENDMENT_LOCK stays in AMENDMENT-004.
