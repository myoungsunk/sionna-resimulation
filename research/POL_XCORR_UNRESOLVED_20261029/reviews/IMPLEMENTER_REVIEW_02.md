# POL-XCORR-001 — IMPLEMENTER_REVIEW_02 (P0V3_DELTA_PREFLIGHT_ONLY)

| Field | Value |
|---|---|
| Role | IMPLEMENTER (this is not an audit; R-10 independent auditor still required) |
| Contract | POL-XCORR-001 **v0.3 DRAFT** (sha256 `39c396c7…cb76e`), FROZEN prohibited |
| Base / governance SHA | `250d617ad89a4105fa1af546cc83ceed9de98f42` / `d5f84d9d04d28d465f3357e9299352eb184e6bfc` |
| Branch | `research/pol-xcorr-p0v3-implementer-20261029`, from proposer HEAD `cd6e7e43` |
| Governing run | Actions **40882345773**, execution SHA `4d2c18078732146de9019b9af761a6a98ddaf84e`, `results_p0_v03/run_40882345773/`, MANIFEST sha256 `ab90fff9…adbb` |
| Earlier run (preserved) | 40881680379 at `2736419`. Identical computation, result `TECHNICAL_QA_ONLY`. The job went red only because the workflow's status printer lacked `export OUT`. Fixed in `4d2c180`. |
| Result | **TECHNICAL_QA_ONLY**. Scientific verdict NOT_ISSUED. S0/P1/P2/P3 BLOCKED. No label or metric join. |

## Checks (run 40882345773)

| Check | Class | Status | Observation |
|---|---|---|---|
| v0.2 files immutable (contract, spec, INPUT_LOCK_v2, PLAN_v0.2) | CORE | PASS | recorded hashes unchanged |
| v0.3 doc/source/workflow sha256 recorded | CORE | PASS | 11 files in `MANIFEST.v03_document_and_source_sha256`; no v0.2 hash reused |
| Input core sha256 / T4 trace set | CORE / T4 | PASS / PASS | 925 + 925 trace files hash-match (full checkout); T4 science stays blocked by R-01 re-synthesis |
| R-05 pose join | CORE | PASS | 9519 poses, 7251 timeline |
| **R-04 tap / branch / valid exact** | CORE | **PASS** | 19038 records (7 cases × Full/LoS, tx 0): tap 0, branch 0, valid_g5 vs `features.valid` 0, valid_fp vs v0.2 observer flag 0, common-tap s_fp/log_fp_power 0 mismatches |
| R-04 common-tap discrimination | info | — | per-port leading-edge taps differ in 9252 records; there a per-port extraction would change s in all 9252, yet `features.s_fp` equals the common-tap value in every record |
| R-04 validity semantics | info | — | 0 historical records with valid_fp ∧ ¬valid_g5; the edge fixture (tap 995 > 948) proves the definitions differ, so their equality is **not** asserted |
| **R-14 math identities** | CORE | **PASS** | q_W = 4u(1−u)ε_ρ: max rel 5.6e-16 (tol 1e-10); ε_ρ = 1 − coherence²: 1.1e-16 (tol 1e-12, implementer-declared before the run); u inverse: 3.2e-14 (tol 1e-9) on 9510 rows. 9 rows skipped by the pre-declared conditioning rule (ε ≥ 1e-6, 1 − q/ε ≥ 1e-6). |
| **R-14 counts (audit guard)** | CORE | **PASS** | 9519 valid, 3492 weak; TIMELINE 3105/7251. Per case (timeline): R2–A 54.2 %, R2–A m45 1.0 %, R2–B 55.7 %, R4–A 8.9 %, R4–B 8.5 %, R5–A 66.6 %, R5–B 67.0 %, equal to the auditor's values |
| R-14 reconciliation with P0 `LOS_FLOOR.csv` (run 40867521966) | CORE | PASS | one-to-one; status identical; q max diff 9.6e-16, ε max diff 1.3e-15 |
| R-02 / R-12 / R-13a lineage (hardened comparison) | CORE | PASS | 1.1e-16 / 1.8e-15 / 7.1e-15; table sha256 match |
| R-13b lineage (artifact 39376076166) | SUPPL. | PASS | 19038 × 17, 7.1e-15, artifact sha `6a69a36a…`. **Not** an independent replicate of R-13a (shared upstream). |
| Negative fixtures | CORE | PASS | 24 fixtures; 23 behave as specified, and the 24th (`…_OLD_compare_reference`) intentionally documents the v0.2 defect. They are: tap offset, branch swap, valid flip, RX-port swap, tap+80 edge; tiny one-port, balanced, rank-1, 0/0, NaN, inf, negative det, four window boundaries; reference NaN pattern, inf vs finite, absent key, duplicate key, swapped port. Each deliberately false input fails its specific test. |
| Label isolation | CORE | PASS | every tabular read via `usecols`, logged; no label-pattern column loaded (`tabular_reads` in STATUS) |

## Code review of the v0.2 proposer execution patch (e999f82)

1. **Defect, confirmed by fixture.** `compare_reference` excludes ±inf from the finite difference and never compares inf patterns, so `inf` vs a finite value passes silently. Fixture `ref_inf_vs_finite_OLD_compare_reference` reproduces this. It did not affect run 40867521966: no inf exists in any compared column, and v3 finds the same PASS. `compare_reference_v3` adds explicit inf-pattern, duplicate-key and missing-column checks.
2. **v0.2 R-04 was not a parity test.** `R04_COMMON_TAP` was hard-coded `PASS`; only s_fp closeness was implicitly checked, which the handoff forbids. v3 replaces it with exact array equality on tap, branch and both validity definitions.
3. In v0.2, duplicate keys raised a pandas `MergeError` that surfaced as `UNHANDLED` (CORE_FAIL). The outcome was correct but not explicit. v3 reports `duplicate_keys`.
4. `coherency` validity order and the rounding-only determinant clamp (≥ −1e-12·tr²) are preserved. Large negative determinants are flagged, not clipped (fixture).

## Files

- **Added:** `scripts/p0v3_preflight.py`, `.github/workflows/pol-xcorr-p0v3-preflight.yml`, `results_p0_v03/run_40881680379/`, `results_p0_v03/run_40882345773/` (bot), this review.
- **Preserved, unmodified:** every v0.1/v0.2 contract, spec, config and checklist file; `scripts/p0_preflight.py` (imported read-only for `sha`, `verify_hashes`, `align_poses`, `load_source`, `independent_observer`); `results_p0/run_40867063352/`, `results_p0/run_40867521966/`; all raw H, SAMPLES, timelines, references.
- **F-16 (R-13b expiry 2026-11-19):** `R13B_REFERENCE_PROJECTION_KEYS_G5.csv.gz` (sha256 `806ba7cc…6de7`) archives the label-free key + G5 projection of the artifact, together with the source artifact sha. Labels were never loaded. The original artifact bytes are not archived (out of P0 label-free scope).

## Not done (outside this handoff's first-implementation scope)

- F-11 label-free q-only power simulation.
- F-08 F2 physics/slope derivation (auditor task).
- R-01 trace re-synthesis (T4 stays blocked).

## Claim boundary and next step

- `TECHNICAL_QA_ONLY` means the stored pipeline reproduces itself and the new R-04/R-14 definitions are implemented as specified. It is **not** an independent audit and **not** a science result.
- `WEAK_PORT` is a diagnostic flag only. No row is excluded and no threshold was chosen from labels.
- Next: R-10 independent auditor session recomputes raw H → Hann → 4N IFFT → tap/branch/valid → 7-tap J → q/ε/u on random and adversarial keys with a separate implementation, and signs. Only then may the proposer consider the v0.3 freeze.
- Re-run command: push to `research/pol-xcorr-p0v3-implementer-20261029` touching `scripts/p0v3_preflight.py`, or `workflow_dispatch` on `pol-xcorr-p0v3-preflight.yml`.
