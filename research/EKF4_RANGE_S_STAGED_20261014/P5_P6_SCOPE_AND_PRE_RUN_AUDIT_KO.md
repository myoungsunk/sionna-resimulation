# P5/P6의 범위 경계 — 2026-10-14

## P5의 엄격한 판정
기존 H3/G3 위치 주변화 적분의 posterior TV=0.387065(41→65), RQMC ESS≈1에서 reference는 **NOT_VALIDATED**. 아무 근거 없이 완화하거나 종결 PASS를 부여하지 않는다. 별도의 정확 G2-G3 likelihood 분해는 수학적으로 성립하더라도 수치적 기준 posterior 확보와 다르다.

## P6-R0 재귀 분기 — 별도 기술 가능성 검증
P6에서 목표가 전체 G3 다봉 posterior의 확정이라면 P5 reference 실패가 실제 blocker다. 하지만 **4-state Gaussian EKF/MAP 재귀 측위** 자체는 G3 reference가 없이도 구현·검증할 수 있는 다른 방법이다. 따라서 'P6_R0_LOCAL_GAUSSIAN_RECURSIVE'라는 분리된 실험으로 1개 동결 RF case(예 R2_aA_m0), LoS/Full, noise_pair 및 큰 gyro-bias 조건을 먼저 실행한다. P5의 적분 기준을 사용해 성공이라고 주장하지 않는다.

원 RF H/LUT/observer, Sensor-v2, R0 `Rs=.0081`, `Rr=.0068578637`, `Rsr=0`, 원 range offset과 NIS gate를 보존. 상태 `[x,y,psi,bg]`, gyro bias prior mean 0 SD0.1deg/s, q_b=0는 **사전 가설**이며 실제 캘리브레이션이 아님. 참값은 오차 점수에만 사용. DR3, EKF3, EKF4, MAP4의 같은 입력·RF 감지 시점 평가, bias heading 보정 효과/정상 비용/NEES와 P95, rejection, numerical failures를 분리한다. R3 numerical failure는 해당 method의 경로를 invalid로 표시하고 조용히 예측으로 대신하지 않는다.

**실행 전 소스 코드·입력·기존 P3/P4 provenance 및 사용한 실험 코드 자체를 감사한다.** P4 real RF one-step가 수치/physical hard defect이면 P6 입력을 그 상태로 재활용하지 않는다.

결과가 예상을 위배하면 해당 가정·센서/solver/likelihood 원인을 진단하고 동일 결과를 보존한 다음 관련 수정 여부를 결정. 절대 'P6 전체 scientific PASS'로 자동 승격하지 않는다.
