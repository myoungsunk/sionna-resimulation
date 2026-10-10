# SENSOR-V2 실행 전 계약 (2026-10-08)
기준 SHA: 2337c33fe25917029c2aa95973e6ae7672386a5e.
별도 clone: artifacts/DRIVE_SIM_SENSOR_V2_20261008_01a11a01/checkout; branch codex/sensor-model-v2-20261008.
원격 기존 branch 768404e3716c47f323d2c26e9458731b077bc96e (추가 19파일: RF 잔차, steering probe 진단). 이전 미커밋 9 tracked 및 2 untracked 경로 보존, 가져오지 않음.
clone 초기 LFS smudge 실패 exit128: 로컬 origin에서 246MB bank 누락. GIT_LFS_SKIP_SMUDGE로 pointer만 checkout. RF artifact 접근은 별도 확인하며 pointer를 실데이터로 쓰지 않음.

## 구현 범위
legacy 파일 동작/seed 보존. additive sensor_v2/filter_v2/evaluation_v2 모듈, dedicated runner, tests, 문서. 기존 RF solver/LUT/antenna tuning 없음.
true radius=r_nominal / ((1+common_scale)*(1 +/- eps_d/2)); b_true=b_nominal/(1+e_b). 기존 eps_d는 effective encoder-distance 비대칭이며 물리적 radius 오차와 부호가 반대. low/mid/high magnitude 유지, hardware 등급 아님.
새 적분은 SE(2) 원호 exponential; legacy previous-heading Euler 유지.
공분산 상관 처리: e=true-est; e_minus=F e_previous-G n. odom residual v=n_yaw-h_d n_distance-h_g n_gyro; C=-G Q B^T. S=HPH^T+R+HC+C^TH^T; K=(PH^T+C)/S. bias RW는 left-endpoint rate를 사용하고 odom update 후 endpoint prior에 추가.
무오차/단독/주요 조합/전체, exact pose 및 legacy pose prior 분리. truth/drift 필드는 evaluation 전용이며 inference에 전달 안함.
EKF v2만 지원. IEKF/UKF/GSF 및 inverse s는 명시적 오류. 추가 calibration state 없음.

## 출력
results/SENSOR_V2_20261008/: NPZ raw (전체 상태6, covariance6x6, timestamp/truth, sensor raw, innovations/R/S/status, slip/initial/prior/masks), JSON config/provenance/hash, metrics, audit.
출력 파일 존재시 덮어쓰기 거부. seed namespace 2201008와 stream identifiers 분리.

## 사전 고정 검증
- 결정론적 float64: zero-motion/increment integration atol 1e-10; analytic Jacobian central FD step1e-6 max abs2e-7; covariance symmetry atol1e-12, eigmin>=-1e-10.
- 직선10m, v=.2m/s: bias .05deg/s, eps=.005, initial heading5deg; endpoint 연속식과 SE2 exact 비교1e-9. legacy Euler discrepancy 별도 보고.
- gyro N^2 T, wheel A Q A^T, RW sigma_b^2 T: 4096 independent runs, seed100..4195, T10s, dt .1/.2/.4. 상대분산 허용15% (약6 표준오차 sqrt(2/(4095)), 다중 비교 보수). 시간 표본은 반복수로 세지 않음.
- slip p=.01 at dt .2 -> lambda=-ln(.99)/.2; eligible rotating time10s, rates dt .1/.2/.4, independent runs4096. 발생 횟수 합이 Binomial trials,p의 6sigma 이내. t3 scale와 SD=sqrt(3)*scale 구분.
- 소규모 localization MC: seed200..247, 48 runs/cell, dt .2, fixed mixed-motion path(정지/속도변화/직선/양방향회전/후진), low/mid/high 보존 중 mid 대표 실행, exact/legacy pose initialization, e_b0와 unknown e_b=.0075, noRF와 synthetic idealRF 분리. drift별 튜닝/calibration 없음.
- 비교 ideal increments / wheel-only / distance+gyro fixed / wheel+gyro EKF / +range / +range+s. synthetic heading은 ideal-sensor 별도 진단만.
- RMSE, endpoint pose NEES 및 coverage 각각 보고. NEES/coverage 신규 production 합격기준 없음. 종전 제안 NEES<=6 등 사용 안함. matched Gaussian 별도 선형 검산만 chi-square 기준 사용.
- calibration 실행 없음. evaluation seed만 사용. 기존 RF H/LUT 접근 가능하면 별도 작은 평가, 아니면 synthetic만이며 RF 검증 미완료.
- legacy 동일 input/seed exact array regression: frozen source dynamic load와 비교; 기존 기록되지 않은 raw 복원 주장 금지.
- F01/F02 기존 scientific_PASS=false 유지. 수치 개선을 목표로 반복 튜닝하지 않음.

## 검증 보충 (수치 실행 전)
공유 잡음 선형 Gaussian 검산은 4096 독립 prior/input draw, seed 88001. sample covariance 상대 Frobenius 오차15%, mean NEES의 4096*6 자유도 chi-square 0.000001..0.999999 구간, coverage의 binomial 6sigma. gate 없는 선형식 검산이며 비선형 localization 수용기준으로 확대하지 않음.
관측성은 gyro calibration 열 [bias,SF,eps]의 Jacobian rank/SVD 진단. 일정속도 직선, 정지, 속도 변화, 양방향 회전의 구조적 rank를 비교하며 실물 관측가능성 PASS 아님.

## 기존 RF artifact 제한 평가 (RF 수치 실행 전)
접근 확인한 R1 y0/mount0 기존 H_y0_m0.npy 및 hs_lut_2deg.npy를 읽는다. timeline_y0_Tnone의 첫201 sample(40초), seeds200..207(8 runs/cell), exact/legacy-prior 및 e_b=0/unknown .0075, EKF online / +range / +RF-derived s 비교. calibration 없음, SNR=35dB는 민감도 가정이며 production 보정값으로 주장하지 않음. metric/NEES/coverage는 보고만 하고 새 production PASS 기준 없음. 원본 전체 SHA와 선택 pose_id를 기록, 원본 파일은 읽기만. F01/F02 gate 재검증·해소 판정은 하지 않음.

## RF 연결 입력 규약 보충 (첫 RF 시도 중단 후, RF 수치 결과 없음)
기존 R1 truth는 yaw가 매 step 변해도 위치는 이전 heading Euler로 생성된다. strict SE2 입력검사에서 lateral chord residual 최대 0.000145997m가 나와 RF8은 결과 생성 전 중단(exit1). 허용오차를 완화하지 않는다. 기존 artifact 평가에는 명시적 `legacy-euler` motion convention을 추가한다(이전-heading signed projection, lateral residual1e-9 유지). filter-v2의 SE2 적분과 기존 Euler truth 사이의 이산화 mismatch를 따로 저장하고 해석한다. 무오차 SE2 시험은 그대로 유지하며 이 RF 비교를 무오차 정합시험으로 취급하지 않는다. 모든 원본 truth/H/timeline 유지.
