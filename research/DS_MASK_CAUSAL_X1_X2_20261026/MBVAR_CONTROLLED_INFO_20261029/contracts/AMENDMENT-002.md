# AMENDMENT-002 — h-differentiability rule for geometry windows (pre-freeze, pre-outcome)

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 (DRAFT, sha256 `9fc4538c2d1c90e7b26acacfd460255ea9af9dc0bceceeeb3b7926082f974955`; not yet frozen) |
| Governance | `250d617ad89a4105fa1af546cc83ceed9de98f42` |
| Trigger | The implementer's S0 self-check (independent information-form path, `audit/audit_s0_independent.py`) compared the analytic FFD Jacobian with a central finite difference on the P0 run `40840770105` choice. |
| Author role | PROPOSER role exercised by the implementing session under the user's directive of 2026-10-29. **SELF_REVIEW_ONLY**. |
| Results seen before change | P0 geometry evidence. A local technical smoke of S0 was run; only its PASS/FAIL status was read. Its predictions were not inspected and nothing was used to choose this rule. **No S1 (noise Monte-Carlo) or Track R outcome exists.** |
| Affected runs | P0_PREFLIGHT. Run `40840770105` is preserved unchanged. Its geometry choice is superseded and never used for S0/S1. |

## Finding

The window chosen by P0 run `40840770105` as LOW, `A|T3_ARC_A_R5345|60`, is a CCW arc about anchor A with yaw equal to the tangent. As a result, the anchor sits at relative bearing **exactly +90.0° at every pose**, which is a grid node of the FFD pattern bank. At that node the pattern interpolation has a kink:

| Quantity at pose 0 of that window | Value |
|---|---|
| ∂h_s/∂ψ, left side (finite difference) | −0.185 |
| ∂h_s/∂ψ, right side (analytic H) | −0.207 |
| FD-vs-analytic deviation, poses affected | 60 / 60 |
| Max deviation | 6.2 % of max\|H\| |
| FD noise floor on smooth windows | ~1e-8 |

The linear-Gaussian S0 premise needs one well-defined H per pose, so S0 is not valid on that window. It is a measure-zero accident of the geometry, but it covers the whole window. S1 estimators would cross the kink on both sides, which adds a linearisation confound the contract lists as a competing explanation.

Generic straight or curved paths cross a grid node at isolated poses only (0–1 of 60 in every other candidate window).

## New rule (added to PLAN_P0_P6 §K validity; selection algorithm otherwise unchanged)

- A pose is **non-differentiable** if the central-FD Jacobian deviates from the analytic Jacobian by more than `1e-4 × max|H|` of the window. The FD step is `1e-5` in every state.
- A window is **invalid** (`H_NONSMOOTH`) if more than **5 %** of its poses are non-differentiable.
- Isolated kink poses in valid windows are reported (`n_kink_poses`) and listed as a limitation.
- The \|h_s\| ≤ 0.7 domain rule, the matching tolerances, the G definition, the max-ΔG choice and the lexicographic tie rule are unchanged.

P0_PREFLIGHT is re-run under the same DRAFT contract hash. The science contract is frozen only after that run reports `PASS`.
