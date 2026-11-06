# FP-SC-001 — VAB staged shadow integration, code-only handoff

**Status: CODE_IMPLEMENTED / SCIENCE_NOT_RUN / NO_EXECUTION_APPROVAL / NOT_INDEPENDENTLY_AUDITED.**

Source parent: \`e416cf62c0cde15151a1851168231da73a0cbfff\`, existing implementation branch \`implement/fp-sc-001-e1-run-20261105\`. This package is a separate branch. Preserve all E0, E1-01 original FAIL/HOLD, VAB 87/87 exposed candidate evidence, 11,095 mapping-stress exclusions, the old E1-02 HOLD, and previous P/M input sensitivity. No retroactive gates.

## User-selected approach B

The intended order is **S1 actual VAB proposed selection (shadow, no production write) → S2 F01/F11 posthoc observation errors → S3 one-update fixed-prior EKF arithmetic → S4 later recursive EKF after separate authorization → S5 hardware timing only after scientific review**.

S1–S3 have opt-in offline functions and an explicit three-stage local CLI. This code changes NO actual robot or currently active EKF selector. It does NOT execute existing scientific stages \`E1-02\` or \`E2\`. No user approval to run scientific RF is assumed. S4/S5 are NOT activated; old E4/E5 are not VAB-integrated and must not be launched as if they were.

## Exactly which model is reused?

- VAB \`TWO_PORT_UNION\` produces genuine current-CIR candidates. \`RevisionEvidenceAdapter\` emits bridge identity; \`binding_for()\` verifies the Policy hash, candidate config and bridge recipe.
- Both the legacy \`select()\` and new shadow path call \`prepare_candidate_set()\` **and the same pure \`decide_prepared_candidate_set()\`**. There is no altered threshold, altered confidence, learned ranking, new provider or hard 4cm cut.
- Old heuristic \`J = 0.7[-log q] + max(p,m)^2\`, \`wrong_cut=2\`, \`replace_gain=0.8\`, \`margin=0.5\` stay frozen as **an intentionally weak baseline**, not a calibrated likelihood.
- P is the **archived pre-measurement prior** mapped through the native SourceFFD detector with the original 7-point/support model. M uses **only the immediately preceding raw first-path tap**, its original timestamp, and current-versus-previous detector offset; a missing/stale raw FP causes M hold. M is an **untrusted diagnostic hypothesis**, not \`TrustedHistory\`.
- All P/M are \`UNKNOWN\`, not \`VALID\`. The selector never receives GT/Native-LoS/reference, never changes an online FP and never feeds a proposal to a recursive filter. The S1 stored result carries \`counterfactual=True\` and \`provider_allowed=False\`.
- Comparison S2 uses S1's **stored, hash-locked output**, only later loads \`evaluator.npz\`, exact-joins pose/time and computes errors to Native-LoS direct-only reference. This reference is not a universally optimal Full-CIR tap.
- S3 computes existing four extraction modes F00/F10/F01/F11 in a **single fixed-prior, fixed-model-mean/R/mask** EKF update. It proves \`K Δz\` and identical \`P\` for the fixed context, NOT better recursion or calibrated error.
- If gyro bias ground truth is unavailable, later Heading/XY/coverage can use explicitly opt-in 3-column truth, while **4D NEES remains null, NOT_TESTED**. Never fill missing gyro bias with 0.

## Code changes and invariants

1. \`selection.py\`: extracted mathematically identical pure decision function from guarded legacy \`select\`; original \`select\` and its no-live-VAB guard are unchanged in authorization behavior. Test synthetic parity is essential.
2. \`vab_shadow.py\`: three isolated S1/S2/S3 APIs; never calls \`select()\`, \`ArmProcessor\`, main EKF replay, or history mutation. Future reference changes cannot alter already saved S1 outputs.
3. \`data.py\`: online-only input loader for S1/S3 and separate exact-join/evaluator loader for S2.
4. \`evaluation.py\`, \`study.py\`, \`data.py\`: explicit future 3-column truth support without treating absent bias as 0; default 4D requirement preserved.
5. \`scripts/fp_sc_vab_shadow_stages.py\`: **plan / preflight / run** one stage at a time. \`plan\` doesn't load science data; \`preflight\` only validates hashes and schema. \`run\` requires a fresh manifest and separate \`execute_shadow_science=true\` approval for EXACT stage/case/code/input, creates a NEW result directory and preserves FAILED result. An E1-02/E2 approval is not valid here.
6. For S2/S3, immutable S1 (and S2 for S3) result+receipt **and a separately reviewed \`ACCEPT_TO_NEXT_STAGE\` document** must be hash locked. No automatic continuation on technical completion alone.

## Stage-specific scientific decisions after later approval

| Stage | What to judge | How to stop |
| --- | --- | --- |
| S1: shadow selection | Correct/wrong→correct, correct→wrong, no-change, C/P/M/PM holds, route-episode and 0/1/2+ tap groups; absolute/relative margin, raw-vs-alternative evidence | No usable/beneficial replacements, excessive safe-FP changes, invalid prior/context -> HOLD; report per-case, not pooled only |
| S2: observation comparison | F00 vs F01 vs F11 range/signed-polarization error; harm/rescue and joint effects; same ref tap for each packet | F01 harms range unexpectedly, or signed polarization error worsens on normal FP -> HOLD |
| S3: same-prior EKF | Heading and XY **one-update** difference; fixed gate vs calibrated future own gate kept separate; \(K Δz\), identical covariance under fixed R/mask | Missing original h/H/Pprior/Reff/mask, failed original replay parity -> HOLD |
| S4: full recursion (NOT ENABLED) | independent 6-arm state/history, R2/R4/R5 B0/L2, Full/LoS, Heading/XY/R/NEES/coverage, copied noise/seed identity; F01 vs F11 | Separate new version, no pseudo 4D bias truth, no reuse of original frozen priors as own recursive state |
| S5: 5Hz/field (NOT ENABLED) | actual arrival-to-sink latency, null and stale input, mounting/field effects | Separate hardware ID+resources and real-device acceptance |

**Research decision:** This patch deliberately does NOT invent an integrity provider or alter the science criteria. The earlier C-only 0/1,015 and nominal PM 35/1,003 virtual detections remain failures/diagnostics; changing the threshold just to make S1 look good is prohibited. If S1's basic model cannot select useful FP cases, improve it in a new post-S1 design+contract; do not reinterpret S2/S3 as a failed-provider implementation.

## Mandatory input/approval recipe (NOT filled; NO execution now)

Manifest schema \`FP_SC_VAB_SHADOW_STAGES_V1\`. Required:
\`stage\` one of \`S1_SHADOW_SELECT / S2_OBSERVATION_COMPARE / S3_FIXED_PRIOR_EKF\`;
\`case_id\`, one canonical dynamic \`case={online_npz,evaluator_npz,expected_rows,metadata}\`;
\`policy\` and \`policy_sha256\`;
\`candidate_arm=VAB\`, \`candidate_mode=TWO_PORT_UNION\`;
\`source_commit=e416cf62c0cde15151a1851168231da73a0cbfff\`;
full SHA256 dictionaries \`code_files\`, \`baseline_sources\`, \`input_files\`, including banks and prepared NPZ real payloads (LFS pointer rejected);
\`previous\` is {} for S1, S1 receipt/result/review for S2, S1+S2 for S3;
\`archived_context_verified=true\` for S3 only after original trace evidence review.

Approval schema: \`execute_shadow_science=true\`, exact \`stage\`, \`case_id\`, \`manifest_sha256\`, \`code_lock_sha256\`, \`actor\`, \`issued_utc\`; no \`execute_science\` or blanket stages. This code patch **does not create any approval**.

Example safe commands (do not start a study):
\`\`\`bash
PYTHONPATH=src python scripts/fp_sc_vab_shadow_stages.py plan
PYTHONPATH=src python -m unittest discover -s tests -p 'test_fp_sc_vab_shadow.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p 'test_fp_sc_vab_staged_contracts.py' -v
\`\`\`

After a separately approved contract:
\`\`\`bash
# One stage/case only. Approval and prior reviews must match this exact manifest.
PYTHONPATH=src python scripts/fp_sc_vab_shadow_stages.py preflight --manifest APPROVED_STAGE_MANIFEST.json
PYTHONPATH=src python scripts/fp_sc_vab_shadow_stages.py run --manifest APPROVED_STAGE_MANIFEST.json --approval APPROVED_STAGE_SCOPE.json --output research/FP_SC_SHADOW_S1_NEW_OUTPUT
\`\`\`

## Acceptance scope for implementer audit

- Test full legacy 1,000 synthetic Decisions exact after refactor; no change to old VAB technical evidence.
- Verify no SourceFFD/GT/evaluator access to S1 from output/logs, and no \`select()\` unlock, EKF closed-loop, non-audited trusted history.
- Check one-source one-policy SHA with no midpoint threshold retuning.
- Confirm F01 keeps original range value, F11 uses new range, and posthoc reference cannot affect S1 output.
- Require genuinely reviewed and SHA-locked prerequisites for next stage.
- Code compile and synthetic checks do NOT imply S1/S2/S3 or original E1-02/E2 science ran.
