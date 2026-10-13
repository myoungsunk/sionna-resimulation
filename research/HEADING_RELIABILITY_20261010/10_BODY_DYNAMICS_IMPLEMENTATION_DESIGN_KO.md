# Noisy 본체 회전 구동 모델 설계 및 구현 근거

상태: **CODE_ONLY / UNIT_CONTRACT_VERIFICATION_PENDING_IN_REPO / RF_NOT_RUN / HARDWARE_NOT_TESTED**

기준: \`codex/probe-mixture-reliability-20261010\` HEAD \`7fefdbbf6c4f36ebff72fb281bbbbc5900fffd25\`. 동결 sensor-v2 revision \`16d22fc3121963743cf7f1bf56233e00083c5518\`. 상위 계약: \`06_SENSOR_V2_NOISY_PROBE_FULL_COV_DATA_SPEC_KO.md\`, \`09_COMBINED_HANDOFF_FULL_COV_AND_MOUNT_0_45_KO.md\`.

## 설계 이유 — 기존 코드 기준

- \`trajectory.py\`와 \`steered_probe.py\`: 기존 body probe는 고정 XY에서 yaw만 변경한다. 물리 시간·가감속·미세 위치 이탈을 반영하지 않는다.
- 동결 \`sensor_v2.py::generate()\`: scripted truth 증분으로 센서값을 역생성한다. 기존 Student-t \`slip\`은 encoder yaw 오차 **뿐**이며 true XY/yaw를 바꾸지 않는다.
- 동결 \`sensor_v2.py::motion_increments()\`: lateral residual을 허용하지 않으므로 실제 횡방향 slip의 inverse motion으로 사용할 수 없다.
- 동결 \`filter_v2.py\`: 6x6 SE(2) EKF 및 gyro–wheel noise correlation을 이미 처리한다. 최초 단계에서 filter는 변경하지 않는다.
- 연구용 물리 slip은 관측 오차와 분리해야 하므로 별도 plant가 필요하다.

## 추가한 파일·API

- \`src/qclean_uwb/drivesim/body_dynamics.py\`: \`DifferentialDriveBodyPlant.step(command_v_m_s,command_w_rad_s,dt_s)\`. 1차 모터 응답+휠 가속도·속도 제한, left/right 실제 encoder shaft angle, ground-contact longitudinal slip과 lateral ICR, true pose의 exact constant-twist SE(2) 적분. 물리 RNG 독립 namespace \`2201016\`. 출력 \`BodyTick\`은 **oracle truth**.
- \`src/qclean_uwb/drivesim/body_sensor_adapter.py\`: \`sensor_v2_from_physics(...)\`는 physics ticks를 실제 sensor timestamp로 집계. 추정기 전용 입력(\`ds_odom\`, \`dtheta_odom\`, \`dtheta_gyro\`, measured encoder)은 오차를 단 한 번 주입한다. 별도 \`evaluation_only\`에 true pose, motor increments, slip mask, bias 보관.
- \`src/qclean_uwb/drivesim/body_probe_controller.py\`: \`ProbeBodyController.update(estimated_yaw_rad, estimated_yaw_rate_rad_s,dt_s)\`는 오직 **추정값**으로 각도 제어/정착/측정/복귀 상태 전환. 1/2/3점 [0], [0,10], [0,10,20], timeout, 1회성 RF-fire 신호.
- \`tests/test_body_probe_contract.py\`: deterministic 단위 계약. 실제 Monte Carlo/ROS/Gazebo/Sionna 주행은 아님.
- \`configs/body_probe/assumed_body_probe_v1.json\`: 기본 설정의 출처/가정 구분.

## 수식·물리적 의미

\[
\Omega^{cmd}_{L/R}=\frac{v^{cmd}\mp B_0\omega^{cmd}/2}{r_0},\quad
\dot\Omega_i=\mathrm{clip}((\Omega_i^{cmd}-\Omega_i)/\tau_m,-a_{\max},a_{\max}).
\]

\[
u_L=(1-\lambda_L)r_L\Omega_L,\quad u_R=(1-\lambda_R)r_R\Omega_R,\quad
v_x=\frac{u_L+u_R}{2},\quad \omega=\frac{u_R-u_L}{B_{true}},\quad
v_y=-x_{\rm ICR}\omega.
\]

\[
\dot x=v_x\cos\psi-v_y\sin\psi,\qquad
\dot y=v_x\sin\psi+v_y\cos\psi,\qquad \dot\psi=\omega.
\]

각 interval의 constant body twist를 exact SE(2)로 적분한다. \`r_true,L/R=r_nom / [(1+c)(1∓eps/2)]\`, \`B_true=B_nom/(1+e_b)\`는 sensor-v2 문서의 **동일한 부호 규약**이다. encoder shaft angle은 ground-slip 이후 차체 이동량에서 역추정한 것이 아니라 *ground-slip 이전 실제 motor shaft angle*이다. 이 차이가 physical slip을 센서 데이터에 반영하는 핵심이다.

슬립 episode 발생 hazard는 \`1-exp(-lambda dt)\`, duration은 지수분포, 크기는 제한된 Student-t 가설 분포이다. **1%/sample encoder slip 모델의 실제 물리 해석이 아니다.** 기본값은 physical slip 비활성화. 추정기에는 event truth를 보내지 않는다.

## 구현상 검증해야 할 경계

1. 물리 plant와 같은 \`WheelGeometry\` run realization을 sensor adapter에 공유해야 한다. 불일치 시 \`GEOMETRY_REALIZATION_MISMATCH\`로 실패한다. 동결 sensor-v2의 \`draw_drift\`과 동일 seed namespace의 low/mid/high 부호 구조를 보존한다.
2. sensor-v2 \`generate()\`를 다시 호출하면 geometry와 wheel noise/slip이 중복 적용될 수 있어 금지한다. 새 adapter로 sensor-only measurement를 생성한다.
3. 실제 lateral slip이 있는 경우 기존 filter의 비홀로노믹 과정모델은 불완전하며 NEES가 틀어질 수 있다. 필터 Q/R을 결과에 맞춰 임의 tuning하지 않는다.
4. 5Hz estimator 입력과 빠른 physics integration은 다른 clock을 갖는다. 센서 timestamp의 물리 tick이 일치하지 않으면 실패한다. RF packet은 별도 실제 발생 시각에만 생성하고 true pose를 사용한 Sionna RF H를 새로 계산해야 한다.
5. Controller는 측정 heading feedback을 받기만 할 뿐, 이 커밋은 \`plant → sensor → EKF → controller\` orchestrator나 RF 호출 스케줄러를 생성하지 않는다. **전체 실험 실행 가능 단계라고 주장하지 않는다.**
6. RF H 재계산, full P6 trace, s–range joint covariance, 0°/45° 12case, full-route 성능, 실제 Waffle 실험과 동역학 calibration은 **NOT_RUN/NOT_IMPLEMENTED**로 남는다.
7. 기존 raw/results/frozen/source commit을 덮어쓰지 않는다. \`scientific_PASS=false\`, F01/F02 OPEN 및 L1/L2 미해결 상태는 유지한다.

## 수치 선정

nominal wheel radius 0.033m, wheelbase 0.287m는 ROBOTIS Waffle nominal. motor time constant .10s, accel 8 rad/s², speed 8 rad/s, physics step <=.02s, angular accel 100deg/s², yaw tolerance .7deg, settle .4s, RF window .2s는 **실측 없는 구현 출발 가정**이다. 25deg/s는 사양서의 *후보*이지 실물 측정 한계가 아니다. default slip zero, stress-only episode 값은 실제 환경 확률로 해석 금지.

## 근거

- [ROBOTIS Waffle Gazebo SDF](https://github.com/ROBOTIS-GIT/turtlebot3_simulations/blob/main/turtlebot3_gazebo/models/turtlebot3_waffle/model.sdf): wheel geometry와 구조; 마찰 파라미터는 SDF 자체에서 unreliable 주석이 있다.
- [Gazebo WheelSlip](https://gazebosim.org/api/sim/10/wheel_slip_systems.html): 종/횡 slip의 물리 simulation reference. Gazebo compliance를 현재 ratio로 그대로 변환하지 않는다.
- [ROS 2 diff_drive_controller](https://control.ros.org/humble/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html): velocity/acceleration/jerk 명령 제한 참고, 접촉 물리 검증 소스 아님.
- Borenstein & Feng, *Measurement and Correction of Systematic Odometry Errors in Mobile Robots* (1996): geometry systematic error 분리.
- Mandow et al., *Experimental Kinematics for Wheeled Skid-Steer Mobile Robots* (IROS 2007): ICR parameterization idea; skid-steer 계수는 TB3에 복사하지 않는다.
- Kelly, *Linearized Error Propagation in Odometry* (IJRR 2004): position/heading uncertainty propagation.

## 개발 상태

이 브랜치에서는 위 세 개의 독립 모듈, 설정 및 계약 테스트만 추가한다. 코드가 existence만으로 experimental validation이 되는 것은 아니다. 구현을 통합하려면 estimation loop·measurement times·RF pose provenance·full P6 output을 차례대로 연결하고, 소스 SHA 및 독립 실물 calibration을 추가해야 한다.
