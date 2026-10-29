# 구현 준비 완료형 신규 실험 실행 계획 — MBVAR-INFO-001

**작업 역할**: PROPOSER. **현재 상태**: `DRAFT-0.1/PLAN_ONLY`. No code or RF runs executed by this authoring handoff. The frozen contract is the sole numerical authority after sign-off. **계약 ID**: `MBVAR-INFO-001`.

## A. 문제 정의와 허용되는 주장

- **Q1**: 같은 H, Q, R marginal, 샘플 시각에서 시간/공간 잡음의 cross-time Σ만 바꿀 때 각 상태의 조건부 정보량이 어떻게 변하는가?
- **Q2**: 같은 Σ에서 다른 관측 H를 택하면 정보량의 중복/상쇄가 어떻게 변하는가?
- **Q3**: 실제 pose-dependent RF 잔차와 시간-only OU는 왜 달라야 하며 정적 RT에서 무엇을 물리적으로 재현할 수 있는가?
- **Q4**: correlated-covariance-aware estimation이 기대 MSE 및 posterior calibration에서 독립오차 모델보다 합리적인가?
- **Q5**: 새로운 reflection scene과 anchor/trajectory pairing에서 동일 메커니즘의 부호가 유지되는가?

**이 계획의 부정 명제**: lag-1 ACF만으로 실제 중복 정보량 산출 불가; static ray-tracing의 ACF는 독립 temporal drift가 아님; block permutation E4 `H_TC REJECT`를 '상관 없음'으로 쓰지 않음; 하나의 FOGM으로 모든 경로 성능을 개선한다고 가정하지 않음.

## B. 잠금 원칙

1. GitHub 기존 root `AGENTS.md`를 덮어쓰지 말고 append router만 제안. 모든 작업자는 고정 `governance_git_sha`와 `contract_sha256`를 사용.
2. 이전 연구 `mbvar_control_correction_20261029`, `mbvar_premodel_diag_20261029`, `reflect_model`, `pol_bias_model`은 **read-only**. 새 실험은 `MBVAR_CONTROLLED_INFO_20261029/` 하위로 작성.
3. New pose dataset에는 예전 packet-keyed µ/R을 전용하지 않는다. S primary `mu=0`, known Σ; R primary `mu=0` physical model discrepancy and independently calibrated empirical covariance if needed.
4. 3개의 데이터 용도: train/calibration (`CAL`), design/dev (`DEV`), final confirm (`HOLDOUT`). Scene/field IDs disjoint; manifest에서 SHA 고정. 홀드아웃을 먼저 열어보고 설계 바꾸면 다시 새 홀드아웃을 예약해야 하며 과거 자료는 DEV로 격하.
5. 위상·신뢰구간·시간창·원시 시드 모두 기록. 0과 NA와 미실행은 다른 상태.

## C. 기존 자산 정확 경로 및 우선 참조

| 항목 | 저장소 경로 / 브랜치 정보 | 사용 범위 |
|---|---|---|
| 기존 E4 신뢰성 대조 | `research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/results/run_40820579727/DECISIONS.json` | 기존 주장·반례, 새로운 독립 holdout 아님 |
| 재귀 기준 필터 | `research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py` | 수치 산술/parity 로깅 참고 |
| RF/FFD 비교 코드 | `research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/{common.py,refl_model.py,PROTOCOL_REFLECT.md}` | RF h, range, Jacobian, complex channel 규약 |
| 기존 상태 전파 | `research/EKF4_RANGE_S_STAGED_20261014/core.py` | f/F/Q 식, 버전 잠금 |
| 원시 관측 추출기 | `results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/observation.py` | `s` signed first-path, port processing, optional receiver noise |
| 기존 RT scene 정의 | `src/qclean_uwb/scenarios/{corridor,office,ply}.py` on `claude/office-e-layout` | geometry sheets/material examples; 새 브랜치에 존재 여부 별도 확인 |
| E5 교정 | `research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_e2_e5_revalidation_20261029/revalidate.py` | 정규화·동역학 검산, 과거 미교정 eigen값 재사용 금지 |

모든 행에 실제 source commit SHA와 blob SHA를 P0 manifest에 기록. `AGENTS.md` 내용은 현재 q_clean 원본 연구 관련 규칙을 포함하므로 파괴하지 않는다.

## D. 실행 단계별 정확한 범위·출력·승인 규칙

| Gate | 구현자 작업 | 필수 산출물 | 반드시 만족할 조건 |
|---|---|---|---|
| **P0** | 수학/입력/pose 기하 전제 검증 | `P0_PREMISE.json`, `P0_POSE_LEDGER.csv`, `P0_PARITY.json`, `P0_SOURCES.json`, `P0_GEOMETRY.csv` | root/source SHA 고정, noise-free identity, µ 구분, original MB_VAR X/P parity, legal poses and H rank; 미확정 임계치 동결 전 R 금지 |
| **P1 S0** | 해석해+4-state 선형 Gaussian 정보량 | `S0_UNIT_TESTS.json`, `S0_INFORMATION.csv`, `S0_ORACLE_PARITY.csv` | analytic same/opp .52631578947/10; full Σ vs blockdiag difference independent; prior/Q-aware posterior agree |
| **P2 S1** | pose random field+OU+iid, paired Monte Carlo | `S1_COVARIANCE_QA.json`, `S1_FIELDS.json`, `S1_RESULTS.csv`, `S1_STATS.csv` | same exact pose same spatial field; marginal variances fixed; Σ PSD; no look-ahead; paired field_id preserved; state-specific information and ensemble calibration audited |
| **P3 R canary** | C00 direct / C01 floor / C10 parallel, limited pose | `RT_CANARY_QA.json`, `RT_BUDGET_RECEIPT.json`, `RT_POSE_KEYS.csv`, `RT_PATH_LEDGER.csv` | correct complex H/full-direct, tap/s/r, reflection counts, LoS policy, no collision, measured throughput; user approved budget before scale-up |
| **P4 R limited** | C10/C11 + A/C, T1/T4, paired sensor seeds | `RT_PHYSICAL_CONTRAST.csv`, `RT_CONFOUNDER_LOG.csv`, `RT_SCORE.csv` | physical co-changes recorded; no “correlation-only” conclusion; every scene unit hashed |
| **P5 R confirm** | reserved unseen scene variants and family-level replication | `HOLDOUT_SPLIT_LOCK.json`, `R_CONFIRM_STATS.csv`, `CAL_MODEL_HASHES.json` | holdout not used in tunings; ≥ target independent scenes from pilot power calculation; no across-packet iid CI |
| **P6 T/release** | retrospective Corridor/Office plus new holdout report | `FINAL_CLAIM_MATRIX.md`, `AUDIT_REPORT.md`, `RELEASE_MANIFEST.json` | independent auditor verdict, claim-register updated; retrospective vs confirmatory distinction maintained |

### Gate transitions

- P0_PREFLIGHT runs under **DRAFT** with recorded draft hash and produces evidence to resolve contractual placeholders; if tests fail, stop. After P0, proposer and independent auditor freeze the science contract before S0. No synthetic/RT performance claim before freeze.
- S0 algebra fail → stop S1 and RT model inference. Do not tune numeric thresholds after seeing outputs.
- S1 PSD, matching or repeat-pose identity fail → stop. Physics canary can proceed independently only with explicit `NO_S1_MECHANISM_CLAIM`.
- P3 RT direct parity fail → do **not** run plate scenes for scientific conclusions. Predeclared source extractor tolerance and RT computational acceptance are separate checks.
- P4 uncontrolled tap/LoS/gain variation → log as co-change; if matching requirement cannot hold, revise the causal claim, not silently exclude.
- P5 no independent scenes → descriptive only; never say confirmed generalization.
- G6 reviewer `REVISION_REQUIRED/REDESIGN_REQUIRED` → no release promotion.

## E. Synthetic S0 and S1 exact factorization

### S0 (no physical RT)

Baseline test `rho ∈ {0,0.5,0.9}` with scalar `H_same=[1,1]^T`, `H_opposite=[1,-1]^T` and `Σ=σ²[[1,rho],[rho,1]]`. Compare `I_corr/I_iid`: 1/(1+rho) vs 1/(1−rho). `rho=.9` expected same=.5263157894736842, opposite=10 exactly at tolerance 1e−10.

Then choose two **fixed 4-state Jacobian schedules** from FFD candidate poses using only h/H and prior, not RF or achieved errors. In experiment `S0-COV` hold F/H/Q/P0/times fixed and vary only Σ. In `S0-H` hold Σ/F/Q/P0/times fixed and vary only H schedule. Compute full Q-aware batch posterior and marginal state precision, not only J^T Σ^-1 J.

### S1 (physically realizable pose-correlated synthetic residual)

`ε_i = D [sqrt(αp)u_pose(q_i)+sqrt(αt)u_time(t_i)+sqrt(αw)u_iid(i)]`, with `αp+αt+αw=1`; each component has same normalized cross-channel C, pose and time kernels specified in SCIENCE_SPEC. Use primary config: `(αp,αt,αw)=(0,0,1)` vs `(.7,0,.3)`, `ell_p=.5m`, `ell_yaw=20°`, `c=0`, `σr=.05m`, `σs=.02`. **Both cells identical per-packet variances.**

The GP is sampled over all possible experiment pose indices once per `field_id` before path extraction. If the same pose appears twice, reuse its spatial random draw (not two independently generated draws). Other paths/anchors see the same field only if contract explicitly assigns the same `field_id`; otherwise evaluate within-env dependence and group correctly.

Use S0 exact fixed-Σ geometry contrast to isolate geometry; S1 physical pose contrast may change Σ and therefore must be labeled `geometry+pose covariance interaction`. 10 field draws pilot followed by at least 30 independent draws in frozen confirm, subject to pilot power calculation without opening holdout.

**Additional negative controls:** `(αp,αt)=(0,0)` white; `αt=.3` and `τ=1s,5s` for synthetic temporal drift; `c=.3` for r–s covariance. Do not include all combinations in primary 2×2; additive predeclared sensitivity runs.

## F. Geometry and pose generation — deterministic candidate set

- Frame: new 12×12m test room, floor z=0; robot antenna z=.45m, anchor z=2.65m, mount=0°. Robot body 0.6×0.4m; minimum wall/plate clearance checked before registration. Anchor A=(2,2,2.65), B=(10,2,2.65), C=(6,10,2.65). **A and C are primary**; B is reserve and must not be cherry-picked based on RF outcome.
- Common global path (same for both anchor contrasts): `T1_HORIZONTAL`: x=2..10, y=6, yaw=0; compute at exact planned 0.05 m arc-length intervals, with first/last pose included.
- `T4_S_CURVE`: x=2..10, y=5.5+0.8*sin(2π(x−2)/8), yaw=atan(dy/dx); arc-length resample at ≤.05m. Do not use yaw offset incompatible with differential drive.
- `T5_SPIN`: stationary pose `(6,6,z=.45)` with yaw 0,5,10,...,355,360 degrees. The initial/final 0°/360° poses are the **same physical pose** but distinct timestamps; spatial field and static raw RF must match. A 5° sampling step is an **initial budget proposal**, not a guarantee of no first-path discontinuity; dense yaw refines only after canary and amendment.
- `T6_RETURN` only after P0 exact same-pose visit test. Traversal reversal normally changes robot yaw by π and is NOT same pose; identical `(x,y,ψ)` must be explicitly repeated or revisited after full 360° orientation return.
- `T2_TANGENT`, `T3_ARC` add only if G0 low/high preflight matching requires; define them before examining Track S/R performance.
- Target `Δd` combinations feasible on .05m ledger: `(v=.1m/s,dt=.5s)`=.05m, `(.1,1.0)`=.1m, `(.2,.5)`=.1m, `(.2,1.0)`=.2m. Other combinations cannot use .05m discrete pose grid without new RT. Do not interpolate complex channels at off-grid poses.
- Geometry classification: use FFD-only fixed derivative and **corrected** 4-state prior/Q-aware conditional state information, and 30 s windows. Candidate LOW/HIGH must have same number of measurements, same timestamps and distance distribution within predeclared 0.5m median absolute mismatch. If infeasible, mark `BLOCKED_GEOMETRY_MATCH` and amend candidate paths **before any S1 outcomes**.
- Do not assume `T1` is always LOW and `T4` HIGH. Actual H determines class; no old E5 eigenvalue can select them.

## G. Track R physical RT — exact initial geometry and controls

### Scene constants (proposed P0 lock)

- `C00_DIRECT`: direct-only ray contribution, zero reflection/refraction/diffuse, use same 257-frequency grid and FFD port setup for both paths.
- `C01_FLOOR`: single concrete slab sheet 12×12 m at z=0; include direct + floor specular. Do not call it direct-only.
- `C10_PLATE_PAR`: `C01` + vertical 2.0m(w)×2.7m(h) single slab, center `(x=6,y=1.5,z=1.35)`, plane parallel to x axis, approximate thickness `.005m` for specified conductive model. Note: exact metal/PEC parameters must be resolved against supported RT material before freeze (`P0_TO_RESOLVE_MATERIAL`).
- `C11_PLATE_OBL`: same plate center/area/material, rotate about z by +45°, keep z/span; checks for scene boundary, LOS blockage and presence of specular path.
- `C12_MATERIAL`: replace C10's plate material with named ITU material and frozen thickness only after controlled material compatibility/RT parity canary.
- `C20_ROOM`: add 4 wall sheets and ceiling; only after pilot physical QA.

### RF implementation contract

- Pin `Sionna RT 2.0.1` as **proposed version** then verify actually installed version/API in P0. Ray depth=3 (reflection/transmission config frozen), diffuse/diffraction OFF in primary. Number of frequency bins 257, two RX ports, two TX ports if source convention provides; tag port/LP polarization basis and bank SHA.
- For each exact pose/anchor/scene compute paired `H_FULL`, `H_DIRECT` (no carrier changes). `r,s` = original observation extractor semantics: Hann window, zero-pad×4, first-path threshold 30%, signed two-port power ratio, range calibration offset as in old source. `s` range [-1,1], raw tap index and received powers logged. Record blocked or invalid path as explicit outcome, no drop.
- Materials in Sionna may be slab half-spaces/finite thickness; do not infer metallic reflection coefficients from a material label without test. Scene with a single plate must not inadvertently double-count front/back slab surfaces.
- Pose key for caching = sha256(canonical JSON with scene SHA, anchor position/rotation, robot 3D position/yaw/mount, bank SHA, frequency grid SHA, solver config SHA, source version SHA). Duplicate keys reuse H exactly; missing keys force new RT calculation. **No unverified interpolation**.
- P3 canary budget: at most 24 poses per T1/T4 × 2 anchors × 3 scenes = 288 pose–scene–anchor configurations, plus T5 repeat-pose QA. This is a **hard proposal cap**, not a duration promise. Before bulk, benchmark actual throughput and memory and ask user to approve a numeric RF budget.

## H. Information metrics and statistical evaluation

- 1-state analytic ratios and 4-state conditional information use normalized `D^T I D` (D fixed physical state scales). Nuisance p_r,p_t,ψ,bg removed by Schur complement when appropriate; include prior and Q to avoid false observability conclusions.
- `OC_a=I_iid_eff/I_corr_eff` (states radial, tangent, ψ, gyro bias), plus posterior marginal covariance ratio. The primary response for experiment interaction is a **difference-in-differences of log OC**, evaluated only where identifiable. No universal monotonicity imposed.
- Compare exact synthetic oracle batch GLS/smoother vs IID model on **ensemble** expected MSE and calibration; no requirement that oracle wins for every realization. Existing MB_VAR is an exploratory practical filter benchmark with fixed gate and separately self gate.
- Independent unit for inference: Track S `field_realization_id`, Track R `scene_variant_id` within `scene_family`; sensor seed and packet/anchor/path repeated. Predefined paired effect/cluster-robust CI with effect threshold set before holdout. Pilot sample size n=10 and confirm ≥30 are **proposals**; formal sample power and cost receipt must be signed off before P2 confirm.
- Track R report: raw H, path count, visibility, tap index, r/s means+variance, pose/spatial ACF, r/s simultaneous covariance, normalized information, and Heading/rad/tan/XY filter RMSE. Mean/variance changes must be reported alongside correlation changes.

## I. CI and independent audit

- GitHub CI must implement `VALIDATE_CONTRACT`, `VALIDATE_INPUT_LOCK`, `CHECK_MATH_UNIT`, `CHECK_POSE_IDENTITY`, `CHECK_BASELINE_PARITY`, `CHECK_OUTPUT_MANIFEST`, `CHECK_NO_TRAIN_TEST_OVERLAP`, `CHECK_CLAIM_REFS`. A documented green workflow is only mechanical QA.
- Pre-run audit verifies mathematical control and partition, reruns independent 1D information derivation and process-noise batch calculation.
- Post-run independent auditor samples at least 1 path/seed from each cell, re-evaluates raw H→z, GPS/pose identity, posterior info and confidence intervals without reusing all implementation helpers.
- Verdict states `ACCEPT_WITH_BOUNDARIES / REVISION_REQUIRED / REDESIGN_REQUIRED / BLOCKED_EVIDENCE`; no self-audit promotion.

## J. Unresolved decisions that MUST be frozen in P0

- `P0_TO_RESOLVE_GOVERNANCE_SHA`: install governance docs; lock full SHA and contract hash.
- `P0_TO_RESOLVE_SOURCE_SHA`: pin exact qclean RT source branch/blob and observation extractor + banks.
- `P0_TO_RESOLVE_MATERIAL`: choose supported plate material, thickness, conductivity or PEC setting with RT calibration and validation; do not hardcode unverified RF physics.
- `P0_TO_RESOLVE_HGEOMETRY`: identify physical candidate LOW/HIGH H schedules under same sample count/times and unobserved-truth criteria; freeze pose ledger.
- `P0_TO_RESOLVE_DIRECT_PARITY_TOL`: set per-quantity raw-H, s, range tolerances before canary; use existing recorded tolerances as initial guides but do not claim equivalence before test.
- `P0_TO_RESOLVE_FINAL_SPLITS`: reserve independent scene variation seed list and field test seeds before any confirmatory run.
- `P0_TO_RESOLVE_RF_BUDGET`: measured canary throughput, GPU/memory limit, user-approved total pose cap.

**None of these can be silently filled from evaluation results.** Once frozen, reference the amended, immutable version for every run.

## K. Low/High geometry candidate selection algorithm (deterministic, no outcome use)

The first version must not let the implementer simply label T1=LOW/T4=HIGH. Exact P0 rule:

1. Use only physically valid P0 FFD `h,H` and controls, predeclared path candidates (T1, T4, plus T2/T3 if a signed amendment was made **before** S1/R results). Anchors A/C are compared at the same poses; valid scene coverage only.
2. Generate candidate non-overlapping 30.0s windows at `dt=.5s`, `N=60` observations/window, speed `.1m/s` for moving paths. Controls, P0/Q, RF observation variance and baseline model source are fixed. No predictor uses true **RF residuals**, filter RMSE or first-path outcomes for selecting geometry.
3. For each candidate, compute the exact linearized Q-aware batch posterior, rotate state position to radial/tangent at window reference anchor and then get nuisance-marginalized posterior precision `I_eff_psi` and `I_eff_tan`. Use `D^T I D` unit normalization. Report separately before/after prior.
4. Define scalar geometry score `G = (1/2)log(I_eff_psi/I_eff_psi_prior) + (1/2)log(I_eff_tan/I_eff_tan_prior)` only when both ratios positive and all matrix tests pass. This score is a **selection heuristic**, not a physical truth/claim metric.
5. Enumerate ordered candidate low/high window pairs: matching `N=60`, identical relative time grid, anchor-relative range median difference ≤0.5 m and range IQR difference ≤0.5 m; no overlap in used pose indices if within the same candidate path. Sort pairs by greatest `G_high−G_low`, break ties lexicographically by `(anchor_id,trajectory_id,window_start_s)` and choose the first pair. Record ALL candidate scores, failures and chosen pair; do not drop excluded windows silently.
6. If the candidate set yields no pair, return `BLOCKED_GEOMETRY_MATCH`. The proposer must amend the candidate set (T2/T3) without looking at Track S/R response outcomes; repeat P0 and freeze updated choice before actual experiments.
7. S0 fixed-Σ geometry contrast uses selected two H schedules with identical F,Q,P0 and time; **do not carry over different physical motion F** into a “H-only” experiment. S1 pose-world comparison may include different F and Σ and must label joint physical change.

For stationary spin, dynamic speed/time differ from moving geometry windows; treat it as separate diagnostic stratum, not forcibly matched to 30s moving windows.

## L. Numeric label meanings

- `P0_TO_RESOLVE_*`: required deterministic P0 audit or proposer sign-off; this is a **STOP**, not permission for the implementer to improvise.
- `proposed`: numeric draft value, may change only via signed amendment **before** a final held-out test.
- `frozen`: protocol and data split hashed; changing input/code requires an amendment and separate run manifest.
- `oracle`: calculation using true synthetic generative Σ and/or scoring truth; **not deployable**.
- `fitted`: covariance estimated on independent calibration scenes (not exact Σ).
- `independent`: field seed for S; scene variant nested in scene family for R. A/B/C anchor or trajectory variation is repeated conditional measurement, never a new independent environment.
