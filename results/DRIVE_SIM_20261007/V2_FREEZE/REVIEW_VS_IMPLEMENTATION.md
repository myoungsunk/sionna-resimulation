# Sensor-v2 as frozen vs. the user's sensor-model design review (checked 2026-10-10)

Method: read `sensor_v2.py`, `filter_v2.py`, `evaluation_v2.py`, `MODEL_CONTRACT.md`; reproduced the review's numbers with the frozen generator (`tests/test_sensor_v2_review_consistency.py`, 5 tests, all pass). "Matches" means checked by code or computation; the physical correctness of the numbers (Waffle Pi) is not claimed by either document.

## Matches (verified)
| Review item | Frozen v2 | Check |
|---|---|---|
| §3.1 fixed true trajectory, errors injected into measurements, report as localisation error | truth fixed; `generate()` takes true increments; truth only in `evaluation` output | code |
| §3.2 wheelbase error generated but absent from the filter state; model-matched (e_b = 0 / known) vs mismatch experiments | `wheelbase` term in the generator (b_true = b_nom/(1+e_b)); `known_wheelbase_error` in the filter; no e_b state | filter odometry model with true states and known e_b: error 1e-17; with e_b unknown: mismatch = e_b·Δψ (7.4e-5 vs 7.5e-5) |
| §3.2 linear relation Δψ_o − Δψ_g ≈ ε Δs/B − (e_b+s_g)Δψ − b Δt | same relation | noise-free generator: relative difference 9e-15 (straight), 4e-3 and 3e-3 (turning cases; second-order products of the small parameters) |
| §3.3 constant-speed straight drive identifies one combination only (ε v/B vs b_g) | same algebra | ε = 0.5 %, v = 0.2 m/s → 0.200 °/s fake rotation (computation) |
| §3.4 shared gyro sample in prediction and odometry-heading update | `step()` applies the correlated update with C = −G Q Bᵀ, B = [−h_d, −h_g, 1] (wheel-distance and gyro terms); Joseph form with cross terms | code; the stage-2 Gaussian Monte Carlo is the user's, not re-run |
| §3.5 wheel-only increments separate from IMU; `/odom` may contain the IMU | encoder-level wheel increments generated separately from the gyro | code (the real robot's `use_imu` setting is not verified) |
| §4.2 table: gyro bias 0.01/0.05/0.20 °/s → 0.50/2.50/10.00 °, 4.36/21.81/87.05 cm; wheel ratio 0.2/0.5/1.0 % → 3.99/9.98/19.96 °, 34.83/86.89/172.46 cm; gyro white noise σ 0.106 ° / 1.07 cm; 5° initial heading → 87.16 cm | all seven rows and the noise row reproduced by the frozen generator | test (tolerances 0.01 ° / 0.02 cm; noise 8 % with 600 seeds; 3000 seeds gave 0.106 ° / 1.07 cm) |
| §2.2 gyro definition Var(Δangle) = N² dt, no √2 correction claimed | `gyro_definition='Var(delta_angle)=N^2 dt'`, N = 0.015 °/√s, manifest says no PSD/√2 claim | code |
| §5.2 left/right wheel geometry, common scale separate from asymmetry, radius convention stated | `m_L = (1+c)(1−ε/2)`, `m_R = (1+c)(1+ε/2)`, r_true = r_nom/m; `common_scale` default 0 | code |
| §5.3 fixed residual bias by default, bias random walk as separate extension | `bias_rw` term, default 0; left-endpoint discretisation documented | code |
| §5.4 slip: event rate λ = −ln(0.99)/0.2 = 0.0503 s⁻¹, P(≥1 event in 10 s) = 39.5 %, Student-t(3) scale 0.5 ° has σ = 0.866 °, eligible only during in-place rotation | `slip_rate_per_s`, time-based probability 1 − exp(−λΔt), eligibility `|ds|≈0 & |Δψ|>0`, `slip_std_rad` in the manifest | test |
| §5.5 position slack is a filter-side assumption | `SensorV2Filter` refuses `pos_process_std ≠ 0` | code |
| §6.1 baseline list (ideal, wheel-only, wheel distance + gyro without online correction, wheel+gyro online, + range, + RF-type observation) | `ideal_increments`, `wheel_only`, `wheel_distance_gyro_fixed`, `wheel_gyro_online`, `online_range`, `online_range_s_*` | code |
| §6.3 single-term → pair → all conditions | `CONDITIONS`: none, each term, `bias_asymmetry`, `asymmetry_wheelbase`, `noise_pair`, `all` | code |
| §6.4 exact vs prior initialisation | `--initial exact legacy-prior` | code |
| §7.1–7.3 forward/lateral, radial/tangential errors and the heading- / distance-only re-integrations | `directional()` and the two auxiliary re-integrated poses are stored | code |
| §7 raw states, covariances, innovations, slip events saved | NPZ with full state/covariance, innovation/R/S/status, slip event fields | contract |

## Differences from the review text (deliberate or unresolved) — to decide, not hidden
1. **Order of noise generation (§5.2).** The review proposes noise on the left/right increments first and then `Q_{s,ψ} = A Q_LR Aᵀ` (which gives distance noise and distance–yaw correlation, e.g. a small spurious translation during in-place rotation). v2 draws independent distance and yaw noise (variances `k_d|Δs|`, `k_ψ|Δψ| + k_ψd|Δs|`, chosen to keep the legacy coefficients) and maps it to correlated left/right increments. The distribution of left/right increments is the same Gaussian structure only if the distance/yaw covariance is diagonal, which v2 imposes; consequently there is **no distance noise and no distance–yaw correlation during in-place rotation**.
2. **Sign balance (§6.3).** v2 draws the four systematic signs per seed at random; it does not enumerate the 16 sign combinations. The `parameters` override allows fixing them, but no runner enumerates them.
3. **Path set (§6.2).** Only the mixed synthetic path (straight, two in-place turns, arc, reverse arc) and the stored RF routes exist. No stationary segment, speed variation, forward/backward equal-distance, ±90°/±180° turn series or UMBmark CW/CCW squares.
4. **Warm-up (§6.4).** Summary metrics use one evaluation mask per script; the raw arrays allow both full-run and post-warm-up values, but both are not written to the summary tables.
5. **Filter bias random walk (§5.3).** The generator's default is a fixed bias, but `FilterConfig.bias_rw_std` defaults to radians(1e-3) > 0. `evaluation_v2.evaluate` and `filter_fixed_bias.json` set it to 0; **any new runner must set it explicitly** (the full-route runner to be written).
6. **RF-type observation (§6.1).** In `evaluate()` the `s` and range observations are synthetic (ideal ratio with σ 0.09, true range with σ 0.05); the real-RF connection exists only in `evaluate_sensor_v2_rf.py` (first 201 samples of R1, 35 dB). No full-route RF evaluation under v2.
7. **ARW / PSD convention (§2.2).** Whether the datasheet density and `N` share a spectrum convention (the √2 question) is not resolved; the review also leaves it to an Allan-deviation measurement.
8. **Truth convention.** Stored routes use legacy Euler increments; v2's strict SE(2) extraction rejects them, so RF runs need `legacy-euler` and an evaluation-only mismatch field.

## Not covered by v2 (as the review also leaves open)
Closed-loop control (§3.1 second/third rows), e_b as a state (§3.2), hardware calibration and the Waffle Pi values of every number (§2.1: low/mid/high are sensitivity levels), Allan deviation estimation, persistent / curved-motion slip (§5.4), the real `/odom` composition (§3.5).
