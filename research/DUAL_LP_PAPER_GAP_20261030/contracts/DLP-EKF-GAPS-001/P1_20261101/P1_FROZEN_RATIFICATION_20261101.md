# DLP-EKF-GAPS-001/P1 — APPEND-ONLY FROZEN RATIFICATION
Date: 2026-11-01 (KST). **Phase authorization: P1 ONLY.**

This is the post-audit, proposer-approved *separate* FROZEN decision. It does not modify the earlier `PROPOSER_LOCKED_AUDIT_PENDING` contract or receipt.

## Immutable bindings
- Proposer science commit: `340877f3537b4cc65cdaa9d687423cba92e0b28b`
- Contract SHA256: `373781e0a2395032faa49ff0228d84ebf8d93bb9c880e0504105bc5e12e82594`
- Input lock SHA256: `65d16d2941a57e636a6b0c6269039631d82d7a6dd1334ad665b168264ad113e0`
- Science config SHA256: `82c715f4ab7d0517f42d902e50124cb00f04a2b01a25282ca5aba923c95a8014`
- Numerical thresholds SHA256: `8739e721a10a95c6113c7198972c7c00983c97da6475e86606d7a1fac60d904f`
- Sample lock SHA256: `9d92e4a926d2877d1969e718210ea0ed8aeeb6cac6a6dae46c867bf3d742277f`
- Auditor independent raw receipt SHA256: `d9530bccdd5eb753aecba0475c52ed092bf3aaf221b3cba389ed2aa492a9548c`; run [41289874166](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41289874166); 21 PASS, 0 FAIL.
- Full machine-readable ratification: [P1_FROZEN_RATIFICATION_20261101.json](P1_FROZEN_RATIFICATION_20261101.json).

## Co-signatures (linked evidence; not impersonated human cryptographic signatures)
**PROPOSER approval**: Original proposer role locked the above contract; user's explicit current 2026-11-01 instruction authorizes drafting this ratification **and immediately running the P1 experiment**. This chat is authorization, not a cryptographic signature.

**AUDITOR countersignature**: Independently written numerical audit on physically separate GitHub Actions runner and prior signed `ACCEPT_WITH_BOUNDARIES` record, immutable at `189b38c0fda16ff3b47862f1e251982ccedd0572`. The auditor's signed computational verdict is joined to this record **by SHA reference**, not rewritten as a newly authenticated human signature. GitHub account used for writing is the repository owner; independent human GitHub approval is not claimed.

## FROZEN scope
- Existing C0 Corridor (one scene), 7 paired R2/R4/R5 Full/NativeLoS cases only; 9519 pose-case keys/mode, 7251 timeline case-steps/mode, t>=30 gives 6201/mode.
- Raw H -> symmetric Hann with N-1 denominator -> 4N IFFT times N -> strongest receiver 30% earliest first-edge -> SAME index on dual ports; signed s=(P+−P−)/(P++P−); raw r first-edge.
- Only the LoS polar predictor changes: source-pinned FFD vs archived LUT; r prediction stays d−0.5315983906250129 m; same case, pose, packet, observer, range convention.
- Offline retrospective signed e_r/e_s, differences, ddof1 stratified moments/covariance and boundary ledger. All T00–T15 tests and invalid rows preserved, no filter and no RF generation.

**Prohibited**: 2026-10-16 historical SourceFFD promotion, after-seeing-results threshold adjustment, training of mean/conditional covariance, Full-only Mount45 extensions, Office/new scenes, 3D/M2, P2+ replay, EKF or new RF.

**Run gate**: the workflow must independently verify all locked SHA256s, the signed auditor receipt, 39 original assets, 2 full bank NPZs, and historical trace eligibility BEFORE collecting new P1 science. If any fails it records BLOCKED/FAIL and preserves logs. Output must be append-only with runner-specific provenance. Final science approval is separate from mechanical gate PASS and is not conferred by FROZEN alone.
