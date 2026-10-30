# IMPLEMENTER P0 — source/evidence metadata preflight (2026-10-30)

**Status: P0_PARTIAL_METADATA_COMPLETE / P0 NOT PASS / DRAFT CONTRACT / NO SCIENTIFIC RUN.**

- `role=IMPLEMENTER` — `contract_id=DLP-EKF-GAPS-001`
- `governance_git_sha=6c7200091028fd3f0e55aa83b777d0f10b7cf063`
- `source_base_git_sha=6c7200091028fd3f0e55aa83b777d0f10b7cf063`
- `proposer_source_sha=5f0a4ac5259210dca8aa866ed887b7117c080aad`
- `draft_contract_sha256=c7d18db29a2c6ea5a509f93b1f64559428e173c09beb293c0084b07bae480a6d` (draft **not FROZEN**)
- Source: GitHub **metadata API reading only**, not a materialized RF simulator filesystem. Outputs below are append-only evidence files, not RF data, filter code or recalculated results.

## Verified (metadata, NOT numerical/raw payload)

1. EKF3 P0 input manifest has **39** frozen assets. Every path/declared Git blob SHA/declared byte size agrees with the tree at immutable source base **39/39**. This is **not** a fresh SHA-256 digest or tensor alignment test.
2. Historical Snowball H-store register contains **12** FULL H SHA-256 entries for R2/R4/R5, A/B, mount 0/45. **7/7** corresponding canonical C0 Full H SHA-256 strings match exactly; the four R4/R5 mount45 H **generation records**, shapes, reported hashes and historical S6 output CSVs exist. Historical README explicitly says raw H/NPZ **were excluded** from the posted archived package. Recovery/current binary content is unverified; LoS counterpart unknown. Do not claim those four complex H are present or validated in C0.
3. The R2 4-state replay implements DR4/S4/J4/SR4, no scalar range-only 4state arm in its `METHODS`. Prior EKF3 B is **3state one-step**. Prior Sensor-v2 Range-only is **6state full-recursive**, not 4state. Source `rt_cp_uwb_py/localization.py` contains `solve_known_z_wls` for >=3 anchors and **2state known-Z EKF**; it does not establish synchronized third-anchor C0 RF.
4. FFD source P0-P3 report validates a new source `h_s` but retains legacy continuous detector-range bridge. Its full 256-trace runnable ZIP was not deposited under this repository path; cannot treat it as a directly reproducible full-run artifact here.

## Scope of negative search

Read immutable source tree (11,535 entries) and proposal tree, inspected six relevant historical branch trees and source/report files. **Not** a proof of nonexistence across every GitHub branch, GitHub Actions artifact or local archive. For that reason G2, G3 and G4 remain evidence-limited, not definitively MISSING.

## Artifacts

- `P0_SOURCE_LEDGER.csv`: 39 manifest assets + 4 R4/R5 mount45 historical-only H manifests, with metadata-level verification status.
- `P0_DATA_CROSSWALK.csv`: 7 C0 cases + 4 archived mount45 H candidates; time/pose parity correctly `NOT_RUN`.
- `P0_BENCHMARK_INVENTORY.csv`: M0/M1-A/M1-B/M1-C/M2 evidence vs missing definitions.
- `P0_GAP_DECISIONS.json`: G1–G6 states, evidence and next gated action.
- `P0_READ_RECEIPT.json`: source refs, draft SHA-256, read-scope, verification limits.

## STOP / gate

Contract is DRAFT, not independently signed, and science-affecting numeric model/observer/anchor/missing-packet/resource choices remain unresolved. **No new code, RF, replay, numerical estimator output, P1–P4 run, source mutation, independent audit or scientific verdict.** Required before P1: proposer locked source + observer + scalar range mean/R/gate, matched control/f/Q/initial states, numeric tolerances, signed FROZEN contract, and independent pre-run audit. Before P3/P4: verify third-anchor absence, freeze physical geometry/sync/RT budget and obtain user approval.

Status of `P0_INVALID_OR_UNMATCHED.csv`: **NOT_RUN_DATA_PAYLOAD_AUDIT**, not an empty success table; raw/pose checks require an approved data-materialization step.
