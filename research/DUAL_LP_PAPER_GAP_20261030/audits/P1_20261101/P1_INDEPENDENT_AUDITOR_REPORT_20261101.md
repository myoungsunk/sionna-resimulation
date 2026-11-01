# DLP-EKF-GAPS-001/P1-V1 — Independent computational auditor verdict (2026-11-01)

**VERDICT: `ACCEPT_WITH_BOUNDARIES` — PRE-RUN P1 ONLY.**  
**P1 science = NOT_RUN; FROZEN = FALSE; PR #4 NOT MERGED.**

## Exact immutable identities

- Proposer PR HEAD (unchanged): `340877f3537b4cc65cdaa9d687423cba92e0b28b`.
- Contract SHA-256: `373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594`.
- GitHub Actions independent run: [41289874166](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41289874166), SUCCESS.
- Independent runner script SHA-256: `a689af0e3fdeb4ceb51bbf0bf29ea22a6280fed6f076f4adebdd19f418c962d2`.
- Actual `AUDIT_RESULT.json` SHA-256: `d9530bccdd5eb753aecba0475c52ed092bf3aaf221b3cba389ed2aa492a9548c`.
- [Full machine-readable auditor verdict](P1_INDEPENDENT_AUDITOR_VERDICT_20261101.json).
- [Append-only raw receipt](runs/41289874166/AUDIT_RESULT.json) · [all input SHA receipts](runs/41289874166/INPUT_SHA_LEDGER.json) · [canary numeric records](runs/41289874166/CANARY_QA.json) · [runner log](runs/41289874166/AUDIT_LOG.txt).

## Evidence, measured on real locked original data

| Gate | Independent outcome | Bound / interpretation |
|---|---|---|
| 39 C0 files | 39/39 exact raw SHA256 and byte length, including 14 H binaries + old LUT | Actual bytes, not Git metadata alone |
| 2 FFD .npz | 2/2 full original-binary SHA256 and byte length | Original GitHub Actions bank artifact staged outside working tree |
| 7 cases, same keys | 9519 Full + 9519 NativeLoS, route timeline 7251/mode and t>=30 6201/mode | No missing/duplicate pose IDs in manifest sample/timeline; native H shapes and dtype checked |
| 257-bin observer | Actual Full/LoS random + adverse case canaries H -> symmetric Hann(N-1) -> 1028 IFFT -> strongest-RX 30% first edge -> signed s and r | Parity vs pinned original observer ≤1e-9; port-swap s-flip difference 0 |
| Separate direct RF oracle | 42 samples, max complex relative difference **3.601931×10^-13** | Independently coded spherical vector bilinear + complex field contraction (not implementer helper) |
| SourceFFD vs Native complex H | 9519, max relative **3.254054×10^-4**, RMS **7.311434×10^-5** | Within locked 5e-4 / 1e-4 limits; no common-phase correction |
| SourceFFD vs Native signed s | 9519, RMSE **6.592045×10^-7**, max abs **1.082114×10^-5** | Within 2e-6 / 2e-5; first-path tap mismatch **0** |
| Analytic SourceFFD J_s | 45 real-bank test states, 44 stable, 1 crossing, max stable abs FD difference **2.920184×10^-9** | One boundary separately counted, not incorrectly passed as smooth |
| Polar cap, seam, yaw period | 6 targeted angles, 13 stable FD columns; seam H relative difference **7.381307×10^-10** | Source-only cap QA, not subdegree EM solver truth |
| Old LUT | Independent eight-corner trilinear s interpolation agrees with locked FrozenLut canary | Old LUT metadata's historic interpolation gate `passed=false` remains a limitation |
| Signed residual/covariance | Independent algebra identity, synthetic ddof=1/PSD check passed | **NO** new C0 P1 signed residual statistical results before freeze |

**Total pre-run auditor QA checks: 21 PASS / 0 FAIL**. P1 final tolerance gates T00–T15 remain frozen and must be reported for the complete eventual P1 execution; selected pre-run canaries are not complete post-run T05/T15 statistics.

## Actor and claim limits

- Audit actor: **GPT-6, separate ChatGPT audit session relative to proposer; independently authored scratch numerical code; separately executing GitHub Actions runner `runnervm48cm3`**.
- All GitHub writes are through the same repository owner's linked credentials; **no separate human GitHub reviewer identity** and no GitHub APPROVE status are asserted.
- Historical C0 is a **single corridor** already seen in model development. These are **retrospective engineering-reproducibility tolerances**, not unseen or confirmatory performance evidence.
- Actual P1 signed error moments, learned mean/covariance, any EKF, new RF, Office/3D/M2 or generalization claim were **not run**.
- The R4/R5 Mount45 recovered Full-only extension was excluded because Native LoS partners are absent, as contract requires.
- Range remains the continuous baseline `d-0.5315983906250129 m` despite tap-derived raw r.

## Approval boundary / required transition

The **computational pre-run audit gate is accepted with explicit scientific boundaries**. The frozen proposer contract is unchanged, PR #4 is not approved/merged by a distinct GitHub reviewer, and `FROZEN=false` remains binding. A **separate append-only FROZEN ratification signed by proposer and auditor**, referencing the unchanged input/config/threshold/contract SHA-256, is required before any P1 science run. Do not promote this receipt to P2–P4 or final journal-claim evidence.

Signed audit role: **GPT-6 independent computational auditor, GitHub Actions run 41289874166**. Identity scope and independent computation are recorded in the linked machine-readable verdict.
