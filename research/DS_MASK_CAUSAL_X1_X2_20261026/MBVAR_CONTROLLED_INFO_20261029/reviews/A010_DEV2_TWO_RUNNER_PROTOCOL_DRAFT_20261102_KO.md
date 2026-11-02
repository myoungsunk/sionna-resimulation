# MBVAR-INFO-001 / A010 — Two-runner archived DEV2 replay pre-run protocol (DRAFT)

**Role IMPLEMENTER / independent auditor NOT SIGNED / no A010 science freeze / no DEV3, HOLDOUT2 or RT.**

## Why this is not an A010 science run

- Replay uses exactly A010-P0 GEN archived canonical source `results/P2_A010P0_GEN_run_41269011836/A010_CANONICAL_INPUTS.zip` (sha256 `316efcc04946197cbb5c10417e3b6bfca3e4e8f5e4d3433535dfbba09b7bb9f3`).
- The allowed scope is existing DEV2 forensic keys **K1 and K2 only**, whose source coordinate and exact input arrays are already known. No additional field draw is permitted.
- Both jobs read source arrays but never redraw z or modify frozen input. Main FROZEN A008/A009/A010-P0 and past C3/C3V4 FAIL are unchanged. The future A010 amendment remains DRAFT.
- Replays compare current **S1V5 estimator + F2 polish** using archived canonical estimator inputs; source Sigma_true is retained exclusively for provenance, NEVER used to choose the non-oracle state.

## Preregistered strict mechanical criteria

| Criterion | Requirement |
|---|---|
| Provenance | Same 40-hex current code SHA, same archived generator MANIFEST SHA256, identical original canonical ZIP SHA256 and complete per-array ledger |
| Runner separation | Distinct GitHub Actions matrix runner jobs and distinct Linux boot IDs; record both. Different CPU **models not required** and not claimed |
| Input | 48 archived arrays hash-matched with original ledger. Both jobs record identical per-case estimator-input dtype+shape+bytes hashes and separate truth-only hashes |
| State | Normalize maximum absolute state differences by D_ref = (0.02m,0.02m,0.25°,0.01°/s); maximum <= 1e-6 |
| Cost | Absolute difference <= 1e-6 chi-squared, including E and polished E' references |
| Full C10 | All 10 upper-triangle elements normalized by natural marginal state SD, relative <= 1e-3; each 4x4 SPD; delta log10 normalized condition <= 1e-3 |
| NEES | Replay `nees4_C10` relative <= 1e-3; score recomputation independently from rotated e and full C10 within 1e-8 relative-scaled |
| Discrete | Same mode label, best start, n_alt_ambiguous, precise near-cost start IDs, class_v31, solver status |
| Coverage | Exactly K1+K2 once each; no missing/duplicate or additional case |
| Enforcement | Fail closed on mismatch, output missing, reused boot ID, wrong source SHA or changed historical contract |

## Interpretation after CI

An overall green job with two runner receipts and an independently downloaded comparison artifact may be recorded as `K1_K2_TWO_RUNNER_TECHNICAL_REPLAY_PASS` only. It **does not** demonstrate DEV3 S1V5/C3V5 full-row replay, statistical calibration, uniqueness of MAP, or H1/H2/H3 support. It is an implementer-designed mechanical cross-runner check, not an independently authored auditor calculation.

## Reviewer handoff and stop

- Require an unrelated auditor/session to inspect raw Actions receipts/logs, locally independently recompute source hashes, 4x4 C10 and NEES, split-overlay contract, old FAIL record retention, and hidden-data nonuse.
- Full A010 FROZEN requires separate proposer + independent auditor sign-off, then separate user-authorized DEV3 run. HOLDOUT2 and physical RT require additional gate approvals.
- If any CI stage fails, mark this prefreeze request `REVISION_REQUIRED` or `BLOCKED_EVIDENCE`; do not relax thresholds after observing output.

**Implementation provenance:** 2026-11-02 handoff base `2bc262715ccf51ae0212af988e5a1973478c8540`.