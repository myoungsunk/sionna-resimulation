# P0 실행 동결: V00–V03

2026-10-11. 사용자 승인 범위: 기존 통합 검토의 단계 A P0 실제 복구. 기반 native commit 5a50fa9f0813a3dd0f9ca53e26da3cd3fbcfada9. 원본 7case bank / old LUT / 과거 결과는 보존하고 새 결과만 생성한다.

V00: SAMPLES의 명시적 pose_id→H row map으로 모든 Tnone/T10 시간행 대응. 원 잘못된 128-seed script(cd8f3ef9)와 동일한 sensor/RF seeds를 사용하여 faulty reference와 fixed 전체 이력 각각 128회 재실행. Mapping 수정의 효과와 covariance model 자체의 정합은 분리 판정한다. 결측/중복/재사용/반환/셔플된 bank row 회귀 포함.

V01: native 및 frozen observation.py를 동일 H/동일 noise stream으로 비교하고 독립 IFFT 계산으로 검산. 실제 freq 배열에 따른 양자화 분산 동결; 4/8/16 tap을 연구용 early-gate v1으로 선택하고 구 5/9/17은 별도 legacy ID로 보존. 장치 지원은 UNKNOWN. 관측기 일치와 legacy/native 전파 source-family 동등성은 별도 gate. 모든 source-family full H 비교가 없으면 후자는 NOT_VALIDATED로 남긴다.

V02: 6상태 Gaussian initial prior에 맞게 truth/estimate를 생성하는 matched 제어 실험. 128 independent seeds/arm, 240 ticks(48s), checkpoints 0/12/24/48s. RF-off / exact h range / exact h range+s, measured input Q vs known exact primitive Q, gyro-wheel C 제거 진단, Euler truth mismatch, gyro bias RW, original calibration assumptions의 구별. 이상적 s는 original physical LUT를 사용하는 arm과 구분한 analytic smooth sanity model이며 source sensor-v2 equations 검사 목적. Gaussian error/공분산/coverage 및 NIS를 평가한다. 통계 gate는 각 mean NEES의 chi-square MC bounds와 bias/MSE를 별도로 제시; FAIL을 성공으로 만들기 위해 Q/R 재조정하지 않는다.

V03: 원본 SHA LP±45 FFD의 Cartesian near-pole field를 물리 local horizontal direction에서 4차 다항식으로 모델링하는 새 후보. 원점 E는 원본 theta0 Cartesian mean으로 고정. theta≤4° 원본 필드로 fit, 1° 이내 사용, 1–3° smootherstep transition, 3° 이상 original LUT 유지. 실제 body yaw·Cartesian 방향으로 TX/RX를 회전하며, analytic field/ratio gradient를 finite difference와 비교. 새로운 model은 candidate/새 SHA로 구분한다. 기존9519 LoS, near9, yaw seam,8 bearings,rho grid,mount0/45 회귀. 시간 허용 범위에서 original/guard/clamp/corrected를 7case 8seed matching stream replay; 실제 native fresh near-pole PathSolver 비교가 없으면 NOT_VALIDATED 명시한다.

전체 P0는 모든 하위 scientific gates가 통과해야 PASS. 스크립트 성공/PSD/mapping PASS와 통계적 consistency/전파 source parity PASS를 혼동하지 않는다. P1 이상의 bias state/active estimator 채택은 이번 범위 아님.
