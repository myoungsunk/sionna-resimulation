# 21 — 저장된 RF H 기반 128개 독립 센서·수신기 seed로 시점 간 6×6 공분산 재구성 검증

실행일 2026-10-11. [GitHub Actions 38114771245](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38114771245) SUCCESS. 원 코드 run_pose_rf_cross_time_mc_existing_H.py. 기존 R2-A mount0 T10 g50 저장 원 H, 시간, x/y/yaw, frozen sensor-v2 F/G/Q Kalman gains. 실제 native Sionna 신규 생성은 안 했다. 기존 full H로 thermal Gaussian noise (nominal SNR30)만 128번 독립적으로 생성.

## 1. Theory vs empirical

측정 시점은 기존 T10 전체 이력의 k=[68,88,90], t=[13.6,17.6,18.0]s. 이전 프로브 이력까지 모두 range-only EKF로 계속 갱신한 뒤 각 시점에서 pre-s(no s used) P6와 참 상태오차를 저장했다. Odometry의 H는 pre-transition calibration state를 기준으로 하므로 effective linear state propagation A_odom=F−K_odom H_pre; range update A_range=I−K_range H_range. 시점 i,j 이론 교차공분산은 P_i × (A_j ... A_{i+1})^T로 계산했고 128seed empirical center covariance Cov(e_i,e_j) 및 bias-inclusive MSE E[e_i e_j^T]와 구분했다.

| Component | EKF mean predicted | MC centered variance | MC error MSE | MC MSE/pred |
|---|---:|---:|---:|---:|
| t=13.6s heading rad² | .002486 | .001655 | .001944 | .782 |
| t=18.0s heading rad² | .002503 | .002909 | **.005401** | **2.158** |
| t=18.0s XY covariance trace m² | .006427 | .006357 | .008022 | 1.248 |
| t=13.6→18.0s heading cross rad² | .002361 | .001851 | .000966 | .409 |

Bootstrap independent seed 1,500 repeat (seed 20261011) t=18.0 Heading MSE/pred ratio 95% CI [1.77,2.56], centered covariance ratio1.16 CI [.90,1.44]. Thus this test's dominant error in uncentered MSE includes **systematic pose/heading mean bias** despite centered variance being near the model. Centered sample covariance agreement **alone** would not prove a consistent full posterior.

## 2. RF quality distinguishes receiver white noise from site RF bias

At the SAME physical xy but three yaw snapshots, modeled range residual means (z_r − true geometric range − fixed hardware/pulse offset):
- t13.6s: −0.040731m;
- t17.6s: −0.339835m;
- t18.0s: −0.489387m.

After thermal receiver seeds 128 repetitions, empirical variance of range residual at each snapshot ≈ 0: strongest 30dB first-path tap remained fixed. Thus receiver noise resampling did not remove orientation-specific multipath/pulse-selection bias. Filter assumed range σ≈.082812m. Independent thermal noise cannot be used to infer persistent site multipath bias variance by itself.

s residual means (noisy full s − h_LUT(true pose)): +.030623, −.070902, −.221501. Empirical across-noise covariance correlations between different yaw snapshots were only 0.056,0.071,0.095, near zero at n128. This is NOT contradictory to original 169-site spatial multipath s residual corr≈.8, because one statistic is receiver thermal-noise independence at fixed RF H and the other is variation of deterministic spatial bias across sites.

## 3. Conditions and limits

All 128 independent seed trials are ONE corridor/ONE anchor/ONE stationary XY and original fixed T10 true yaw kinematics. State estimation included 6state sensor-v2, full 6×6 P; K from actual odom/range gates and input F/G/Q; RF range was sampled from stored clean frequency H with independent simulated thermal noise. This *is* a real source-backed cross-time verification of a LIMITED conditional stochastic model, not the full 12case dynamic physical yaw/q_site posterior.

Predicted P_ij recursion is a first-order approximation and assumes new noises independent of previously accumulated state errors. Persistent multipath bias, thermal sampling quantization and gyro/wheel nuisance calibration violate the general unconditional inference model. Real actuator slip, time-dependent RF geometry and joint s/range posterior were not run here. No permanent "validated P6 cross-time for all scenes" or correct q_site/qpoint statement may be issued. Scientific_PASS remains false.

Required next: predeclare sensor/radio seed/sample size and jointly compare estimated P_ij, E[ee^T], range/s measurement covariance and state–measurement noise cross covariance at >1 site and mount0/45, independent new geometries. Next full-route fixed-lag/bias-state EKF variants must test 95% coverage and NIS residual whiteness, not just RMSE.
