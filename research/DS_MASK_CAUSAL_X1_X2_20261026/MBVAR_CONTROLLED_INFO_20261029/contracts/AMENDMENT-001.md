# AMENDMENT-001 — geometry candidate set extension after BLOCKED_GEOMETRY_MATCH (pre-outcome)

| Field | Value |
|---|---|
| Contract | MBVAR-INFO-001 (DRAFT, sha256 `9fc4538c2d1c90e7b26acacfd460255ea9af9dc0bceceeeb3b7926082f974955`) |
| Governance | `250d617ad89a4105fa1af546cc83ceed9de98f42` |
| Trigger | P0_PREFLIGHT run `40840192251` (commit `2f40fbf81250277ef3cd55ed6d5fd9f04befb615`): `BLOCKED_GEOMETRY_MATCH` |
| Author role | PROPOSER role exercised by the implementing session under the user's directive of 2026-10-29 16:54 KST. **SELF_REVIEW_ONLY** — no independent proposer/auditor session. |
| Results seen before change | P0 geometry/source/parity evidence only. **No Track S or Track R response outcome exists** (none has been run). |
| Affected runs | P0_PREFLIGHT only. The blocked run is preserved unchanged. |

## Original rule

PLAN_P0_P6 §F/§K: the candidate set is T1_HORIZONTAL and T4_S_CURVE for anchors A and C. T2/T3 may be added "only if G0 low/high preflight matching requires", defined before examining Track S/R performance.

## Evidence that matching requires it

| Finding (run `40840192251`, `P0_GEOMETRY.csv`) | Value |
|---|---|
| Candidate windows | 8 (N = 60, Δt = 0.5 s) |
| Windows failing the \|h_s\| ≤ 0.7 domain rule | 6 |
| Anchor-C windows failing the domain rule | all 4 (max \|h_s\| 0.89–0.97) |
| Valid windows | 2: A\|T1\|0 (range median 4.80 m), A\|T4\|60 (5.78 m) |
| Range-median difference of the valid pair | 0.98 m > 0.5 m → 0 admissible pairs |

## New rule (added candidates; selection algorithm §K unchanged)

The following candidates are added for **anchor A**. Anchor B stays reserved and unevaluated.

| ID | Definition | Role |
|---|---|---|
| `T2_TANGENT_A_Y7` | Straight pass y = 7.0 m, x = 2 → 10 m, yaw = 0, 0.05 m spacing | Tangential pass at 5 m lateral offset from A; plan T2 |
| `T3_ARC_A_R4266` | CCW arc about A, horizontal radius √(4.80² − 2.2²) = 4.266 m, θ = 10° → 80°, yaw = tangent | Constant-range arc; 3-D range equal to the A\|T1\|0 median; plan T3 |
| `T3_ARC_A_R5345` | Same, radius √(5.78² − 2.2²) = 5.345 m | Constant-range arc; 3-D range equal to the A\|T4\|60 median |

**Why these radii:** they are fixed **only** from the range medians of the windows that were already valid. This creates range-matched alternatives under the existing matching constraint. They use no information, posterior, residual or filter quantity.

**Arcs expected to fail the domain rule:** a pre-check showed the arcs keep the anchor at a fixed ±90° relative bearing and reach \|h_s\| ≈ 0.92–0.93. They are registered anyway so that their exclusion is recorded by the deterministic rule rather than dropped silently.

**What stays unchanged:**
- Window construction: N = 60, Δt = 0.5 s, starts at 0, 60, 120, … within each path.
- The \|h_s\| ≤ 0.7 domain rule.
- The matching tolerances (0.5 m median and IQR).
- The G definition, the max-ΔG choice, and the lexicographic tie rule.

If P0 is still `BLOCKED_GEOMETRY_MATCH` after this amendment, S0/S1 do not start. A further amendment would be required.

## Status after this amendment

P0_PREFLIGHT is re-run under the same DRAFT contract hash with the amended candidate set. The science contract is frozen only after a P0 `PASS`.
