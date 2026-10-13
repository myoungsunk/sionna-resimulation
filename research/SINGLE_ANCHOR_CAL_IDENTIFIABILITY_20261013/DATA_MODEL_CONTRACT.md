# I0 데이터·모델 계약

자료 위치에 관한 최초 감사의 공백 설명은 `out/RF_LOCATION_ADDENDUM_KO.md`로 갱신한다. 입력 분리와 단계 중지 계약은 유지한다.

온라인 상태 순서는 [x m, y m, psi rad, bg rad/s, SFg dimensionless, eps dimensionless]. 좌표와 yaw 부호는 동결 MOTION CSV와 sensor_v2 SE(2) 정의를 그대로 사용한다. 임의 TF 변환은 없다. gyro=(1+SFg)*true_dtheta+bg*dt+noise이며 추론은 (gyro-bg*dt)/(1+SFg)를 사용한다. wheel 좌우 배율은 (1+common_scale)*[1-eps/2,1+eps/2]이다.

wheelbase nominal=0.287 m; true=nominal/(1+true wheelbase error). 기본 필터 known_wheelbase_error=0. 참 wheelbase는 scoring 파일에만 있다. I0는 Oracle 입력을 금지한다. 기존 B0에는 slip/wheelbase 등 모델 불일치가 있고 gauss_level은 slip off/wheelbase error 0이다.

public.npz에는 t_s, dt_s, ds_odom(m), dtheta_gyro(rad), dtheta_odom(rad), x0만 허용한다. truth.npz에는 true increments, true parameters, true trajectory, generated noise variance 등을 둔다. config.json에는 필터가 아는 prior 표준편차와 설정을 둔다. x0 pose는 생성기에서 참 초기 pose에 동결 initial-stream 잡음을 더해 만든 외부 prior 측정이다. 추론은 저장된 x0만 읽는다. Calibration 초기 평균은 0이다. 명령속도는 이 데이터에 제공되지 않으며 truth 이동량으로 대체하지 않는다.

시간축은 CSV의 t를 유지한다. 첫 dt=0, 이후 양의 diff(t). 누락·비유한 wheel/gyro·시간 불일치는 명시적 오류이며 보간하지 않는다. 순서는 이동 예측 → 동일 입력과 상관된 odometry heading 갱신 → RF(range 다음 s)이다. I0에서는 마지막 두 갱신을 비활성화한다.

Q=diag(k_s*abs(ds_odom), Ngyro^2*dt, k_theta*abs(dtheta_odom)+k_stheta*abs(ds_odom)); C=-G Q B, R=B Q B, S=H Pminus H'+R+2 H C. frozen SensorV2Filter.step을 호출해 입력 공유 상관을 유지한다. covariance 진단 실패 시 중단하며 PSD projection이나 inflation을 추가하지 않는다.

미래 RF 스키마는 별도 acquisition timestamp, range_m, s, detected/missing, power, joint-noise-model ID를 public 영역에 둔다. I0 구현은 RF-off만 허용하므로 이 스키마의 온라인 처리·시간 정렬은 아직 NOT_RUN이다. 합성 RF로 공백을 채우지 않는다. range/s가 없는 것은 유효한 RF-off 입력이다.

## RF 계보와 공백

참조 commit: 160841d93fbd09c1949551ba08fcd0ed2a8c42ab. 근거는 research/LOS_RANGE_RECAL_20261012의 P5_AUDIT_R2_1_KO.md, R23_PREREG_KO.md, R23_RESULT_KO.md, R2_STATUS_KO.md, out_p0_p5/R1/RUN_MANIFEST.json 및 P0/P3 manifest이다.

P5는 고정된 12개 case의 noise-free 채널/관측을 seed 간 재사용한 range-only 실험이다. R2-3은 같은 채널에 seed별 CIR 열잡음을 추가한다. 독립 multipath 실현이 seed마다 늘어나는 것은 아니다. office 35 positions × 19 yaw 정적 시험은 동적 5 Hz 주행의 대체 입력이 아니다.

수신기는 동결 observation.py와 p3_common.py 계열(H→CIR/IFFT, Hann, 4N padding, strongest RX/first arrival). E1은 P3_FROZEN_MODEL.json/P3_FREEZE_ADDENDUM.json으로 추적한다. 과거 LUT는 hs_lut_2deg.npy와 meta이며 range-only P5에는 사용하지 않았다. 개별 RF 입력의 실제 bytes/SHA 전체 검증은 미완료이다.

r23_run.py는 조사한 커밋 tree에 없고 P5 per-run trace도 없다. P0는 전체 H 해시를 기록하지만 명령은 임시 경로를 참조한다. 전체 full/LoS H와 주파수 배열, 정확한 R23 실행기를 확보해야 RF 통합 재현을 완료할 수 있다. 과거 보고서의 결과를 현재 재실행 증거로 표시하지 않는다.

현재 DR cfg의 anchor=(4,0,2.65), robot_z=.45는 RF-off에서 비활성 값이다. 이를 신규 B0의 검증된 anchor 배치로 자동 채택하지 않는다. RF detector/LUT/E1 bytes 및 training-fold 계보 동결은 UNRESOLVED_CONFIG이다.
