# EKF4 Range → s 공동 추정: 단계별 구현·실행 계약

기준 commit: `32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20`.
연구 브랜치: `research/ekf4-range-s-staged-20261014`.
새 폴더와 새 Actions workflow만 추가한다. 원본 코드·RF·LUT·결과·기존 판정은 변경하지 않는다. 실행 환경은 GitHub-hosted Actions이며, 로컬 문법 검사는 실험 실행으로 세지 않는다.

## 모델
상태 [px,py,psi,bg], 입력 [ds,dtheta_gyro], bg의 단위 rad/s.
alpha=dtheta_gyro-bg*dt; 원호 이동량 ds*sinc(alpha/2), 중간 방향 psi+alpha/2.
전체 4x4 공분산과 교차항을 유지한다. 잡음은 유효 이동·회전량 오차와 스텝 끝 bias random walk이다. 연속시간 bias 적분을 구현했다고 주장하지 않는다.
RF는 원시 [r,s] 전방 모델이며, 역산 Heading을 독립 관측으로 추가하지 않는다.
상관 Gaussian RF는 e_s|r=e_s-R_rs/R_r*e_r, R_s|r=R_s-R_rs^2/R_r로 분해한다.
Range-first는 공동 최적화 초기값이다. 최종 목적함수의 prior는 원래 운동 prior이며 r,s는 각각 한 번만 사용한다. 반복 중 prior/P를 누적 갱신하지 않는다.

## 단계 및 사전 가설
P0 수식·단위 계약: F/G 중앙차분 오차 <1e-6; 상관 RF 분해, 선형 공동/순차 갱신, bias 조건부 복원 및 반복 선형 MAP의 오차 <1e-9. 비유한 값·비양정정부호 관측 공분산은 차단한다. 실패 시 이후 단계 금지.
P1 국소 비선형 MAP: noiseless 정답 불변성, 독립 scipy least_squares 최적화와 동일 목적함수/해의 국소 수치 일치, angle seam, 고정 prior 반복 및 수렴 실패의 명시적 반환. 다른 초기값의 다른 mode는 구현 오류로 단정하지 않는다. 국소 GN 공분산을 전체 다봉 분포로 주장하지 않는다.
P2 정합 합성 재귀 실험: 같은 입력·관측·초기오차를 사용한 3-state와 4-state 비교. gyro bias 0 및 +0.05 deg/s, 직진·회전·왕복, 각 100 독립 trial, 60 s. 실제 FFD/RF가 아닌 명시적 합성 전방 관측. 주가설은 비영 bias에서 Heading MSE의 paired 평균 차이(4-state minus 3-state)가 음수. seed 단위 95% paired bootstrap CI가 0을 포함하면 INCONCLUSIVE, 전부 양수면 CONTRADICTED. 세 경로를 사전 지정하고 경로별 결과를 모두 보고한다. bias 0에서의 자유도 증가 비용은 감추지 않는다. 고정 true bias coverage와 prior-predictive calibration은 구분한다.
P3 동결 RF 사전검사·어댑터: P0 원본 manifest의 SHA, H/LoS/LUT/observer/sensor 의존성 및 실제 입력 접근을 확인한다. 누락·해시·parity 실패 시 RF 실행 금지. Frozen legacy-Euler와 SE2 예측 불일치는 유지·표시한다.
P4 동일 prior 동결 RF one-step: 기존 3-state, 4-state 공동 EKF, Range-first 고정 선형화, Range-first 재선형화 비교. 동일 R·같은 관측 수용 mask로 순서 효과와 gate 효과를 분리한다. truth는 평가 전용이다.
P5 넓은 prior/다중해 reference: 위치를 적분한 Heading 주변 posterior의 수렴을 독립 해상도/적분기 비교로 검증한다. 기존 G3 TV 실패 0.387065>0.001은 유지한다. 국소 공동 MAP의 성공으로 이 gate를 우회하지 않는다.
P6 전체 재귀 및 독립 검증: P3–P5를 통과한 모델만 동결 RF 전경로/보류 데이터에서 평가한다. 하나의 scene과 여러 sensor seed를 독립 RF scene처럼 세지 않는다. 새 scene 없이 일반화 PASS 금지.

## 진행 및 중단
각 단계는 전 단계 PASS receipt와 코드/입력 identity를 확인한다. workflow 실행 성공과 과학적 채택을 구분한다. scientific_PASS=false를 기본 유지한다.
구현 결함: 실패 증빙을 보존하고 최소 수정·회귀검증을 별도 commit으로 시행한다. 임계값은 완화하지 않는다.
과학 가설이 CONTRADICTED/INCONCLUSIVE: 원인 진단을 작성하고 기존 가정·결과와 대조한다. 모델 변경이나 추가 실험은 새 가설/계약을 먼저 기록하고, 사용자 확인이 필요한 과학적 방향 전환은 멈춘다.
예상된 음성 대조군의 실패는 양성 대조군의 gate 실패와 구분한다. 실패를 숨기거나 우수한 조건만 골라 다음 단계로 가지 않는다.

## 산출물 및 provenance
각 cloud run은 stage status, Git SHA, run ID/attempt, Python 및 패키지 버전, 코드 SHA256, frozen contract, 입력/출력 SHA256, 명령, 종료코드, 원시 trial/trace, metrics, hypothesis verdict를 보존한다. 실패해도 artifact 업로드는 수행하되 stage의 nonzero exit를 보존한다. 출력 폴더가 존재하면 덮어쓰지 않는다.
최종 보고는 구현/실행/수학 PASS/과학적 주장/NOT_RUN/BLOCKED를 분리한다. 이 문서는 구현 전 사전등록이며 아직 실행 결과가 아니다.
