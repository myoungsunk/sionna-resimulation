# DLP-EKF-GAPS-001 — 2026-11-01 구현자 G4 원본 복구 검토 및 P1–P4 실행 게이트

**최종 판정: G4 회수 증거 확보 / P1 기술적 사전정합 준비 가능 / P1 계산 실행은 BLOCKED_CONTRACT_NOT_FROZEN.** 본 문서는 P0 source/document preflight이지 P1 science run이 아니다.

## 식별자
- role: `IMPLEMENTER`
- frozen source base: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`
- 기존 P0 head: `07244877e77836d97888431891b44aa601b2d11f`
- recovered external data commit: `2b41f562063739d8d8f2011bc7248b561359580d` (`codex/r4-r5-m45-original-20261101`)
- contract_id: `DLP-EKF-GAPS-001`
- proposer DRAFT SHA256: `c7d18db29a2c6ea5a509f93b1f64559428e173c09beb293c0084b07bae480a6d`.
- `FROZEN`: NO; independent pre-run auditor: NONE; P1–P4 executable permission under contract: NONE.

## P0 G4 recovered evidence
- ZIP 88,656,933 bytes; repository Git blob SHA1 `2764a44d6cbad84c2062f3316ebc7959f41578bf`; recovery report ZIP SHA256 `5e6622da9f01d4de65c83de763e71c77f66a21003b03f4aaeb1aba8dd6cf34ef`. **ZIP contents were not freshly hashed by this implementer**.
- Source transport/self-check reports: ten preserved original files = 4 Full RF H + 4 S2 manifest + 2 original S1 pose JSON, plus one new delivery manifest. 4 H `complex128` finite arrays reported, no regeneration. Array shapes 922/1883 ×257×2×2.
- Immutable historical Snowball `TRANSFER_MANIFEST.json` SHA256 was **freshly computed from GitHub text** and matches `755ce2ce0225eb5a453d8f13de07b9f3a2df7055ebafeebc283863421bdca552`.
- Four historical S2 H manifests' Git text SHA256 were independently recomputed **4/4 exact**, and the four H hash strings/size in the new delivery each equal historical manifest values. Original route RF pose input hash **4/4 equals the canonical C0 SAMPLES SHA** (R4 `a79780...`, R5 `cd0c1e...`).
- Recovered files expand SAME SCENE/MOUNT COVERAGE, **not a third anchor, not a second independent RF environment, and not a confirmed Full/NativeLoS pair**.
- Source report `LOCAL_VALIDATION.json` states actual H SHA/structure checks PASS, but this is a packager self-check, not independent auditor verdict. Independent direct ZIP/H byte recomputation remains NOT_RUN.

## Important correction — delivery validator reproducibility
GitHub's committed `SOURCE_LOCK.json` bytes are **LF**: 1,406 bytes, SHA256 `42f4a519c44957c43bc5b4c8864e728704971d7d4531be280282cb1b0cce95aa`. The immutable `TRANSFER_VERIFICATION.json` refers to `d67a2640fda1c53a98a2e8bed2d3a00c26ad4b2e98e564019f3c04541f2c255c` which equals the exact same text serialized with **CRLF** (1,440 bytes).

The historical original verifier `verify_delivery.py` would fail its `SOURCE_LOCK.json` direct byte SHA assertion from a clean GitHub checkout. This is a packaging/line-ending verifier reproducibility defect; **it is not evidence that any original H/pose changed**. Do not rewrite the source file in place; publish an append-only validator erratum or a separate self-contained independent verifier with explicit LF/CRLF checks before claiming clean-checkout validator PASS.

## P1 scope check (do not execute)
- Primary C0: seven R2/R4/R5 × A/B/mount cases, 7 Full + 7 Native LoS binary H, trace keys. Historical P0 and FFD reports exist, with explicit SourceFFD model source `source_model.py`, legacy `p3_rf_adapter4.py`, and archived measurement observer.
- Old `FrozenLut` uses `B_OLD=-0.5315983906250129 m`, `RR=0.0068578637 m²`, `RS=0.0081`, `R0=diag(RR,RS)`, `GATE_JOINT=9.210340371976184`, but these historical values **are not automatically the final P1 FROZEN choice**.
- 2026-10-16 `FFD_P0P3_20261016/RESULTS_KO.md` states SourceFFD observer and refit were already executed under a separate historical project. Their effects on `h_s`, residual labels, means, covariance, and recursive state are nontrivial; particularly the range bridge remained continuous `d+B_OLD`. The complete original 256-trace package/runner is not present at that GitHub path. Avoid re-running every figure without an explicit source-to-output crosswalk.
- P1 needs proposer to lock **one observer, h_s source SHA, r bridge/policy, 4state f/F/Q, priors/seeds, R/μ/gates, packet mask, metric population, numeric tolerances**, then auditor independent pre-run review. Only after this may implementer re-calculate minimal affected 3-A/B/C/E outputs. 3-D and final M2 are RESERVED.
- Four recovered R4/R5 M45 Full H may enter a **clearly labeled C0_EXISTING_EXTENSION_FULL_ONLY** secondary analysis after freeze. If paired LoS/Full comparisons are demanded at those mounts, LoS H must be recovered/validated; do not invent LoS or silently mix geometry.

## P2–P4 gating
| Phase | Feasible now? | Reason |
|---|---|---|
| P1 metadata/source preflight | **YES, completed in these documents** | No RF/filter results generated |
| P1 affected-statistics recomputation | **NO** | DRAFT, no independent pre-run audit, source/model/tolerance locks unresolved |
| P2 scalar 4state R-only recursive | **NO YET** | Conditional on no existing identical trace, P1 lock, frozen contract; no new RF needed if approved |
| P3 third-anchor physical canary | **NO** | Mount45 adds no anchor; geometry/budget/independent preflight needed |
| P4 third-anchor RF plus comparison | **NO** | Requires P3 success, signed budget, clocks/covariance/fair-resource policy |

## Engineering preservation/STOP
No raw files, historical results, `main`, MBVAR/POL-XCORR, source FFD bank, data LFS, or original uploader recovery branch modified. No RT, no calibration fit, no EKF run, no 3-D/M2 design or independent audit claimed. Do not confuse GitHub CI mechanical PASS with scientific evidence acceptance.
