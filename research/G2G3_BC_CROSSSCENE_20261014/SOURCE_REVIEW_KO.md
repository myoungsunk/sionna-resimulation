# B/C 외부 독립 장면 실험 — 실행 전 소스·물리·수치 감사

## 사용자 목적·동결 근거
GitHub 오피스 RF와 다른 Anchor 장면을 이용해 B의 RF signed likelihood를 독립 장면에 대해 보정·검증하고, 같은 모수를 고정한 C1–C4를 실행한다. 기존 DR-only/RF 자료의 PASS를 다른 데이터에 자동 이전하지 않는다. 기준 감사 규칙: 9beb061f354edef18e1f977f5d462d7e0d8b1f2e. 기존 B 결과: 3c9d8f826f5cc41f43ddcf20d754f791cce19f8a.

## 외부 원본·독립성
- 외부 장면 원본 claude/office-e-layout, commit b05af070a87981f8712fdd41eac4c1bbb882e9c7.
- 오피스 35개 물리 위치 중 기하 LoS clear 25, blocked 10; 각 위치 yaw 19개, bin 257. 위치별 RF 결과는 19개 독립 장면이 아님.
- Anchor A2 위치 15개, Anchor A2B 위치 14개. 서로 같은 복도 장면의 상이한 Anchor 배치로 연관돼 있음. 오피스 vs 복도는 장면 기하가 다르나 실제 실물 측정 자료는 아님.
- 수신기/H 배열 검산: office 기존 보고서는 네 RX/TX 조합 중 가장 큰 branch를 선택. 먼저 이를 원본 H.npy와 동일한 Hann, 4배 IFFT zero padding, 30% threshold로 복구해 OFFICE_RANGING.json position별 mean과 1e-7m 이내 일치해야 함.
- 실제 B 분석에는 frozen P3 detector와 유사하게 TX0 fixed, strongest RX 방식 사용. Office legacy all4 detector와 P3 TX0 차이는 별도로 기록; 두 종류의 관측 오류분포를 같다고 주장할 수 없음.
- 해당 Office 원래 보정 상수는 사무실 LoS 자료에서 추정된 값 -0.5234322358575277 m. 외부 검증에 이를 적용하면 누수가 발생하므로 절대 사용하지 않음. 이전 B_OLD=-0.5315983906250129 m만 그대로 적용.
- E1 original P3 mount/feature schema와 office H 정의의 대응 관계는 미검증. E1의 외부 calibrated transfer는 이번 B의 PASS 대상이 아님.

## B likelihood 모형 및 평가
- 위치별 signed error e=z_RF-r_true 평균을 학습·평가 기본단위로 사용.
- Office LoS 25점으로 clean Gaussian mean/std, blocked 10점으로 df3 Student-t loc=median, scale=max(0.06,1.4826 MAD). 가중치 25/35,10/35. 검증 대상 A2/A2B에서 모수 변경 금지.
- 기하 LoS label은 학습 데이터 분할에만 사용, 온라인 추정기 입력에 사용 금지. 현재 알고리즘은 두 그룹의 unconditional mixture.
- 원래 office에서 19 yaw의 repeated channel observation을 위치 독립 표본으로 중복 집계하지 않음.
- 검증: Anchor A2/A2B에서 one-sided signed q05/q01 coverage, PIT uniformity, negative log-likelihood, RMSE, 오차 꼬리. Bootstrap confidence 과대 주장 금지. 외부 장면 수가 너무 적으면 scientific calibrated probability CLAIM_BLOCK.
- CIR에서 first/peak, peak delay gap, first energy fraction을 추출해 설명력 탐색. 이는 아직 사전 고정 prediction feature가 아닌 진단 지표만. 새 CIR 품질모형 성능을 주장하지 않음.
- Office/A2/A2B에 측정 gyro/odom 주행 경로는 없음. DR fault prior의 독립학습은 NOT_ELIGIBLE, 기존 합성 pFault=.05 및 fault sigma=2m만 C 계산 대조용으로 고정.

## C 검증 가설 및 수식
- 기존 C1 nominal DR, C2 large DR drift, C3 RF overcorrection, C4 long-path RF 원본 숫자 유지.
- 모델 입력: d=DR predicted range, z=RF corrected range, sigmaDR, office-fitted signed error fR. 정답 rtrue는 post-hoc 오차 평가로만 사용.
- delta=d-z=eD-eR; DR mixture fD(e)=0.95 Normal(0,sigmaDR²)+0.05 Normal(0,sigmaDR²+2²).
- p(eR|delta) proportional to fR(eR)*fD(eR+delta). delta>0 RF-closer event eR > -delta/2, delta<0 eR < -delta/2.
- 각각 SciPy quad와 독립 Simpson 확률 적분으로 수치 검사, 허용 오차 1.5e-5; 관측 RF Range 이중 곱 금지.
- 선택 정책(합성 readout only): delta>0 and NIS>6.634896601 and RF-win probability>=.95이면 action=z-mu_clean; 나머지 action=d. 이는 새로운 Bayesian full-state posterior가 아니며 확률 calibration 주장 금지.
- 성공: C2에서 DR 대비 0.5m 이상 개선; C1,C3,C4에서 DR 원래 절대오차보다 악화되지 않음. 위배가 발견되면 해당 C adoption CLAIM_BLOCK, 계획 외 모수 변경 금지.
- 추가: 다른 Anchor의 RF signed measurement를 진짜 관측에서 취해 synthetic DR radial overestimation +.03m 및 +2.8m 대조 생성. 이는 실제 Gyro 기반 DR Fault와는 별개이므로 독립 DR 검증으로 주장 금지.

## 감사 및 중단 범위
HARD_EXECUTION_BLOCK: source SHA mismatch, external commit mismatch, office legacy detector parity, observer coordinate/units, invalid H/covariance, truth estimator leak, duplicate Range factor.
CASE_RESULT_INVALID: selected numerical integration disagreement or nonfinite sample, that affected sample only.
CLAIM_BLOCK: corrected RF generalization, E1 calibration, independent gyro fault prior, small 35-location scene, A2/A2B overlapping geometry, actual joint G2/G3/recursive performance.
DIAGNOSTIC_DEFECT_OR_WARNING: optional chart/metadata/save fault. Fix only affected output and retain unchanged science calculations.
Per stage source-bound gate runs BOOTSTRAP -> EXTRACT -> B -> C; APPROVAL.json triggers cloud workflow, not code push. Each result distinguishes EXECUTION/CALCULATION/HYPOTHESIS/SCIENTIFIC claim; none overwritten or retroactive PASS.
