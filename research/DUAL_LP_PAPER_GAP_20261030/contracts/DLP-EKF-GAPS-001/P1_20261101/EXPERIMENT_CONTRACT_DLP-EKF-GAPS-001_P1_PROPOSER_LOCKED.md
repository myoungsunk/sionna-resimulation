# EXPERIMENT_CONTRACT DLP-EKF-GAPS-001 — P1 proposer-locked candidate v1

**Status: `PROPOSER_LOCKED_AUDIT_PENDING`; NOT `FROZEN`; science / RT / EKF runs remain `NOT_AUTHORIZED` until independent pre-run approval.**

## Authority and provenance

- Role: `PROPOSER` (acting under user's 2026-11-01 request to finalize P1 science and seek independent review). This signature is not an independent auditor signature.
- Contract ID: `DLP-EKF-GAPS-001/P1-V1`.
- Governance/base Git SHA: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`.
- Source proposer HEAD reviewed: `1aac4d38a6fa335116bcecbebc91ba53c876ecfd`; earlier P1 implementer HEAD: `10529733bb74eb7efe3739b9199e8d8ad9693a37`.
- Snowball R4/R5 Mount45 recovery: `2b41f562063739d8d8f2011bc7248b561359580d` (Full-only C0 extension, explicitly **excluded** from P1 primary paired universe).
- The document SHA-256 is recorded externally in `P1_PROPOSER_LOCK_RECEIPT.json` to avoid a self-hash.
- Input lock SHA-256: `65d16d2941a57e636a6b0c6269039631d82d7a6dd1334ad665b168264ad113e0`.
- Scientific config SHA-256: `82c715f4ab7d0517f42d902e50124cb00f04a2b01a25282ca5aba923c95a8014`.
- Numeric tolerance SHA-256: `8739e721a10a95c6113c7198972c7c00983c97da6475e86606d7a1fac60d904f`.
- Sample/split SHA-256: `9d92e4a926d2877d1969e718210ea0ed8aeeb6cac6a6dae46c867bf3d742277f`.
- Original C0 P0 manifest actual SHA-256 `462c0bc89e1b55653d289d8a529c1c7022c17a8d954c5ea5740a99092d367455`; immutable Git blob `8bf216cf606f5e3c11139cacbf42f15a44556feb`.
- All 39 input assets have actual historical/newly verified SHA-256 in the input lock; every input must be freshly verified before a science run.
- P1 output root, only once the gate opens: `research/DUAL_LP_PAPER_GAP_20261030/runs/P1_SOURCE_HARMONIZATION_<RUN_ID>/` (new, append-only; no old output overwrites).
- Proposer lock signed by: **role=PROPOSER / this authored document under user instruction**; date: 2026-11-01.
- Independent pre-run auditor: **NOT_ASSIGNED**. Distinct real actor/session and independently generated calculations required, not the same implementer/proposer labeling itself AUDITOR.

## Research question and estimands

On **identical** frozen C0 Full/NativeLoS complex H, does changing **only** the LoS polar observation predictor from legacy 2-degree LUT to the pinned source FFD model alter the inferred signed r/s error statistics and geometric Jacobians? This P1 is a retrospective **source and characteristic data harmonization**, not a new-performance superiority trial.

The deterministic identities and descriptive estimands are `e_s^old=z_s-h_s^old(x_GT)`, `e_s^src=z_s-h_s^src(x_GT)`, `Δe_s=e_s^src-e_s^old=h_s^old-h_s^src`, `e_r=z_r-[d(x_GT)+B_OLD]`. No causal claim that a changed mean/covariance proves a deployable EKF improvement.

Null reference: exact same raw input and observer should yield exact same `z_r,z_s,tap,pose,time`; the range model must remain unchanged, while `h_s` may differ by geometry. Model equivalence of old LUT and SourceFFD is **not** assumed. Sign of SourceFFD-vs-legacy aggregate state accuracy is **not preregistered**.

## Physical observation lock

- One Corridor 20×2.4×2.7 m, tag z=0.45m, anchor A=(4,0,2.65), B=(10,0,2.65). Fixed scene family, **independent scene n=1**.
- **Exactly seven** primary cases: R2-A0, R2-B0, R2-A45, R4-A0, R4-B0, R5-A0, R5-B0.
- Stored raw complex H per case `(N,257,2,2)` with N=1303/922/1883; matched 9519 Full and 9519 native LoS `case,pose_id` records.
- Frequency f=6.2504GHz+1.95MHz·k (k=0..256), TX0+45LP and RX±45LP. Symmetric Hann `w_k=0.5−0.5cos(2πk/(N−1))`, IFFT zero padding to 4N, scaled by N; strongest Rx peak 30%-leading-edge first index; both ports sampled at **same** tap.
- `s=(P_+−P_-)/(P_++P_-)`, dimensionless, powers from the same tap. `r` from first-path delay × c in metres, static channel `noise_var=None`. All invalid/zero-power/crossing cases are explicit records; no silent imputation.
- LoS `h_s`: `research/FFD_P0P3_20261016/source_model.py` Git blob `ea1cac65d6291681a4b5abf9a2c83b77f5997631`; bank hashes in `P1_INPUT_LOCK.json`. Actual estimated-state 3D distance for polar prediction, frequency-dependent complex fields and the same observer chain, RX/anchor rotation in original source. Use source-only north-pole cap with 1°/3° ring and 0.1°–0.5° blend; do not re-fit from RF truth.
- Old baseline `h_s`: `FrozenLut` Git blob `cb676aea8e6710ff2c0e175e1e422271b696cebe`, source LUT SHA256 `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079`.
- **Both arms**: `h_r=d+B_OLD` with `B_OLD=-0.5315983906250129 m`. This is an earlier continuous range surrogate; never present it as exact tap-derived ranging likelihood.
- Conventional historic filter reference only: `R0=diag(0.0068578637 m², 0.0081 unit²)`, `R_rs=0` unverified assumption, scalar `χ²_1(.99)=6.6348966010`, joint `χ²_2(.99)=9.2103403720`. **No EKF, gate decisions or recursions are recomputed in P1.**
- State convention `x=[x(m),y(m),ψ(rad),b_g(rad/s)]`; `H_r=[Δx/d,Δy/d,0,0]`; `H_s=[∂s/∂x,∂s/∂y,∂s/∂ψ,0]`. The gyro bias may be indirectly observed via `F_{ψ,b}=-dt`, but this is P2+ mechanics, not a new P1 score.
- Source bank loading caveat: `p0_initial.py` expects `ROOT.parent/BANK_MANIFEST.json` and bank binaries. Any staging adapter must create a *transient* manifest and verify byte SHA at the pinned path before loading; independent reviewer must inspect the adapter. No silent fallback to the Git LFS pointer bytes.

## Population/split/statistical scope

- Primary offline characteristics: 9519 matched pose-case keys per RF mode, both Full and NativeLoS = **19038** records. Timeline subset 7251 case-time keys per mode = 14502. A predeclared comparable t≥30 s subset is 6201 per mode = 12402.
- Each table must preserve `scene_family,route,anchor,mount,channel,pose_id`; time only for timeline-matched subset, neither path count nor sensor seed counts as independent scene.
- Retrospective descriptive moments only (`n,mean,sd,RMSE,2×2 sample covariance ddof=1,signed C_rs`, counts and boundary metrics). Predeclare case/channel and distance bins 0–5, 5–10, ≥10 m. Insufficient n<2 → `INSUFFICIENT`; invalid groups must be present in an invalid ledger.
- Ground-truth pose may be used **only** for offline characterization labels; it is unavailable to runtime models.
- No new model fitting, learned µ/R, hyperparameter tuning, crossfit evaluation or final unseen-test claim is authorized in P1. The 2026-10-16 SourceFFD fit/256 trajectory runs remain *historical retrospective evidence*, never post-hoc preregistered output.
- Existing repaired R4/R5 Mount45 Full-only H is **excluded** from P1 primary, with an explicit extension receipt; no invented Native LoS channel and no 3-anchor claim.
- 3-D covariance/information and M2 algorithm choice are RESERVED; Office is a separate scene not pooled into primary C0.

## Acceptance, falsification and pre-run numerical stops

`P1_NUMERIC_TOLERANCES.json` is a **fixed** 16-gate engineering-reproducibility contract, authored before the next P1 run, including exact full-file SHA, pose/time parity, locked observer r/s/tap, FFD complex source/native checks, s RMSE/max residual, Jacobian FD only on stable cells, PSD and signed error identity. Tolerances on already-analyzed C0 use **historical visible results as engineering regression bounds** and are NOT independent confirmatory criteria. Any failed test blocks downstream P1 output; no after-seeing-results tolerance rescue without append-only amendment.

Never interpret an Actions green build as scientific success or a genuine external independent auditor sign-off.

## Implementation evidence required once independent auditor accepts

- Original-byte SHA receipt (39 C0 + source bank), exact source Git SHAs, bank staging provenance and runner SHA.
- `P1_SOURCE_OBSERVER_CANARY.csv`, `P1_RAW_OBSERVER_PARITY.csv`, `P1_MATCHED_SIGNED_ERRORS.csv`, `P1_STRATIFIED_MOMENTS.csv`, `P1_INVALID_AND_BOUNDARY_LEDGER.csv`, `P1_SCIENCE_QA.json`, `P1_MANIFEST.json`, `P1_LOG.txt`.
- All signed residuals in SI units, same packet pairing, no truth at runtime. Report every failing case, count, timestamp, source model, model-version, provenance and paired output; use append-only paths.
- Completion result can be `PASS` mechanically or `FAIL/BLOCKED`; scientific comparative advantage is OUT_OF_SCOPE.
- No P2/P3/P4 RF/replay implied by an approved P1.

## Signature and required transition

`PROPOSER_SCIENCE_LOCKED=YES` for this **candidate**. `AUDITOR_INDEPENDENT_PRE_RUN_VERDICT=NOT_RUN`. `FROZEN=NO`. Once a truly separate auditor independently reproduces required math/source/splits, records own immutable evidence, identifies their actor/session and signs `ACCEPT_WITH_BOUNDARIES`, the proposer and auditor can issue **a new append-only FROZEN ratification record referencing the unchanged exact SHA-256 of this contract**. Until then `allowed_experiment_phase=NONE` under the original DRAFT and current proposer-locked candidate.
