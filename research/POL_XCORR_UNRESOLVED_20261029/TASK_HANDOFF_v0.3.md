# TASK_HANDOFF_v0.3 — next IMPLEMENTER run after P0 decision (NOT FROZEN)

## Context / immutable authority

- Role=IMPLEMENTER, contract_id=POL-XCORR-001, phase=P0V3_DELTA_PREFLIGHT_ONLY.
- Base data/source git SHA (unchanged): \`250d617ad89a4105fa1af546cc83ceed9de98f42\`.
- **Governance router commit:** \`d5f84d9d04d28d465f3357e9299352eb184e6bfc\`. Do not substitute moving branch HEAD for this pinned governance SHA.
- Historic P0 successful workflow source SHA: \`0574d26f4d71ec11b455d80374e4b6683b9f9f36\`, run \`40867521966\`. Source code was patched by prior proposer; have implementer review those patches.
- Existing v0.2 draft contract SHA256: \`468249a7b32c9699c20a3227fc0241eef3ab92773d00bc52a981a32cf6e56ddb\`.
- New **DRAFT** files to use: \`contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.3.md\`, \`SCIENCE_SPEC_v0.3.md\`, \`config/PLAN_PARAMETERS_v0.3.json\`, \`reviews/PROPOSER_DECISION_03.md\`.
- All v0.1/v0.2 plans, \`results_p0/run_40867063352/\`, \`results_p0/run_40867521966/\` and historical raw/input/reference files MUST remain immutable.
- Freeze fields: calculate actual SHA256 of all new v0.3 documents and new source/workflow files, record role, output root, base and governance SHA. Do NOT reuse v0.2 hardcoded EXPECTED hashes for v0.3 silently.
- Until proposer **and independent AUDITOR** approve the new v0.3 contract: **NO S0, P1, P2, P3; no label/metric join**.

## Task R-04: per-packet original observer index parity, CORE

\`research/PHYSICS_RS_STAGED_20261015/code/features.py::extract()\` already exports \`tap\`, \`branch\`, \`valid\`. The P0 independent observer returns \`(cir,tap,branch,s_fp,logp,valid)\`.

For each of seven cases × Full and LoS channel = 19038 records:
1. Use locked 257-bin H and SAME tx index 0. Reproduce the common stronger-port 30% first-path index.
2. Assert **array equality**, without tolerance, for \`tap_independent == tap_features\`, \`branch_independent == branch_features\`, \`valid_independent == valid_features\`.
3. Also verify both RX port powers are extracted at the exact single common tap, not separately selected port taps.
4. Report per-case/channel mismatched counts, first 20 adversarial keys if any. Zero total mismatches is CORE PASS. Never infer tap identity only from scalar s_fp/log-power closeness.
5. Negative tests: deliberately offset a tap in one record; swap selected branch; change valid flag; change RX port order while holding reference fixed. Every fixture MUST fail parity.

Output: \`P0V3_TAP_BRANCH_PARITY.csv\` + negative-fixture JSON.

## Task R-14: independent weak-port calculation, LoS only in P0

Use ONLY LoS H in P0 (Full M1 metrics and all Full/LoS label relations remain prohibited until FROZEN).

For each of the 9519 LoS (case,pose_id):
1. Build the ORIGINAL 7-tap coherency from \`n0+[-2,4]\`, preserving the existing validity and determinant-PSD logic.
2. Define \(a=\Re J_{11},b=\Re J_{22},t=a+b,d=ab-|J_{12}|^2\). If invalid, emit \`INVALID_WINDOW\` / \`NULL_PORT\` / \`NONFINITE\` / \`NEGATIVE_DET\` *without clipping large invalids*.
3. For finite valid \(a,b>0,t>0,d>=0\): \`u=min(a,b)/t\`; \`weak_port = (u<0.05)\`; \`q_W=4*d/t^2\`; \`epsilon_rho=d/(a*b)\`; additional direct \`coherence_sq=|J12|^2/(a*b)\`.
4. Assert \`q_W \approx 4*u*(1-u)*epsilon_rho\` at numerical tolerance recorded **before this run**, and \`epsilon_rho \approx 1-coherence_sq\`; if \`epsilon_rho\` not near zero, compare direct \`u\` to inverse from \`q_W/epsilon_rho\`.
5. \`WEAK_PORT\` is a **boolean diagnostic flag, not an invalid status and not an exclusion mask**. Every valid row remains in the label-free summary. \`q_W\` and \`epsilon_rho\` values are retained.
6. Per case × TIMELINE drive/turn / STATIC_YAW_SWEEP report \`n_total, n_valid, n_weak, fraction_weak\`, and all/weak/strong q_W and epsilon quantiles. Expected P0 reference as audit guard: 9519 valid, 3492 weak overall; TIMELINE 3105/7251; exact counts must be reconciled using the same math and source input.
7. Negative fixtures: tiny nonzero one-port energy, balanced two-port, rank1 Jones, 0/0 null port, NaN/inf, a significantly negative determinant and 7-tap window at boundary. All invalid rows must be flagged rather than silently corrected.

Output: \`P0V3_LOS_PORT_BALANCE.csv\`, \`P0V3_WEAK_PORT_SUMMARY.csv\`, \`P0V3_R14_MATH_QA.json\`. Label-free only.

## Task R-12/R-13: preserve existing PASS and reference lineage

- \`P0_REFERENCES_v0.2.json\` is valid. R-02/R-12 reference: HP_PACKETS sha256 \`c45a14c82816ba40bad74f77b0c8c93df14533eeb70f82329bada691418dcfbe\`; R-13a UM sha \`3e590d4ec4d5ad991b845dd6aad33e1756a95264595d788b0608398fa1ea000c\`; R-13b artifact sha \`6a69a36ad0f521e33a130a1bc1fbde5a4b7aae17ba62ec347ccc611fdd5c6fe4\`.
- Preserve key coverage and same values; don't call R-13a and b independent science replicates (they share upstream).
- Code review the proposer-provided \`compare_reference\` and \`reference_parity\` functions. New negative fixtures must cause FAIL on NaN pattern, \`inf\` vs finite, an absent key, a duplicate key, and swapped port mapping. Only reference keys + G5 columns may load; labels must not be imported.
- R-13b historical artifact expires 2026-11-19; preserve provenance and available legally permitted archived evidence before expiry.

## R-14 changes to *future science* (do not execute before freeze)

- Primary M0 = G5 + abs(ds1); primary E1 = M0 + q_W vs M0 (all valid timeline keys).
- M1b epsilon_rho is **secondary** only; E1c (M0+q+eps vs M0+q) all-valid and paired strong-only contrasts.
- On optional strong-only analysis, both baseline and new arm must evaluate on the SAME keys. Per-case weak rates from LoS range from 1.0% to 67.0%, so masking one arm only or silently dropping weak rows is scientifically invalid.
- If a secondary epsilon feature is deliberately missing, apply an imputer trained on training routes only and add explicit missingness indicator; no test data is used to learn threshold/imputation.
- E1b replacement, E2 and E4 now use M0+[q_W] as base. Retain original block-bootstrap, route leave-one-route-out and scene n=1 claim ceiling. Statistical power simulation updated to q-only (without labels).

## R-10: independent auditor required before FROZEN

A distinct auditor session/runner must verify:
- exact raw H→Hann→4N IFFT→tap/branch/valid→7-tap J→q/epsilon/u on random and adversarial keys, with separate implementation, across both Full/LoS (Full raw feature check only; no Full metric/label aggregation before freeze);
- raw SHA and reference lineage plus P0V3 report output hashes, all failures and no omitted keys;
- q_W reference floor threshold is still the old S0 rule and **not measured against q_ref before science freeze**;
- labels absent from every P0 reading path;
- negative fixtures and code change diff; show auditor identity, independent execution record, SHA and verdict.

The implementer may self-test but cannot sign their own audit. A failure means \`REVISION_REQUIRED\`, not green workflow = science PASS.

## Required implementation output and stop rules

Create an **append-only new P0V3 output directory** \`results_p0_v03/run_<id>\`, never edit historical run directories.
Write \`P0V3_TAP_BRANCH_PARITY.csv\`, \`P0V3_LOS_PORT_BALANCE.csv\`, \`P0V3_WEAK_PORT_SUMMARY.csv\`, \`P0V3_R14_MATH_QA.json\`, \`P0V3_NEGATIVE_FIXTURES.json\`, \`MANIFEST.json\` with hashes + 40hex \`execution_git_sha\`, \`P0V3_STATUS.json\` and \`IMPLEMENTER_REVIEW_02.md\`.

Stop on any core hash, tap/branch parity, label-isolation, coverage, mismatch, invalid-flag fixture or math-identity failure. No S0/P1/P2/P3 trigger should exist in this v0.3 preflight branch.

Mandatory summary: files changed, files preserved, raw source/provenance SHAs, checks, failures, scientific claim boundary, next command. Additional governance/contract changes must be additive and identified by a new version or signed amendment.
