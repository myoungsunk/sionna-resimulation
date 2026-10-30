# Proposed implementation/audit handoff — DLP-EKF-GAPS-001
Status: NOT_RELEASED_FOR_EXECUTION. No commands in this file were run.

## Implementer start header template (not authorized now)
role=IMPLEMENTER
contract_id=DLP-EKF-GAPS-001
base_git_sha=6c7200091028fd3f0e55aa83b777d0f10b7cf063
governance_reference_sha=6c7200091028fd3f0e55aa83b777d0f10b7cf063
frozen_contract_sha256=P0_TO_RESOLVE
phase=P0_INVENTORY_ONLY (only after separate approval)
output_root=<new append-only path>
artifact/source/input hashes=<locked IDs from P0>
All DRAFT contractual references must be resolved before science/replay/RT.

## Suggested implementer order AFTER approval
1. Read root AGENTS, governance applicability, common contract and role files, DLP contract and science spec, source manifest, previous controls.
2. Materialize exact original C0 input (do not write to raw): test 7 cases × paired LoS/Full. Inspect H frequency, frames, timestamp/pose_id and per-arm mount/anchor.
3. Search *all* accessible repository branches/release manifests, previous workflow artifacts for 4state R-only full-recursive and ≥3 Anchor synchronized range; classify EVIDENCE_FOUND/PARTIAL/NOT_FOUND_AFTER_SCOPED_SEARCH and note search coverage/expiry.
4. Crosswalk observation and source versions (old LUT vs SourceFFD), Q/seed/gate/full-vs-one-step, same-key matched subsets. Produce schema-only first, never auto rerun.
5. Report exact missing data and STOP. Every run-specific follow-on requires proposer amendment and auditor review.
6. If approved P1/P2: same C0 re-analysis or 4state range-only replay with original full x/P/gate parity.
7. If approved P3/P4: same scene additional anchor canary, signed computational budget; only then full RF and 4state range-only >=3A comparator.

## Required future output files
P0_SOURCE_LEDGER.csv: file, ref, git/blob SHA, SHA256, status, source role
P0_DATA_CROSSWALK.csv: source, case_id, route_id, anchor_id, mount, pose_id, t_s, H hash, observer, model_h, model_FQ, R, gate, seed, eval population, status
P0_BENCHMARK_INVENTORY.csv: M0/M1-A/M1-B/M1-C/M2, source+data present?, full state/P?, n anchors?, method dimension, missing reason
P0_GAP_DECISIONS.json: evidence-backed gap statuses and shortest remediation
P0_INVALID_OR_UNMATCHED.csv: missing/silent invalid rows, time mismatches, crossings
P0_READ_RECEIPT.json: unchanged prior source hashes; commands; reader; environment
P2_RANGE_ONLY_*: only after approved phase, full X/P/innovation/status/metrics
P3_ANCHOR_CANARY_*: only after approved phase, physical source/scene/version/geometry hash and measured compute cost
P4_MULTI_ANCHOR_*: only after approved phase, matched packets and self-gated recursive outputs
Every output accompanied by MANIFEST.json and SHA256 receipt; absence explicitly NOT_RUN rather than empty success.

## Auditor independent contract (not performed)
- separate actor/session, own source calculation path; no mere reuse of implementer helper
- check original input/bank SHA, axes/units/pose keys, source families and 3anchor actual measurements
- independent one-step 4state gaussian calculation and random/adversarial end-to-end H→CIR→r/s→EKF
- exact same motion/noise/initial settings and correct mask/gate selection
- verify single-scene independent-unit limitation and resource budgets; no results selected posthoc
- verify rejected/missing data recorded; no benchmark claim before audit
- report one of ACCEPT_WITH_BOUNDARIES/REVISION_REQUIRED/REDESIGN_REQUIRED/BLOCKED_EVIDENCE with independent ID and raw evidence.
Current independent verdict: NOT_RUN.

## Strict stop boundary for current user request
Preparing and storing these documents is allowed. No executable implementations, input copies, reference data materialization, RT cost, replay, test, independent signoff, or freeze.
