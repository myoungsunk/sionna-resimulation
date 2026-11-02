# MBVAR-INFO-001 — A010 신규 구현자 인수 및 통합 기술검증 보고 (2026-11-02)

**역할 IMPLEMENTER / SELF_REVIEW_ONLY. 독립 감사 서명 아님. A010 SCIENCE_DRAFT. DEV3/HOLDOUT2/RT NO-GO.**

## 1. 재현 가능한 기준

- Base implementation: `research/mbvar-info-a010-s1v5-fix-20261101@9e0686602b612cd9f948e8a2f9f8e9098facd434`.
- Handoff: `handoff/mbvar-info-a010-new-implementer-20261102@3e3bec436a23ef4eed27387234e085e7f4a46b2b`.
- Implementer code HEAD (before this report-only commit): `2e402b066b75d47b2587216ecc04cc182487ba31`.
- New branch: `implement/mbvar-info-a010-d2-d3-d4-d6-20261102`.
- Initial handoff comparison: code and tests identical to baseline; four handoff documents added. No old implementation or evidence branch was overwritten.
- Frozen A008/A009, previous G5 FAIL, C3/C3V4 FAIL, A010-P0 outcomes are preserved. No changes to RUN_REQUEST.json or contract_lock.py.

## 2. What was changed (source of truth: GitHub diff)

| Topic | Implementation | Important limit |
|---|---|---|
| D2 | Field-qualified MAT receipts retained; cross-field delta_max and delta_F <=1e-10; SPD and exact schema | Copying another field's Sigma is forbidden |
| D3 RECEIPT | Per-array dtype, shape, byte SHA sidecar; manifest hash, original ZIP SHA, unique keys, truth-only ledger, optimizer-input SHA | Receipt integrity does not prove generator distribution |
| D3 GENERATOR | Independent K_pose, K_time OU, full Sigma closed-form, canonical 180-pose factor law | Resampled z byte mismatch is diagnostic, not a hard gate |
| D3 P | Full 4x4 end C10: upper 10, SPD eigen, normalized condition, NEES; log10 condition tolerance candidate 1e-3 | Posterior calibration is a distinct scientific test |
| D3 SOLVER | Two-runner verifier for identical canonical input, source/manifest SHA, distinct runner identities, state/cost/C10/class/mode | No independent two-runner proof yet: hard gate remains FAIL |
| D4 | Numeric replay gate allowlist, separate mode identifiability and full-row legacy stability; near-cost candidate paired ΔMSE/ΔP/ΔNEES/logdet | Full scientific H/CAL sensitivity not rerun; release NO-GO |
| D6 | Full S_field snapshot copied, only DEV3 20–29 added in un-applied DRAFT; dispatcher verifies actual FROZEN lock, old split, exact fields and source code SHA | Track-level effective_lock merge unchanged, old HOLDOUT not revived |

## 3. Technical tests and evidentiary scope

- Fast Actions run: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41404670571 — job a010-fast-contract-and-negative-fixtures: 21/21 PASSED, 1 expected duplicate-member warning (head `2e402b066b75d47b2587216ecc04cc182487ba31` is earlier than current tested HEAD; run 41404670571 executed at code commit 2e402b0).
- Initial 20-test CI detected one true zero-row schema bug (19 PASS / 1 FAIL); corrected in a10_validation.py. A later run passed 20/20. This failure is retained in Actions history.
- Baseline inherited SMOKE CI runs 41288826577 and 41290274463 passed 26/26 on the inherited version; not evidence that this modified tree passes.
- Latest new-version integrated S1V5→C3V5 900/901 SMOKE CI was still RUNNING as of report authoring. DO NOT claim integrated PASS without inspecting final run and artifact.
- S1V5 reduced subset expected 44 records, C3V5 reduced 10 records; C3V5 full-row STATUS=FAIL is expected from subset insufficiency even when individual technical checks pass.
- Exact frozen DEV3 field IDs have NOT been executed; HOLDOUT2 and physical RT are unopened.

## 4. Current gate status

| Gate | Pre-freeze status |
|---|---|
| D2 schema/covariance mathematical fixture | 21-test synthetic suite PASS |
| D3 receipt/generator/C10 mathematical fixture | 21-test synthetic suite PASS |
| D6 split preservation fixture | 21-test synthetic suite PASS |
| C3V5 end-to-end reduced SMOKE | PENDING verification of complete Action logs/artifact |
| SOLVER_REPRO two independent runner evidence | NOT VERIFIED / HARD GATE FAIL |
| G5_NUMERIC_REPLAY full DEV3 | NOT RUN / NO-GO |
| G5_MODE_IDENTIFIABILITY and full science | NOT RUN / NO-GO |
| INDEPENDENT_AUDITOR_SIGNED | false |

## 5. Fail-closed scope

- A010 DRAFT cannot authorize DEV3 through run_phase.request even if a text fragment says FROZEN; actual applied amendment, exact 20–29 list, S_field diff, all code SHA must match.
- All original arrays and per-field Sigma are retained independently. No silent dtype conversion, field-matrix merging or estimator truth-start selection.
- STATE_STABILITY_FIXED_LEGACY continues to be evaluated; old FAIL is neither deleted nor retrospectively promoted.
- Reporting MSE/NEES alternative-state sensitivity is conditional diagnostics only, NOT a basis for selecting favorable subsets or science release.
- The design/prototype is not a substituted independent audit. See audit/A010_NEW_IMPLEMENTER_AUDIT_REQUEST_20261102_KO.md.