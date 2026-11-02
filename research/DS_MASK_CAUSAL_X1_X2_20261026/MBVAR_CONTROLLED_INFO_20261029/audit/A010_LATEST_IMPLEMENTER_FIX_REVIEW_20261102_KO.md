# A010 S1V5/C3V5 최종 구현 교차검토 — 신규 구현자 인수 감사 (2026-11-02)

**Verdict:** `ACCEPT_TECHNICAL_SMOKE_WITH_BOUNDARIES` / `REVISION_REQUIRED_FOR_A010_FREEZE`. 이 문서는 소스/CI/계약 감사이며 **S1V5 DEV3, C3V5 full, HOLDOUT2, 물리 RT를 실행하거나 검증한 기록이 아니다**.

## 감사 출처

- 대상 repo `myoungsunk/sionna-resimulation`; source `research/mbvar-info-a010-s1v5-fix-20261101`, HEAD `9e0686602b612cd9f948e8a2f9f8e9098facd434`.
- 변경 기준 `research/mbvar-info-a010-canonical-smoke-20261101@e16e98dc92d744e98007e75b53ad8b500242668b`.
- 구현자 보고 `reviews/A010_S1V5_C3V5_FIX_HANDOFF_20261101_KO.md`.
- 사전 실패 workflow [41288591968](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288591968): `13 failed/13 passed`.
- 수정 후 workflow [41288826577](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41288826577) 및 [41290274463](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41290274463): `26/26 passed`, no failed job steps. Successful run `f9eb608`의 `s1v5.py`, `c3v5.py`, 새 tests 및 workflow Git blobs는 HEAD와 동일함을 검사.
- 원본 C3 [40992589158](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40992589158) FAIL, C3V4 [41005158792](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41005158792) FAIL.
- A010-P0 four-key forensic input+solver replay [41269011836](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41269011836), [41269246996](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41269246996), separate independent source arithmetic [41277884578](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41277884578). No full 1080-run independent replay.

## 확인된 코드 변경과 한계

| ID | Code check | Finding |
|---|---|---|
| D1 | `s1v5.cmd_run/cmd_aggregate` now call `lock_v5()`; source searches + direct reduced-e2e tests | **Resolved in smoke.** |
| D2(a) | `s1v5.mat_key(f,role,cell,...)`, `c3v5.load_receipts_with_stats` unique + fail-closed field-qualified full Sigma keys | **Resolved mechanically.** Across-fields equivalence is still REPORTED only. |
| D5 | `c3v5.mode_ambiguity(sol)` tests **all truth-free** close-cost alternatives, not only lowest candidate; retains truth exclusion | **Resolved mechanically.** Starts use `FL.batch_map_v2` whereas E' also has probe polish: diagnostic solver-precision fairness remains open. |
| D6 partial | `A010_KP_BYTE_MATCH` reports ULP-dependent Kp values in QA; no false gate | Resolved diagnostic. Split/key merge remains OPEN. |
| D7 | stale labels, handoff counts, code provenance | Corrected main labels; unrelated `Claude-Session` trailer does **not** accurately identify prior implementer session. |

## Material remaining blockers

**B1. D3 receipt tautology.** `c3v5.cmd_run` copies z/x0/controls from receipt and then calls `input_diffs(rec, ... inp ...)`; it will return 0 by construction. Existing `INPUT_REPRO` is a receipt integrity check; generator redraw difference is just `generator_regen_d_z_REPORTED`. The code does check output ZIP hash, but this is neither an independent regeneration of z nor a proof the law/covariances are correct. Need `RECEIPT_INTEGRITY`, `GENERATOR_LAW`, `CROSS_FIELD_COV_EQUIVALENCE` three separate tests and individual array SHA under a frozen new contract.

**B2. D4 silent change.** `STATE_STABILITY_FIXED_REPORTED` is removed from C3V5's automatically selected gating via `"REPORTED" not in k`. This differs from original A008/A009 C3 gate and has not been signed in A010. Preserve original legacy FAIL in side-by-side table and introduce explicit `G5_NUMERIC_REPLAY` vs `G5_MODE_IDENTIFIABILITY` gate IDs; no automatic waiver/claim release.

**B3. D6 split not established.** Current `AMENDMENT-010.md` is DRAFT, `contract_lock.effective_lock` merges `splits` per track with `update`, and lacks an authorized DEV3 split. Adopting per-key merge globally would resurrect the removed old HOLDOUT; only full `S_field` snapshot + DEV3, with deep-equality test, is acceptable under the new proposer decision. Require proper full code SHA and separate independent audit.

**B4. Full covariance scientific validation.** Current C3V5 checks all 10 C10 elements and `NEES4_C10` repeatability, but does not check positive definiteness/eigen condition for each C3 rerun in its gate. `P` numerical reproducibility is not posterior calibration. Explicitly report normalized condition-number and independent field-level NEES confidence intervals.

**B5. Narrow smoke coverage.** The reported 26 PASS includes two SMOKE fields 900/901, selected cells and sensor 0; S1V5 44 rows, C3V5 only 10 rows. `C3V5_STATUS=FAIL` with rows 10/72 was correctly anticipated. Same-runner S1V5→C3V5 does not establish two-runner reproducibility of the new code. All 10 DEV3 fields and ~1080 batch cases not yet run. A separate two-runner forensic replay, then 10-field pre-registered plan, still required.

**B6. Scientific mismatch unchanged.** Existing S1V4 DEV2 H1 LOW/POSE_HIGH tan claim variance inflation 3.72 vs S0 target 8.91; H2 tangent DID −0.988 vs S0 +0.435. This cannot be cured by relabeling technical gates and is not evidence of physical RT efficacy.

**B7. Audit separation.** Implementer `SELF_REVIEW_ONLY` cannot be auditor. This present proposer+review session also cannot confer final independent science release; distinct audit actor/session must confirm the completed A010 change and mathematical/causal boundaries.

## Proposer decisions applied prospectively

See `reviews/PROPOSER_A010_D2_D3_D4_D6_DECISIONS_20261102_KO.md` for binding **DRAFT** instructions:
- D2(a) field-qualified MAT accepted; field-to-field covariance numerical equivalence must be checked.
- D3 rename/segment receipt integrity vs generator-law vs full covariance; verify all complete matrix entries and conditioning.
- D4 dual verdict technical reproducibility vs scientific mode identifiability, all original strict findings preserved.
- D6 original `splits` track replace unchanged, entire existing `S_field` plus DEV3 appended, never global deep-merge.
- Existing FROZEN A008/A009/A010-P0 unchanged; A010 main still **DRAFT**. DEV3 20–29/HOLDOUT2/RT remain NO-GO.

## Inference limitations & disclosure

The exposed first three HOLDOUT2/reserve field IDs in the previous developer console are **not outcome leakage** if the user report is accurate that no held-out z/truth/performance was created/read, but the episode must remain logged. The inaccurate prior `Claude-Session` trailer must not be repeated as evidence of the new implementing actor. Existing unrelated `powerjoint-separate-rs-model-validation.yml` failure is not evidence of the MBVAR smoke failing; investigate separately if global CI is a merge requirement.

**This is an independently authored source-review memorandum, not a separately authorized auditor signature or a full numerical rerun. Verdict: `REVISION_REQUIRED` for A010 science freeze, while accepting the 26/26 technical smoke for its exact tested scope.**
