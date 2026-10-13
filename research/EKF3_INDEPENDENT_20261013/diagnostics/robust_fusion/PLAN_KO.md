# M0–M2 Robust Fusion 실행 계약

기준 커밋 991d511. 원본 FP s, B_OLD/E1, RF·Wheel·IMU 및 pose 초기조건을 보존한다. experiment_contract.json과 실행 manifest snapshot이 수치 계약이다.

실행 순서: M0 parity → RF 잔차 구조 gate → 공통 평균·척도·Huber → M1 → GTSAM preflight → M2-T0 → 구조/식별성 gate 통과 시 M2-T1. 학습·평가 경로 분리, 0.25 m 공간 buffer, E1 동일 outer-fold 계수 적용. 처음 실행 grid는 7조건, seed0/1/2, level1, noise_pair/gyro_bias, LoS B_OLD 및 Full B_OLD/E1, D0/A/B/C: 모델당504셀.

M0 기존 R0/NIS gate 유지. M1은 bias4 + 상수 학습 평균 + 총 잔차 척도 + 표준화 Huber delta1.345. C는 두 관측의 단일 블록 가중치. RF covariance는 학습 표본 ddof1 diagonal, 미검증 교차항0. Huber 임계값은 관례값을 실행 전 고정했으며 평가값으로 선택하지 않았다. Bias prior .1 deg/s, random walk0은 기존 진단 계약을 재사용하며 센서 참 bias를 온라인 입력하지 않는다.

M2-T0는 같은 관측 likelihood와 motion noise를 써야 한다. M2-T1은 총 분산=지속+순간 성분 정합과 Qc=Sigma_c-Phi Sigma_c Phi^T PSD, 식별성을 확인한 경우만 허용한다. 주 결과는 x[k|k]이며 지연 smoothing을 섞지 않는다. 운동잡음은 정확한 rank2를 유지하고 jitter로 덮지 않는다. 사전검사 covariance API, 주변화, Schur 정합, motion Jacobian/moment 일치가 필수다.

M1 공분산은 고정 prior·고정 EKF 선형화의 block-Huber MAP에서 얻는 local IRLS Gaussian/Joseph 근사다. 독립 합성 반복 표본으로 포함률을 점검하며 이상치 조건의 calibration을 자동 승인하지 않는다. M0/M1 대비는 bias와 강건 RF모델을 함께 바꾸므로 각각의 인과효과로 분리 주장하지 않는다.

E1 모델군은 동일 scene에서 선택된 이력이 있다. 공간 제외 후의 개별 잔차 분석과 전체 재귀 E1 평가는 구별한다. 전체 재귀 궤적에서 제외 위치의 측정이 이전 상태에 미친 영향을 scoring mask로 제거할 수 없으므로, 전체 E1 비교는 탐색 전용이다. 독립scene/새 seed 확증 전 scientific_PASS=false.

현재 코드: m0_adapter.py, rf_residual_structure.py, rf_error_model.py, m1_bias_robust_ekf.py, covariance_checks.py, observability_checks.py, gtsam_preflight.py, run_comparison.py, evaluate_results.py. run_comparison은 검증된 M1 실행만 제공하며 미검증 M2를 대신 실행하지 않는다.
