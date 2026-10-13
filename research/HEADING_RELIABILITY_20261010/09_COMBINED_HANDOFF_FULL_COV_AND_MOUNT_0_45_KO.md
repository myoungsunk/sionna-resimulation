# Sensor-v2 + Mount 0°/45° + First-arrival dual-LP 신뢰도 시뮬레이션 — 통합 전달본

버전: 2026-10-10 / 상태: SPEC_ONLY, 신규 채널 및 noisy-probe 필터 시뮬레이션 아직 미실행.

## 전달 및 실행 지시

이 파일은 먼저 06(전체 P6 및 noisy 2–3점 프로브), 이어 08(0°/45° 대칭 매트릭스와 first-peak/cluster 편파비)을 **원문 그대로 연결**했다. 실행 에이전트는 두 규격을 동시에 준수한다. 충돌 시: 08이 mount 범위 및 편파 특징의 실험 우선순위를 구체화하지만, 06의 full-P6/동역학/공분산/노이즈/보존/검증 필드 의무는 축소하지 않는다. 기존 결과는 수정/재라벨링 금지하고 새 결과 디렉터리에 저장한다.

새 Sionna full/LoS RF 채널이 필요한 것은 기존 7개를 제외한 5케이스다. 본격적인 probe 시뮬레이션 전에 5케이스와 RX/TX 편파축, LoS 기준의 검산을 먼저 완료한다. 실제 앵커 송신은 TX +45° LP 하나이며, +45° 수신 포트를 항상 co라고 부르면 안 된다. 1/2/3점의 원천 s, q_point, q_site, heading posterior와 P6를 함께 저장한다.

현 기준 소스 sha: sensor-v2 16d22fc3121963743cf7f1bf56233e00083c5518. 입력 정합/개선 성능이 미확정이면 명확히 BLOCKED/FAIL로 보고한다. F01/F02 OPEN / scientific_PASS=false 유지.

---

## Part A — 기존 06 데이터 사양서 (원문)

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

추가 필수 항목: 같은 RF observation에서 얻는 s와 range 사이의 교차공분산 Cov(s_i,range_j), 서로 다른 yaw sample들의 range–range/s–s 교차항을 포함한 joint covariance Sigma_sr[2M,2M] 및 공분산 PSD 검증 결과. 이전 A23에서 clean range–s lag0 상관이 약 +0.523으로 관찰됐으므로 독립 측정으로 단정하지 않는다. 이 행렬의 추정 소스·훈련 구간·유효 RF 독립 표본 수와 estimator 적용 여부를 명확히 구분한다.

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


---

## Part B — 추가 08 실험 명세서 (원문)

# 추가 시뮬레이션 명세서 — Mount 0°/45° 완전 대칭 비교 + First-path 편파 응답 불일치
버전: 1.0 | 작성: 2026-10-10 | 실행 상태: SPEC_ONLY / 신규 RF·filter 실행 미완료

**동반 필독:** 06_SENSOR_V2_NOISY_PROBE_FULL_COV_DATA_SPEC_KO.md (전체 P6, noisy 2–3점 프로브, cross-angle/range–s covariance의 상위 필수 데이터 계약).
이 문서는 06의 데이터 계약을 대체하지 않는 **실험 요인·편파 분석·판정 기준 추가 명세서**다.
기존 센서 v2 5,697회와 3점 MIX 분석은 비교 기준으로 보존한다. 본 문서 게시가 신규 0/45 RF 생성 완료를 뜻하지 않는다.

## 0. 고정할 질문과 설계 원칙

R-MOUNT: 45° mount가 0°보다 높은 LUT heading 민감도를 주는 구간에서 multipath에 대한 heading 안정성과 NEES가 함께 개선되는가?
R-POL: 송신 +45° LP / 수신 ±45° LP의 **동일 첫 경로 tap 및 첫 도착 뭉치**에서, 측정한 두 포트 전력비가 clean LoS 기준 전력비로부터 얼마나 달라지는가? 해당 불일치가 실제 heading 오류와 연관되는가?
R-POINT: 2–3개의 yaw 각도에서 일부 측정이 부정확할 때 해당 점의 위험도(q_point)와 측정 위치의 공통 위험도(q_site)를 동시에 추정하고, 모든 점을 확률적으로 가중해 heading 및 불확실성(전체 P6 포함)을 산출할 수 있는가?
R-NOISE: 열잡음에 의한 약전력 변동과 unresolved 반사파 간섭을 구분하는가?

물리 장면과 RF/FDD 입력이 서로 다른 것처럼 표시하지 않는다. 센서 사용 가능 특징은 포트별 first-path amplitude power P1/P2 및 장치가 실제 출력하는 magnitude-CIR까지만 허용한다. 복소 per-port 위상, Jones/path truth, reflected path delay는 **시뮬레이션 정답·진단 전용**이다.

### 중요한 물리적 규약 — "TX +45°이므로 RX +45°만 co"가 아님

현 소스의 안테나-local nominal boresight LP 벡터는 +45°=(x+y)/sqrt(2), −45°=(x−y)/sqrt(2)이다. 천장 TX의 회전은 diag(1,−1,−1), RX의 회전은 Rz(body_yaw+mount)이다.

- 수직 LoS, body yaw 0°, mount 0°의 이상적 직교 LP 극한에서, TX-local +45°는 world 기준 (x−y)/sqrt(2)이므로 **RX-local −45° 포트가 co-like**이고 RX-local +45°가 cross-like이다.
- 동일 극한에서 mount 45°이면 RX 두 포트가 TX 편파를 각각 절반씩 받으므로 P1≈P2, s≈0이 clean LoS에서 **정상**이다. 이때 다른 포트에 전력이 있다고 탈편파로 판정하면 안 된다.
- 로봇 yaw, 입사각, FFD pattern, 편파 누설과 강한 null에 따라 예상 P1/P2가 변한다. 포트 이름 자체를 보편적인 co/cross 명칭으로 쓰지 않는다. co-like/cross-like는 물리적 LoS 기준과 기준좌표를 함께 기록한 **조건부 설명**이다.
- 기존 corridor.py가 위 nominal 벡터를 기록하지만 실제 FFD bank의 해당 방향 Jones readback이 완료된 증거는 아니므로, 0°/45° 전 범위 원 RF 계산 전 **FFD boresight/transverse basis parity 검사**를 필수로 수행한다. 위 이상적 예는 PASS 기준의 방향성 sanity이며 FFD 정확한 수치를 강요하지 않는다.

## 1. 0°/45°를 대칭으로 채울 실험 매트릭스

직전 7개 full-RF/LoS 케이스의 상태는 아래와 같다.

| Route | Anchor A mount 0° | A mount 45° | Anchor B mount 0° | B mount 45° |
| --- | --- | --- | --- | --- |
| R2 (loop) | EXISTING | EXISTING | EXISTING | **NEW** |
| R4 (14-leg zigzag) | EXISTING | **NEW** | EXISTING | **NEW** |
| R5 (serpentine) | EXISTING | **NEW** | EXISTING | **NEW** |

**총 3 route × 2 anchor × 2 mount = 12개 케이스. 기존 7개 재사용, 신규 5개만 생성.**
신규는 R2_aB_m45, R4_aA_m45, R4_aB_m45, R5_aA_m45, R5_aB_m45.
모든 신규 케이스에 paired full-multipath H와 matched native direct LoS-only H를 모두 생성/보존해야 한다. 동일 (route,anchor)의 mount 0°/45°는 정확히 동일한 좌표·body yaw·타임라인·센서 noise seed를 사용하고 달라지는 것은 RX 장착각이다. 앵커는 한 번에 A 또는 B **한 개**만 작동한다. 앵커 위치 A=(4,0,2.65)m, B=(10,0,2.65)m, 로봇 RX 높이 0.45m, TX rotation diag(1,−1,−1).

각 H shape = [n_pose,257,2_RX,2_TX], 실제 관측 TX index0 +45°만 사용. RF pose 수는 R2=1303, R4=922, R5=1883.
신규 full 채널 pose-case 수=1303+2×922+2×1883=6913, 기존 9519와 합치면 총 16432 pose-case. **이는 서로 다른 16,432 위치가 아니다.** Full H 및 LoS H의 2종 SHA·pose-index parity와 12개 complete flag를 보존한다.

- 각도는 antenna_yaw = body_yaw + mount (rad/deg를 혼용하지 않음).
- mount 45°를 가진 R2-A 기존 데이터를 신규 생성하면 안 된다. 먼저 SHA parity 확인하고 재사용한다.
- 단순히 mount 0° RF H의 포트 전력을 재라벨링/교환하거나, yaw angle +45°를 오도메트리 truth에 대입해 mount 45° H를 만든다고 가정하지 않는다. Sionna solver 및 FFD의 동일 위치에서 RX orientation을 실제로 바꾼 RF 채널로 재검증한다.
- LUT 자체는 최초 동결된 공통 2° LoS FFD LUT (SHA 711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079)를 유지하고, h_LUT의 입력에 mount=0 또는45를 넣는다. 신규 LoS-native H와 모델의 F01/L1/L2 기존 FAIL은 새 PASS로 미화하지 않는다.
- ROUTE R2/R4/R5는 동일 복도 geometry(20×2.4×2.7m, plasterboard 양 측벽, 콘크리트 바닥·천장)를 공유한다. 12케이스 역시 cross-environment 반복이 아님.

**불균형 금지:** mount 45°는 이전 프로브 유효 subset에서 R2-A의 물리 지점 두 곳에만 존재했다. 프로브 가능한 전 장소를 두 mount에 대해 대칭으로 만들고 비교의 primary 집합을 두 mount 공통의 paired station으로 고정한다. 예전 RF-off prior 커버리지가 동일할 때 최대 공통 16 물리 지점 ×2 anchor ×2 mount 중 유효 route-specific case-station은 64개까지 가능하지만, 이 숫자는 미리 PASS/표본 수로 주장하지 않는다.

**예산 제약 시:** R2/R4/R5의 앵커 A에서 0/45 paired subset을 먼저 완결하고, 둘 중 45° 결과만 독립적으로 과장하지 않는다. 최종 main analysis는 12-case 완결 후 확정한다.

## 2. First peak / first-arrival cluster 편파비 — 주 분석 지표

delay spread, CIR kurtosis, 전체 CIR의 위치별 late-tail 통계는 주 분석에서 제거하고 **보조 진단**으로만 사용한다. unresolved path가 LoS와 시간상 분리되지 않는 상황에서는 에너지 분포보다 해당 early signal의 편파가 LoS 예상과 달라지는지 직접 검사한다.

### 2.1 First-path power ratio (모듈 최소 관측 가능 계약)

동결 observation.py와 정확히 같은 한 개의 common first-path tap k_fp:
Hann window → 4× zero-padding → IFFT×N → strongest RX branch 30% leading edge → **동일 k_fp에서 양 RX port 동시 power 채취**.

P1_FP=|CIR_RX+45[k_fp]|², P2_FP=|CIR_RX−45[k_fp]|².
s_FP=(P1_FP−P2_FP)/(P1_FP+P2_FP).
R_FP,dB=10log10[(P1_FP+floor)/(P2_FP+floor)].

s와 R_dB는 서로 독립적인 측정이 아니라 같은 두 전력의 변환이다. floor는 실제 수신기 잡음 바닥 또는 사전정의한 양의 수치 floor로만 설정하며 포트간 gain imbalance와 포화는 별도로 기록한다. numerator/denominator의 불안정성이나 first-path 검출 실패는 결측으로 기록한다.

### 2.2 첫 도착 "뭉치" (cluster, 추가 magnitude-CIR가 실제 출력되는 경우만)

두 RX 포트에서 서로 다른 peak/tap를 골라 비교하면 본래 물리적 편파비가 아니므로 금지. 동일 k_fp 기준의 공통 시간창 W_j을 설정한다.

E_i(W)=Σ_{n ∈ W} max(|CIR_i[n]|²−N_i[n],0).
s_W=(E_1(W)−E_2(W))/(E_1(W)+E_2(W)).
R_W,dB=10log10[(E_1(W)+floor)/(E_2(W)+floor)].

- 원 observation의 single-tap s_FP가 primary로 유지된다. first-cluster s_W는 amplitude-CIR가 하드웨어에서도 제공되는 경우에만 deployment candidate이다. 시뮬 complex H를 offline IFFT로 magnitude만 만든 경우에는 **research-only surrogate**라고 명시한다.
- 시험창은 single tap 및 공통 k_fp 기준 폭 약 2 ns / 약 4 ns / 약 8 ns의 세 후보를 사전 등록한다. 복소 CIR의 4× zero-padding sample grid는 실제 4× 지연 분해능을 의미하지 않는다.
- 어떤 cluster window를 primary로 정할지는 held-out heading error를 보기 전에 clean LoS-only 채널의 Hann/IFFT mainlobe 에너지 포집률과 포트간 상대 gain 보존성으로 판단한다. 선택된 구간의 실제 sample 시작/끝, window 및 noise floor는 LUT/reference와 measured 채널에 동일하게 적용한다.
- tap이 mount나 yaw에 따라 튀는 현상은 first-path 검출기의 비선형성일 수 있으므로 k_fp, strongest port, leading edge, peak 위치와 window boundaries를 모두 저장한다. 선택된 tap을 truth로 고정하는 oracle test는 온라인으로 해석 금지.
- 절대 전력 ratio와 cluster 적분은 하드웨어 gain, noise floor, port sensitivity에 영향을 받는다. 반드시 dB 포트 교정/드리프트를 포함한 noise arm을 따로 시험한다.

### 2.3 "수신된 다른 편파"의 증분은 clean LoS reference 대비로 정의

co/cross 포트를 yaw·mount에 무관하게 고정하지 않는다. 각 실험 각도와 입사기하에 대해 정확히 매칭된 LoS-only FFD의 예상 포트 전력을 기준으로 설정한다.

**Oracle 진단(진짜 XY/yaw, online 금지):**
e_MP,FP=s_FP,full_clean−s_FP,LoS_clean.
e_LUT,FP=s_FP,LoS_clean−h_LUT(p_true,psi_true,mount).
e_total,FP=s_FP,full_clean−h_LUT(p_true,psi_true,mount).

**Online 품질평가(사용 가능한 IMU/wheel/range 추정만):**
r_FP=s_FP,measured−h_LUT(p_beforeRF,psi_beforeRF,mount+delta_measured).

Cluster에 대해서도 원 FFD LoS-only 채널을 동일 창과 수신기 모델로 처리해 reference h_W를 **별도로 보정·검증**한다. 기존 single-tap LUT h_FP를 cluster s_W에 그대로 빼는 것은 서로 다른 observation chain이므로 금지. 별도 cluster-LUT가 물리 정합에 실패하면 cluster는 offline distortion 진단까지만 적용.

추가 feature:
- |e_MP,FP| / |e_total,FP| (오직 oracle label), online |r_FP| (predicted pose 오차가 섞임).
- s_FP, |s_FP|, P1+P2 및 R_FP,dB; cluster s_W, |s_W−s_FP|, R_W−R_FP,dB (magnitude-CIR available일 때).
- 두 포트 상대 gain 보정 후 **부호 있는** s와 그 LoS reference residual. |s| 자체는 비정상 편파·탈편파의 증거가 아니다.
- first-lobe 형상 및 port ratio의 yaw 변화량 [s(δ2)−s(δ1)] 같은 **실측 변화량**과 모델 예측 변화량의 차이; 모델이 맞으면 시간적·각도별 shared bias와 heading correction 구분에 도움이 될지 평가.

**물리적 한계:** coherent한 unresolved 반사파는 두 LP 포트에 다른 합성 전기장을 만들어 P1/P2를 왜곡하지만, 측정값 자체에서 LoS와 reflected power를 양의 에너지로 분리할 수 없다. 진짜 탈편파(DoP 저하), 편파 방향 회전, 타원편파는 두 LP 포트 amplitude power만으로 유일하게 구분할 수 없다. 따라서 최종 목표는 **LoS 편파응답 대비 mismatch 및 heading 오염위험도**이고 '절대 탈편파량'이라는 이름을 붙이지 않는다.

## 3. 2–3점 yaw probe와 편파 응답의 연결

로봇 본체 회전 시 ψ_antenna=ψ_body+mount+δ_body; 별도 head mode는 ψ_antenna=ψ_body+mount+δ_head로 분리한다. 직접 전파 계산은 true physical orientation을 쓰되 estimator는 gyro/wheel/head encoder 관측 orientation만 사용한다.

각 i에서 z_i=s_FP(δ_i), model h_i=h_LUT(x_beforeRF,δ_i). 잔차 r_i=z_i−h_i.
2점/3점은 사전 고정한 원 sweep의 [0, 2], [0, 2, 4] 인덱스(약 0,±10,±20°)를 우선 사용한다. 0/45 mount에서 두 점 세트의 상대 회전각과 회전 제어잡음 seed를 똑같이 대응한다. 다만 mount 45°에서 센서가 가파른 관측 구간에 놓이는지 q_slope도 실제 FFD LUT Jacobian으로 함께 기록한다.

임의로 가장 residual 작은 1점만 골라 사용하지 않는다. 점별 오염잠재상태 c_i, 위치 공통 오염상태 M을 둔 robust mixture/batch likelihood로 모든 z_i를 공동 사용한다. 결과에 q_site_bad, q_point_bad_i, heading multimodal posterior, heading mean/credible interval, P6 update, NIS/NEES를 보존한다.
- r_raw max/mean, common heading fit 이후 shape residual, Jacobian condition, angular response modulation depth 등을 특징으로 비교한다.
- 큰 raw r은 정상적인 heading correction 때문에 생길 수도 있으므로 RF corruption label로 직접 사용하지 않는다.
- 3점에서 모두 똑같이 heading 방향으로 이동한 clean-shaped curve는 gyro prior 없이는 true yaw shift인지 effective polarimetric rotation인지 구분할 수 없는 경우가 있다. 확률 보정·abstention/uncertain output을 평가한다.

이상적 균등 이득 직교 LP 수신이라면 s(α)≈(Q/I)cos2α+(U/I)sin2α. 단, body yaw/anchor 입사기하 및 FFD pattern이 모델과 일치한다는 가정하의 진단이다. 3개 yaw에서 Q/I, U/I를 추정할 수 있는가와 **로봇 절대 heading을 구할 수 있는가**는 다른 문제다. 작은 ±10~20° span에서는 선형 조화계수 추정이 불안정할 수 있으므로 설계행렬 condition과 noisy heading prior를 함께 기록한다. 수신 두 LP 포트 power만으로 V/I는 미측정이므로 sqrt[(Q/I)^2+(U/I)^2]를 전체 DoP라고 주장하지 않는다.

## 4. Full covariance + noisy 회전 실험 (06 사양서와 동시 적용)

06번 사양서의 모든 JSON/NPZ field requirement를 그대로 적용한다. 특히 다음을 누락하면 '완료'가 아니다.
- (T,6) 상태 및 (T,6,6) P6를 예측·odometry·range·RF 각 단계에 저장. 기존 pre_rf_cov는 range 전 단계임을 주의.
- 실제 본체 yaw, 명령 yaw, IMU/encoder yaw, slip, 회전 중 XY displacement, 회전/정착/측정/원위치 비용·시간.
- 원래 5Hz v2의 초기화·drift low/mid/high·wheelbase error·noise seed를 0/45 양 mount에 동기화. 독립 thermal noise seed와 realized SNR(제안 30/10dB) 분리.
- 위상 없는 관측 P1_FP/P2_FP, cluster power (available일 때), port gain/noise floor calibration, measurement timestamp.
- Sigma_probe: 같은 station의 2/3점 사이의 off-diagonal s–s covariance, range–s 및 range–range covariance까지 포함. Same H를 다른 gyro seed로 반복한 것은 독립 multipath sample이 아니므로 training covariance 독립표본 수 별도 보고.
- full/LoS channel에서의 관측 parity (same RX index convention, strongest port 30% FP index, shared tap), LUT L1/L2 FAIL 보존.

## 5. 완전 대칭 비교군 및 평가 표

0°와45° 각각 모든 6 route×anchor 조합에서 다음을 같은 RF station, path, seed, clock에 실행:
A = IMU+wheel, RF off.
B = IMU+wheel+single-anchor range.
C = B + matched native LoS-only s (full-route EKF).
D = B + full-multipath first-path s (full-route EKF).
E = 기존 1-point passive quality 정책 (single-angle, 가중/abstention).
G1/G2/G3 = 1/2/3점 naive independent Gaussian (부적절한 독립성 가정의 명시적 대조군).
F1/F2/F3 = 1/2/3점 latent site+point soft-weighting (초기에는 FP s만).
H2/H3 = 2/3점 F + port-power-ratio / calibrated first-cluster feature 기반 learned prior.
Optional S2/S3 = full amplitude-CIR가 실제 장비에서 가능할 때만 first-cluster s로 구현한 joint model.

**다음 두 결과표를 절대 혼합하지 않는다:**
T1: 같은 복도 **전체 주행** 후 A~H의 heading/position RMSE, NEES, coverage, 실제 probe time budget.
T2: 같은 station에 RF-off에서 출발한 **동일 시점 조건부 1/2/3-point correction** (LoS-only vs full RF, 0 vs45 mount). 이 T2는 부분 구간·한 번의 국소 추정이며 전체 주행 EKF 누적 성능이 아니다.
과거 T1 LoS-only C 0.720°, D 2.942°, A 9.893°와 과거 T2 3점 MIX 7.030°를 하나의 RMSE 순위처럼 비교 금지. T2의 동일 prior를 full/LoS·0/45에 공통 적용해 양쪽 모두 실제 재평가한다.

명시적 primary 평가:
- 같은 station에서 mount 45−0의 heading RMSE 차이(°), P95, mount 조건별 good/bad5 비율, distance/yaw/LUT slope stratification.
- first-path/cluster ratio의 LoS reference mismatch vs 실제 RF-only heading error, Spearman/Pearson; 정보 추가가치: distance+Psum 기준선 대비 measured s와 |s| 추가, 그 후 cluster mismatch/cross-angle residual 추가 (label truth는 feature에서 제외).
- q_site/q_point multipath 분류 AUROC/Brier/ECE/false clean; 실제 heading 5° 이내 판별 AUROC/Brier/ECE, risk-coverage; no-match/ambiguity 포함 분모.
- full-route pose-NEES (df=3), 95% pose/heading coverage, post-RF harmful update, long bad wall segments, probe elapsed time and yaw rotation energy.
- LoS-only full-route도 NEES가 3 이론값과 크게 다를 수 있음: 0.720°는 정확도 지표이지 model consistency 승인 아님.

모든 통계는 route/anchor/mount 별 분석, 같은 (route,anchor,station,seed) 내 0/45 paired comparison; 학습·검증은 route 단위로만 나누되 같은 복도라는 사실을 명시하고 완전한 cross-geometry 주장을 보류한다. Station/환경 cluster 기반 bootstrap 1000회(seed20261010). RF/noise seed가 많아도 독립 site 수가 늘지 않는다.

**PASS 최소 조건:** 12개 full+LoS H 입출력 parity와 해시, 실제 FFD co-like sanity, 06 데이터 schema, full-P6 PSD+단위, gain calibration, 포함 가능한 RF evidence, no-truth inference, paired coverage가 모두 통과해야 지표 비교 가능. 개선 주장에 대해서는 mount별 개선량 paired 95% CI, NEES/coverage와 accuracy trade-off, cross-geometry FAIL을 함께 공개한다. 일부에서만 RMSE 좋아도 "일반적인 향상"이라 말하지 않는다.

## 6. 구현 및 보존 단계

Stage 0 [기존자료 확인]: 총 12개 중 7개 존재/5개 없음, timestamp/pose IDs 동일성, TX/RX frame/FDD nominal parity, LoS/native observer parity, 기존 LUT SHA·FAIL 상태 확인. 신규 RF 계산 전 동결 manifest.
Stage 1 [신규 5개 RF]: Sionna full-multipath H와 native LoS-only H 생성; 0/45 동일 station RX mount orientation만 다르게 적용, 원본 절대 덮어쓰기 금지.
Stage 2 [관측 특징 추출]: first-path P1/P2 및 같은 tap s_FP primary; 동일 first-lobe common gate ratio secondary. Clean LoS reference와 full channel 분리, noise/gain controls.
Stage 3 [matched station]: F/G/H 1/2/3점, full 6×6 prior covariance, noisy gyro/wheel body turn, Sigma_probe offdiagonal와 range–s covariance, LoS-only와 full 비교.
Stage 4 [full-route filter]: 실제 수집 시간 포함한 12case×drift×seed 기법 비교, NEES·RMSE·업데이트 안정성.
Stage 5 [외삽 검증]: 복도 폭, 측벽 재질, 앵커 위치, R2/R4/R5 밖의 새로운 위치/방 layout. 이 단계 전 GENERALIZATION_NOT_PROVEN 유지.

반드시 제출할 추가 artifact:
A. MOUNT_CASE_MATRIX.json (12 조합, 5 NEW, full/LoS H SHA, station ids/FFDs).
B. ANTENNA_POL_FRAME_AUDIT.csv/json (actual TX+45 world vector, RX0/1 world axes vs body+mount, expected co-like, FFD Jones parity).
C. FP_CLUSTER_RATIO.csv / NPZ (P1/P2, s_FP, gate window and s_W, receiver gain, LoS prediction and oracle mismatch in separate file).
D. MOUNT_PAIRED_SITES.csv (0/45 same x,y,heading,anchor, RF seed and sensor prior, 1/2/3probe).
E. FIRST_CLUSTER_GATE_CALIBRATION.json (Hann mainlobe, capture fraction, no adaptive test leakage).
F. POL_RATIO_HEAD_ERR_ASSOCIATION.csv (by mount/route/anchor/distance/slope, valid root availability).
G. V2_FULL_COV_NOISY_PROBES.npz + CROSS_ANGLE_COV.npz; 06 document fields remain mandatory.
H. MOUNT_0_45_FILTER_COMPARE.csv, PAIRED_BOOTSTRAP.csv, EXECUTION_STATUS.json, exact source and output SHA256 manifest, failure/partial logs.

Explicit statuses: NEW_H_NOT_RUN, RAW_P6_NOT_BACKFILLED, COV_NOT_VALIDATED, FIRST_CLUSTER_HARDWARE_UNAVAILABLE, NOISE_ARMS_NOT_RUN, ROUTE_FILTER_NOT_RUN, FULL_GEOMETRY_NOT_VALIDATED. Never mark them completed based only on this document.

## 7. 보고용 핵심 표현 (연구 주장 범위)

확인할 가설은 "RX의 어느 하나가 항상 cross-pol이라서 cross power 증가가 직접 탈편파다"가 아니다. 정확한 표현은 **"LoS-only FFD가 예측한 dual-LP first-arrival power ratio 대비, multipath가 실제 합성 편파응답을 얼마나 왜곡하는지; 이 왜곡과 2–3점의 공통/각도별 구조로 single-anchor heading의 정확도·신뢰도를 개선할 수 있는지"**이다.

독립적인 전문 polarimeter 없이 두 LP amplitude만으로 절대 탈편파도(DoP)를 계산했다고 주장하지 않는다. 필요하다면 offline Sionna Jones oracle로 어떤 반사 경로가 port ratio 변화에 기여하는지 검증하지만 estimator inference에는 넣지 않는다. F01/F02 OPEN, scientific_PASS=false는 원문 그대로 유지한다.

