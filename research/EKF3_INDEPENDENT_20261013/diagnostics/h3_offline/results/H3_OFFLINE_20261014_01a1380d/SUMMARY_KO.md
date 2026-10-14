# H3 offline paired experiment 실행 기록

2026-10-14. 기준 커밋 `fc8b6c1ca56540570fdbe5e4d228a0e23fdcc00b`.

## 판정

**전체 1–4단계 실험은 FAIL_CLOSED / INCOMPLETE.** 전체 성능 비교 결과는 없다. 실행 전 동결한 0.5 m 공간 buffer를 적용한 경로 홀드아웃 학습에서 R2의 학습 표본이 없어 중단했다. 후속 점검에서 R5도 동일하게 학습 표본이 없음을 확인했다. buffer, parity 허용치, RF 분산이나 NIS gate를 사후 조정하지 않았다.

`scientific_PASS=false`, `recursive_fusion=NOT_RUN`.

## 실제 완료한 검사

| 항목 | 결과 | 증빙 |
|---|---|---|
| P0 동결 입력·RF cache·핵심 Git blob 확인 | PASS | GATES_02/VERIFIED_INPUTS.json |
| 선형 Gaussian 공동/조건부 순차 보정 | PASS; 교차공분산 음수·0·양수 | GATES_02/SYNTHETIC_GATES.csv |
| 원형 seam·다봉 posterior·분리된 HPD 영역 | PASS | GATES_02/SYNTHETIC_GATES.csv |
| LUT 연쇄 Jacobian 및 수치미분 | 7조건 × 12시점 PASS; 최대 오차 1.54e-9 | GATES_02/NUMERICAL_GATE_SAMPLES.csv |
| 원본 6-state inverse update 규칙의 offline 재현 | 84시점 PASS; Heading 차이 0 | GATES_02/NUMERICAL_GATE_SAMPLES.csv |
| D0 DR prior 기준 결과 재현 | 84 prior 셀 / 252 RF 기준 셀 PASS; 최대 절대 차이 2.2737367544323206e-13 | AUDIT_02/D0_PARITY.csv |
| R0 실제 LoS smoke | R2_aA_m0, noise_pair L1, seed 0; 3시점 × G0/G1/G2-H/G2-X/G3 = 15행 PASS | GATES_02/SMOKE.csv |
| 전체 paired experiment | 학습 게이트에서 exit 1; 완료 비교쌍 0 | FULL_01/VALIDATION_RECEIPT.json |

Smoke는 선택된 한 조건의 세 시점이다. 전체 경로, Full RF, 큰 Gyro bias 또는 학습 공분산의 검증을 대신하지 않는다. 기존 역해는 원본의 0.5도 격자, nearest-prior 선택, 낮은 기울기 거부, NIS gate 및 Kalman 보정까지 재현한다. oracle root는 정답에 가까운 해를 고른 진단용 수치이며 온라인 입력으로 사용하지 않는다.

## 학습 게이트 중단 원인

`SPATIAL_HOLDOUT_FEASIBILITY.csv`는 다른 sensor seed를 추가하지 않고 RF cache 위치만 검사했다.

| 평가 경로 | 다른 경로의 학습 후보 시점 | 0.5 m buffer 통과 시점 |
|---|---:|---:|
| R2 | 3,714 | 0 |
| R4 | 5,017 | 1,241 |
| R5 | 3,671 | 0 |

R2를 제외한 후보 경로의 최근접 평가 위치 거리는 최대 0.471 m이고, R5를 제외한 후보 경로에서는 최대 0.219 m이다. 따라서 경로 명칭이 다르다는 이유만으로 공간적으로 독립인 학습·평가 데이터라고 볼 수 없다. R4에만 표본이 남더라도 이를 전체 세 경로 홀드아웃의 성공으로 보고하지 않았다. μ_s, μ_r, R_s, R_r, R_sr의 전체 홀드아웃 학습 및 성능 해석은 수행하지 않았다.

## 코드·실행 감사 범위

신규 파일은 이 독립 산출물 폴더에만 작성했다. 원본 EKF3, RF s, B_OLD/E1 Range, LUT, 센서 생성기, 기존 실험 결과 및 Git 상태는 변경하지 않았다. 종료 시 원본 checkout은 위 커밋의 clean 상태로 확인했다.

최초 smoke 이후 각도 격자 비교의 bin 중심 정렬을 수정했다. 서로 다른 중심의 두 bin을 그대로 합치던 대신 공통 중심을 기준으로 인접 fine bin의 절반을 배분했다. 허용치와 격자 크기는 그대로 유지하고 GATES_02에서 재검증했다. 최초 DR 검산에서 발견한 NumPy batch solve 입력 차원 오류도 수정해 AUDIT_02에서 재검증했다. GATES_01, AUDIT_01 및 FULL_01의 기존 기록은 보존했다.

이번 기록은 실행 증빙과 자체 검산이다. 독립 코드 감사의 ACCEPT, 신규 알고리즘의 성능 우위 또는 과학적 확증을 의미하지 않는다. 전체 runner의 완료 경로는 실행되지 않았으므로 전체 실행 준비 PASS도 선언하지 않는다.

## 다음 검토에 필요한 결정

현재 계약을 유지하려면 평가 경로에서 0.5 m 이상 떨어진 추가 학습 구간 또는 독립 RF 장면이 필요하다. 학습이 없는 1–3단계와 R0 기반 4단계만 먼저 평가하는 부분 실험은 별도 범위로 분리할 수 있지만, 이번 전체 실행 실패를 그 부분 실험의 성공으로 바꾸지 않았다. 실행 결과에 맞춰 buffer나 학습 조건을 사후 변경하지 않고 결과 검토에서 멈춘다. 재귀 융합은 실행하지 않았다.
