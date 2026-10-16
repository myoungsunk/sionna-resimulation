# 04. 누락 입력에 대한 Sionna / FFD / Sensor-v2 시뮬레이션 요청 사양서

**문서 상태: REQUEST SPECIFICATION / DATA NOT YET GENERATED.** 입력이 없을 때 임의 보간, 파일 이름만으로 샘플 존재 추정, original data 대체 성공 선언 금지. 이미 존재하는 동결 R2/4/5 데이터는 새 독립 scene으로 취급하지 않는다.

## 1. 시뮬레이션 우선 요청 목록

| 요청 | 목적/해결하는 Blocker | 필요한 모델 | 현재 상태 |
|---|---|---|---|
| **SIM-A: Original complex FFD bank + near-pole direct channel** | F0 θ=0 source physics, $\theta\ge2^\circ$ interpolation gate FAIL, $\hat q_\mathrm{LoS}$ antenna pattern | 원래 TX(+45 LP) / RX(±45 LP) FFD의 complex $\mathbf E_\theta,\mathbf E_\phi$ vs frequency/angles and rotation calibration | **필수 · SOURCE MISSING** |
| **SIM-B: R4/R5 authentic or clearly regenerated synchronized motion inputs** | Existing R4/R5 P2 static RF paired packets와 4-state recursive Sensor-v2 controls 대응 | Real t/pose/gyro/wheel sequence, motion and original sensor seeds, or a **newly generated** labeled sensor-v2 control sequence | **필수 · TIMED INPUT MISSING** |
| **SIM-C: independent Sionna multipath scenes/trajectory** | F6/F7 external scene generalization, rare FP/reflector mismatch, temporal/site effects | Multi-material/layout ray tracing, actual full two-port complex H(f) **per pose/yaw**, corresponding native LoS packet, multiple RF seeds | **필수 · INDEPENDENT SCENE MISSING** |
| SIM-D: hardware transfer diagnostics | Claim of real DW1000 deployment, gain/AGC drift, FP tap robustness | Recorded matched hardware CIR registers/gain/sensor time calibration | **Optional** for simulation-only publication; indispensable for hardware-ready claim |

Priority for next execution: SIM-A acquisition request immediately; SIM-B/C generation specification and scene split frozen before fitting. F2/F4/F5 original-dataset exploratory can run while waiting, but their independent science conclusions remain locked.

## 2. SIM-A: FFD raw bank and polar singularity physics

**Source sample:** Original HS LUT source source/src/qclean_uwb/drivesim/hs_lut.py with 257 frequency bins and existing HsLut. Existing original hs_lut_2deg.npy has shape [46,180,180], float64, theta_deg 0,2,...90 and phi_tx/rx -180,-178,...178. Existing original LUT SHA256:
711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079.

**Required raw data** (not interpolated scalar s from old table):
- For each named original TX/RX port pattern, complex FFD $E_\theta(f,\theta,\phi),E_\phi(f,\theta,\phi)$, coordinate convention (spherical theta/phi basis), global Cartesian orientation and rotation matrices, complex phase reference, amplitude/polarization calibration and frequency axis. Include per-file SHA; antenna mounting $\beta_\mathrm{mount}$ and physical aperture coordinates.
- Original TX0 +45LP (the full H has TX two polarizations if simulated; preserve 2×2 port order), RX0/1 ±45LP, Anchor boresight down rotation diag(1,-1,-1), RX yaw rotation, robot z=0.45m, anchor z=2.65m for original replay.
- Direct H(f) from actual source FFD at positive theta 0.1,0.25,0.5,1,1.5,2,3,5 degrees, azimuth seam -180/178°, robot yaw grid and mounts 0/45° plus 15/30° probe, horizontal rho 1mm,1cm,0.03839m,0.1m,0.15m,0.3m; all source patterns and absolute gain.
- For each source generated H(f), run EXACT original FP observer Hann window, 4N zero-padding IFFT, stronger-RX peak 30% first edge, common FP tap, $P_1,P_2,s,r$. No arbitrary q normalization after the fact.
- Additional off-pole sample bank (theta 2–90; stratified near 2/60/90 and phi grid boundaries) to re-evaluate existing 500-point F01 interpolation; original gate max 0.023972 >0.01 must be documented and remedied or reasoned limitation.
- Range: original no-retuned bias B_OLD -0.5315983906250129 m from 150 directions and its direction variation. The physical 10m reference-distance effects and first-tap delay staircase must be included in direct-H vs model tests.

**Output artifacts:**
1. FFD_SOURCE_MANIFEST.json (port naming, freq list, geometric rotation and gain convention, source/version/hash), raw ffd-banks in versioned NPZ/Zarr.
2. FFD_DIRECT_POLE_GRID.parquet or CSV: (theta, phi_tx, phi_rx, mount, yaw, direct s, direct r, direct P1/P2/tap, old LUT h, pole-candidate h, analytic Jacobian, finite-difference Jacobian, source seed).
3. SOURCE_BUILT_LUT_[revision].npy + metadata/sha and original NPY preserved.
4. F01_INTERPOLATION_QA.json with distribution median/p90/p99/max and specified threshold reason; pass/fail true from numerical source checks, not manually changed.
5. Reference R5 AnchorB pose_id706 true s −0.946821 and 9,519 original native LoS source-matched comparisons as regression tests.

**Physical caution:** At theta=0 the spherical azimuth basis is undefined. Simply re-evaluating θ=epsilon at fixed arbitrary phi without carrying the correct global orientation can reproduce the old gauge mistake. Source model must project Cartesian fields consistently first.

## 3. SIM-B: R4/R5 4-state gyro/wheel dynamic stream

**Existing data:** R4/R5 archived RF observations, LoS LUT and GT sample sequence with some timestamps/pose IDs. But authentic synchronized Sensor-v2 wheel/gyro controls and original generation provenance needed to call original dynamic recursive run matched. Do not infer missing controls by reconstructing from SAMPLES and present as original measured stream.

**Required per chronological frame k (strict one-to-one time/pose join):**

| Column / array | Shape | Unit / notes |
|---|---|---|
| scene_id, route_id, anchor_id, mount_deg, source_revision | per run | stable identifier |
| t_s, dt_s | [N], [N] | strictly increasing, usually 0.2s intervals; dt[0]=0, others >0 |
| pose_id | [N] integer | unique, exact RF same pose ID |
| truth_pose_xy_yaw | [N,3] | x/y m, yaw rad; GT only offline generator/scoring |
| ds_true, dtheta_true | [N] | GT physical controls, generator-only |
| ds_odom_m, dtheta_gyro_rad | [N] | estimator receives **only these measured streams**, gyro includes defined bias and white noise |
| true_bias_rad_s | [N] | offline evaluation only |
| motion_config, sensor_seed and gyro/wheel noise source revision | metadata | B0/L0/L1/L2 true Bias 0,+.01,+.05,+.2deg/s and negative counterparts where requested |
| original first-path observer ID/config | metadata | synchronized with RF |
| input_source | per sequence | "AUTHENTIC_ORIGINAL" or "REGENERATED_SENSOR_V2" explicit |

If authentic streams are irrecoverable, create **new** controls using original source SensorV2Config/generate with declared true trajectory/time/seed and mark provenance "REGENERATED_SENSOR_V2". Can run new valid simulation experiments, but cannot claim archival original R4/R5 output parity. Do not claim new source controls are real TB3 hardware measurements. Verify generator reproduces known reference R2 seed0 only in a separate canary.

**Target scenarios:** R4 anchor A/B Mount0 and R5 anchor A/B Mount0, paired Full/Native LoS; expose both ORIGINAL_R0 and SOURCE_BUILT_LUT for old/new label comparisons. Training and evaluation must still be scene-disjoint for independent generalization—R4/R5 same corridor not external scenes.

**Acceptance:** synchronized join exact; no N>1 duplicate/timestamp reverse; motion convention explicitly legacy-Euler vs SE2 (previous mean discrepancy is not free random Q); positive definite dynamic covariance; latent GT stripped from estimator input.

## 4. SIM-C: new independent Sionna multipath scenes (HARD gate for paper)

### Desired splits and sample counts

Predefine at least **2 physical train scenes + 1 validation scene + 3 independent locked test scenes** (6 minimum distinct RF layouts). If only 3 scenes total are available, treat as feasibility pilot; do not label independent performance generalization. Prefer ≥5 true independent test scenes for meaningful scene-block CI.

Per scene:
- Distinct room/corridor/wall reflection layout/material/roughness/diffuse/scattering/ceiling constraints, not just a translated copy of R2. Independent anchor placement/height/orientation and different obstruction types. Store scene geometry YAML/JSON, material parameters and ray tracer version/seed.
- Path families: forward straight, exact reverse traverse, S/curved, turn 90°, stationary with yaw sweeps (e.g. −20°→+20°), near-anchor traversal $\theta\in[0,2]$ and otherwise representative $\theta>2$.
- Mounts: original 0°/45° plus heldout 15°/30° as design targets; relative TX–RX antenna orientation/LP ports physically maintained. Some cases may be intentionally low-information near LUT ambiguity.
- Gyro Bias: 0, +0.01, +0.05, +0.20 and negative matched levels, independent sensor noise seeds (target >=5 per full RF scene), but independently regenerated **RF multipath realization seeds and geometry/material** must also be provided.
- At least one 5Hz (dt .2s) 160–280s trajectory sequence per path family/scene; number of actual poses N documented, not silently reused from R2. Training/holdout composition balanced by mount and geometry, with explicitly unseen mount stress.
- No stage may peek at locked scene test metrics before architecture/parameters/gate rules are committed. Test performance can only be viewed once per frozen candidate and revising after failure requires new heldout scenes.

### Channel arrays at each k (Full and corresponding native LoS)

| Variable | Format | Meaning |
|---|---|---|
| freq_hz | float64 [257] | canonical original 6.2504–6.7496GHz range and per-bin actual values; hash |
| H_full_f | complex128 [N,257,2,2] | per-pose/per-real-yaw ray-traced complex response, receive port, transmit port; record original Tx0 selection |
| H_los_f | complex128 [N,257,2,2] | matched same position/yaw physically generated Native LoS only, not the scalar s LUT |
| r_full_m, s_full | float64 [N] | identical canonical FP detector, same packet |
| r_los_m, s_los | float64 [N] | matched native counterpart, same detector and gain calibration |
| fp_tap_full, fp_tap_los | int [N] | selected common tap, detector threshold/status |
| fp_P1/2_full, fp_P1/2_los | float64 [N,2] | selected same common tap energy |
| full/los_FP_quality | per k | noise_std, strongest_RX, leading tap/margin, detector_s_span, any hardware-available analogue with documented provenance |
| source seed and Sionna revision | metadata | ray tracer, interference, materials and reflection order |
| input motion/control arrays | as SIM-B | exact time/pose matching with each RF packet |

**Creation requirement:** generate actual Full H(f) at every requested pose and yaw via ray tracing; rotating only LoS FFD LUT cannot manufacture multipath's angular variation or qualify for active scan validation. Full and Native LoS must differ *only* in declared propagation channel condition, not by different unrelated sensor noise or incompatible first-path extraction. Keep the complex channel noise-free reference and generated receiver noise separately available.

### Repeatability and stress
- Replay each matched pair under common gain +/−3/6dB, per-port gain imbalance, port group delay, FP threshold 20/30/40%, 1/3/5-tap energy. Keep true physics and generated observation variants separately; do not silently modify source H.
- Time/space persistence: revisit identical pose under different independent multipath seeds (if static scene unchanged, a deterministic ray tracer should reproduce same H; temporal stochasticity requires a declared physically varying object or receiver noise). Distinguish fixed-site systematic bias from independent random process.
- Profile compute/time/memory; frequency and spatial sampling enough for old Native LoS vs scalar LUT source checks.

**Output file naming:** SCENE_{scene_id}/{route}/{anchor}/{mount}/{rf_seed}/{sensor_seed}/ with MANIFEST.json, GT_OFFLINE.npz, SENSOR_INPUTS.npz, H_FULL_COMPLEX.npz, H_NATIVE_LOS_COMPLEX.npz, OBS_FULL.npz, OBS_LOS.npz, FP_QUALITY.parquet/CSV, metadata and per-blob SHA256. Stable primary key (scene_id, route_id, anchor_id, mount, rf_realization_id, sensor_seed, pose_id,t_s,channel), unique at its grain; avoid duplicate sampling as independent rows.

## 5. SIM-D (optional) real DW1000/robot hardware transfer

When claiming hardware deployability, request logged raw CIR/FP registers and time-aligned wheel/gyro from actual hardware, gain/AGC state and calibration pulses, antenna port gain and relative delay, actual first-path tap and available cir/noise terms, temperature if available. No RF-port coherent phase assumption unless physically calibrated. Hardware sensor data cannot be replaced with Sionna model arrays in hardware claims.

## 6. Input acceptance script requirements for next execution

- Source/asset SHA and schema validation first; complex H finiteness, shape/freq/units; RX/TX port order and original TX0; original two-port observer parity.
- Same anchor/mount/pose/time exactly paired Full/LoS, source GT separate; no uncontrolled future/GT features in deployable model.
- Physics guards: FFD $\theta\to0^+$, azimuth/yaw seam, 1-mm polar ring, range first-path delay vs B_OLD; Jacobian FD. Angle/observer correctness before training model.
- Scene hashes fully disjoint across train, validation, locked test; RF seed independence vs sensor seed independence explicitly separate; scene-wise sample counts, effective independent unit and cluster metadata.
- No missing FFD, motion or ray-traced channels quietly replaced by LoS LUT or inferred sensor streams. Report BLOCKED_INPUT plus exact missing hashes/files and proceed with previously available independent stages.

## 7. Minimal complete request to the simulator team

Deliver:
1. **Original FFD complex banks** and new source-generated pole consistent LUT with direct observer validation (SIM-A).
2. **R4/R5 time-aligned verified or transparently regenerated Sensor-v2 controls** paired by pose_id with already archived RF (SIM-B).
3. **≥6 fully distinct Full multipath RF scenes** with corresponding LoS, true complex channels at actual yaw/position, sensor seed streams, source manifests/hashes, split specification and independent test lock (SIM-C).

These three deliverables are the minimum to claim final external scene validation of a new, physically corrected POWER_JOINT method. If only SIM-A/B become available, limit paper to source correctness and single-corridor empirical mechanism study; report missing generalization faithfully.
