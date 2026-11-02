# A010 신규 구현자 사전 동결 독립 감사 요청

**Status:** AUDIT_REQUEST_DRAFT / IMPLEMENTER_SUBMISSION / INDEPENDENT_AUDITOR_SIGNED=false.

Subject commit: `2e402b066b75d47b2587216ecc04cc182487ba31` (the code-and-tests commit). New report-only commit does not change these Git blobs.
Repository: https://github.com/myoungsunk/sionna-resimulation/tree/implement/mbvar-info-a010-d2-d3-d4-d6-20261102

## Mandatory independent checks BEFORE A010-FREEZE

1. Independently compare original implementation 9e068660 with new implementation and verify FROZEN A008/A009, A010-P0, previous FAILs and RUN_REQUEST are byte-unchanged; contract_lock.py whole-track split rule unchanged.
2. Re-execute 21 pure-math/adversarial tests on pinned Python/NumPy and check zero-length, endian/dtype, corrupted manifest, wrong field, duplicate keys, bit flip and SHA swap all fail-closed.
3. Download complete latest 900/901 S1V5 and C3V5 Actions outputs; independently verify original input ZIP plus sidecar manifest SHA256, per-array dtype/shape/hash and optimizer actual-input parity.
4. Independently recompute full covariance and 180-pose factor law, compare every field-qualified Sigma within 1e-10 in both max and Frobenius normalized metrics, verify SPD.
5. Independently inspect 4x4 covariance upper-10, PSD, eigen minima, normalized condition and NEES differences; independently check all row keys and duplicates. A smoke subset internal STATUS=FAIL must not be relabeled.
6. Reproduce identical canonical input with *two physically distinct GitHub runners*; tie both to exact same source/manifest/input SHA, check class, every state, cost, full C10 and near-mode labels with registered tolerances; no single-runner self-check is admissible.
7. Confirm D4 includes legacy full-row STATE_STABILITY_FIXED verdict (including failures), does not auto grant unique-map claim, and documents near-minimum alternate-state field-paired MSE, covariance and NEES effects.
8. Verify exact full effective S_field copy plus new DEV3 only, with no legacy HOLDOUT resurrection; inspect dispatcher fail-closed negative tests and code SHA lock.
9. Only after independent proposer/auditor approval and explicit A010 FROZEN contract may full DEV3 be considered. HOLDOUT2 and RT remain separately NO-GO.

## STOP conditions

- Any altered historical receipt or old FAIL; unverified SHA, duplicate/zero row, missing original field covariance, type substitution, failed full matrix/SPD or mismatched split.
- Any truth/oracle used to choose the operational solution; any automatic favorable-subset selection for main H/CAL metrics.
- Any attempted science PASS based on same-runner or reduced 2-field SMOKE, or on unconfirmed solver-mode uniqueness.

## Evidence/status

- Fast unit CI: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41404670571 — 21/21 PASS on pre-report code.
- Integrated reduced technical CI: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41404670571 — pending final job/artifact assessment at time this request was issued.
- The auditor must open Actions artifacts and independently compute hashes, not accept this document as proof.
- Auditor role and session must be separate from the implementation role. Auditor signature is BLANK; no full science freeze request is considered approved.