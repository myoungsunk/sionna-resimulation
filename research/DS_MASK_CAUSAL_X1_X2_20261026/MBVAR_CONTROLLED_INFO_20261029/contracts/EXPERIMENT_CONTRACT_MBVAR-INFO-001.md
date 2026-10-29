# EXPERIMENT_CONTRACT_MBVAR-INFO-001 — proposer draft, NOT FROZEN

| Property | Value / rule |
|---|---|
| ID | `MBVAR-INFO-001` |
| stage | `DRAFT-0.1`; invalid for confirmatory runs until P0 required locks |
| author role | `PROPOSER` |
| goal | State-specific RF information overcount vs true spatial/time covariance, followed by physical Sionna RT mechanism replication |
| base repository | `myoungsunk/sionna-resimulation` |
| base branch candidate | `research/mbvar-e2-e5-revalidation-20261029` — full git SHA must be locked |
| governance commit | `P0_TO_RESOLVE_GOVERNANCE_SHA` |
| full source commit | `P0_TO_RESOLVE_SOURCE_SHA` |
| params | `config/PLAN_PARAMETERS.json` frozen SHA after P0 |
| data isolation | S synthetic field_id, R scene_variant_id nested in family; anchor/path/gyro seeds repeated |
| baseline | 4-state `[px,py,psi,b_g]`, r/s measurement, original `ctl_core` parity |
| prior studies | E4 `H_TC=REJECT` globally; E5 uncorrected information normalization not reusable |

## Registered estimands

**E1 fixed-H covariance effect**: For a fixed linearized `F,H,Q,P0`, compare per-state nuisance-marginalized info/posterior variance with `Σ_corr` vs `Σ_blockdiag` at identical marginal σ. Controlled from ex ante symbolic Σ; repeated independent draws validate theoretical prediction.

**E2 fixed-Σ geometry effect**: For identical `Σ,F,Q,P0`, compare `H_low` vs `H_high` schedules selected from FFD-only pilot using geometry (not residual or RMSE). Physics may not realize fixed-Σ geometry changes; E2 is S0 mathematical experiment.

**E3 geometry×correlation interaction**: 
`DID_a = [log(OC_a(highcorr,LOWgeom))−log(OC_a(lowcorr,LOWgeom))] − [log(OC_a(highcorr,HIGHgeom))−log(OC_a(lowcorr,HIGHgeom))]`.
`OC_a=I_iid,eff(a)/I_corr,eff(a)` on a consistent prior/parameter target; no universal sign preregistered. Compute exact predicted DID from selected matrices **before** noise outcomes.

**E4 estimator consequence**: Under matched synthetic datasets and known true Σ, compare ensemble Heading/rad/tan/XY MSE, posterior covariance calibration and 4-state NEES of IID model and oracle correlated Gaussian reference. No “oracle wins each realization” rule.

**E5 physical RT mechanism**: Within each paired scene variant and exact anchor/pose, compare C00 DIRECT vs C01 FLOOR vs C10/C11 plate complex H, s/r, paths/taps, and the direction of matched state information/accuracy metrics. RT intervention is multifactor (mean/variance/tap) and does not isolate correlation.

**E6 robustness/transfer**: Record B0 and sensor-seed variations without counting them as new RF scenes; final unseen scene variants withheld until estimator and claims frozen. Existing Corridor/Office runs for retrospective diagnostic only.

## Competing explanations and decisive controls

| Explanation | Controlled observation | Distinguishing evidence |
|---|---|---|
| inter-time covariance alone | S0 fixed H/Σ arms | exact predicted OC and Gaussian posterior |
| spatial pose field vs pure temporal drift | same pose, different t / different pose, same elapsed time | pose-field repeated exactly; OU varies with t |
| H/J variation | S0 fixed covariance, swapped H | conditional state information change |
| RF mean and distance dependent variance | S1 primary zero mean constant σ; R reports raw mean and σ separately | eliminate confounding from synthetic primary, quantify in physical |
| r/s cross-correlation | C_rs=I then c=.3 | per-state info sensitivity |
| geometry/model linearization | full FFD h/H vs exact finite differences, ell remainder | report large nonlinear error |
| tap switching | raw tap index and first-path discontinuity | separate strata, do not delete |
| gate selection | no-gate/fixed/self separate | changes from gate are not called covariance-only effect |
| gyro/odometry | paired sensor seeds, same paths | within-field repeated effects |

## Acceptance tests (technical, non-scientific)

- `MATH-01`: same/opp analytic ratios at rho=.9 `.5263157894736842`, `10.0` within 1e−10.
- `MATH-02`: symmetric PSD covariance operator; max asymmetry ≤1e−12 scale-normalized, eigenvalue min ≥−1e−10×largest eigenvalue on canary N≤32; Cholesky with explicit diagonal jitter policy or STOP.
- `MATH-03`: correct normalized information `D^T I D`, validated under m↔cm and rad↔deg unit transformations within relative 1e−10.
- `DATA-01`: identical canonical `(scene, anchor, pose, solver)` yields identical `H` digest; pose GP spatial part equal within 1e−12.
- `DATA-02`: marginal variance invariant under low/high correlation arms to relative 1e−12 by construction. Monte Carlo sample covariance is approximate and uses predeclared tolerance set from field-trial power, not a blanket deterministic ±10% rule.
- `FILTER-01`: original MB_VAR on R4-B and R5-A B0 state+P full-trace parity ≤1e−10 absolute to pinned reference (if input version mismatch -> BLOCKED_INPUT).
- `RF-01`: direct-only and floor distinct path counts; full/LoS complex reference differences preflight-defined in `P0_TO_RESOLVE_DIRECT_PARITY_TOL` and frozen *before* canary.
- `RF-02`: no invalid robot/anchor pose, unreported blocking, invisible path, or changed 2×2 port/channel convention; if unsupported -> STOP.
- `LEAK-01`: no train/development/test overlapping `field_realization_id` or `scene_variant_id`. Matching repeated anchors within scene retained in one fold.
- `REPRO-01`: all frozen config/source/scene/pose hashes and raw output manifests preserved; failures are tracked.

## Candidate experimental values (all PLAN; not physical truth)

- `rho_S0 ∈ {0,0.5,0.9}`; `sigma_S0=1` for analytic proof.
- S1 `sigma_r=.05 m, sigma_s=.02`, `alpha_high=.7`, `ell_p=.5m`, `ell_psi=20°`, `time-alpha=0`, `c_rs=0`; white control `alpha_p=0,alpha_w=1`.
- Negative controls: `alpha_t=.3`, `tau∈{1,5}s` (synthetic-only), `c_rs=.3`, same pose exact revisit.
- Anchors A=(2,2,2.65), C=(6,10,2.65), B=(10,2,2.65) reserve; robot z=.45, mount=0°, 12×12 m world.
- Paths T1 x=2..10 y=6 yaw0; T4 sinusoidal y=5.5+.8sin(2π(x−2)/8) tangent yaw; T5 (6,6) spin 0..360° step 5°, initial=final same physical pose.
- Track R canary C00/C01/C10 at no more than 288 unique pose-anchor-scene configs plus exact pose identity QA; actual budget require user approval before higher-scale RT.

## Units and interventions

All code must log whether an effect changes H, covariance, measurement mean, observation selection, time, Q and gate; **no intervention may be described as single-factor unless all other components invariant**. 

## Expected scientific verdicts (labels only, no declared outcome)

- `SUPPORTED`: evidence satisfies preregistered effect/uncertainty conditions in S0/S1 and/ or R, exactly specifying which track.
- `MIXED`: mechanism works in some geometry/scene conditions but not global; R5-B-type harm reported.
- `NOT_SUPPORTED`: pre-specified expected quantitative effect not observed with valid data and sufficient power.
- `INCONCLUSIVE`: insufficient independent realizations, PSD/geometry mismatch, model nonidentifiability, or unresolved covariance fitting.

No exact effect-size/CI threshold for physical R may be assigned until **P0_TO_RESOLVE_EFFECT_SIZE** from pilot/design power is frozen before holdout. A missed threshold is not a technical runtime failure.

## Lock/STOP fields (required before a run can be called confirmatory)

`P0_TO_RESOLVE_GOVERNANCE_SHA` ; `P0_TO_RESOLVE_SOURCE_SHA` ; `P0_TO_RESOLVE_MATERIAL` ; `P0_TO_RESOLVE_HGEOMETRY` ; `P0_TO_RESOLVE_DIRECT_PARITY_TOL` ; `P0_TO_RESOLVE_FINAL_SPLITS` ; `P0_TO_RESOLVE_RF_BUDGET` ; `P0_TO_RESOLVE_EFFECT_SIZE`.

Science-affecting fields (`GOVERNANCE_SHA`, `SOURCE_SHA`, `HGEOMETRY`, `FINAL_SPLITS`, `EFFECT_SIZE`) block S0/S1 until resolved and science contract freeze. RF-only (`MATERIAL`, `DIRECT_PARITY_TOL`, `RF_BUDGET`) may instead be resolved and frozen in a signed **pre-P3 RT amendment**, but no canary/bulk RT may run without exact config and a numerical budget. P0_PREFLIGHT is allowed with DRAFT contract hash, audit only.
