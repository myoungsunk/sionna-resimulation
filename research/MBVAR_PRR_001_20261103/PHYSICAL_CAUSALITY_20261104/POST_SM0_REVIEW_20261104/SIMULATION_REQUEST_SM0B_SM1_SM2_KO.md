# SIMULATION-REQUEST-PRR-RT-POSTSM0-001 — Snowball/Codex 신규 Sionna RT 생성·검증 요청

**문서 역할:** 구현자에게 전달하는 실행 계약 + 산출물 명세  
**작성:** 2026-11-04 KST · **실행 주체:** IMPLEMENTER_SELF_RUN / USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY  
**상위 설계:** RT_NEXT_PHASE_SCIENCE_DESIGN_KO.md · **실제 신규 RT 호출:** 0회 (본 요청서 작성은 설계 작업)  
**기준 원본:** PR #33 e69fcdd6123d3d056cd95ea210ac8eb732f17628; Snowball rerun 증거 + 기존 원본 R2/R4/R5 BLOCK_C, CAUSAL_VERIFICATION_PLAN_KO.md / SIMULATION_DATA_REQUEST_KO.md.  
**주의:** 8,224회 성공한 통제 floor/plate 장면과 앞으로 생성할 **원본 6면 corridor 장면**의 H를 단일 원본인 것처럼 연결하면 안 된다.

## A. 구현자에게 요구하는 최종 목표

1. 기존 성공 SM0 raw 32개(16 config ×2)를 **재계산 없이** 경로·포트·FP 단계별 물리 메커니즘으로 분해한다. 성공/음성 사례 194/234/500/525를 모두 분석하고 \(\mathrm{plate}-\mathrm{floor}\) effect를 계산한다.
2. 원래 R2/R4/R5 corridor의 15개 지정 pose에서 ray-resolved Native LoS/Full 채널을 생성한다. 이전 archive H와 같은 포트·장면·solver·phase dtype 아래 수치적으로 재현하고, 경로별 물리 기여 및 FP 변화를 검증한다.
3. 원래 R4·R5의 고정 시간구간에서 오염 발생·유지 상태를 추적할 경로별 RF를 생성한다. 해당 구간은 원래 SAMPLES와 Tnone join 후에만 key를 확정한다.
4. 정확히 같은 (x,y,z)와 동일 물리 조건에서 yaw만 바꾸는 신규 RF counterfactual 데이터를 최소 1개 좌표에 대해 생성할 계획을 설계한다.
5. 기존 R2/R4/R5 경로 오염을 EKF 추정기 prior → innovation → Kalman gain → posterior \((x,P)\)·NEES에 연결할 수 있도록 동일 pose/time/source key의 조인 원장을 만든다. **본 요청의 RT 출력만으로 EKF 성능 개선을 선언하지 않는다.**

성과물 유형: 원본 복소 H·경로 NPZ, SHA256 manifest, 통계/메커니즘 CSV, QA JSON, 실패 목록, 원래 archive parity 및 물리적 주장 가능 범위. 기존 S1V5/C3V5 DEV3의 science/solver 코드와 기존 고정 실패 기록은 **수정하지 않는다**.

## B. 필수 입력 및 정적 검증 (STAGE R0, RT 0회)

### B1. Source & data identity

기존 파일을 직접 열고 SHA256으로 **바이트 단위** 확인:

- Source: PR #33 final SHA e69fcdd6123d3d056cd95ea210ac8eb732f17628; production RT 위상 assemble SHA256 79226718784565a5b7d414350ed2eeb884363ad547654d555065275df5ff9de4.
- Fixed LP+45 source bank NPZ SHA256 **b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b**.
- Fixed LP−45 source bank NPZ SHA256 **39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9**.
- Original 6-wall source: results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/{R2,R4,R5}_aB_m0/MANIFEST.json, scene PLY materials, SAMPLES.json, INPUTS/timeline_R{2,4,5}_Tnone.csv.
- Ground truth: **route+pose_id key**; 원본 시뮬레이션 sample 수와 Tnone 979/742/1415 평가 sample 수의 차이를 인식하고 순서 기반 joining 금지.
- Original Full H: BLOCK_C/FULL_RF/H_R{2,4,5}_aB_m0.npy; original LoS H: BLOCK_C/H_LoS_R{2,4,5}_aB_m0.npy. 원본 자체를 다시 쓰지 않는다.
- One-frequency/bin cannot masquerade as full-band: exact 257 bins, starting 6.2504 GHz and spacing 1.95 MHz, original FFD bank frequency equality enforced.
- Native pinned family: Sionna RT2.0.1, Mitsuba3.8.0, DrJit1.3.1, LLVM mono polarized, original config seed20260924, MaxDepth3 Full, original same source flags, frozen two RX×two TX port order and TX-selection convention.
- Scene mesh/material/anchor.xyz/robot_z/mount/pose GT/coordinate transform exact PLY SHA (new floor+plate scene SHA is NOT a substitute).

If one byte SHA or numeric input is missing, output **BLOCKED_SOURCE** with exact filename; don't fill it from inference and don't generate rays. Original epsilon/calibration offset position, Hann, IFFT n=1028, threshold30%, signed s power channel must have identical frozen version.

### B2. Mandatory initial archived-data-only computation

Input: snowball_20261104/rerun.tar.gz, previous_failure.tar.gz, BUNDLE_SHA256.txt, QA JSON, paired_contrasts.csv. New read-only evidence auditor already passed #41815490532: 151/151 new SHA, 19/19 failed SHA, 32 raw key H/tau rehash and no source mutation.

Implement R0 with **0 new PathSolver invocations**:
- Exact path-count offset, per-frequency complex 2×2 field closure H=sum(ray), and archived H hash.
- Factorial contrasts **C01−C00**, **C10−C01**, **C11−C01** including per-port complex ΔH, delay/phase and power cross term. C10−C00 alone is not the pure plate factor.
- Same-tap fixed vs redetected tap comparison of signed s/r, tap threshold crossing, per-surface path labels and visible/unobservable limits.
- Negative controls 500/525 (C10/C11 exact H equal to C01); C11 pose194 exact H equal to C01; positive 194 C10 tap+1, 234 C10/C11 polarization without tap motion. All four including negatives in the figure/CSV.
- Results that would be different if amplitudes were summed as power must be treated as an implementation bug. Sum complex fields first.

Required output (no RT): R0/R0_INPUT_HASHES.json, R0/R0_RAY_INTERACTIONS.csv, R0/R0_PLATE_VS_FLOOR_H.csv, R0/R0_TAP_RESELECTION.csv, R0/R0_COHERENT_POWER_TERMS.csv, R0/R0_POS_NEG_CONTROLS.csv, R0/R0_QA.json, R0/REPORT_KO.md. Provenance must cite original Snowball failed and success SHA separately.

## C. SM0-B original corridor Native RT, staged and bounded

### C0. Pre-register all 15 pose keys

| Route | exact original pose_id | N |
|---|---|---:|
| R4-B | 168,172,173,194,234,500,525,729 | 8 |
| R5-B | 401,465,979,980,982,983 | 6 |
| R2-B | 525 | 1 |

No pose selection/substitution after seeing RT RF results. Archive pose 525 from R2 and R4 are distinct keys (route matters). All routes Anchor B, mount 0°, **original 6-wall scene**, not controlled 2-object SM0.

### C1. Run split, exact solver calls, proof-of-budget

| Stage | exact scope | Native PathSolver call count | automatic progression |
|---|---|---:|---|
| SM0-B0 | R4-B 194,234 × Full + Native LoS × 257 | **1,028** | no until original archive Full/LoS parity PASS |
| SM0-B1 | remaining 13 route/pose × Full + LoS × 257 | **6,682** | no unless SM0-B0 PASS |
| Combined mandatory | 15 pose ×2 modes ×257 | **7,710** | STOP on gate failure |
| SM0-B2 optional rerun | 4 preselected pose ×2 modes ×257 | **2,056 additional** | separate budget; cannot silently repeat failed pose |

**User self-run approval** must specify N solver calls (including retries), actual CPU/GPU workers, wall-clock deadline per shard, total GPU/CPU-hour cap and storage, and actual billing cap. The numerical cost may be 0 for local hardware but still must be stated. R0=0 calls; B0 approval≠B1 approval.

Observed reference (not guaranteed for original six-wall scene): Snowball's 8,224 calls in 14m55s using four workers on CPU set 0–31, so same throughput would imply ~14m for 7,710 calls. **Original six-wall paths may be more expensive** and queue/startup/data I/O may dominate; cap on actual wall-time, not inferred ETA, is mandatory.

### C2. Source-preserving raw ray outputs

Each (route,pose,mode) output must include:
- Complex ray coefficients a (original dtype), tau in s, per-frequency path offsets/counts/valid, interaction type and object IDs, theta/phi Tx/Rx, path source IDs; frequency index 0..256.
- Full 257×2×2 complex H for Native LoS and Full; original archived Full/LoS column as immutable reference. Zero, invalid and missing paths must remain explicit with statuses.
- Stable path-group id across bins using material+interaction chain+reflection geometry+delay proximity; mark ambiguous matching, don't rename automatically to create desired attribution.
- Receiver ±45 CIR via original Hann and 4×257 IFFT, original threshold, fpFull/fpLoS, rFull/rLoS (raw vs offset-corrected explicitly), sFull/sLoS, per-port powers at both fp taps.
- Same-tap vs detector-change algebraic decomposition and closure residual. Per-path power cross term / leave-one-group-out diagnostic including order dependence and nonadditivity caveat.
- Source lock, original mesh/FFD/Solver SHA, pose ID, Full vs LoS selector, thread/backend seed and available hardware. Never invent physical labels for a ray lacking an object ID.

### C3. Numeric fail-closed tests

- Same original beam/solver config, full 6-surface scene and phase32 archive convention. Strict archive **Native LoS relative L2≤1e−5**, candidate pre-registered **Full relative L2≤1e−3**, original port column and frequency/sampling. The 1e−3 Full value was proposed in the prior source request; freeze before running B0, never adjust after results.
- Reconstructed native complex H vs per-ray recombination: report producer source-precision max rel/max abs and independent high-precision diagnostic separately. The previous controlled pilot's independent cross-dtype maximum was 9.29e−8; do not substitute F64 code into source parity or silently widen hard thresholds.
- Material/mesh SHA, port order, 257 frequency sequence, dtype/units, path delay, finite values, direct path identity and LoS geometrical delay must all match expected originals. Any missing source or one ray-sum error → STOP and keep raw.
- Negative fixtures: swap ±45 bank, flip TX column, perturb one complex coefficient, 1bit SAMPLES, perturb delay/frequency/mesh SHA, missing/duplicate key, field out of pose set, route mixing, zero power FP. All must be rejected.
- Failure status names: BLOCKED_SOURCE; BLOCKED_GEOMETRY; BLOCKED_BANK; NATIVE_LOS_ARCHIVE_MISMATCH; NATIVE_FULL_ARCHIVE_MISMATCH; RAY_COMPLEX_SUM_MISMATCH; FP_EXTRACTOR_MISMATCH; OOB_OR_INVALID_KEY; PASS_TECHNICAL.
- Do not unseal C1/SM1/SM2 based on generic GitHub job success alone: **read original produced QA and SHA**.

## D. SM1 and SM2 after original-corridor parity

**SM1a initial:** R4 33.0–35.2 seconds, R5 195–198 seconds. File hash exact timebase and find all original Tnone pose IDs first; save SM1_KEY_LEDGER.csv and unique pose count **before any solver call**. Required extra calls = N_new_unique_poses×257×2, subtracting previously SM0-B saved keys. Failure in R4 or R5 original archive parity → no SM1. Preserve time event boundaries and 0.2/1/5 s vs 0.1/0.25/0.5/1 m comparative windows, same point yaw/position along actual trajectory.

**SM1b optional:** old proposed R4 0–15, 59–61, 99–105.4 s; R5 79–81, 92–94, 132–135 s; R2 no-tap-shift extreme/negative. This is a separate future approval. Do not select new windows based on which SM1a performed best.

**SM2a:** same XY of archived R4 pose168, robot z and all original six-wall material/FFD geometry fixed. Yaw array [−35.7,0,+35.7,180,original pose168 yaw] degrees. Exact 1 location×(≤5 unique yaw)×2 mode×257 = **≤2,570 calls**; input yaw duplication is represented as no-call duplicate. Confirm collision/valid LoS and hash original x,y at all rotations. SM2b R5 pose982 one more XY can require ≤2,570 additional calls. No interpolation between unrelated R4/R5 coordinates.

Each SM1/SM2 result: original Full/LoS, ray H, port s/FP/r and ground truth orientation, matched model h and Hψ from frozen model *per rad*, absent/unresolved rays, cause label with observed vs hypothesized. SM2 is synthetic physical counterfactual, not a real measured robot yaw.

## E. Offline EKF follow-on interface — requested data, not a new EKF model

After SM0-B original H parity, prepare join ledger for existing MB_VAR C1/C2:
- keys: source_run_sha, route, anchor B, source sample pose_id, Tnone index/t, xGT/yGT/ψGT, Full/LoS RF source SHA, mask, original sensor noise seed.
- C1 fixed one-step prior \(x^-,P^-,H,K,R,\mu\) and observed (rF,sF), (rL,sF), (rF,sL), (rL,sL). Fixed K/mask arm differences in \(\Delta x\) are checked by KΔz and Joseph covariance unchanged **by construction**. Separate gate-recompute arm is optional and explicitly marked as changed policy.
- C2 natural recurrent four-arm filters with identical controls/odom/Q, gate fixed vs self-gate; log innovation NIS, heading Hψ, full posterior 4×4 P, NEES4/XY95/Heading95, first accepted contaminant, recovery before/after windows and history. No future knowledge leaks into filter initialization or thresholds.
- C1/C2 without this exact original source parity still may operate with already pinned Full/LoS, but must be labeled **original composite-channel offline oracle**, not verified ray-attribution cause.

## F. Deliverables, validation and report contract

Root: research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/{POST_SM0_R0,SM0B,SM1,SM2}/. Large immutable raw may reside in another durable GitHub tracked archive but the SHA, source and index must remain usable after Actions artifact retention expires.

| Output | Required contents |
|---|---|
| INPUT_LOCK.json, APPROVAL.json | code/mesh/material/FFD/source original SHA, exact pose/yaw IDs, scene family, solver flags/version/hardware, numeric tolerance, per-stage max calls/hours/storage/cost, self-run authority |
| KEY_LEDGER.csv | every expected key and executed/not-run/failed status; all variants/duplicates/pose collisions |
| RAW_H_PATHS_*.npz | complete 257-bin 2×2 complex H, per-path complex a/tau, native ray path/source/valid/object labels, offsets |
| ARCHIVE_PARITY.csv | per route/pose/mode max abs/rel L2, source FP/port validity and failed rows |
| RAY_GROUP_COMPLEX_CONTRIBUTIONS.csv | complex field/power cross terms, object interaction, leave-one-group fixed-path ablation |
| FP_SAME_TAP_DECOMP.csv | fpF/fpL, same-tap & detector choice, signed s, r meter correction |
| SM1_TIME_EVENT.csv | original time/pose/trajectory indices, delta r/s, path group, causal event timing |
| SM2_FIXED_XY_YAW.csv | verified exact XY, yaw sweep, matched channel, port/FP, Hψ unit |
| FAILED_KEYS.csv / QA.json | all failed and not-run keys, fail reason, source SHA and budget stops |
| RUN_MANIFEST.json | original source commit & bytes, model/versions, runner limits, timing, raw output file SHA256 and evidence location |
| REPORT_KO.md | claims supported/unsupported, negative controls, physical vs algorithmic intervention, what requires more scenes/GT |

**Pre-release gates:**
- No untracked source or missing raw path.
- No CI PASS without exact key coverage and raw artifact SHA.
- No go to higher stages when original LoS/Full archive parity fails.
- No post hoc new effect thresholds/recovery policy in this dataset.
- Two deterministic runs cannot be treated as two independent stochastic scenes.
- HOLDOUT2/reserve remain closed; **EXTERNAL_INDEPENDENT_AUDIT_SIGNED=false**, user-approved self-run exploratory only.
- New simulator generation starts only with explicit stage approval in an immutable budget lock; **this request itself does not run RT**.

## G. 직접 전달용 Codex 실행 지시문

You are IMPLEMENTER_SELF_RUN for MBVAR-PRR-001. Read RT_NEXT_PHASE_SCIENCE_DESIGN_KO.md, the original CAUSAL_VERIFICATION_PLAN_KO.md and SIMULATION_DATA_REQUEST_KO.md, and the accepted SM0 Snowball evidence at PR #33 e69fcdd. Do not change original H/FFD/GT, previous failed records, A010 S1/C3 or old numerical criteria. Work in this strict order:

(1) Build R0 with zero new RT calls from the 32 stored raw H/path receipts and report positive+negative controls.
(2) Freeze the exact original six-surface corridor input and route/pose/source SHA + numeric resource budget. If missing, emit BLOCKED.
(3) Implement/validate a small SM0-B0 two-pose Full/LoS ray-resolved canary and stop on original archive parity fail. Only then authorize SM0-B1 13 more poses. Save all 2×2 complex H/path data.
(4) After full original-scene parity, produce the true Tnone timeline pose ledger for SM1a and collision-verified same-XY yaw ledger for SM2a. Do not generate SM1/SM2 by inventing pose IDs or mixing route geometry.
(5) Deliver immutable raw/checksum/QA and physical mechanism analysis separately from any EKF result. Explicitly label all output USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY.
(6) Stop if any input/port/bank/phase/geometry/source or 257-bin/Full/LoS parity fails. Never silently widen tolerance or discard a failed pose to make a claim.

**Final boundary:** We ask for source-preserving ray-level physical mechanism evidence and a future EKF interface, not immediate new estimator performance claims. If the physical ray provenance cannot be matched to the original archive, the scientific claim is BLOCKED rather than optimized away.
