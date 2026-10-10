# 15 — 상시 Sensor-v2 EKF + 측정 신뢰도 조건부 정지·제자리 프로브·계속 주행: 구현/검증 결과

작성 2026-10-11 | 연구브랜치 codex/continuous-trigger-ekf-bridge-20261011 | 상태: **SOURCE_INTEGRATED / MOCK_CONTRACT_PASS / NATIVE_SIONNA_FULL_ROUTE_NOT_RUN / SCIENTIFIC_PASS_FALSE**.

## 목적을 다시 고정

정상 주행의 매 0.2초 센서 시점마다 IMU+wheel 및 single-anchor range로 전체 6상태 EKF를 진행하며, 편파 RF s가 충분히 신뢰되면 그 시점에 갱신한다. 신뢰도가 낮으면 먼저 RF s를 보류한다. 로봇이 실제로 멈춘 좌표에서 2/3개의 서로 다른 body-yaw 관측을 수행하고, **동일 위치 오염 잠재변수(site)와 각 yaw 포인트 오염잠재변수(point)를 한꺼번에 고려해 모든 s를 소프트하게 반영**하여 전체 x6/P6를 갱신한다. 그 갱신값을 다음 주행 시점의 같은 EKF로 전파한다. 주행 중 이동 중 측정된 trigger s를 멈춘 정지점 s0로 재활용하지 않는다.

이전 오프라인 7.03°는 요구 시스템의 결과가 아니다. 기존 저장 T10 bank를 사용하는 840회 **지속 주행 EKF**는 별도 실제 실험으로 완료됐지만, arbitrary new real-XY trigger, 12case mount 0/45 및 실제 동역학을 모두 반영한 결과는 아니다.

## 실제 코드 연결

| 소스 | 담당 |
|---|---|
| src/qclean_uwb/drivesim/body_dynamics.py | 명령→wheel/motor 응답/ground slip→참 XY/yaw (RF oracle만 참 pose 접근) |
| body_sensor_stream.py | 실제 motor shaft + gyro true yaw를 기반으로 지속 RNG IMU/odom 센서 관측 생성 |
| body_ekf_bridge.py | frozen Sensor-v2 SE2 6state transition, odom C cross covariance, range/s update, 전체 P6 추적 |
| body_active_drive.py | **매틱 주행→range→pre-s quality→정상 s / low시 stop physical probe→site batch→same EKF continue** |
| body_probe_loop.py + body_probe_controller.py | 센서 기반 각도 제어, 정착, 실제 2–3측정, 복귀, RFPoseRequest at actual true XY/yaw |
| body_pose_channel.py | native Sionna exact-pose provider (FFDs 외부 필요), first-path tap과 shared early window (4/8/16 tapped) LP 진폭비·P1/P2를 measured packet에 포함 |
| body_active_policies.py | **임시 비보정** pre-RF NIS + 측정 cluster contrast 기반 q_good 위험도, 정상 single-s soft R 업데이트 콜백 |
| body_site_mixture.py | 2×2^M latent site+point 6state multivariate Gaussian likelihood/Joseph updates 및 moment matching; q_site/q_point, x6/P6 출력. 모든 측정점 사용하며 minimum residual point selection 없음 |

Normal x6 after range에 대한 R_s innovation을 확인하기 전까지 해당 s를 EKF에 넣지 않는다. s posterior의 R inflation and quality conversion numbers are **hypothesis constants**, not validated as real probability. Low-quality site/point mixture의 common site offset/yaw covariance 역시 20261010 사전등록 탐색값을 사용한다.

## Unit source-backed 테스트

- GitHub Actions https://github.com/myoungsunk/sionna-resimulation/actions/runs/38065267401 — **31 passed**.
- 실제 동적 plant slip 발생 시 Sionna용 true pose request의 XY 변화 반영 확인.
- simulated first-arrival 4/8/16-tap P1/P2 & s gate가 measured RF packet과 site posterior callback에만 들어가는지 확인 (위상/LoS oracle 누설 금지).
- Low q triggers, high q normal RF update, q false/NaN fail close, 2/3 packet count, q_site/q_point normal/dirty hypothesis count=2×2^M (3점 시 16), P6 PSD, range-only pre-quality, no double-use of trigger s.
- Posterior x6/P6를 **다음 drive predict F/G/Q의 입력**에 사용하는지 계산 수준에서 parity 확인; step time and sensor clocks synchronized.

**실행 범위 제한:** 소스 테스트는 FakeRFBackend analytic synthetic H와 frozen v2 filter를 사용하는 mock contract이다. 실제 native Sionna를 사용한 12case×route Monte Carlo 아니다. 구현이 SOURCE_INTEGRATED인 것과 과학적 효과가 검증된 것은 다르다.

## 본 실행 전에 해결할 네 가지 필수 경계

1. **실제 FFD/LUT 연결 및 RF source parity.** NativeSionnaAtPose requires FFD bank bytes and BANK_MANIFEST (default config currently null), correct solver setup and frozen 2° LUT; old legacy Method B vs new native full H 5-case parity unresolved. Newly generated native LOS must be used with correct mount/anchor; full-path high-level FFD ports verified on actual bytes.
2. **Quality risk probability calibration.** Nominal NIS sigmoid and |s_early−s_FP| are measured feature heuristic, not calibrated q=P(|heading error|<5°). Low confidence can occur from actual odom heading error in high LUT slope; threshold and thresholds learned on train routes/geometry held out needed. CIR hardware availability UNKNOWN; if only P1/P2 accessible, firstcluster must be disabled, not simulated from inaccessible hidden phase.
3. **Mixture model's cross-time correlations.** SitePointMixture6 uses full P6 at end of turn but treats 2–3 s collected at different times with an approximate shared site covariance; full pose–measurement cross-time correlation is unvalidated. Spatial moving/actual slip between packet captures is not physically an identical site; default estimated XY stationarity guard .02m rejects mismatch. q_site/q_point posterior only nominal and must never claim physical calibration. Range and s correlations in newer dataset have not yet been applied to this source.
4. **Full-route physical test.** ContinuousRFQualityDrive takes an externally supplied (v,w) command sequence; it does not replan robot navigation commands using corrected pose. Thus it demonstrates estimator propagation/active motion and true slip RF requests, not navigation-path optimization. Run user-requested 12case×mount0/45 physical true XY/yaw native Sionna with independent holdout geometry; compare D/E/SHAM/F2/F3 and sensor-noise/SNR with correct full-route progress/time, bad5, P6 NEES/95coverage, posterior q Brier/ECE.

## Existing uploaded 2026-10-10/11 evidence caveat

RUN_01a125b3 uploaded 12case old/new H, 53,280 endpoint results; this is fixed-truth **station end-state** comparison, not full-route. G1/G2 also reduce range sample count, so not a clean probe-s-only ablation. Firstcluster new station harness uses 5/9/17 tapped while this integrated online source uses registered 4/8/16 tap. Before statistical parity comparisons align gate indices and hold all three range samples fixed.

Older 840-run T10 bank result heading F3 2.787° vs passive E 2.909°, but pose NEES F3 180.4 vs E 156.4, so full-route scientific no-harm/consistency not PASS. Need compare 12-case cross-geometry and physical stop/turn conditions before adoption.

**Current verdict:** Real user-requested causal flow is connected and covered by 31 mock-contract tests, but native RF Monte Carlo, quality probability calibration, full cross-time covariance, accurate pose-control navigation and physical motor parameter calibration remain UNVERIFIED. F01/F02 OPEN and scientific_PASS=false preserved.
