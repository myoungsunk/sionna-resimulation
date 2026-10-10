# Sensor-v2 사용·수식 계약

모델은 명시적으로 선택한다. 기존 `run_experiments.py`, `run_route_experiments.py`는 `--model-version legacy`(default)이고 production 동작/RNG는 유지된다. `sensor-v2` 지정은 별도 runner를 안내하며 거부한다. 새 runner는 `--model-version sensor-v2`가 필수다.

```powershell
py -3 scripts/drive_sim/run_sensor_v2.py --model-version sensor-v2 --out results/NEW_SENSOR_V2_RUN --runs 48
```

CPU 직렬 실행이며 기존 출력이 있는 디렉터리는 거부한다. `--sensor-config`와 `--filter-config` JSON으로 생성기와 추정기의 가정을 별도로 지정한다. `configs/sensor_v2/neutral.json`은 common scale와 bias RW가 0인 기본 조건이다. 다른 두 assumed 예제의 .01 scale, 1e-4 rad/s/sqrt(s)는 민감도 가정이다. 실물 보정 수치가 아니다. `condition`은 none, 각 단독 항, bias_asymmetry/asymmetry_wheelbase/noise_pair, all을 지원한다. sensor JSON이 있으면 JSON의 condition/level을 사용한다. timestep은 입력 timestamp 차분이 권위이며 필터의 dt 고정값을 사용하지 않는다.

생성기와 필터 상태는 별개다. true pose/drift는 `evaluation_*` 필드에만 저장한다. 센서 생성·초기 오차의 통제된 정의·평가·명시적 ideal 재적분에서만 truth를 사용한다. 추정기는 measured input/observation과 설정/prior만 받는다. 여섯 상태는 [x,y,psi,b_g,SF_g,eps]로 보존하고 common scale나 e_b 상태를 추가하지 않았다.

## 기하·잡음

m_L=(1+c)(1-eps/2), m_R=(1+c)(1+eps/2), r_true,L/R=r_nom/m_L/R, b_true=b_nom/(1+e_b).

고정 truth에서 실제 좌우 이동은 l_true=ds-b_true*dpsi/2, r_true=ds+b_true*dpsi/2이고 encoder angle=l_true/r_true,L, r_true/r_true,R이다. nominal odometry는 r_nom*angle을 이용한다. eps>0은 오른쪽 nominal 이동 과대이며 실제 오른쪽 radius는 작다. e_b>0은 실제 wheelbase가 nominal보다 작다. 이는 문헌의 Ed/Eb 정의와 동일 이름의 수치를 그대로 대입한 것이 아니다. 기존 magnitude만 유지했다.

A=[[1/2,1/2],[-1/b_nom,1/b_nom]]. q_d=k_s|ds|, q_theta=k_theta|dpsi|+k_stheta|ds|. 기존 aggregate 계수를 보존하기 위해 Q_LR=A^-1 diag(q_d,q_theta) A^-T를 정의한다. 따라서 Q_(distance,yaw)=A Q_LR A^T이다. 좌우 noise가 일반적으로 서로 상관된다. 같은 noisy raw encoder에서 distance/yaw를 복원하며 추가 독립 odometry 잡음을 다시 얹지 않는다. 실제 Q_LR는 평가 필드에 저장하고 추정기는 truth Q를 받지 않는다. 추정기 Q는 measured distance/yaw에서 같은 계수를 적용하는 EKF 근사다.

gyro=(1+SF)*dpsi+b_start*dt+N*sqrt(dt)*normal(0,1), Var(delta_angle)=N^2 dt. b_endpoint=b_start+sigma_b*sqrt(dt)*normal. gyro는 해당 interval의 left endpoint bias를 사용한다. 기본 sigma_b=0이며 활성화된 bias RW는 별도 생성 조건이다. continuous Brownian bias를 interval 내부에서 정확히 적분한 모델은 아니다: T=n dt에서 Var(sum b_start dt)=sigma_b^2 dt^3 (n-1)n(2n-1)/6, continuous 기준 sigma_b^2 T^3/3과 차이를 `bias_rw_discretization.json`에 기록했다. 실물 PSD/대역폭 일치나 sqrt(2) 보정은 주장하지 않는다.

시간 slip p(dt)=1-exp(-lambda dt), lambda=-ln(.99)/.2. `legacy-event`는 .01/sample. 두 모드는 5 Hz에서 같은 event 확률이다. 제자리 회전 interval에만 적용하며 nominal 좌우 increment에 [-b*s/2,+b*s/2]를 더한다. Student-t(df3)의 scale은 .5deg, SD는 sqrt(3)*scale. 원시 event/적용 yaw 크기/eligibility를 저장한다. fixed truth를 바꾸는 동역학 모델이 아니라 encoder 오차 모델이다. 지속/곡선 slip은 추가하지 않았다.

## SE(2)·기존 truth 규약

u=distance-eps*b_true*a/4, a=(gyro-b_g dt)/(1+SF), 이동=u*sinc(a/2)[cos(psi+a/2),sin(psi+a/2)], yaw+=a. 여기 sinc(x)=sin(x)/x이며 작은 각은 Taylor 전개한다.

`motion_increments(...,convention='se2')`는 midpoint 방향 chord를 투영해 signed distance를 구한다. `legacy-euler`는 이전 heading 투영이며 기존 R1 artifact만 이 규약으로 생성됐다는 확인에 사용한다. 두 규약 모두 lateral residual을 검사한다. 180deg 이상 interval 회전은 ambiguous하므로 resample을 요구한다. unwrap 입력 여부를 명시한다. 정지/후진/원호/yaw 경계 검산을 수행했다. legacy truth를 SE2 truth로 조용히 바꾸지 않았다.

## 공유 입력 상관 갱신

오차 e=true-est. n=[n_distance,n_gyro,n_odom_yaw], e_minus=F e_prev-Gn, P_minus=F P_prev F^T+GQG^T.

known e_b 값은 외부 보정 설정이고 unknown 조건에서는 0으로 남긴다. c=0 가정일 때 h=( (1-eps^2/4)*a + eps*distance/b_true )/(1+known_e_b). H는 calibration 상태 derivative이며 pose 열은0이다. input derivative h_d,h_g에서 v=B n, B=[-h_d,-h_g,1]. 따라서 C=Cov(e_minus,v)=-GQB^T. wheel distance 및 gyro 항 모두 포함한다.

S=H P_minus H^T+R+H C+C^T H^T, R=BQB^T, K=(P_minus H^T+C)/S.

M=I-KH, P_plus=M P_minus M^T+K R K^T-M C K^T-K C^T M^T. state+=K innovation. calibration state는 이 interval에서 고정돼 있으므로 pre-step H를 propagated covariance에 적용할 수 있다. endpoint bias RW는 odom 갱신 후 더한다. C=0에서 표준 Joseph 갱신으로 환원된다. R에 gyro variance만 추가한 처리가 아니다.

기존 RF range/s 갱신식은 그대로 사용한다. RF range와 s의 공통 H-noise 상관, 시간/기하 LUT 잔차는 해결하지 않았다. near anchor horizontal distance<=1e-6에서 s azimuth는 정의되지 않으므로 명시적으로 skipped status를 남긴다. range의 3D distance는 유효하면 사용한다. covariance gate/σ/position slack으로 결과를 맞추지 않았다.

v2는 EKF/direct-s만 지원한다. IEKF/UKF/GSF/inverse-s는 입력 단계에서 오류다. legacy 4종은 그대로 실행된다. 일반적인 nonlinear EKF/6-state 관측성을 입증했다고 해석하지 않는다.

## 저장·평가

NPZ: time, truth, measured raw input, true parameters/bias/Q, slip, initial/prior, full estimate state/covariance, observation data/innovation/R/S/H/C/status, masks, directional errors. applied/rejected/missing/disabled/initial/zero_variance/skipped_turn/undefined_geometry를 구분한다. fixed/ideal dead reckoning은 full covariance를 계산하지 않으므로 unavailable로 명시한다. 기존에 저장되지 않은 legacy raw를 복원했다고 주장하지 않는다.

기존 `experiment.summarize_output`을 공유해 공통 drive mask, coverage/RMSE를 중복 구현하지 않았다. seed/run이 통계 단위이고 시간 평균 NEES는 descriptive다. 합성/실제 RF는 별도 디렉터리다. manifest는 설정/단위/seed streams/source SHA+file hash/input/output hash/명령/UTC를 기록한다.

body-forward/lateral은 true body frame 투영이라 후진에도 축을 바꾸지 않는다. body_motion_valid는 ds!=0, reverse_mask/stop_mask를 따로 저장한다. anchor radial/tangential은 horizontal rho<=1e-6이면 invalid/NaN이다. heading/distance 재적분은 ideal truth heading 또는 true distance를 사용하는 평가용 보조 진단이며 오차 원인의 가산 분해가 아니다.

## 공식·원문 근거

- [Borenstein/Feng, UMBmark 원문](https://www.cs.columbia.edu/~allen/F15/NOTES/borenstein.pdf): unequal diameter, effective wheelbase, average scale의 분리와 양방향 검사 구조. 다른 로봇의 수치는 사용하지 않았다.
- [Kelly 2004 원문](https://www.ri.cmu.edu/pub_files/pub4/kelly_alonzo_2004_1/kelly_alonzo_2004_1.pdf): 초기조건 및 systematic/random input의 선형 전파 분리. 본 endpoint 기준은 코드와 별도로 연속 원호식을 계산했다.
- [Kalibr IMU Noise Model](https://github.com/ethz-asl/kalibr/wiki/IMU-Noise-Model): rate white noise sigma/sqrt(dt), bias RW sigma_b sqrt(dt). 실제 필터링/대역폭 전제는 실물에서 미확인.
- [ROBOTIS Waffle Pi nominal YAML](https://raw.githubusercontent.com/ROBOTIS-GIT/turtlebot3/main/turtlebot3_node/param/waffle_pi.yaml), [odometry source](https://raw.githubusercontent.com/ROBOTIS-GIT/turtlebot3/main/turtlebot3_node/src/odometry.cpp): radius .033m, separation .287m; use_imu=true면 IMU orientation yaw 차분, false면 좌우 encoder 차분. upstream source 확인이며 현장 설치 revision/실제 /odom 설정을 확인한 것은 아니다. upstream midpoint odometry와 이번 exact-arc 적분도 동일하다고 주장하지 않는다.
