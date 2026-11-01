# Exact independent Codex audit handoff — P1

**Run in a NEW Codex session/runner, not the proposer/implementer session.** This file is instructions only, NOT execution evidence or approval.

Pinned repository: `myoungsunk/sionna-resimulation`
PR: https://github.com/myoungsunk/sionna-resimulation/pull/4
Source SHA: `340877f3537b4cc65cdaa9d687423cba92e0b28b`
Contract SHA256: `373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594`
Audit protocol: `research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101/P1_INDEPENDENT_AUDIT_REQUEST_KO.md`.

### Required instructions for external Codex

You act as **independent pre-run AUDITOR**, not proposer/implementer. Begin with git checkout of the exact commit, verify HEAD, then read `AGENTS.md`, `docs/research-governance/COMMON_CONTRACT.md`, `docs/research-governance/ROLE_AUDITOR.md`, and the correct DLP applicability file at `research/DUAL_LP_PAPER_GAP_20261030/GOVERNANCE_APPLICABILITY_KO.md`. Do NOT treat previous self-review, precheck or a GitHub green check as passing evidence.

Independently write your own scratch program; record its exact SHA256, language/packages, process identity, hardware, scratch root and reuse ledger. Independently calculate raw SHA256 for the 39 canonical C0 inputs plus both NPZ bank physical bytes. Git LFS pointer OID or artifact metadata without actual byte validation is insufficient. Verify 7 paired Full/NativeLoS H shapes/dtypes and the P0 historical traces. Bank loader expects `ROOT.parent/BANK_MANIFEST.json`, with NPZ files next to it, and must be staged in an isolated scratch directory with hashes checked before loading.

Recompute real raw H -> Hann with denominator N-1 -> 4N IFFT scaled by N -> strongest RX -> >=30%-first-edge -> SAME tap -> signed s and raw r. Audit random AND adversarial packets; log every missing/invalid/zero-power/crossing case. Verify SourceFFD direct two-port complex spectrum and NativeLoS H/s with exact T06/T07/T08 from locked tolerances; never conceal phase error with posthoc alignment. Independently finite-difference `SourceFFD` J_s for stable FFD cells/taps, mark cell/cap/tap boundary separately. Check the 2x4 H shapes, r derivative, b_g derivative 0, old LUT baseline and source/old signed residual identity, no ground truth at runtime.

Re-derive exact C0 matched 9519 H pose-case pairs PER mode, 7251 timeline case-steps PER mode, 6201 eval t>=30 PER mode, zero silent exclusions. Report all case/anchor/mount/route/channel/distance groups with ddof=1 covariance, determinant/eigen PSD, unit conventions and failure rows. Preserve R4/R5 Mount45 Full-only extension excluded, 2026-10-16 SourceFFD retrospective, one Corridor scene, no new training/heldout claims and no P1 EKF.

Return a machine-readable and Markdown independent report containing: `contract_id,contract_sha256,source_head_sha,input_hashes_verified,math_checks,data_leakage,unreported_exclusions,matched_design_checks,statistical_independence,claim_overreach,required_remediation,allowed_claims,audit_code_sha,audit_sha,auditor_actor,independent_session_or_runner,tool_versions,all_fail_rows` and exactly one of `ACCEPT_WITH_BOUNDARIES / REVISION_REQUIRED / REDESIGN_REQUIRED / BLOCKED_EVIDENCE`. Report numerical outcomes with exact test IDs T00–T15; preserve all fail cases. If any original binary is inaccessible, use BLOCKED_EVIDENCE and do NOT sign ACCEPT.

Do not merge PR, update proposer locked branch, modify main, rewrite contracts, change tolerances, or execute actual P1 science before a separate append-only proposer+auditor FROZEN ratification with unchanged SHA.
