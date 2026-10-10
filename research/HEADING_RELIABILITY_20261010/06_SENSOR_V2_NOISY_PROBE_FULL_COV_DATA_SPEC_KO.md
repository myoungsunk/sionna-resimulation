# Sensor-v2 전체 공분산·노이즈 포함 2–3점 프로브 데이터 사양서
버전 1.0 | 작성: 2026-10-10 | 상태: SPEC_ONLY — 후속 실험 미실행

## 0. 연구 목표 및 가설

H1. 한 개의 +45° LP 송신 앵커와 ±45° LP 수신 포트에서 얻는 amplitude-only 특징(CIR 형태, P1/P2, s, 총 수신전력)이 다중경로에 의한 RF heading 오류의 확률과 어느 정도 관련되는지 검증한다.
H2. 동일 위치의 2–3 yaw 관측에서 각 점의 정상/오염 가능성(q_point_i)과 동일 위치에 공유된 다중경로 위험(q_site)을 동시에 추정한다. 모든 점을 보존하고 낮은 신뢰도에 따른 likelihood 가중치를 적용하여 heading 및 불확실성을 산출한다.
H3. 전체 6×6 상태 공분산과 yaw 관측 간 교차 공분산, 실제 noisy 회전을 반영할 때 RMSE와 NEES가 모두 개선되는지 검증한다.
H4. 학습에 사용하지 않은 완전히 새로운 geometry에서도 효과가 유지되는지 별도 검증한다.

최소 잔차 점 하나만 골라 채택하지 않는다. q_site_bad와 q_point_bad가 작거나 클 때도 왜 그런 결과가 나오는지 기록한다. 정답 heading을 이용한 분류·branch 선택은 oracle 대조 이외 절대 금지한다.

## 1. 소스, 장착, 현재 정량 기준선

코드: myoungsunk/sionna-resimulation, codex/cir-heading-reliability-prereg-20261010, results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff. 동결된 sensor-v2 source revision 16d22fc3121963743cf7f1bf56233e00083c5518. RF 원본은 POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C의 기존 full/LoS H 7개. LUT 원본 SHA256 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079.

RF 물리: 6.2504–6.7496 GHz, 257 frequency bins, TX0 +45° LP 단일 포트, RX0 +45° LP와 RX1 −45° LP. 안테나 boresight: 앵커 아래(-z, rotation diag(1,-1,-1)); 로봇 위(+z, rotation Rz(yaw_body + mount)). 앵커 A=(4,0,2.65)m 또는 B=(10,0,2.65)m, 한 번에 한 앵커. 로봇 안테나 z=0.45m. R2/R4/R5 경로, 원 복도 20×2.4×2.7m, 콘크리트 바닥/천장·석고보드 측벽. Mount 0°는 모든 7케이스, 45°는 R2-A에만 추가. 구조가 같은 복도의 총 7개 설정이다.

기존 sensor-v2 전체 주행의 케이스×drift×seed 평균 heading RMSE: RF-off A=9.893°, range+LoS-only s C=0.720° (pose NEES=69.36), range+full-RF s D=2.942° (NEES=268.45), 종전 단일점 신뢰도 E=3.382° (NEES=175.05). C의 관측은 LUT와 완전히 정합된 이상적 관측이 아니다.
별도로 시행된 오프라인 프로브는 34개 케이스별 station, 16개 물리 XY 위치 × 반복 sensor seed/drift 5100묶음만 평가하였다. 같은 subset의 RF-off prior=9.555° RMSE, 3점 mixture=7.030° RMSE. 이는 전체 주행 필터 결과가 아니라 특정 위치의 RF-off prior 조건부 계산이다. C=0.720°와 동일 시험처럼 비교하지 않는다.

기존 F01/F02 OPEN, scientific_PASS=false 및 cross-geometry 미검증을 그대로 유지한다.

## 2. 먼저 기존 RAW에서 full P6 회수 (새 RF 불필요)

Snowball 기존 root: /home/KMS/DRIVE_SIM_HEADING_SENSOR_V2_20261010_01a124ff. README_KO에 RAW_ARCHIVE.tar SHA256과 위치가 기록되어 있으며 raw TRACE NPZ의 전체 필드가 이 곳에 보존되었다. 공개 PROBES/07_PROBE_STATIONS.csv.gz의 Pψψ만으로는 full covariance 분석할 수 없다.

TRACE 예시: TRACES/main/<case>_d<drift>_s<seed>_A_stochastic_unknown.npz, E는 TRACES/E. 각 run에서 t, pose_id, truth(평가전용), pre_rf_state[T,6], pre_rf_cov[T,6,6], post_range_state[T,6], post_range_cov[T,6,6], est[T,6], cov6[T,6,6], input_F/G/Q, odom_H/C/S/R, range_H/S/R, s_H/S/R, gyro/wheel 관측, detected, RF s, P1/P2, range, mask, generator true parameters/slip를 추출하고 해시 검증한다.

이름 주의: 기존 simulate.py의 pre_rf_state/P는 **odom correction 이후이지만 range update 이전** 단계이다. 새 저장에서는 x_after_odom/P_after_odom, x_after_range/P_after_range, x_before_RF/P_before_RF, x_after_RF/P_after_RF를 별도 명확히 저장한다. Range 사용 조건에서 x_before_RF = x_after_range라는 사실을 수치 검산한다. 초기 prior, 6차원 캘리브레이션 상태 추정치는 진실값이 아니므로 evaluation truth를 대입하지 않는다.

추출한 자료는 원본을 덮어쓰지 말고 new/RAW_BACKFILL에서 기록한다. Tnone 주행 timeline에 없는 probe pose는 NOT_IN_TNONE, 평가 구간 30초 이전은 OUTSIDE_MASK, raw 누락은 RAW_MISSING으로 구분한다. 기존 RAW만으로 noisy 실제 프로브 중간 자세의 P6를 발명하지 않는다.

## 3. 다음 시뮬레이션의 구동·센서 조건

센서 5Hz, nominal dt=0.2s, 평상시 주행 속도 0.2m/s. 상태 순서는 [x(m), y(m), psi(rad), gyro_bias(rad/s), gyro_scale, wheel_asymmetry]의 6차원. 최초 실험은 sensor-v2 원본의 SE(2) propagation, measured-increment Q, 공유 gyro–wheel 교차상관 C=-GQBᵀ, bias/slip RNG, 각종 이상치 게이트를 유지한다. Source 기본 wheel radius 0.033m, wheelbase 0.287m, gyro ARW 0.015deg/sqrt(s). Drifts 및 초기화는 원본 config와 seed 스트림에서 가져오고 모든 실제 적용 값을 MANIFEST에 기록한다.

모드는 다음과 같이 분리한다.
- OFFLINE_IDEAL: 저장된 yaw sweep와 원 RF full/LoS H를 재사용, 실제 yaw offset을 아는 진단용; 결과에는 IDEAL_ANGLE=true 표시.
- PROBE_BODY: 본체 중심 회전, 명령→속도상승→회전→정착→측정→기본 heading 복귀→주행 재개. 본체/안테나 yaw_true와 센서 기반 yaw_est를 **다르게 저장**한다. 회전 중 gyro bias/noise, 좌우 엔코더, slip, 미세 위치 이탈, pose P6 propagation 필수.
- PROBE_HEAD: 수신 안테나 헤드만 별도 회전하는 경우. heading_body + mount + heading_head로 계산하되 독립 head encoder noise, 실제 장치 구현 가능성 및 FFD/로봇 산란 영향의 RF parity 확인 필요. 기존 본체 회전을 아무 근거 없이 독립 head 회전으로 해석하지 않는다.

1점 [0], 2점 [0,약10°], 3점 [0,약10°,약20°]을 기존 station의 실제 부호/offset과 페어링한다. 대칭 [-10,0,+10] 별도 arm은 필요한 각도의 RF H가 원 저장본에 없으면 추가 생성으로 표시한다. 기본 회전속도 시뮬레이션 후보 25deg/s(5°/0.2s)는 측정된 로봇 속도 제한이 아니라 사전등록할 가정이다. 매 샘플 실제 시간과 총 회전/복귀 시간을 기록한다. 추가 측정은 무료가 아니다.

RF 관측: 같은 원천 H의 no-noise full/LoS parity를 먼저 실시한 뒤 receiver thermal noise 등 독립 신호 잡음을 추가한 팔(권장 예시: nominal 30dB /10dB, realized SNR 반드시 기록)을 분리한다. 고정 H를 sensor seed만 바꿔 150회 복제하는 것을 RF 다중경로 독립 표본으로 취급 금지한다. Full magnitude-CIR가 하드웨어에서 읽히는지 UNKNOWN; first-path power-only 장치라면 CIR 기반 feature는 HARDWARE_UNAVAILABLE로 구분한다.

## 4. 파일별 필수 데이터 사양

### A. MANIFEST.json (run마다)
schema_version, case_id, scene_id, route, anchor_xyz, anchor_rotation, tx_port, rx_port_pair, mount_deg, robot_antenna_z_m, FFD/LUT/H hash, Sionna version, sensor-v2 exact hash, frequency axis, noise seed, sensor seed, RF seed, drift_level, trajectory ID, probe policy, duration, Q/R/gate/P0/initialization, execution command, file SHA, complete/failed state. 모든 변형에 사용자 지정 표기 아닌 **실제 적용 파라미터**를 기록한다.

### B. STATE_TRACE.npz (T sensor timesteps)
- t_s[T], dt_s[T], station_id[T], pose_id[T], phase[T], probe_id[T], route/control ID
- raw encoder_L/R[T], wheel_increment_L/R[T], ds_odom[T], dtheta_odom[T], gyro_dtheta[T], gyro_rate[T], commanded_v/w[T], head_yaw_meas (있을 경우)
- x_pred_before_odom[T,6], P_pred_before_odom[T,6,6]; x_after_odom, P_after_odom; x_after_range, P_after_range; x_before_RF, P_before_RF; x_after_RF, P_after_RF (모두 [T,6] 또는 [T,6,6])
- F[T,6,6], G[T,6,3], Q_input[T,3,3], C_odom[T,6]; H_range[T,6], H_s[T,6]; innovation_odom/range/s, S_odom/range/s, R_odom/range/s, NIS_raw_r/s, gate status, effective_R_s, state P eigenvalues, update accepted/rejected reason
- gyro-wheel source, wheel slip status, actuator yaw variance, correlation/calibration model ID; legacy Euler truth vs exact-SE2 filter 차이를 로그에 명시.

P6의 xy–yaw, yaw–gyro bias 등 교차항이 반드시 존재해야 한다. 축약 yaw sigma만 보내면 FAIL.

### C. PROBE_RF_PACKETS.npz (S stations, 총 G RF 관측)
- ragged offsets[S+1], time_rf_s[G], corresponding_state_index[G], packet index, station pose ID, RX port convention
- yaw_body_true_rad[G] (ORACLE namespace), yaw_body_est_rad[G], yaw_antenna_true_rad[G] (ORACLE), yaw_antenna_est_rad[G], delta_probe_meas_rad[G], angle_noise_variance_rad2[G]
- P1_firstpath[G], P2_firstpath[G], s_firstpath[G], power_sum[G], ratio_db[G], range_m[G], selected_tap[G], peak_branch[G], peak[G], detect[G], realized_snr_db[G], noise_var[G]
- optional cir_amplitude[G,1028,2] with CIR_HARDWARE_SUPPORTED flag and calibration of receiver gain. If not present, mark unavailable (not fill from oracle H).
- joint RF covariance Sigma_probe_R[S,M,M] for fixed-size or list per station; off-diagonal terms REQUIRED for claimed correlated measurement evaluation, plus covariance fit input IDs. If estimating using sequential update retain full time correlation and propagators, no repeated independent assimilation of same RF.

### D. ORACLE_EVAL_ONLY.npz / csv
Never accessible to online estimator, model quality input, inverse-root selector or EKF.
true_xypsi, true_sensor_biases/scale, true_body/head yaw, true slip, exact H and path labels if needed; s_LoS_direct, s_full_clean, s_full_noisy, h_LUT(p_true,psi_true+delta), e_MP=s_full_clean−s_LoS_direct, e_LUT=s_LoS_direct−h_LUT_true, e_total=s_full_clean−h_LUT_true; range bias, heading ground truth errors, harmful-update label. Separate noise error=s_noisy−s_clean.
point_bad based on |e_total|>0.1 (sensitivity 0.05/0.2), site_bad based on any among three points, RF heading bad if >5° (2/10° sensitivity). Missing/no-match/ambiguous not silently labeled correct.

### E. INFERENCE_QUALITY.csv
q_site_bad, q_point_bad1..3, q_heading_good5, full heading posterior or mixture modes, psi_est_deg, sigma_psi_deg, calibrated vs nominal flag, geometry/reliability feature inventory, raw per-point LUT residual r_i using **estimated** pose, H_i wrt x/y/psi and antenna angle, site bias posterior, effective R or covariance, timing cost, gate/weight/reject causes. Include site ID for downstream spatial correlation analysis.

## 5. Correlation / depolarization physics

The first-path s and dB ratio of the two RX powers are algebraically equivalent:
s=(P1−P2)/(P1+P2)
R_dB=10log10(P1/P2)=10log10[(1+s)/(1−s)].
Therefore these are not two independent polarization measurements. Measure s, |s|, Psum, CIR mismatch and **LUT-predicted s difference** separately. High |s| indicates strong port imbalance, not automatically physical depolarization.

Under an ideal rotating orthogonal LP receiver, s(alpha)=(Q/I)cos(2alpha)+(U/I)sin(2alpha). Angular sweep can estimate linear Stokes Q/I,U/I if the angle span/Jacobian condition is sufficient, but lacks coherent V/I, so cannot establish total Stokes DoP or uniquely separate elliptical polarization from depolarization. Real FFD, incidence geometry, first-path selection and gain imbalance must be included as calibration/model effects. Optional complex Jones/Stokes from Sionna are ORACLE EVALUATION ONLY, NEVER online features. New scenes with altered incidence and material essential.

Measure both (i) RF heading error and (ii) multipath s residual. Repeat ratio ablation in each route and distance/mount/yaw strata. Baselines: distance, distance+total power, ratio-only, distance+power+ratio, CIR-only, combined, combined+2/3-point residual, combined+full P6. Evaluate Pearson/Spearman vs error, Brier / AUROC / calibration / high-confidence false accepts; use route/station cluster bootstrap and report that 7 cases share one corridor.

## 6. Fair experiments and covariance audit

Minimum paired arms, identical initial state and seeds and same physical clocks:
A RF-off IMU+wheel; B range only; C range+LoS-only s; D range+full-RF s; E previous one-point DPK quality; G2/G3 2/3-point naive independent Gaussian; F2/F3 correlated mixture with per-point and site bad hypotheses; H2/H3 CIR+power-ratio informed per-point/site mixture. Range is single anchor only. Oracle true-root branch run is diagnostic only.

For each station compare **same subset** and same schedule in all arms; separately evaluate full-route navigation after reinserting actual probe travel/rotation time. The saved 16-site offline result and 0.720° full-route LoS result are not directly comparable.

Required covariance separation:
Sigma_thermal = independent repeated receiver noise at same pose;
mu_MP / Sigma_MP = conditional multipath mean and correlated residual across calibration sites and yaw angles;
Sigma_pose = J_pose P6 J_pose^T;
Sigma_actuator = J_delta P_delta J_delta^T.
Avoid double counting pose P already used in the filter. Need both diagonal and OFF-DIAGONAL Sigma_probe. Multiple noisy measurements at same point are not independent samples of multipath. If full temporal cross-covariance is not estimated, restrict claim to diagnostic.

Metrics: heading RMSE/MAE/P95, position/lateral RMSE, NEES pose df3 and coverage, heading 95% interval coverage, pre-gate/accepted NIS, temporal residual ACF, q_site and q_point Brier/AUROC/ECE, failure/outage length, timing and no-harm vs RF-off/range baselines. Perform bootstrap over physical stations (1000 runs, seed20261010) and independent new environments. Use explicit NO_DATA, NOT_RUN, FAILED statuses rather than fabricated numbers.

## 7. Execution and outputs

STAGE0: verify Snowball RAW_ARCHIVE.tar, backfill base P6; report pose/station matching and no-data. STAGE1: matched 16-station LoS-only/full-RF with ideal fixed offsets + complete P6; compare 1/2/3 points. STAGE2: real noisy in-place rotation, independent thermal/noise seeds, 30/10dB arms, timing, return. STAGE3: fit frozen CIR/ratio prior + joint site/point posterior on training routes, held-out routes and independent geometry. STAGE4: integrate full-route correlated EKF/batch updates and NEES. STAGE5: different corridor widths/material/anchor, experimental hardware if available.

Files to deliver:
00_INPUT_AUDIT.json, 01_BACKFILL_P6_CHECK.json, 02_BODY_HEAD_ROTATION_CONTRACT.json, 03_HARDWARE_CIR_ACCESS.json, 04_STATE_TRACE_<run>.npz, 05_PROBE_RF_PACKETS.npz, 06_ORACLE_EVAL_ONLY.npz, 07_COVARIANCE_MODEL.npz, 08_RATIO_ASSOCIATIONS.csv, 09_SITE_POINT_RELIABILITY.csv, 10_PAIRED_FILTER_RESULTS.csv, 11_STATION_BOOTSTRAP.csv, 12_CALIBRATION.csv, figures, execution/containers/commands log and byte-level SHA manifests.

No parameter adjustment after inspecting held-out result. All 7 existing RF cases are one physical corridor, so even a statistically large sample does not establish transfer to general indoor environments. End status should retain F01/F02 OPEN and scientific_PASS=false unless independent model audits demonstrate otherwise.
