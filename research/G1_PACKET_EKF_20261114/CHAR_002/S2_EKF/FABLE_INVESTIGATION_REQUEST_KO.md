# Fable 요청: E0 integrity의 원인과 Goal 1 경계 안에서 E0 수준 integrity를 재현하는 조사 설계 (2026-11-15)

## 상황

- **목표.** Goal 1은 편파(dual-LP s)를 heading/편파 자체의 다중경로 완화 없이 써서, packet EKF의 integrity(Pose95, heading 95% coverage)를 먼저 확보하는 것이다.
  - 허용: ranging 수준 완화, 불확실성 표현(상관 상태, Schmidt/consider, 분산, 꼬리)
  - 제외: s 평균 보정, 반사 경로 편파 모형, 오염 감지 기반 s 가중
- **실행 결과.** G1-CHAR-002 S2(`c7f0cf7`)에서 TEACH/REPEAT로 학습한 관측 오차 모형(E1–E5)을 R2/R4/R5 × 앵커 A/B × B0/L2에서 실행했다.
  - 모든 arm이 기존 native MB_VAR(E0, pooled Pose95 88.8%)보다 integrity가 낮았다.
  - 평가 궤적 참값으로 다시 맞춘 E5가 가장 나빴다(Pose95 0.8–21%).
- **감사 결과.** 상세는 [AUDIT_KO.md](AUDIT_KO.md)에 있다.
  1. 구현은 사양대로였다. E3/E4 실패의 직접 원인은 사양 결함이다. Student-t 재가중이 R을 줄였고, E4는 이동 2 cm에서 상관을 끊었다.
  2. 모든 학습 arm이 관측을 독립으로 가정했다. 그런데 정규화 혁신의 lag-1 자기상관은 s 0.75–0.93이다. 기존 진단의 n_eff/N은 1/6–1/37이다.
  3. E0가 이 정보 중복을 견디는 것은 다음 때문이다.
     - in-sample hand σ_b table: 10 m에서 0.24로, 잔차 적합값 0.109의 약 2배
     - 같은 복도 LORO로 학습한 μ_B, μ_M
     - 편파 평균 보정 μ_M 포함: Goal 2 항목
  4. E1의 Pose95 저하는 heading이 아니라 거리 모형 차이에서 온다. heading coverage는 E1 85.3%, E0 87.1%로 비슷하다.

## 요청

이 진단을 검토하고, 다음 조사를 **분석 전에 사전 등록할 사양**으로 정리해 주기 바란다. 실행은 사용자가 한다. 데이터는 다음으로 제한한다.

- R2/R4/R5 B0/L2 seed10 앵커 B
- 앵커 A packet
- G-T1 TEACH/REPEAT, G-T1 경로
- G-T2/G-V는 봉인 상태이며 쓰지 않는다

### I1. E0 성분 분해 (원인 규명)

E0에서 아래 성분을 하나씩, 그리고 함께 바꾼 arm으로 Pose95, heading 95% coverage, heading/XY RMSE를 본다. 목적은 E0의 integrity가 어느 성분에서 나오는지를 가르는 것이다.

- μ_M(편파 평균) = 0으로 둔다. 이렇게 하면 Goal 1 경계 안의 E0가 된다.
- μ_B(거리 채널 보정)를 학습 모형 R2의 μ_r로 바꾼다.
- hand σ_b → 잔차 적합 σ_b(LORO)
- hand σ_b → TEACH 학습 σ_s(d)

### I2. 정보 중복 정량화와 예측 가능성

- 궤적별로 시간 상관 길이, n_eff, z_ψ=1에 필요한 R 팽창 배수(또는 decimation m)를 잰다.
- 이 값을 **TEACH 데이터만으로 사전에 예측**할 수 있는지 본다. 예측 근거는 sweep의 yaw 상관, TEACH 직진 구간의 거리 상관, 운동 속도·회전률이다.
- CHAR-001의 위치 재방문 상관은 0.5 cm 0.98, 2 cm 0.8, 5 cm 0.3–0.6, 10 cm 0.47–0.88로, 단조 감소하지 않는다. 이를 어떻게 모형화할지 의견을 바란다.

### I3. 상관 표현 비교 (Goal 1 경계 안)

학습 모형(E2 기반, s 평균 0)에 다음 표현을 각각 얹어 비교하는 설계를 요청한다.

- (a) 이동·회전 모두에 상관을 두는 colored s/r 상태. 상관 길이는 I2의 TEACH 추정값을 쓴다.
- (b) Schmidt/consider 상태
- (c) n_eff 기반 R 팽창(시간 또는 이동 거리 창)
- (d) decimation
- (e) covariance intersection 계열

E0를 이기는지보다, **E0 수준 integrity를 in-sample 조정 없이 만드는지**를 판정 기준으로 해 주기 바란다.

### I4. Student-t 처리 수정

팽창만 하는 가중(w≤1), 또는 분산 등가 scale²·ν/(ν−2)를 쓴 변형을 E2와 비교한다. 기존 E3 결과는 "R을 줄이는 재가중" 결함으로 기록한다.

### I5. R4와 앵커 A 취약성

E0도 R4에서 60–64%, 앵커 A에서 56.5%다. 원인을 다음 후보로 가르는 진단을 요청한다.

- 기하(지그재그, 비스듬한 heading, 원거리)
- 거리 오차
- heading 관측성(|∂s/∂ψ|)
- gate

### 판정 구조와 비교 공정성

- 판정은 S2와 같다. pooled Pose95 ≥ 0.90, 궤적별 Pose95 < 0.75면 심각 실패, pooled heading 95% ≥ 0.90이다.
- 위 수치를 유지할지, 옵션 B의 기존 수치로 바꿀지도 의견을 바란다.
- 비교 공정성 규칙을 정해 주기 바란다. 예를 들어 E0의 in-sample 성분을 그대로 둔 비교는 참고로만 쓰는 식이다.

## 참고 자료

- [S2 결과 보고](run_20261115_a/REPORT_KO.md), [S2 사양](../SPEC_S2_EKF_KO.md), [S1 calibration](../REPORT_KO.md)
- [CHAR-001 특성화](../../CHAR_001/REPORT_KO.md): 기전, 상관 척도, mount
- `mbvar_premodel_diag_20261029/README_KO.md`(브랜치 `analysis/fp-native-b-causal-20261108`): ε²/R, 시간 상관, 정보 축소 시험, σ_b 재적합
- `FP_B_CALIBRATION_RESULTS_20261108/REPORT_KO.md`: native frozen 88.8%와 B 검출기 보정
