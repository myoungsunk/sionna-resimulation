# INDEPENDENT_AUDIT — <contract-id>/<run-id>

Status: `PENDING` until independent calculation actually run.

## Identity / independence

- auditor actor/session:
- implementer actor/session:
- shared code/helpers:
- independent executable/calculation:
- full governance commit:
- contract sha256:
- code/run/input/scene/pose/output SHAs:

## Pre-run design correctness

| Test | Expected | Recomputed observed | PASS/FAIL/BLOCKED | Evidence |
|---|---|---|---|---|
| Exact same/opp 1-state information | 0.52631578947 / 10 at rho=.9 | | | |
| PSD, units, state ordering | all valid | | | |
| Fixed-H/Σ arms independent | match declared | | | |
| Train/cal/test disjoint | no overlap | | | |
| Frozen prereg after exploratory pilot | protocol locked | | | |

## Run correctness

| Test | Expected | Independent recomputation | Result | Ref |
|---|---|---|---|---|
| Baseline full-state/P parity | ≤1e−10 or approved bound | | | |
| Exact pose revisit (spatial component) | equality | | | |
| r/s channel extraction & tap identity | source semantics | | | |
| Σ diagonal matching / PSD | prescribed tests | | | |
| Q-aware full information and Schur | independent path | | | |
| Scene-level grouping & uncertainty | independent units | | | |
| Failure/invalid observations retained | zero silent drop | | | |
| Raw RF ref/hash alignment | all verified | | | |

## Scientific claims

- Supported exactly:
- Rejected exactly:
- Mixed or unresolved:
- Alternative explanations:
- Inadmissible extrapolations:

## Verdict

Select exactly one: `ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, `BLOCKED_EVIDENCE`.

- Rationale with evidence:
- Blocking defects and owners:
- Permitted claim-register promotions:
- Independent auditor signature/date:
