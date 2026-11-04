# MBVAR-INFO-001 — A010-FREEZE PROPOSER HANDOFF (BLOCKED, NOT FROZEN)

**Date:** 2026-11-03 · **Role:** PROPOSER PRE-FREEZE PREPARATION (not distinct independent AUDITOR)  
**Status:** `FREEZE_NOT_AUTHORIZED / AUDITOR_APPROVAL_PENDING / SOURCE_LOCK_PENDING`  
**Audit base:** [PR #20](https://github.com/myoungsunk/sionna-resimulation/pull/20) head `8590cbc409c9f34d5b87dee9e35181f16532038d` (post-test doc only); tested code source `360b496d089c54aaaa488ff1c2a571605547d96b`.  
**Governance:** `250d617ad89a4105fa1af546cc83ceed9de98f42`.  
**Experiment contract:** `contracts/EXPERIMENT_CONTRACT_MBVAR-INFO-001.md` originally FROZEN for earlier Track S phases, not approval of proposed `AMENDMENT-010.md`.  
**Tracking:** [Issue #22 — independent approval & RT stop gates](https://github.com/myoungsunk/sionna-resimulation/issues/22).

## Final proposer decisions already made — NOT retrospective changes

- **Operational estimator:** retain original `S1V5 E′` with unchanged `batch_map_v2_ms + F2`; `s1v5.py` Git blob `01c84e028ee2326d5127ecdaa62d74fcd697ce54`.
- **Fixed nonoracle diagnostics:** E′ + nine starts, same objective and terminal precision criterion `1e−3 χ²`, at most 30 F2 steps, any cap/bad common probe `UNRESOLVED_PRECISION`.
- **R5 data analysis:** H1=8/H2=2/H3=4/CAL=8/H4=8/H4_REPRO=32, all 62 registered; 4000 field-bootstrap, fixed seed 20261029, no selection/exclusion of ambiguity to rescue a hypothesis; all terminal key/seed/policy SHA checked; complete 4×4 C10/NEES checks.
- **R1–R6 validation:** A18 technical outcome `ACCEPT_WITH_BOUNDARIES` for SMOKE and archived DEV2; [CI #41607204271](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41607204271) 141/141, [62 hypothesis arithmetic #41607204028](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41607204028), [K1/K2 #41606839019](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41606839019). The accepted code is the tested code SHA, not the science result.
- **Synthetic evidence scope:** S1V5 SMOKE 44/132 and C3V5 SMOKE 10/72 → `G5_NUMERIC_REPLAY=FAIL`. Archived K2 near-cost starts = 5, not five distinct minima.

## Mandatory PRE-FREEZE STOP items (all must be signed off)

1. [ ] **Distinct auditor account and independent source/math artifact review:** full A010 science pre-run audit per `ROLE_AUDITOR.md`, not merely A18 code fixes; actual PR GitHub `APPROVE` review linked to exact head. Current count 0. Record `auditor_actor`, `audit_sha`, `independent_session_or_runner`, code reuse/limitations, complete allowed claim boundary.
2. [ ] **Resolve geometry kink classifier** using fixed interpolation pattern-cell distance and its tolerance; if classifier remains `KINK_CLASS_UNCERTAIN`, do NOT adopt any exception or claim of newly certified geometry.
3. [ ] **Final portable numeric thresholds** must be fixed without inspecting DEV3; no post-hoc loosening to make old C3/C3V4 failures pass.
4. [ ] **Immutable A010 main lock:** exact proposer numeric decisions D2/D3/D4/D6/R5, all `code_sha256` including code/tests/audit/scripts, `input_lock_sha256`, source FFD/scene/config & governance SHA, original experiment contract SHA; never use Git blob SHA as file SHA256. The draft-only amendment is not an applied lock.
5. [ ] **Exact registered split and run plan:** `DEV3=20..29`, 3 sensor seeds, 36 batch rowkeys per field × 10 fields = 1080 registered `S1V5` batch rows. `C3V5` registered LH/RV subset per contract. Retain entire old `S_field` with DEV3 as the only prospective addition; HOLDOUT2 remains sealed.
6. [ ] **Signed proposer and auditor append-only record**: source SHA, contract hash and 2 actual distinct approvers; proposed freeze SHA anchored to reviewed commit. Do not change the old draft's history or historical FAIL. `A010_SCIENCE_FROZEN=true` only after all above.
7. [ ] **Post-freeze limited run authorization:** then and only then change `RUN_REQUEST.json` from present P0 forensic request to the explicitly approved DEV3 run, in a new implementation PR. Run the exact field/split set; record complete failed keys and G5 science vs numeric verdict separately; independently audit results before any HOLDOUT2 decision.

**Non-negotiable:** No self-approval by implementation ChatGPT/GitHub author; `ACCEPT_WITH_BOUNDARIES` from a read-only technical audit report is not itself a GitHub `APPROVE` event. Do NOT auto-FROZEN based on CI.

## RT / P3 remains separately blocked

The **Sionna ray-tracing Track R** contract requires its own **signed pre-P3 amendment** locking scene/materials, FFD orientation/source and extractor, direct-path parity tolerance, RF scene-variant splits, runtime throughput, finite numerical budget and **explicit user budget approval** before even a C00 canary. Existing contract's maximum planned canary scope is <=288 unique pose–anchor–scene configurations, **not** automatic authorization to compute 288.

An A010 science freeze alone does not grant permission for RT. Without that separate RT amendment and budget, `P3_RT=NO-GO`. HOLDOUT2 also requires its own approval and cannot be unsealed automatically.

## Unambiguous machine status

```json
{
  "contract_id": "MBVAR-INFO-001",
  "freeze_packet_role": "PROPOSER_PREPARATION_ONLY",
  "proposer_r5_policy": "FINAL_PRE_FREEZE",
  "r5_a18_technical_verdict": "ACCEPT_WITH_BOUNDARIES",
  "formal_github_review_approve_count": 0,
  "independent_auditor_signed": false,
  "all_p0_to_resolve_closed": false,
  "amendment_010_applied_lock": false,
  "a010_science_frozen": false,
  "approved_next_experiment": "NONE",
  "dev3": "NO-GO",
  "holdout2": "NO-GO",
  "p3_rt": "NO-GO"
}
```
