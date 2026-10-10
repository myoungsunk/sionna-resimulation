# Noisy Body Probe → sensor-v2 6-state EKF → Native Sionna exact-pose RF 통합

상태: **CODE_INTEGRATED / MOCK_UNIT_TESTS_ONLY / NATIVE_SIONNA_NOT_RUN / SCIENTIFIC_PASS_FALSE**

## 0. 기준 및 새 업로드의 보존

- 개발 기준: `codex/probe-mixture-reliability-20261010` HEAD `c9488b8be3a1745cd106ae326a67c17e3fed6459`.
- 해당 기준의 새 자료: `results/DRIVE_SIM_NOISY_PROBE_20261010/RUN_01a125b3/`. `PRE_CORRECTION_ARCHIVE`와 `C_CORRECTION_ARCHIVE`가 별도이며, fixed-truth noisy-body 제한 대조군이다.
- 기존 규격: `06_SENSOR_V2_NOISY_PROBE_FULL_COV_DATA_SPEC_KO.md`, `08_MOUNT_0_45_FIRST_CLUSTER_POLARIZATION_ADDENDUM_KO.md`, `09_COMBINED_HANDOFF_FULL_COV_AND_MOUNT_0_45_KO.md`.
- v2 출처: `16d22fc3121963743cf7f1bf56233e00083c5518` 감사 폴더의 `sensor_v2.py`, `filter_v2.py` Git blob을 변경 없이 별도 실행 파일로 가져왔다. **주의: `filter_v2.py`는 현재 브랜치의 legacy `filters.py`에서 `DriveFilter`를 상속한다. 두 버전의 독립 수치 parity는 실행 전 추가 확인해야 한다.** 기존 v2의 SE(2) transition, C=-GQBᵀ correlated odometry update 자체는 그대로 사용한다.
- 이전 physical plant 개발본 `codex/noisy-body-probe-dynamics-20261010`의 6개 신규 파일을 blob 그대로 가져온 뒤 새 streaming/integration 모듈만 추가했다. 기존 결과와 원 raw를 덮어쓰지 않았다.

## 1. 새 코드 호출 순서

```text
ProbeBodyController (prior ESTIMATED yaw; no oracle access)
    | cmd_v / cmd_w (0.2s held)
    v
DifferentialDriveBodyPlant (0.02s integration; motor + ground slip)
    | TRUE body XY, yaw, motor-shaft L/R ticks
    +----------------------------> RFPoseRequest at actual RF-fire time
    |                              |
    v                              v
BodySensorStream (persistent RNG)  NativeSionnaAtPose
    | ds_odom, dtheta_odom,        | full/LoS complex H from same actual
    | dtheta_gyro (measured)       | true XY/yaw, mount 0/45, TX0 +45
    v                              v
ProbeEKF6.start_interval           FirstPathReceiver
    | frozen sensor-v2             | first-arrival tap: P1,P2,s,range,
    | SE(2), Q/F/G, shared C       | detection, independent thermal RNG
    | x_after_odom, P6             v
    +<------RFFilterPacket (measured only; NO true pose/H/path oracle)
    |
    v
ProbeEKF6.apply_rf (range / diagnostic independent-s / sourced joint sr)
    | 6x6 x_before_RF/x_after_RF, covariance snapshots
    v
Estimated yaw/rate to controller; next physical interval
```

제어기는 시작 시점의 **추정 heading**을 reference로 사용한다. 실제 probe 0/10/20도는 참 각도가 아니라 추정 heading 기준 목표이다. motor acceleration/settling timeout 및 실제 slip 때문에 결과의 true yaw는 목표와 다를 수 있다. 채널 생성에만 true pose를 사용한다. `PROBE_HEAD`는 구현하지 않았다.

## 2. 파일별 책임

| 파일 | 책임/데이터 경계 |
|---|---|
| `body_dynamics.py` | 명령→모터 휠 속도 제한→종방향 지면 slip+횡방향 ICR→참 XY/yaw. 원본 샤프트 회전각 별도 |
| `body_sensor_stream.py` | 샤프트 좌우 + 실제 gyro yaw에서 5Hz 센서 측정 생성. RNG 상태 지속, 초기 zero-row RNG 소비, wheel scale/slip 중복 주입 방지 |
| `body_sensor_adapter.py` | 기하학적 계통 파라미터 부호 규약 및 fixed-timeline 어댑터. 본 폐루프 실행은 streaming API를 사용 |
| `sensor_v2.py`, `filter_v2.py` | 원 archived v2 소스 blob 그대로 보존; six-state EKF step, cross-correlated gyro–wheel C |
| `body_ekf_bridge.py` | 현재 FilterConfig에 v2 필수 속성 추가, time-varying dt, 6x6 P before-odom/after-odom/after-range/before RF/after RF, innovation/PSD guard |
| `body_probe_controller.py` | 회전·정착·측정·복귀. true yaw를 제어 피드백에 사용하지 않음 |
| `body_pose_channel.py` | Sionna heavy runtime lazy import; actual x/y/yaw+mount마다 full/LoS H를 새로 계산; 기존 observer의 공통 first-path tap 사용 |
| `body_probe_loop.py` | 단일 station 실제 센서/구동 clock의 causal orchestration; RF-fire일 때만 Sionna provider 호출 |
| `scripts/drive_sim/run_body_probe_v2_native.py` | 기본 precheck, 명시적 `--execute-native` 경계, overwrite 금지, raw/trace/manifest 보존 |
| `tests/test_body_ekf_pose_rf_integration.py` | mock native provider를 이용한 contract tests; 과학 실험 아닌 unit wiring 확인 |

## 3. 기존 모델과 설정의 유효성

- 6상태 순서: `[x_m,y_m,yaw_rad,gyro_bias_rad_s,gyro_scale,wheel_asymmetry]`. filter state에 물리 slip/ICR을 추가하지 않고 mismatch를 노출한다.
- TurtleBot3 명목값 `r_nom=0.033m`, `B_nom=0.287m`. `b_true=b_nom/(1+e_b)`, `r_true,L/R=r_nom/[(1+c)(1∓eps/2)]` 부호 규약은 archived sensor-v2와 같다.
- 기존 sensor-v2 `generate()`를 physical plant에서 다시 호출하면 ground slip, wheel scale이 이중으로 주입되므로 **호출하지 않는다**.
- 기본 physics step 0.02 s, sensor estimator dt 0.2 s. Native RF packet은 controller settle+integration 경계의 **실제 elapsed sensor time**에서 발생한다. RF 시점은 현재 5Hz tick에 양자화된다(서브샘플 packet 발생은 별도 모델 필요).
- `motor_time_constant_s=0.1`, 최대 휠 가속도 8 rad/s², 각 속도 25 deg/s, settle 0.4 s, RF integration 0.2 s 및 stress slip episode 강도는 **실측 없이 정한 예시 수치**다. 현재 config의 실제 physical slip은 `neutral`로 시작한다.
- wheel+gyro 측정 확률 오차는 기존 `k_s, k_theta, k_stheta`, `ARW`, bias RW의 생성 구조를 유지한다. 생성기의 물리 슬립 RNG와 관측 RNG는 별도 namespace를 사용한다.
- PS: `body_sensor_stream`은 연속 RNG를 유지하되 frozen fixed truth generator와 정확한 per-seed byte parity를 아직 주장하지 않는다.

## 4. RF 생성 및 관측 규약

1. 입력: `RFPoseRequest(packet_id,t_s,true_pose_xyyaw,mount_deg,station_id,point_index)`. 이 request는 RF 물리 계층의 oracle-only 입력이다.
2. `scripts/corridor_sionna_run.py`의 `build_scene`, `make_ports`, `set_bin`과 현 프로젝트의 FFD bank SHA 검사를 재사용한다. 채널 shape은 `[257, RX(+45,-45), TX(+45,-45)]`, 온라인 관측은 `TX0 +45`에서만 추출한다. RX+45가 모든 회전에서 co-pol이라는 주장은 금지.
3. receiver position은 `CorridorSetup.robot_position(x,y)`, 회전은 `CorridorSetup.robot_rotation(degrees(yaw)+mount)`로 계산한다. `C.mi.Point3f` 속성을 packet마다 설정하며 **이상적 고정 XY/yaw grid를 조회하지 않는다**.
4. native full 경로(`max_depth=3`, freq 257개)는 PathSolver의 `a`, `tau`를 coherent sum; LoS(`max_depth=0`)도 선택적으로 함께 생성. kernel 회전·bank·material·scene 파일 및 SHA를 provenance에 기록한다.
5. `observation.observe`의 Hann→4N IFFT→strongest-RX 30% first-arrival 공통 tap으로 `P1,P2,s,range`를 만든다. thermal 및 additive range 잡음 stream은 독립 유지, noise-free full/LoS H는 oracle 보관.
6. 아직 **Sionna 2.0.1 / actual FFD bank bytes / LoS parity가 이 브랜치에서 실행 검증되지 않았다**. Bank manifest/LUT 누락 시 synthetic H로 대체하지 않고 BLOCKED 처리.

## 5. RF update 정책·full P6 한계

- `rf.mode=range_only` (기본): 실제 H 생성 및 amplitude dual LP P1/P2,s 저장; EKF에는 range만 사용. 미검증 range-s correlation이 filter 결과를 오염시키는 일을 기본 차단.
- `rf.mode=independent_scalar_diagnostic` (명시적 opt-in): 실제 H의 range+s를 순차 scalar EKF에 넣어 *진단 대조군*으로만 사용. 원본 LUT 및 metadata가 반드시 필요. s–range cross covariance와 cross-angle temporal covariance를 알고 있다는 주장이 아니다.
- `ProbeEKF6` 내부 `joint_sr_diagnostic`는 **같은 packet의 출처 있는 2x2 Sigma_sr**이 제공된 경우만 동작하고 전체 시점 간 correlation은 여전히 미해결이다. 기본 CLI에서는 이 모드를 거부한다.
- `P6` 전체는 각 물리 샘플에 대해 저장되나, **다중 각도 관측의 joint posterior, site/point latent mixture, off-diagonal Sigma_probe, Sigma_sr[2M,2M]는 구현/적합/검증되지 않았다.**
- `x_after_range/P_after_range`는 range update 직후, `x_before_RF/P_before_RF`는 그 다음 s update 직전(또는 joint RF 직전)이다. `x_after_RF`은 최종 posterior. RF update가 없다면 해당 단계는 유효한 복제 상태다.
- frozen filter의 `H_odom,C_odom,F,G,Q`를 그대로 기록해 EKF 예측–관측 공유 노이즈를 추적한다. **oracle true pose/physical slip true labels를 EKF에 넣는 것은 금지**.

## 6. 실행 준비 및 파일 출력

기본 config: `configs/body_probe/ekf_native_noisy_body_v1.json`.

현재 `rf.bank_dir`, `rf.bank_manifest`는 `null`이므로 새 RF 생성은 준비되지 않았다. 실제 FFD bank .npz 바이트 및 검증된 `BANK_MANIFEST.json` 경로를 별도 제공해야 한다. `independent_scalar_diagnostic` 모드에는 frozen LoS LUT .npy 및 meta JSON도 필요하다. Git LFS 포인터를 bank 내용으로 오인하지 않는다.

```bash
# Precheck only; does not run simulator:
python scripts/drive_sim/run_body_probe_v2_native.py \
  --config configs/body_probe/ekf_native_noisy_body_v1.json

# Configure the external bank paths in a *copy* of the JSON first.
# This command actually launches native PathSolver at physical RF packet poses:
python scripts/drive_sim/run_body_probe_v2_native.py \
  --config /path/to/checked-config.json \
  --out /new/empty/output-directory \
  --execute-native

# No RF, no data runs: syntax & wiring unit contracts only:
python -m pytest -q tests/test_body_probe_contract.py tests/test_body_ekf_pose_rf_integration.py
```

실행 시 신규 out 디렉터리만 허용한다. `STATE_TRACE.npz` (full P6, F/G/Q/odom C/innovations), `ORACLE_EVAL_ONLY.npz` (실제 x/y/yaw, 휠 slip/ICR, motor, bias), `PROBE_RF_PACKETS.npz` (receiver data, timestamp/index), `RF_NATIVE_CHANNELS_ORACLE_ONLY.npz` (packet별 H/full-LoS), `BODY_CONTROL_LOG.json`, `RF_ORACLE_RECEIPT.json`, `COVARIANCE_STATUS.json`, `MANIFEST.json`을 기록한다. `MANIFEST`는 소스코드·외부 bank·config와 산출물 SHA를 기록한다.

## 7. 완료 판정 및 남은 작업

- **완료된 코드 경계:** 명령→물리 true XY/yaw→센서 obs→6-state EKF→추정 yaw 제어→actual-time/pose native RF 요청→first-arrival 측정→EKF update→P6 trace.
- **미완료:** 현 branch에서 native solver RF 수행 및 solver parity; archived filter/base numeric regression; real robot motor/slip identification; full-route 위험감지→probe→복귀→주행 재개; dual-angle joint covariance, q_site/q_point F/H mixture; 12case 0°/45° performance; F01/F02, independent geometry.
- **절대 주장 금지:** mock unit check를 물리 시뮬레이션 검증·Sionna 결과·실제 정확도 개선으로 해석하는 것.
- **현재 판정:** `scientific_PASS=false`, `F01/F02=OPEN`, `COV_NOT_VALIDATED`, `OPERATIONAL_CLOSED_LOOP_FULL_ROUTE_NOT_RUN`. 원 업로드의 C 보정 성능은 별개 제한 실험으로 보존한다.

