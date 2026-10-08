# PREREG 수정 기록 (S0)

원본 `PREREG.json`(커밋 `02009ca`)은 수정하지 않는다. 변경은 이 파일에만 추가한다.

## A1 — G1은 production 설정(`--threads 1`)에서 판정한다 (명확화, 완화 아님)

- 원 문구: G1 "H 상대 오차 ≤ 1e-6". thread 수는 명시하지 않았다.
- 관측(`REFERENCE_CHECK.json`, 같은 position x7.0_y0.0, yaw 0/50°):
  - `--threads 1`: 저장 H와 **오차 0.0**(비트 동일, 65 bin × 2 yaw).
  - `--threads 4`: pose별 상대 오차 3.2e-6, bin별 최대 1.2e-5 → **원 임계값 1e-6 미달(FAIL)**. 원인 추정: 병렬 reduction 순서(float32 비결합성).
- 조치: production A안은 기존 scan 방식대로 단일 thread 프로세스 4개 병렬(`corridor_scan2_run.sh`)이므로 G1은 `--threads 1`에서 판정한다. 임계값 1e-6은 그대로 두고, `--threads 4`는 production에서 쓰지 않으며 FAIL 결과를 그대로 기록한다.

## A2 — S1 설계 결정 (RF/필터 결과를 보기 전에 확정)

원 PREREG에서 모호했던 부분을 구현 전에 고정한다. 모두 `assumption`.

1. **Probe 주기 T는 "주행 시간(drive time)" 기준.** probe 시간(7.2 s)은 주행 시간에 포함하지 않는다. 따라서 위치·주행 heading은 T와 무관하고, T∈{10,20,60}의 probe 위치는 T=10의 부분집합이다 → RF 계산 집합은 T=10 기준 상위집합 하나로 충분하다.
2. **Truth는 kinematic으로 일관.** 위치는 heading을 따라 적분한 unicycle 경로다(`p_{g+1}=p_g+0.04·(cosψ_g, sinψ_g)`). heading 흔들림 때문에 y가 y₀에서 ±수 cm 벗어난다. (직선 경로 + heading 흔들림은 odom 모델과 모순이므로 쓰지 않는다.)
3. **Heading 흔들림은 주행 시간의 함수**: `w(τ)=A·sin(2πτ/T_w+φ)`, A=4°, T_w=12 s, φ는 고정 seed(20261007)에서 한 번 뽑는다(truth는 Monte Carlo seed와 무관). 제자리 회전(probe, 끝 지점 180° 회전) 동안은 흔들림을 고정(hold)한다.
4. **경로 길이**: x₀=1.2 m, 편도 440 step(17.6 m), step 0.04 m. 흔들림에 의한 x 이동 감소와 허용영역 [1,19] 경계 여유(약 0.2 m)를 확보하기 위해 18 m 대신 17.6 m로 한다.
5. **끝 지점 180° 회전**: 25°/s(probe와 동일), 5 Hz 표본당 5° → 36 표본, `turn_phase` flag.
6. **Probe 표본열(36 표본 = 7.2 s)**: 현재 heading 기준 상대 yaw `[−5…−45](9) + [−40…+45](18) + [+40…0](9)`. 한 probe에서 서로 다른 yaw는 19개(−45…+45, 5° 간격).
7. **y₀∈{0, 0.35}**: y₀는 적분의 초기값. 안테나 world yaw = 몸체 yaw + 장착 offset. Lever arm 0이므로 안테나 위치 = 몸체 위치.

## A3 — 앵커 수직축 정확히 위에서는 B안이 퇴화한다 (S2 개발 중 발견, parity 결과 집계 전)

- 관측: 위치 (4.0, 0.0)(앵커 바로 아래, 수평거리 0)에서 B안(trace/pattern 분리)이 A안과 H 상대 오차 1.5e-2로 어긋난다(경로 수 51, 정상 63). 수평거리가 y=1e-4 m이면 1.2e-3, 1e-3 m이면 1.1e-4, 5e-3 m 이상이면 ≤1.8e-5로 사전 등록 G2 기준을 만족한다. LoS 단독은 정상(1.9e-5), 반사 경로가 수직 입사로 퇴화하는 것이 원인으로 추정(미확정).
- 조치(결과를 보기 전의 규칙): (a) 궤적 생성기가 수직축까지 수평거리 ≥0.01 m를 강제한다(`check_anchor_axis_clearance`; 현재 궤적 최소 0.0266 m / 0.3764 m). (b) parity gate의 기준 위치 중 수직축 위(수평거리 <0.01 m, 즉 (4.0, 0.0))는 G2 집계에서 제외하고 보고서에 `excluded_on_anchor_axis`로 남긴다. (c) G4 위치를 (5.5,0.35), (11,−0.5), (15,0)으로 바꾼다((4,0) 제외).
- G2 임계값은 변경하지 않는다.

## A4 — S4 (h_s LUT) gates, fixed before the real-bank LUT is built

- LUT grid: θ 2° over [0°, 90°], φ_tx and φ_rx 2° over [−180°, 180°) (the plan's φ 5° is replaced by 2°: with 5° ideal-dipole banks gave a max interpolation error of 3.5e-2, with 2° 5.4e-3).
- Gate L1 (interpolation): over 500 random points with θ∈[5°, 85°], \|s_LUT − s_direct\| max ≤ 1e-2 and median ≤ 1e-3.
- Gate L2 (LUT vs Sionna `max_depth=0`, 8 random corridor poses, 257 bins): \|Δs\| max ≤ 5e-3. The LUT uses a 10 m reference link, so a sub-tap position difference is part of this number.
- Reported (no pass/fail): LUT-vs-full-simulation mismatch σ_s along the trajectories, overall and by \|ds/dyaw\| bin (feeds the filter's R_s; the earlier branch value was about 0.09).

## A5 — Filter design decisions (S5), fixed before any filter run on RF data

1. **Non-identifiability.** During straight driving at constant speed the gyro bias `b` (proportional to time) and the wheel diameter-ratio error `ε` (proportional to distance) enter the odometry-vs-gyro heading difference identically; they are separated only by absolute heading (`s`) or by stationary rotation. Tests on model-consistent synthetic data showed that with prior σ_b = 0.3 dps the odom/gyro fusion alone gives 10–30° heading RMS even at the *lowest* drift level, whereas gyro-only heading gives 0.4–1.7°.
2. **Priors** are taken from the sweep populations (RMS over the three levels), identical for all conditions and baselines: σ_b = 0.12 dps, σ_SF = 1.04 %, σ_ε = 0.64 %, initial pose σ_θ = 5°, σ_xy = 0.1 m. No per-condition tuning.
3. **Extra baseline "gyro-only"** (`use_odom_heading=False`: heading from the gyro increments only, odometry used for distance): added next to the fused "odom+IMU" baseline, because the fused baseline is weak by construction (point 1). H1 is evaluated against both; the fused one is the pre-registered primary comparison, the gyro-only one is reported as the stronger-baseline sensitivity.
4. **Measurement noise the filter is told:** range R = σ_r² + quantisation (tap spacing 0.149 m, uniform) + (0.05 m)²; s R = delta-method thermal variance from the *measured* tap powers + σ_mismatch²; σ_mismatch = 0.09 until S4 reports the measured value (then the measured value is used for all conditions at once). Gate: χ²₁ 99 % for range and s, 99.9 % for the odometry heading pseudo-measurement (slip).
5. **Range model offset:** the first-path range is quantised (taps 0.149 m) and biased by the 30 % leading edge; the filter uses a constant offset computed from a flat-spectrum LoS channel passed through the same chain, averaged over distance (no trajectory data).

## A6 — S4 gate L1 result (real FFD banks, 2° grid; local development run, deterministic so the Snowball build must reproduce it)

- 500 random points, θ∈[5°, 85°]: **max |Δs| = 0.0240 (threshold 1e-2: FAIL)**, median 5.3e-4 (threshold 1e-3: pass); 5/500 points exceed 1e-2, 14/500 exceed 3e-3.
- All five exceedances sit near |s| ≈ 0 – 0.2 at specific (φ_tx, φ_rx); the cause is not smooth interpolation error but jumps of the first-path chain (the 30 % leading-edge tap changes between neighbouring grid cells), which a trilinear table cannot follow.
- The threshold is **not** changed. The effect is far below the filter's mismatch component (σ_mismatch ≈ 0.09), so it is carried as a known limitation of the LUT; a finer grid would reduce the width of the affected cells but not remove the jumps. The measured trajectory-level mismatch σ (S4 report) is the number the filter uses.

## A8 — G3 refinements found on the full-route traces (local development run, before any parity/filter result was inspected)

1. **Equal-image sequences are one path.** `end_x_max>floor>end_x_max` has the same image as `floor` (two mirrors in the same plane cancel); `wall_y_neg`/`wall_y_pos` coincide on the corridor axis. Labelling by nearest delay therefore flipped between such names and produced ~540 spurious "set changes". The signature now merges image delays closer than 1e-13 s into one class (named after the shortest member). Set changes are reported after this correction.
2. **Delay tolerance.** The pre-registered 5e-14 s (S0 A-block, `classify_paths` default) was checked in S0 at x=7 and the corners (max residual 2.2e-14 s). Over the whole route one path (x=11.4273, y=0.0400, τ=2.16e-7 s) has residual **5.15e-14 s**, i.e. float32 delay rounding of a long path, not a missing image. Result under the pre-registered tolerance: **1 unmatched path → strict G3 fails**; the report additionally gives the result at 2e-13 s and the smallest gap between *distinct* image-delay classes (about 1e-13 – 2.4e-13 s, i.e. comparable to the float32 delay noise: labels of such nearly identical paths can be ambiguous, which is harmless for path-set continuity). The pre-registered threshold is not edited.
3. Trace file tags are built from positions rounded to 6 decimals (as the task lists); the continuity script now rounds the same way (a tag mismatch had produced 13 spurious "missing traces" per lateral).
4. `unmatched` is no longer a condition for assembling the H store (it is judged by G3 only).

## A7 — Experiment constants fixed before the first evaluation run (values from the local development traces; the Snowball run reproduces the inputs)

1. **SNR levels: 30 dB and 10 dB** (nominal per-bin SNR of a unit-gain free-space link at 10 m, 6.5 GHz; the realised median is +3.9 dB higher because of the antenna gain, p10 −8 dB below the median). From `DEV_LOCAL/S3/SNR_CALIBRATION*.json` (lateral 0, mount 0): 30 dB → s noise std 0.020, range noise 0.042 m, first-path index flips 0.7 %; 10 dB → s noise 0.073, range 0.107 m, flips 11 %; 5 dB → s noise 0.15 and range noise 0.72 m (index flips 14 %) was judged too harsh. Detection was never the limiting factor (≥99 % even at 0 dB, because of the 257-bin processing gain).
2. **Filter mismatch sigma σ_mismatch = 0.18** (overall RMS of the LUT-vs-full-simulation residual over both laterals and both mounts, `DEV_LOCAL/S4/LUT_MISMATCH.json`: n = 3668, bias +0.037, σ 0.176, rms 0.180; the branch's earlier value 0.09 was for another geometry). One scalar for all conditions; it is computed on the same routes that are later evaluated, which is disclosed here.
3. **Position process-noise slack** `pos_process_std` (random walk per 0.2 s step, protects against overconfidence from correlated range errors): chosen from {0, 0.002, 0.005, 0.01} m as the value whose mean NEES on `range_s_P0` and `range_s_P1_T20` is closest to 3, using a **calibration set disjoint from the evaluation set**: lateral 0.35, mount 0°, drift 0–2, SNR 30 and 10 dB, seeds 1000–1009. The evaluation uses seeds 0–49 only. The chosen value and the calibration table are appended to this file before the evaluation run.
4. Range σ_r = 0.05 m (sensor) with the filter told 0.05² + quantisation (0.149 m/√12)² + 0.05². Range offset = −0.5316 m (LoS-only chain with the FFD banks, `hs_lut_meta.json: range_bias`).

### A7 result — calibration of `pos_process_std` (local development run, calibration seeds 1000–1009, lateral 0.35, mount 0°; 540 runs per value)

| pos_process_std [m] | mean NEES range_s_P0 | mean NEES range_s_P1_T20 | median heading RMSE P0 / P1 [deg] |
|---|---|---|---|
| 0 | 448.6 | 86.5 | 8.31 / 2.71 |
| 0.002 | 193.0 | 41.2 | 7.46 / 2.39 |
| 0.005 | 119.0 | 23.2 | 7.42 / 2.34 |
| 0.01 | 93.3 | 15.7 | 7.55 / 2.44 |

Rule (closest to NEES 3) → **pos_process_std = 0.01 m**. The filter is nevertheless **not consistent**: NEES stays 5–30 times its expected value of 3. This is reported as a result, not tuned away: the s residual of the corridor (σ ≈ 0.18) is strongly correlated along the route, so a white-noise measurement model with R = 0.18² is overconfident. No further tuning is done (it would break the pre-registered procedure).

## A9 — Additional routes R2/R4/R5 and a second anchor (user request; registered before any result on the new routes exists)

**Scope (user decisions).** Space = the existing 20 m × 2.4 m corridor. R3 (straight line y = 0) is the existing R1 and is not repeated. Anchors: A (ceiling x = 4 m, y = 0, the original) and B (ceiling x = 10 m, y = 0). Each anchor is a separate single-anchor system (TX +45° port); no fusion of the two. Matrix per route: anchor {A, B} × mount {0°, 45°} × drift {low, mid, high} × SNR {30, 10 dB} × seeds 0–49, baselines and filter set exactly as in v1.

**Routes (nominal paths; speed 0.2 m/s, 5 Hz, 0.04 m steps, heading wobble ±4° / 12 s on drive time, in-place corner turns at 25°/s, probe rule unchanged).**
- R2 rectangle / loop closure: start (1.2, −0.45) → up to y = +0.45 → right to x = 18.8 → down to y = −0.45 → left back to x = 1.2. Four 90° corner turns.
- R4 zigzag: lanes ±0.45 m, heading alternates +35.7° / −35.7°; 14 legs of 0.9 / sin 35.7° = 1.542 m, x from 1.2 to ≈ 18.7 m; 13 corner turns of 71.4°.
- R5 serpentine: three lanes y = +0.45, 0, −0.45 of 17.6 m, joined at alternate ends by 0.45 m cross legs; start (1.2, +0.45); two 90° turns at each end (four turns in total per cross leg pair).
Leg lengths are rounded to whole 0.04 m steps; the truth is kinematic (position integrates the heading incl. wobble), so loops are not exactly closed.

**Guards.** Region |y| ≤ 0.74 m, x ∈ [1, 19]; horizontal distance to each anchor's vertical axis ≥ 0.02 m (method B degenerates exactly on the axis, A3). The wobble phase seed is the first of 20261007, 20261008, … that satisfies both guards; the chosen seed is stored in the timeline manifest.

**Predictions registered now (two-sided tests, same statistics as H1–H4):**
- H5 (mount, passive P0): the antenna yaw is heading + mount and the slope of s is largest at 45°/135°. R1: heading 0°/180° → mount 45° better. R2: headings 0°/90°/180°/270° → mount 45° better. R5: same as R1 on the lanes, 90° on the cross legs → mount 45° better. **R4: headings ±35.7° → mount 0° better** (yaw 35.7° is near the steep point, mount 45° puts the yaw at 9.3° and 80.7°, both flat).
- H6 (loop closure, R2): range + s reduces the loop-closure error ‖x̂_end − x̂_start‖ (the true displacement is ≈ 0) versus odom + IMU. Reported for every route as the displacement error ‖(x̂_end − x̂_start) − (x_end − x_start)‖.
- H7 (anchor): anchor A vs B heading RMSE — no direction registered, reported as exploratory.
- H1/H2 are re-evaluated per route.

**Constants.** SNR levels, σ_mismatch (re-measured on the new routes and anchors and then fixed once for all conditions) and pos_process_std = 0.01 follow A7; the σ_mismatch re-measurement is disclosed to use the evaluated routes.

## A10 — Paths that vanish inside the band (found by the anchor-B parity run, before any anchor-B result was compared)

- Observation: with anchor B (x = 10 m, the corridor centre) every checked position lost one path between bin 144 and bin 150 (63 → 62 paths; the same in all five positions). The path (τ = 25.7 ns, 7.7 m) has |a| = 7.0e-6 against a total of 1.79e-3 (0.4 %, −48 dB) and Sionna drops it from the PathSolver output above that frequency. Method A contains the same drop (it is the solver's output), so method B must reproduce it. Method B v1 required an identical path set at all nodes and therefore marked every such position unusable (`PATH_SET_CHANGED_WITH_FREQUENCY`).
- Rule (fixed now): paths are aligned across nodes with a *union* reference (a path missing at a node gets J = 0 there; a path new at a node is added to the reference). A position stays usable if every path that is absent at some node has a relative amplitude (‖a_iso‖ / ‖all paths‖ at the nodes where it is present) **≤ 1e-2**; otherwise the status remains `PATH_SET_CHANGED_WITH_FREQUENCY`. The largest dropped-path amplitude and the nodes where paths are absent are stored per position (`dropped_audit`).
- The G2/G2'/G4 thresholds and the decision rule are unchanged; the anchor-B parity (A direct vs B at 5 positions × 7 yaws) is the test of this rule.
- Re-trace semantics: `rf_b_trace.py` recomputes an existing trace file whose status is not `OK`.

### A10b — screen replaced by parity evidence (written after seeing the dropped-path amplitudes, before any parity result for them)

The first anchor-B run showed that the same path (a frequency cut of the solver above ≈ bin 150) is dropped at every position, with relative amplitudes 0.7 % (x = 7), 2.9 % (x = 2) and 3.5 % (x = 17.5), i.e. two of five positions exceed the 1e-2 screen. A fixed amplitude screen says nothing about the effect on the quantities the experiments use, so it is demoted to a *reported flag* (`screen_exceeded`, `max_dropped_rel_amp` in every trace receipt and in the G3 report). The validity of method B with dropped paths is decided by the anchor-B parity run (A direct vs B, 17 nodes) with the unchanged G2' thresholds (|Δs| ≤ 2e-3, first-path index ≥ 99.5 %, range ≤ 2 mm) **and** it must include the positions with the largest dropped amplitude (x = 2.0 and x = 17.5). If it fails, method A is used for anchor B. Traces keep status `OK`; the zero-filled path is a faithful copy of the solver's behaviour at the nodes, and the interpolation across the cut is the only approximation.

### A10c — anchor-B parity result and the cut refinement (the parity gate itself is unchanged)

Anchor-B parity with the zero-filled union (A10b): 35 poses at 5 positions, **|Δs| max 0.0113 (G2' threshold 2e-3: FAIL)**, H error median 3.2e-4 / max 4.9e-3, first-path index 100 % equal, range difference 0. The failing position is x = 17.5 (3.5 % dropped path); the step of the dropped path between two nodes 16 bins apart is smeared by the cubic interpolation. Remedy (applies to every position with a dropped path): the bin at which the path disappears is located by bisection (≈ 4 extra solver calls) and added as a node; the interpolation treats that path piecewise (spline through the nodes where it is present, exactly zero where it is absent). Gate thresholds and the decision rule (A used for anchor B if this parity fails) are unchanged.

**A10c result (local development run):** with the cut refinement the anchor-B parity passes at all five positions (35 poses, yaws −50°…230°): H error median 2.5e-5 / max 5.9e-5, **|Δs| max 1.2e-5** (threshold 2e-3), first-path index 100 % equal, range difference 0. This includes x = 2.0 and x = 17.5 (dropped path 2.9 % / 3.5 %). Anchor-A traces without dropped paths are bit-identical to the v1 traces (regression check: Jones difference 0.0). Method B is therefore eligible for anchor B under the unchanged decision rule; the Snowball run repeats this parity (`routes-parity`).

## A11 — Exploratory (not pre-registered): `s` from the total received power per port instead of the first-path power

Question (user): does computing `s` from the received power of each RX port (rx power) instead of the first-path (FP) tap power improve the result? v1 and the added routes use FP power: `s = (P1 − P2)/(P1 + P2)`, `P = |CIR[first-path tap]|²`. Variant "rx": `s_rx = (E1 − E2)/(E1 + E2)`, `E_i = Σ_bins |H_i(f)|²` of the TX +45 column (all paths, multipath included), with the thermal-noise bias `n_bins·σ²` subtracted from each E. For a fair comparison the variant gets its own LoS-only LUT (same grid, same banks) and its own measured mismatch σ; range still comes from the FP chain; the noisy channel is the same draw for both. Same filter, priors, `pos_process_std = 0.01`, drift/noise seeds. Reported as exploratory: the local development H stores of R1, seeds 0–9 (not the 50-seed evaluation), so only the direction and size of the difference count.

**A11 result (exploratory, local development H stores of R1, seeds 0–9, 1,440 paired runs; `DEV_RESULTS/S_MEASURE_COMPARISON_FP_VS_RX.json`).** The rx-power `s` is **worse** than the first-path `s` in 11 of 12 mount/baseline cells and about equal in none: LoS-only model mismatch rms 0.301 (fp: 0.180); heading noise implied per measurement 18.3° (fp: 12.2°); heading RMSE median for range+s (P0) 28.3° vs 6.7° at mount 0° and 1.97° vs 1.38° at mount 45° (rx is better than fp in only 23 % of the paired runs there); probes do not repair it (T=10 s: 5.9° vs 1.6° at mount 0°). Reason: the total received power adds the whole multipath energy of every port, while the first-path tap isolates the direct component that the LoS-only model describes. Conclusion: keep the first-path definition.

## A12 — Defect in the G3 continuity script for the added routes (found by the user's review of the Snowball snapshot; corrected before any route-experiment result was inspected)

`path_continuity.py` counted only rows with phase `drive_out`/`drive_back` (the R1 names) as stations. The timelines of R2/R4/R5 use phase `drive`, so the script read **0 stations** and reported `passed` for an empty set (`stations: 0`, residual 0.0, 0 set changes) in all six Snowball G3 files (snapshot `01a11669/…134706Z`, ROUTE_DECISION `G3_strict: true`). Those six passes carry no information. Fix: `drive` is a station phase, and an input without stations now aborts with `NO_STATIONS_FOUND` (an empty check cannot pass); unit tests cover both naming schemes. On the real R4 / anchor A traces of the development run (412 of 547 positions available) the corrected script gives: 2 unmatched paths at the pre-registered 5e-14 s (max residual 9.4e-14 s), 0 at 2e-13 s, 36 path-set changes — i.e. the strict G3 fails again, as for R1, and the relaxed tolerance passes. `routes-continuity` must be re-run on the Snowball traces (seconds; no Sionna) and its result, not the old files, enters the decision. Using the relaxed 2e-13 s tolerance for the routes needs the same explicit authorisation as for R1.

## A13 — Exploratory (not pre-registered): value of the TX/RX angle model — LoS-only LUT versus the ideal curve `s = −cos 2·yaw`

The v1 filter predicts `s` with the LoS-only LUT `h_s(θ, φ_tx, φ_rx)` built from the FFD banks, i.e. it corrects for the transmit and receive angles of the antenna patterns. Ablation: the same EKF with the **ideal** curve (ideal ±45° ports: `s = −cos(2(φ_tx + φ_rx)) = −cos 2·yaw_antenna`, no dependence on θ and no pattern). Each model uses its own measured mismatch σ against the noise-free simulated `s`; everything else (noise draws, drift, priors, `pos_process_std`) is identical. R1 development H stores, seeds 0–9.

### A13 result (R1 dev H stores, seeds 0–9, 4 lateral × mount combos, SNR 30/10, drifts 0–2, EKF; `DEV_RESULTS/ANGLE_MODEL_ABLATION.json`)

Exploratory only, not a pre-registered test. Replacing the LoS-only angle-corrected LUT h_s(θ, φ_tx, φ_rx) by the ideal curve s = −cos 2·yaw (σ_mismatch re-fitted for each model):

- mismatch rms vs. noise-free simulated s: LUT 0.180, ideal 0.294 (the ideal curve ignores the pattern-dependent TX/RX angle response and the multipath that the LUT's LoS term does not represent either).
- median heading RMSE, range+s P0: mount 0° LUT 6.70° vs ideal 18.49°; mount 45° LUT 1.38° vs ideal 8.04°; odom_imu reference 7.64°.
- with probes the gap widens at mount 0° (T10: 1.62° vs 17.31°); the ideal model is better than the LUT in 0–18 % of paired runs depending on baseline (≈0 % for range_s_*).
- Conclusion: the TX/RX angle correction in the LUT is what makes `s` usable as a measurement; with the uncorrected ideal curve the filter is worse than odom+IMU in most conditions. Placeholder sensors and simulation only; R1 dev stores, not routes.

## A14 — Routes: relaxed G3 tolerance (2e-13 s) authorised by the user; G3 evidence for R2/R4/R5 (registered after the corrected re-run, no experiment result changed)

The user explicitly approved the relaxed 2e-13 s tolerance for the routes (the earlier approval covered only the R1 B-restart). Evidence is the corrected `routes-continuity` re-run on the unchanged Snowball traces (`SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/`; all 12 H stores and 37 S6 files verified byte-identical, no S6 re-run):

| route | stations | unmatched @5e-14 s (strict, pre-registered) | unmatched @2e-13 s (relaxed) | max residual [s] | path-set changes | min gap between distinct image delays [s] |
|---|---|---|---|---|---|---|
| R2 (anchor A / B) | 925 | 1 / 1 | 0 / 0 | 5.1e-14 / 5.8e-14 | 53 / 51 | 2.6e-13 / 2.4e-13 |
| R4 (A / B) | 547 | 3 / 3 | 0 / 0 | 9.4e-14 / 8.2e-14 | 44 / 33 | 1.03e-13 / 1.05e-13 |
| R5 (A / B) | 1343 | 9 / 9 | 0 / 0 | 1.01e-13 / 9.7e-14 | 106 / 103 | 1.03e-13 / 1.15e-13 |

Status wording to be used in every report: **strict (pre-registered 5e-14 s) G3 FAILS for all six route/anchor combinations; relaxed (2e-13 s, user-authorised) G3 passes.** The pre-registered threshold is not edited and the strict failure is not removed from the record. The old six "passes" (A12) stay void.

Limitation, stated as in A8: for R4 and R5 the smallest gap between distinct image-delay classes (≈1.0e-13 s) is below the relaxed tolerance, so labels of such nearly identical paths can be ambiguous. G3 judges path-set continuity (no path appears/disappears unmatched), for which this is harmless, but it is not evidence that individual paths keep their labels. `B_G3_eligible_after_recheck: true` applies only under the relaxed tolerance; `scientific_PASS` stays false (L1/L2 FAIL, strict G3 fail, NEES over-confident, placeholder sensors).

## A15 — Corrections after the independent audit (`INDEPENDENT_AUDIT_20261008/`): P0 documentation and code defects (no result file, threshold or evaluation was changed)

Scope: audit minimum plan P0 items "claim/provenance correction", "G3 evidence completion" (code part) and "GSF mathematical stability". No RF run, no filter run for evaluation, no S6 rerun. Every stored result (R1, routes, G3 recheck, ANALYSIS) was produced by the earlier code and stays as published; the code changes below apply to future runs only.

**Code defects fixed**
1. **GSF split (audit F08).** The old `DriveFilter.reseed` shrank only `P[2,2]` and kept the position-heading cross terms, which can give an indefinite component covariance (audit counterexample block `[[1,.8],[.8,1]]` → min eigenvalue −0.245; reproduced in `tests/test_drivesim_filters.py`). New rule: the component means are shifted along `u = P[:,2]/sqrt(P[2,2])` (heading shift `z_i·σ`, correlated position shift) and every component keeps `P − t·u uᵀ`, `t = Σ w_i z_i²` (capped at 0.95; the shift is rescaled by `sqrt(cap/t)` when the cap is active). `P − u uᵀ` is the Schur complement and PSD, so every component is PSD for any correlation, and the mixture mean and covariance equal the input (tests: k = 2, 3, 5, 9, 21; correlations 0, 0.5, 0.95, −0.9; heading-floor path). Consequence: the GSF numbers in the stored R1/routes results (filter-type comparison on `range_s_P0` and `range_s_P1_T20`) were produced with the old rule and are **not regenerated**. Incidence of the defect on R1 development data (`scripts/drive_sim/gsf_psd_incidence.py`, lateral 0.35, mounts 0° and 45°, drifts 0–2, SNR 30 dB, seeds 0–4, 60 GSF runs, 120 reseed calls): the legacy rule gave **0 indefinite matrices** (smallest eigenvalue 2.4e-8, i.e. numerically at the PSD boundary). This is a small development sample, not the production runs; production incidence stays UNKNOWN. Whether to re-run the GSF rows is left to the user.
2. **G3 report (audit F03/F04).** `path_continuity.py` stored only the first 50 set changes. It now stores all of them (`set_changes`, count `n_set_changes`) and lists every station with a residual above the pre-registered tolerance (`strict_unmatched_stations`: tag, position, number of unmatched paths, max residual). Pass/fail logic and tolerances are unchanged. The root-cause review of the changes (which image class appears/disappears) is still open and needs the Snowball traces.
3. **Parity gate coverage (audit M01).** `parity_gate.py` computed G2/G2' pass/fail only from the rows that existed; stored reference positions without a trace or with a non-OK trace were listed but did not fail the gate. Now `coverage_complete` is a check and a missing/unusable position fails the gate. The stored reports had empty `missing`/`unusable`, so no stored verdict changes.

**Statements corrected (documentation only)**
- Anchor height is **z = 2.65 m** (`height_m − anchor_standoff_m`, ceiling 2.7 m); A=(4,0,2.65), B=(10,0,2.65). Computation always used 2.65. PLAN.md/guide/figure text said "2.7 m anchor". A2 and the geometry texts that say "ceiling" mean this.
- **R2 has three 90° corner turns, not four** (A9 line "Four 90° corner turns" is wrong; the timeline has 3 turn segments; R4 13 and R5 4 are correct). The pre-registered A9 text is not edited retroactively.
- NEES: "20–40×" was inaccurate. Audit values: mean pose NEES for `range_s_P0` ≈ 43.7 (R1) / 44.2 (routes) vs expected 3 (≈ 14.6×); route means R2/R4/R5 = 73.6/13.5/45.5.
- H1 must be quoted against **both** baselines: R1 19/24 vs odom_imu, 18/24 vs gyro_only (2 cells worse); routes 66/72 vs odom_imu, 62/72 vs gyro_only (4 worse). `odom_imu` is the weak baseline of A5.
- Probe results (H4) are a combined effect of the extra stationary time (R1 elapsed 183/198/241/306 s for P0/T60/T20/T10), extra observations and the manoeuvre, not an equal-time-budget or information-only gain (audit F09).
- **A14 chronology.** A14 said the relaxed tolerance was authorised for the routes and that it was registered after the corrected re-run. The user's re-run record (`ROUTE_DECISION_CORRECTED.json`) already carries `authorized_tolerance_s: 2e-13` and its README refers to an earlier approval, while the approval that A14 cites was given in the working conversation after the re-run log had been read. The repository does not establish the exact time of the human approval (audit M04: UNKNOWN). A14's "authorised" stays, but nothing here claims the approval preceded the S6 run or the re-run.

**Not changed / still open (audit P1/P2):** L1/L2 FAIL, NEES inconsistency and its causes (reused gyro increments, unmodelled wheelbase error), in-sample σ_mismatch, anchor-B production coverage, truth-near initial prior, probe fairness re-analysis, hardware validity. Old pre-fix GSF rows are unchanged. `scientific_PASS` stays false.

## A16 — Diagnostic re-analyses requested by the independent audit (F09 probe fairness, F10/F11 observability); definitions fixed **before** any number below was computed

Status: exploratory/diagnostic, CPU only, no RF, no filter change, no threshold, no new hypothesis test. Nothing here replaces H4/H5 or any stored result. Audit P1 items "probe fairness" and "observability" only; filter-model/covariance work (F02, F06, F07) and anchor-B parity (F05) need separate pre-registrations and Snowball runs and are not part of A16.

**A. Probe fairness (F09).** The stored per-run metrics average over every sample, so P1 runs (extra stationary probe samples, longer elapsed time) and P0 runs are scored on different sample sets. Additive metrics (the existing columns are unchanged):
- `heading_rmse_common_deg`, `pos_rmse_common_m`: RMSE over the **common stations** = samples with `probe_id < 0` and `drive_g ≥ 150` (30 s of drive time at 5 Hz; identical drive positions and truth in every period, because `drive_g` is the drive-position index). `n_common_samples` is stored.
- `heading_rmse_probe_deg`: RMSE over the probe samples with `drive_g ≥ 150` (NaN for P0).
Descriptive paired comparison per (route, anchor, lateral, mount, drift, SNR, seed): Δ = metric(P1_T) − metric(P0), for the common-station metric and the existing all-sample metric. Per cell (route, anchor, mount): median Δ with a 95 % bootstrap interval (2000 resamples, seed 20261008), 10/50/90 % quantiles of Δ, share of seeds with Δ < 0 and with Δ > 0, next to the median elapsed time of each schedule. No improvement threshold and no significance test are applied. Local evidence: R1 development H stores (laterals 0 and 0.35, mounts 0° and 45°, drifts 0–2, SNR 30/10 dB, seeds 0–9, EKF baselines `range_s_P0`, `range_s_P1_T10/T20/T60`, LUT mismatch σ 0.18 as in the evaluation). A route re-analysis needs the route H stores on Snowball; the command is added to `RUN_SNOWBALL.md` and the stored route CSVs (no new columns) cannot give the common-station numbers. An equal-elapsed control (e.g. a stationary dwell without rotation of the same length) is not part of this analysis and would need its own pre-registration.

**B. Observability and initial-condition ambiguity (F10).** Linearised batch information analysis along the scripted truth trajectory with the **actual** 2° LUT (`DEV_LOCAL/S4`, real FFD banks) and the filter's own equations (`filters.py` predict/odom-heading/range/s models):
- parameters p = [x0, y0, ψ0, b, SF, ε]; state sensitivities by central finite differences of the filter's dead-reckoning recursion (noise-free truth increments); range Jacobian analytic; s Jacobian from `s_model(..., with_jac=True)` chained through the state sensitivities; odom-heading pseudo-measurement `h = ε·ds/wheelbase − SF·dθ_g − b·dt` as in `update_odom_heading`.
- measurement variances as the filter is told them: range `0.05² + 0.149²/12 + 0.05²`; s `0.02² + σ_mismatch²` with σ_mismatch = 0.161 (the route value; the thermal 0.02 is the SNR 30 dB calibration); odom-heading `k_θ|dθ| + k_sθ|ds| + ARW²·dt`. Prior = the filter's `p0_std`.
- configurations: odom+IMU (odom-heading only), range, range+s, each for P0/T10/T20/T60; routes R1 (laterals 0, 0.35), R2/R4/R5 × anchors A/B × mounts 0°/45° (route timelines `S1/routes`).
- reported: eigenvalues of the prior-whitened measurement information `P0^{1/2} I_meas P0^{1/2}` (dimensionless; values far above 1 mean the data dominate the prior in that direction, values near 0 mean the direction is not observed), the linearised posterior heading standard deviation (mean over the common stations and at the last sample), and its ratio to the empirical median `heading_rmse_deg` of the stored S6 results where those exist (context only, not a validation).
- **Initial-heading ambiguity profile:** for Δψ0 in −180°…+180° (step 1°) with x0, y0 at truth and b = SF = ε = 0, the dead-reckoned path is rotated about its start; the profile is the noise-free χ² of range+s (sum of squared residuals over σ²). Reported: all local minima of the profile with their χ² values (reading aid: χ²₁ 99.9 % = 10.83 per measurement; a minimum whose total χ² is of that order or below cannot be told from the truth by the measurements) and the global minimum other than Δψ0 = 0.
Limits that stay in force: truth-linearised local analysis, not global observability proof; LoS-only LUT stands in for the multipath channel (L1/L2 FAIL); independent Gaussian noise; no s-mismatch correlation; not a statement about the filter's actual consistency (F02).

### A16 result (local CPU diagnostics; definitions above were committed first as `e367573`)

**A. Probe fairness — R1 development H stores** (`DEV_RESULTS/PROBE_FAIRNESS_R1.csv/.json`; laterals 0 and 0.35 pooled, mounts 0°/45°, drifts 0–2, SNR 30/10 dB, seeds 0–9 → 120 paired runs per cell; `range_s_P0` vs `range_s_P1_T*`, EKF; routes are **not** covered, see below).

| mount | schedule | P0 median [deg] | P1 median [deg] | Δ median common [deg] (95 % CI) | Δ median all samples [deg] | seeds better / worse (common) | elapsed P0 → P1 [s] |
|---|---|---|---|---|---|---|---|
| 0° | T60 | 6.70 | 3.70 | −2.74 (−2.90, −2.59) | −2.74 | 100 % / 0 % | 183 → 198 |
| 0° | T20 | 6.70 | 3.35 | −3.94 (−4.23, −1.09) | −4.06 | 72 % / 28 % | 183 → 241 |
| 0° | T10 | 6.70 | 1.75 | −4.77 (−5.13, −4.17) | −4.90 | 99 % / 1 % | 183 → 306 |
| 45° | T60 | 1.38 | 1.31 | −0.09 (−0.13, −0.02) | −0.10 | 60 % / 40 % | 183 → 198 |
| 45° | T20 | 1.38 | 1.41 | +0.05 (−0.02, +0.13) | +0.03 | 43 % / 57 % | 183 → 241 |
| 45° | T10 | 1.38 | 1.52 | +0.20 (+0.13, +0.29) | +0.15 | 27 % / 73 % | 183 → 306 |

Reading (descriptive): scoring only on the drive positions that exist in every schedule gives the same picture as the all-sample metric (differences ≤ 0.15°), so the stored P1 benefit at mount 0° is **not** an artefact of scoring extra probe samples. At mount 45° the benefit is ≈ 0 and T10 is worse in 73 % of the paired runs. The elapsed time grows by 8–67 %, and no equal-elapsed control exists; the improvement remains a combined effect of manoeuvre, extra observations and extra time (F09 stays open for that part). Route statistics need the Snowball re-run in `RUN_SNOWBALL.md` §6 (the stored route CSVs lack the common-station columns); nothing is claimed for R2/R4/R5 here.

**B. Observability and initial-heading profile** (`DEV_RESULTS/OBSERVABILITY_A16.json`, 16 route/anchor/lateral/mount cases × 4 schedules, actual LUT, truth-linearised).
- Odom+IMU alone: three of six whitened information eigenvalues are 0 in all 64 cases (x0, y0, ψ0 unobserved); linearised mean heading std 6.9–12.8°.
- Range alone: the smallest eigenvalue is 0 in all cases (the anchor-centred rotation gauge, as stated in the audit); heading std 0.84–6.1°.
- Range+s: all six eigenvalues positive; smallest prior-whitened eigenvalue 0.83–29.9 (lowest: R2 anchor B mount 0° P0 0.83, R5 anchor B mount 0° P0 1.0); linearised heading std 0.16–0.63°. Probes raise the smaller eigenvalues (e.g. R1 y0 mount 0°: 4.3 → 29.9 for P0 → T10) and lower the std; the 45° mount has the smaller linearised std than 0° on R1, R2 and R5 but the larger one on R4 (0.36–0.50° vs 0.23–0.26°).
- The linearised standard deviation is **not** a prediction of the filter: the empirical median heading RMSE of the stored S6 results is 2.1–25.6× (median 7.2×) larger than the linearised value in the 64 cases where both exist (e.g. R2 anchor A mount 0° P0: 0.49° vs 10.7°). The failures behind the larger empirical errors (wrong-branch episodes, LUT mismatch, gating, correlated noise) are outside this local analysis.
- Initial-heading profile (Δψ0 ∈ [−180°, 180°), 1° steps, 16 P0 cases): **no local minimum other than Δψ0 = 0 in any case**; the noise-free range+s χ² for a ±5° initial heading error is 149–2776 (reading aid: 10.8 = χ²₁ 99.9 %), i.e. the measurements separate a 5° error from the truth in this slice. This is a one-dimensional slice (positions at truth, b = SF = ε = 0, noise-free, LoS-only LUT); it does not exclude other roots in the joint position–heading–parameter space, does not include the LUT mismatch (L1/L2 FAIL), and does not explain the observed wrong-branch runs (e.g. 49 % at R2 anchor A mount 0° P0).

Not done: filter-consistency work (F02/F06/F07), anchor-B parity (F05), multimodal initial-condition runs through the filter (F10 "broad initial conditions"), equal-elapsed probe control, route common-station statistics. `scientific_PASS` stays false.

## A17 — Filter-consistency diagnosis and held-out calibration (audit F02, F06, F07 — step 4); definitions and proposed acceptance values fixed **before** any number below was computed

Status: diagnostic + one pre-specified candidate correction, CPU only, local R1 development H stores. Not a replacement of the stored S6 results, not a new hypothesis test. The audit asks for a cause diagnosis and a held-out consistency evaluation and forbids tuning σ until the metric passes; this amendment follows that. **The acceptance values in C are proposed by the assistant and have not been approved by the user; they are fixed here only so that they exist before the held-out result, and the user may replace them (then the result is re-read against the replacement, and the change is recorded).**

**Data split (disjoint in seeds and in geometry).** Calibration set: R1 lateral 0.35 m, mounts 0°/45°, noise/drift seeds 1000–1009. Held-out test set: R1 lateral 0.0 m (a different path relative to the anchor), mounts 0°/45°, seeds 0–9. Drifts 0–2, SNR 30 and 10 dB, baselines `range_s_P0` and `range_s_P1_T20` (plus `odom_imu`, `gyro_only` as consistency references). Routes R2/R4/R5 need the Snowball route H stores and are not touched here.

**A. Cause decomposition on the calibration set** (mean pose NEES over the t ≥ 30 s samples, expected value 3; same truth, sensor draws and seeds in every variant):
- E0 real RF `s` and range (the production observation);
- E1 synthetic observation: `s = LUT(truth) +` thermal noise only (the variance the filter assumes), range = truth range + offset + the same range noise — tests the filter structure (gyro increment reuse, bias/scale states, unmodelled wheelbase error, odometry-heading pseudo-measurement) without any model mismatch;
- E2 = E1 plus white Gaussian mismatch with σ = σ_mismatch (0.18) — tests white mismatch;
- E3 = E0 with the wheelbase error switched off in the sensor drift (`E_b = 0`) — tests the unmodelled wheelbase error on real data;
- E4 = E0 with the odometry-heading pseudo-measurement removed (`use_odom_heading=False` for the range+s filter) — tests the reuse of the gyro increment.
Reading: the variant at which the mean NEES returns to ≈ 3 identifies the dominant cause; nothing is concluded from a single variant alone.

**B. Mismatch-residual statistics** on the calibration set: r_k = s_noise-free-chain(H_k) − LUT(truth_k) per sample; mean, std, rms, and the autocorrelation at lags 1, 2, 5, 10, 25 samples (0.2 s each, drive samples only), per mount, and the integrated inflation factor `κ = 1 + 2 Σ_{k=1..K} ρ_k` (K = first lag at which ρ ≤ 0 or 50, whichever is smaller, truncated at κ ≥ 1).

**C. Candidate correction and held-out evaluation** (the only filter change considered; default values reproduce the stored filter exactly):
- V0 = stored filter (σ_mismatch = 0.18 measured on both laterals, κ = 1);
- V1 = σ_mismatch re-measured on the **calibration** set only (rms of r_k, both mounts pooled), κ = 1 — the held-out version of the stored calibration;
- V2 = V1 with the s-update variance `R_s = thermal + κ·σ²` where κ is the calibration-set value from B (`FilterConfig.s_var_inflation`, default 1.0).
All of V0–V2 are evaluated on the held-out test set. Reported per variant, baseline and mount: mean pose NEES; fraction of samples whose pose NEES ≤ χ²₃(0.95) = 7.815 (pose coverage); fraction of samples with |heading error| ≤ 1.96·σ_ψ (heading coverage); median heading RMSE and pos RMSE; paired change of heading RMSE versus V0.
**Proposed acceptance values (assistant-proposed, see status):** consistency is called *acceptable* for a baseline and mount if the mean pose NEES ≤ 6.0 (twice the expected value) and the pose coverage ≥ 0.90; a variant is called *usable* only if it is acceptable for both `range_s_P0` and `range_s_P1_T20` at both mounts and the median heading RMSE of each of these cells is ≤ 1.25 × that of V0. If no variant is acceptable, that is the result; σ is not tuned further and no value is chosen to pass.

**Additive code (defaults reproduce the stored behaviour):** `FilterConfig.s_var_inflation = 1.0`; extra metric columns `nees_cov95` (pose coverage fraction), `heading_cov95` (heading coverage fraction); `run_unit(..., obs_transform=None, drift_transform=None)` hooks used by the variants above.

Limits stay: LoS-only LUT stands for the multipath channel (L1/L2 FAIL stays), placeholder sensors, one corridor, development H stores, truth-near initial prior; held-out here means other seeds and another lateral of the same corridor, not another environment.

### A17 result (local R1 development H stores; `DEV_RESULTS/CONSISTENCY_CALIB.json/.csv`, `CONSISTENCY_HELDOUT.json/.csv`; code `scripts/drive_sim/consistency_diagnostics.py`)

**A. Cause decomposition (calibration set: lateral 0.35, seeds 1000–1009, 60 runs per cell; mean pose NEES, expected 3; coverage = fraction of samples with NEES ≤ 7.81)**

| variant | range_s_P0 m0° | range_s_P0 m45° | range_s_P1_T20 m0° | range_s_P1_T20 m45° |
|---|---|---|---|---|
| E0 real RF `s` (production) | 93.3 (cov 0.13) | 25.8 (0.36) | 15.7 (0.40) | 23.3 (0.40) |
| E1 synthetic, thermal noise only | 1.21 (0.99) | 1.32 (0.99) | 0.94 (1.00) | 1.45 (0.99) |
| E2 E1 + white mismatch σ 0.18 | 19.2 (0.86) | 2.30 (0.97) | 2.39 (0.97) | 2.42 (0.96) |
| E3 E0 without wheelbase error | 92.5 (0.13) | 25.2 (0.37) | 15.5 (0.40) | 22.6 (0.40) |
| E4 E0 without odometry-heading pseudo-measurement | 102.8 (0.13) | 52.6 (0.34) | 14.9 (0.43) | 22.2 (0.39) |

Reference baselines on the same runs (E0): `gyro_only` 3.16 (cov 0.91), `odom_imu` 4.31 (0.92). Reading: (i) with model-consistent synthetic data the filter is consistent (NEES ≈ 1–1.5, slightly conservative), so the filter structure — including the reuse of the gyro increment in the odometry-heading pseudo-measurement (E4: removing it does not help) and the unmodelled wheelbase error (E3: no change) — is **not** the cause of the 15–93 × inflation in these runs; F07 is not supported as the dominant cause here (it can still cost second-order consistency, which these runs cannot resolve). (ii) White mismatch of the measured size reproduces only part of the effect (2.3–2.4 at three cells, 19 at P0 mount 0°), far less than the real RF data. (iii) The inflation is therefore tied to the real residual `s_chain(H) − LUT(truth)` itself, i.e. its temporal/spatial structure (L1/L2 FAIL).

**B. Mismatch residual (calibration lateral, t ≥ 30 s, P0 timeline)**

| mount | n | mean | std | rms | ρ₁ | ρ₂ | ρ₅ | ρ₁₀ | ρ₂₅ | κ (uncentred) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0° | 767 | +0.067 | 0.200 | 0.211 | 0.90 | 0.83 | 0.52 | 0.17 | 0.19 | 20.9 |
| 45° | 767 | +0.012 | 0.191 | 0.191 | 0.96 | 0.89 | 0.61 | 0.25 | −0.14 | 14.1 |
Pooled rms (σ_cal) = 0.2012; κ (mean of the two mounts) = 17.48. The residual is strongly autocorrelated (about 1 s correlation time at 5 Hz), which a per-sample independent update ignores; the effective number of independent `s` observations is much smaller than the number of samples the filter assumes. The centred autocorrelation is within 0.02 of the uncentred one except at mount 0° ρ₁₀/ρ₂₅.

**C. Held-out evaluation (lateral 0.0, seeds 0–9, 60 runs per cell); V0 σ = 0.18, κ = 1 (stored filter); V1 σ = 0.2012 (calibration lateral only), κ = 1; V2 σ = 0.2012, κ = 17.48**

| variant / baseline / mount | mean NEES | pose coverage | median heading RMSE [deg] | paired Δ heading RMSE vs V0 (median; better/worse share) |
|---|---|---|---|---|
| V0 P0 0° | 37.4 | 0.23 | 4.61 | — |
| V0 P0 45° | 19.9 | 0.33 | 1.22 | — |
| V0 T20 0° | 60.0 | 0.18 | 4.55 | — |
| V0 T20 45° | 20.6 | 0.37 | 1.31 | — |
| V1 P0 0° | 36.2 | 0.24 | 4.71 | +0.13° (17 % / 83 %) |
| V1 P0 45° | 20.1 | 0.36 | 1.21 | +0.00° (48 % / 52 %) |
| V1 T20 0° | 41.0 | 0.19 | 4.41 | −0.09° (78 % / 22 %) |
| V1 T20 45° | 19.5 | 0.39 | 1.25 | −0.06° (92 % / 8 %) |
| V2 P0 0° | 43.9 | 0.28 | 10.87 | +6.70° (13 % / 87 %) |
| V2 P0 45° | 10.4 | 0.59 | 1.37 | +0.17° (23 % / 77 %) |
| V2 T20 0° | 13.7 | 0.55 | 3.61 | −0.87° (73 % / 27 %) |
| V2 T20 45° | 11.4 | 0.59 | 1.17 | −0.20° (70 % / 30 %) |

Heading coverage (|error| ≤ 1.96 σ_ψ): V0 0.51/0.86/0.24/0.74 (P0 0°, P0 45°, T20 0°, T20 45°), V1 0.54/0.89/0.27/0.79, V2 0.37/0.99/0.72/1.00. Reference baselines (V0): `gyro_only` 3.45, `odom_imu` 4.09 with pose coverage 0.91/0.89.

**Outcome against the proposed acceptance values (mean NEES ≤ 6.0 and pose coverage ≥ 0.90, in all four cells, heading RMSE ≤ 1.25 × V0): no variant is acceptable.** V0 and V1 are equivalent (re-measuring σ on a held-out lateral changes nothing material; 0.18 → 0.20 is within the calibration scatter). V2 (variance inflation by the estimated correlation factor) raises the coverage at mount 45° (heading 0.99–1.0) and halves the NEES there, but NEES stays 10–14 in three cells and 43.9 at P0 mount 0° (T20 mount 0°: 60.0 → 13.7, still far above 6), and at P0 mount 0° it more than doubles the heading RMSE (4.6 → 10.9°) because the `s` updates are almost switched off; it fails both the consistency and the accuracy condition. Per the pre-registered rule nothing is tuned further and no σ/κ is chosen to pass.

**Conclusions (diagnostic, local, R1 only).** F06: held-out re-measurement of σ_mismatch shows the in-sample calibration (0.18) is not what drives the consistency failure (held-out 0.20 behaves the same); the concern about evaluation-informed R stays formally open for the routes (needs the route H stores). F02: the covariance inconsistency of the `s`-fusing filters is caused by the strongly autocorrelated, geometry-dependent LUT-vs-channel residual (not by filter bookkeeping, gyro reuse or wheelbase error in these runs); a scalar σ or a scalar variance inflation does not repair it. A model change would have to represent the residual itself (e.g. a better measurement model — the L1/L2 route — or a correlated-error state), which is a new design and a new pre-registration, not done here. F07: not the dominant cause; no change made. `scientific_PASS` stays false.

## A18 — Steered probe (user proposal): rotate in place to the heading at which `s` is most sensitive; stage 1 = information-level comparison; definitions fixed **before** any number below was computed

**Proposal (user).** Instead of the fixed relative sweep −45° → +45° → 0 (A2), probe at the heading for which (driving-direction angle − anchor polarization angle) equals the 45° condition, i.e. where the port power ratio has its steepest slope.

**Geometry used (derived from the model equations, not from a result).** With `φ_tx = atan2(−v, u)` and `φ_rx = atan2(−v, −u) − ψ − mount (+180°)`, the sum `φ_tx + φ_rx` equals `−(ψ + mount)` modulo 360° for every robot position, so the ideal curve is `s = −cos 2(ψ + mount + 180°)`, a function of the antenna yaw `ψ + mount` only and independent of the position; its slope `2 sin 2(ψ + mount)` is steepest at `ψ + mount ≡ 45° (mod 90°)` and zero at 0°/90°. The user's rule is this condition expressed in the anchor's polarization frame. The real LUT adds the pattern-dependent terms (L1/L2 FAIL), so the rule is checked against the LUT slope, not assumed.

**Probe definition (`steered`, same time budget as A2).** At a probe the robot rotates in place from its heading `ψ_b` to the nearest `ψ* ≡ 45° − mount (mod 90°)` (rotation `Δ* ∈ [−45°, 45°)`, at most 5° per 0.2 s sample), dwells at `ψ*`, and rotates back to `ψ_b`, in exactly 36 samples (7.2 s) like the sweep: `n_r = max(1, ceil(|Δ*|/5))` ramp samples, `36 − 2 n_r` dwell samples (at least 18), `n_r` return samples ending at offset 0. Probe times, positions and drive samples are those of the existing P1 timelines. Mount 45° on the corridor heading 0° gives Δ* = 0 (pure dwell); mount 0° gives Δ* = −45° (heading 0°) or ±45°/0 depending on the leg.

**Stage 1 (this amendment): information level, CPU only, no RF, no filter run.** For R1 (laterals 0, 0.35, anchor A) and R2/R4/R5 × anchors A/B, mounts 0°/45°, schedules T10/T20/T60, compare with the stored sweep timelines, using the A16 B linearised batch information (actual LUT, truth linearisation, the filter's own equations, range+s):
- the linearised heading std (mean over the common stations) and the smallest prior-whitened information eigenvalue;
- the mean `|∂s/∂ψ|` on the probe samples (from the LUT, per degree);
- steering with a heading error: `Δ*` is computed from `ψ_b + ε` with ε = 0°, 5°, 10° (the controller only has an estimate), the physical rotation then follows that command; reported as a robustness column.
Descriptive only, no threshold, no hypothesis test.
**Not part of stage 1:** a filter run with RF at the steered yaws (stage 2). Method B stores a trace per position, so H at any yaw of a probe position can be assembled offline, but stage 2 needs its own pre-registration (closed-loop heading estimate, wrong-branch behaviour, elapsed-time accounting) and the route traces on Snowball. Linearised information is not a prediction of filter accuracy (A16: the stored RMSE is 2–26× the linearised value).
Limits: truth-linearised LoS-only LUT; the steering rule needs a heading estimate, which is exactly what is uncertain at cold start (the experiment assumes the tracking regime with the 5° initial prior); a probe at `ψ*` measures a local slope and does not remove the π ambiguity by itself.

### A18 result — stage 1, information level (`DEV_RESULTS/STEERED_PROBE_INFO_A18.json`; 48 cases = 16 route/anchor/lateral/mount cases × T10/T20/T60; code `steered_probe.py`, `scripts/drive_sim/steered_probe_info.py`, tests `tests/test_steered_probe.py`)

- Steering rule check: for the ideal curve the optimum is `ψ + mount ≡ 45° (mod 90°)`, independent of position (derivation in A18). The real LUT slope confirms it: at the steered dwell the mean `|∂s/∂ψ|` on probe samples is 0.025–0.035 per degree (ideal maximum 2·π/180 = 0.0349; R4 mount 0° reaches 0.034–0.035), against 0.020–0.022 for the stored sweep.
- Linearised heading std (range+s, mean over common stations), steered with a perfect heading command versus the stored sweep: lower in **48/48** cases, ratio steered/sweep median **0.93** (range 0.75–0.98); mount 0° median 0.90 (0.84–0.97), mount 45° median 0.94 (0.75–0.98). Examples: R1 mount 0° T10 0.278° → 0.249°, R4 mount 45° T10 0.358° → 0.288°, R5 mount 45° T10 0.165° → 0.151°. The smallest prior-whitened information eigenvalue rises by 3–50 % (e.g. R4 mount 45° T10 6.5 → 9.9).
- With a heading error in the command (the controller only has an estimate): ε = 5° → still lower in 47/48 cases; ε = 10° → lower in 39/48; the nine cases at ε = 10° that are not lower are all mount 0° (R1 5, R2 2, R5 2) and differ from the sweep by at most +0.01°. The steered slope falls from 0.034 to 0.026 per degree at ε = 10° (R4), still above the sweep's 0.022.
- Reading: the proposed steering is the right direction and costs nothing in time (same 36 samples), but its linearised benefit on top of the stored sweep is modest (median −7 %, at most −25 %), because the sweep already passes through the steep region and the drive samples dominate the information. The large empirical probe benefit at mount 0° (A16: 6.7° → 1.7° with the sweep) is therefore mostly already captured by the sweep; the linearised numbers do not show what steering adds to the observed wrong-branch episodes, which the linearisation does not model (A16).
- Not shown: any filter result, any RF at the steered yaws, any behaviour of the closed loop (a wrong heading estimate steers the probe to a wrong angle), cold start. Stage 2 (filter run with H assembled at the steered yaws from the stored Method-B traces, closed-loop command from the filter's own heading estimate, elapsed-time accounting) needs its own pre-registration and the route traces; it is not started.
