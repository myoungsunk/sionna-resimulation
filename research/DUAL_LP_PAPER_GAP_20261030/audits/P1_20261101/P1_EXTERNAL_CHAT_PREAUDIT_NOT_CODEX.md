# DLP-EKF-GAPS-001 / P1 — Separate-chat static pre-audit (NOT Codex sign-off)

Date (KST): 2026-11-01
Requested target: [PR #4](https://github.com/myoungsunk/sionna-resimulation/pull/4)
Audited proposer HEAD: `340877f3537b4cc65cdaa9d687423cba92e0b28b`
Contract ID: `DLP-EKF-GAPS-001/P1-V1`
Contract SHA256: `373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594`
Governance source: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`

**Disposition: PRECHECK_ONLY / BLOCKED_EVIDENCE (provisional). Formal independent Codex auditor signature: NOT_ISSUED. FROZEN=false; P1 NOT_RUN.**

## Provenance / independence

- Auditor actor: ChatGPT GPT-6, this chat, using linked GitHub read APIs and separately authored JavaScript Code Mode checks. **No separately launched Codex agent or verified independent GitHub reviewer identity.**
- Auditor/session identity sufficient for a formal contract co-sign: **NOT_VERIFIED**. GitHub writes use the user's linked account; any PR comment under that account is **not** an independent GitHub reviewer sign-off.
- Calculations were newly written for this precheck; the proposer's `P1_PROPOSER_MATH_QA_SELF_REVIEW.json` was read only as context, not accepted as independent evidence.
- Full executable test script/hash, separate executable CodeX runner, native RF and bank binary parity: **NOT_PROVIDED / NOT_VERIFIED**.
- This branch contains only additive audit documentation; neither proposer source, lock files nor main are modified.

## Checks actually computed

| Gate | Directly checked result | Qualification |
|---|---|---|
| A00 | Fresh SHA-256 and Git blob/UTF-8 byte length for 7 receipt-listed locked documents plus immutable P0 input manifest: **8/8 match**. Independent SHA-256 implementation self-test `abc` matches standard digest. | These are source text bytes retrieved by GitHub API, NOT source bank binary checks |
| A01(part) | Of 39 C0 locked assets: **23 text assets** (7 SAMPLES, 3 Tnone timelines, 7 source Python, 1 LUT metadata, 1 sensor config, 4 lineage files) and **1 binary freqs_hz.npy**: **24/24 raw SHA-256, byte length and Git blob match**. Frequency data are little-endian 257 float64, 6,250,400,000 to 6,749,600,000 Hz in 1,950,000-Hz steps; max deviation 0 Hz. | Remaining **15**: 14 Full/NativeLoS H arrays + old LUT array cannot be accessed as original binary bytes via current GitHub fetch. Do not count Git blob metadata or empty binary API response as raw SHA verification |
| A01(bank metadata) | `LP_plus45_bank.npz` and `LP_minus45_bank.npz` Git LFS pointer OIDs and sizes agree with lock: plus `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b` (247727983 bytes), minus `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9` (247743979 bytes). GitHub Actions artifact ID `12034154094`, 495473098-byte ZIP, was listed as unexpired at inspection and was downloaded to a tool reference. | Pointer is NOT the .npz contents. The full ZIP could not be independently hashed/expanded due container execution `ClientError`; neither bank's actual original bytes were independently verified |
| A02(part) | Fresh JSON/CSV parse: R2 sample=1303, timeline=979, t>=30=829; R4=922/742/592; R5=1883/1415/1265. Weighted by 3/2/2 cases: **9519 / 7251 / 6201 per channel**. All timeline pose IDs are present once, no missing or duplicates; timestamps strictly increasing. Max XY mismatch `4.99949216026252e-7 m`; max wrapped yaw mismatch `4.822848040930694e-7 deg`; max 0.2-s step error `4.546363285840016e-14 s`. | These verify SAMPLES/timeline keys, NOT actual Full-vs-NativeLoS H row content or packet parity |
| A03(part) | Independent synthetic two-port 257-bin symmetric Hann, 1028-tap direct IFFT computation, strongest-RX/30%-leading-edge/common-tap signed-s and range detector; 3 synthetic states. | No actual RF H or archived observation output available for a real-packet chain check |
| A05(part) | Independent synthetic complex-power `ds/d(x,y,psi)` analytic-vs-central-FD max absolute mismatch `9.947103557506054e-11`; geometric `H_r` max FD error `1.8795909273450206e-11`; bias direct observation derivative 0. | **Does not validate pinned SourceFFD FFD interpolation, source north-pole cap, or actual `J_s`** |
| A06(part) | Algebraic sign identity `(z-h_src)-(z-h_old)=h_old-h_src`, no change to r; synthetic `ddof=1` sample 2x2 covariance `[[0.04775,-0.01655],[-0.01655,0.02363]]`, min eigenvalue `0.015212058208892182`. | No C0 residual covariance or raw physical error data recomputed |
| A07/A08 | Contract declares retrospective C0 only, no training or EKF in P1, one independent scene, 16 pre-fixed numerical/regression gates and explicitly acknowledges historical limits. | Textual governance review, NOT science validation |
| A09 | Pinned `research/FFD_P0P3_20261016/p0_initial.py` loads `ROOT.parent/BANK_MANIFEST.json` and sibling NPZs; these cannot be treated as automatically present inside Git checkout. | No independent bank staging adapter or actual source full runner execution available |

## Original source review

- `research/FFD_P0P3_20261016/source_model.py` Git blob from current PR HEAD = `ea1cac65d6291681a4b5abf9a2c83b77f5997631`, matches proposer lock.
- `observation.py` Git blob `3571cb12face26d58fdc8a273c191a128990cb27`, uses symmetric Hann `N-1`, zero-pad 4N, IFFT times N, largest Rx peak, earliest >=30% edge, same first tap for signed s. Config uses misleading word "periodic-endpoint", but additive `P1_CONFIG_TERMINOLOGY_ERRATA.md` clarifies the binding *symmetric* formula.
- `P1_INPUT_LOCK.json.original_manifest_sha256` remains the string `P0_FROZEN_FILE_SHA_REHASH_REQUIRED_AT_START`; the correct freshly checked actual SHA `462c0bc89e1b55653d289d8a529c1c7022c17a8d954c5ea5740a99092d367455` is in the contract/receipt. Preserve lock immutability, and clarify canonical source in an append-only ratification/erratum if needed.
- Audit request names `docs/research-governance/GOVERNANCE_APPLICABILITY_KO.md`, but the actual DLP-specific file exists under `research/DUAL_LP_PAPER_GAP_20261030/GOVERNANCE_APPLICABILITY_KO.md`; correct audit handoff location.
- Historical `hs_lut_meta.json` contains `gate_L1_interpolation.passed=false` (max=0.0239721 vs threshold=0.01). This limits interpretation of legacy LUT, but is not by itself a failure of *new* P1 source-matched reproducibility. Explicitly retain as historic caveat.

## Missing mandatory proof / stop list

1. Independent raw-byte SHA-256 of **all 15 remaining C0 binaries**, and both physical FFD bank binaries; staged `BANK_MANIFEST.json` with matching digests, not LFS pointer text.
2. Actual independent random + adversarial Full/NativeLoS raw H -> 257-bin symmetric Hann -> 1028 IFFT -> same first tap -> signed s/r; compare archived traces with locked T05 and retain every failed packet.
3. Independent direct SourceFFD vs NativeLoS full complex H and s parity against locked T06/T07/T08 thresholds; no phase alignment; include pole/seam/zero-strength cases.
4. Independent analytical pinned `SourceFFD` Jacobian versus fresh central FD on stable cells, first-path/cell/cap crossing ledger, port-swap/2pi invariance; exact `2x4` and zero bias direct column.
5. Independent actual C0 residual mean/variance/covariance for every predeclared stratum; exact keys, zero row omission, test T11-T15 and inspect original historical LUT metadata limitations.
6. Separate auditable code hash, real runner/session identity, package versions, source SHA, physical input hashes, per-case failure records and explicit independent review signature; do not submit a sign-off from the same GitHub PR author's identity.

## Required outcome

**Provisional: BLOCKED_EVIDENCE** because source-specific and native RF binary verification have not run, and separate Codex independent actor has not been launched. No mathematical design failure is established. No approval or FROZEN ratification; do not run P1 science, EKF, new RF, or modify original inputs.

Only a newly launched, truly separate Codex auditor/environment with full raw inputs and independently executed test code may issue the formal `ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, or `BLOCKED_EVIDENCE` record on the unchanged contract SHA.
