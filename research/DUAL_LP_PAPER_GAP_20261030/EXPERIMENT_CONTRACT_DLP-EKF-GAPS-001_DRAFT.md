# EXPERIMENT_CONTRACT_DLP-EKF-GAPS-001 — PROPOSER DRAFT, NOT FROZEN
Status: DRAFT-0.1. No authority for science, RT, code, or replay execution.

## Authority
contract_id: DLP-EKF-GAPS-001
role: PROPOSER
base_git_sha: 6c7200091028fd3f0e55aa83b777d0f10b7cf063
governance_reference_sha: 6c7200091028fd3f0e55aa83b777d0f10b7cf063 (MBVAR-only governance used as adopted guidance, not native router)
contract_sha256: P0_TO_RESOLVE_AFTER_REVIEW
input_lock_sha256: P0_TO_RESOLVE
source_sha256: P0_TO_RESOLVE
numeric_config_sha256: P0_TO_RESOLVE
output_root: research/DUAL_LP_PAPER_GAP_20261030/ (DRAFT documents only)
independent_pre_run_auditor: NOT_ASSIGNED
approved_scope: PROPOSER_DOCUMENTATION_ONLY
allowed_experiment_phase: NONE
paper_section_3D: RESERVED, NOT_APPLICABLE
M2_method: RESERVED, NOT_SELECTED

## Core question and estimands
Q1 (data identity): For each published historical table/trace, does it reuse exact C0 RF H, observation extractor and pose/time keys, and which h/F/Q/mean/cov/gate changed? Estimand = evidence-backed lineage status.
Q2 (range-only): Does a full-recursive M1-A 4state [x,y,psi,b_g] output already exist under the same C0 input and f/F/Q as M1-B? Outcome = existence + parity of state/P/status and sample universe; if absent, require proposed rerun (not authorized).
Q3 (multi-anchor): Does a ≥3-anchor measured/simulated synchronized Range packet set exist using C0 identical scene/bank/pose/observer? Separately, does a 4state compatible implementation exist? The known WLS≥3 and 2D EKF utilities are not sufficient evidence of the first.
Q4 (coverage): Do 45° mount R4/R5 same-scene RF arrays exist? Optional/limitation if absent.
Q5 (harmonization): Which legacy LUT-based errors and models change under vetted SourceFFD and fixed range policy? Separate physical input equality from model output equivalence.

For Q2–Q4, positive evidence must include exact file reference, complete hash, shape/keys, executable source and comparable metric provenance. Absence from one directory is not proof of universal absence. Search all connected repo branches and manifest inventories before marking NOT_FOUND_AFTER_SCOPE_SEARCH.

## Data regime and admissible evidence
Primary C0 = one 20×2.4×2.7 m Corridor, existing R2/R4/R5 with 2 available anchors A=(4,0,2.65), B=(10,0,2.65), tag z=.45, 257 bins, TX+45 and dual RX ±45, 7 cases, Full/LoS 9519 pairs. C0 historical data are retrospective developmental evidence, NOT unseen independent validation. Reused RF sample with changed gyro seeds is not a new RF scene.
Multi-anchor A/B observations may be paired only when identical physical pose, timestamp and receiver mount, with hardware simultaneity or declared synchronization; source A and B channels produced in same scene do not imply independently acquired simultaneous clock/packet data. For ≥3 anchors, existing evidence search precedes any new antenna location choice.
Final candidate benchmark controls: M0 DR4; M1-A 1A range-only; M1-B 1A r+s conventional; M1-C >=3A range-only; M2 1A r+s specialized. All 4state, common motion streams, same trajectory/time/initialization, eval t>=30s, seed pairing, B0/L2; optional L0/L1 secondary. Baseline anchor and mode frozen before outcome comparison. Counts/energy/update rates mandatory; no automatic equal-resource claim.

## Controls/alternatives
- Different model h (old 2° LUT vs SourceFFD) — matched and recompute only affected results.
- Different state dimension (3 vs 4 vs 6) — reject direct equality, separate auxiliary controls.
- Different gate and R/noise model — either hold fixed for ablation or label algorithmic compound change.
- Range detector bridge (continuous bias vs tap-based) — not equivalent likelihood.
- Different anchors/sites — data belongs to C0 extension or external, not same frozen C0.
- Different t/window/truth/seed — merge only after exact pair/key audit.
- Cross-anchor covariance and measurement clocks — do not assume independence from single-anchor R0.
- 3-D temporal/spatial effects — RESERVED and outside scope.

## Phase design (all proposed and NOT_RUN)
P0 INVENTORY ONLY: exact source/input/output hash/pose ledger and complete benchmark inventory; code-free read-only audit first, with missing artifacts recorded, not fabricated. An approved later implementer may write verification scripts under a separate frozen contract.
P1 SAME-C0 harmonization CONDITIONAL: reproduce observer/h/H parity; rebuild matched signed error and existing statistics as necessary; preserve historical outputs.
P2 RANGE-ONLY CONDITIONAL: if missing, 4state frozen f/F/Q scalar r replay and full x/P/gate/metrics, both LoS/Full; no new RF.
P3 MULTI-ANCHOR CANARY CONDITIONAL: if missing, propose 3rd anchor geometry in same Corridor and ensure noncollinear horizontal placement, LOS, angle/bank/frame, collision and RF resource policy. Fix beforehand; verify source pattern/direct only, exact timestamps, path counts, H-to-CIR-to-r parity. Budget separately approved.
P4 MULTI-ANCHOR DATA/RUN CONDITIONAL: only with signed canary, RT budget, immutability manifest, generate missing H_FULL/H_LOS same original exact poses, add multi-anchor range observations, run 4state baseline under two fair resource budgets. New branch/extension, never overwrite C0.
P5 INDEPENDENT CHECK: new distinct auditor reconstructs random+adversarial packet end-to-end and full paired metrics, confirms claims restricted to single corridor.
No phase P1-P5 is unlocked by this draft.

## Acceptance/stop
P0 PASS = for every needed result, exact discoverable source hash and key provenance, or logged exhaustive scoped search failure and concrete gap. Numerical tolerances for future parity and simulator physics: P0_TO_RESOLVE before freeze; do not copy unrelated contract tolerances.
P1/P2 canary = original H, tap, z/h, state, P, gate parity vs frozen references; any mismatch STOP with diagnostic preservation. If legacy source observation and SourceFFD disagree, do not silently adjust R.
P3 physical canary: new anchor geometry valid, no collision, correct TX/RX frames, LoS policy and real RT runtime measured, explicit user approval required before bulk jobs. Anchor third position and number are P0_TO_RESOLVE.
P4 benchmark scientific verdict must report no-harm failures and every route/mount/B0/L2 without posthoc tuning; 3-anchor advantage not presumed. Full replay self-gate distinct from offline matched mask.
Unresolved inputs / hashes / source code / incompatible data ⇒ BLOCKED_INPUT. Algorithm not found ⇒ MISSING_IMPLEMENTATION (not missing RF). Scientific criteria undefined ⇒ BLOCKED_CONTRACT. Reviewer unavailable ⇒ AUDIT_PENDING.

## Handoff and freeze
PROPOSER signature: DRAFT_AUTHOR_ONLY, NOT_FREEZE_SIGNED
AUDITOR signature: NOT_ASSIGNED
IMPLEMENTER signature: NOT_ASSIGNED
Amendments: PENDING; new versions append only.
No scientific conclusion/implementation permitted until independent pre-run review and explicit user authorization of named phases. Root protected data/results/MBVAR/POL-XCORR remain untouched.
