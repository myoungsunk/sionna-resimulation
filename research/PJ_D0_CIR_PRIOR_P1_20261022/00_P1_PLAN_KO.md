# P1: d0 + CIR LoS 복원기의 Heading prior 오차 확대 검증 — 실행 전 고정

2026-10-22. 목적은 **동일한 CIR_PLUS_D0 복원기가 heading prior의 0°, ±1°, ±2°, ±5°, ±10°, ±20° 오차를 실제로 줄이는가**를 검증하는 것이다. 기존의 G≥0.8 같은 임의 기울기 합격 기준은 사용하지 않는다.

## 무엇을 고정하고 무엇을 바꾸는가
- **고정:** Full/LoS 짝의 원본 RF, GT 위치, SourceFFD 안테나/LUT, 모델 HGB의 구조·특징, 학습된 함수, 각 pose의 관측, 단일 heading 갱신식, 기본 σψ=3°와 σs=0.1.
- **변경:** 추정 heading prior만 GT+δ로 변경한다. δ=0, ±1, ±2, ±5, ±10, ±20°.
- LoS LUT는 기존의 GT±1° 표를 ±10°/±20°로 선형 외삽하는 것이 아니라 **원본 SourceFFD를 각 prior yaw에 실제로 평가**해 얻는다.
- 3개의 held route(R2/R4/R5). 평가 route는 HGB 학습에 사용하지 않는다. 이미 개발 과정에서 사용된 세 route이므로 새 환경 일반화를 주장하지 않는다.
- **CIR_PLUS_D0 HGB는 기존 실험과 동일한 특징·하이퍼파라미터·±1° 학습 prior로 route마다 결정적으로 재학습**한다. 새로운 δ에서 재학습하거나 하이퍼파라미터를 조정하지 않는다. ±1° 기존 결과를 자동 검산한다. 원본 HGB의 직렬화된 모델이 없으므로 ‘재학습 없이 고정’이 아니라 ‘원래 훈련 프로토콜 그대로 다시 적합한 후 새 δ에서는 고정’이다.
- **GT는 합성 prior 구성 및 채점에만 사용한다.** 보정기에 GT pose/LoS 값을 입력하지 않는다. 현재의 s, 과거 s 측정은 원본 Full에서 얻는다.

## 모델과 비교군
- \`PRIOR_ONLY\`: heading을 갱신하지 않음
- \`RAW\`: 보정 없는 s_Full
- \`CIR_ONLY\`: Full 파형 요약 특징으로만 e_s 예측
- \`CIR_PLUS_D0\`: 동일 특징 + d0(=s_Full-h_s(prior))로 e_s 예측
- \`D0_DIRECT\`: e_hat=d0이므로 innovation=0, 음성대조군
- \`ORACLE_LOS\`: 실제 LoS 편파비 사용(진단용, 온라인 사용 금지)

## 갱신과 평가
- z_clean=s_Full-e_hat, ν=z_clean-h_s(prior), e_ψ^+=δ+Kν.
- **주 분석:** 실제 온라인 prior에서 계산한 SourceFFD analytic Jacobian g_prior=∂h_s(prior)/∂ψ [s/deg]으로 K=9g_prior/(9g_prior²+0.1²). 사전에 정한 고정 σψ=3°, σs=0.1. 결합 gate·위치 갱신 없는 단일 step.
- **과거 결과 재현:** 기존 연구와 정확히 같은 g_GT=(s_MGTp1−s_MGTm1)/2로 만든 K. 이것은 GT를 이용한 분석 reference일 뿐 실제 운영 가능 gain이 아님.
- **민감도:** 매우 큰 δ에서 Pψψ를 3° 고정한 경우와 \`σψ=max(3°,|δ|)\`로 확대한 경우 비교(실제 prior error를 안다는 진단용 설정, 운영 가정 아님).
- Primary: (route, signed δ, arm, gain mode)별 단일 step heading RMSE, PRIOR_ONLY 대비 RMSE 비율, CIR_ONLY 대비 성능; 절대오차 q95/q99, 95/99 백분위, 개선된 pose 비율(δ=0 제외).
- Secondary: \`RMSE(s_hat-s_LoS)\`와 innovation RMS vs oracle, 신호 보존 기울기 G는 진단 전용; G의 임계값으로 성공 판정하지 않는다.
- 대조: δ=±1°에서 기존 \`los_bias_validation.py\`의 결과를 같은 GT-reference gain으로 재현해야 한다. \`SourceFFD\`에서 직접 평가한 s(±1°)와 저장된 \`sMGTp1/m1\` 차이 QA.
- 오차 부호가 다른 것을 한데 평균해 소실시키지 않는다. 3개 route 결과, 7개 case 결과 모두 저장한다.

## 사전 질문
1. **Q1:** 같은 route에서 δ=±2°,±5°,±10°,±20° 조건의 CIR_PLUS_D0 단일갱신 RMSE가 PRIOR_ONLY(|δ|)보다 감소하는가?
2. **Q2:** 개선이 있다면 CIR_ONLY보다 큰가, 그리고 LoS oracle에 얼마나 가까운가?
3. **Q3:** 성능이 무너지면 ±1° 훈련 범위 밖의 d0 외삽, LUT 모델 비선형성·다중해, 잔여 e_s 때문인지 구분할 수 있는가?
4. **Q4:** 실제 prior 국소 Jacobian으로 갱신한 결과도, GT-reference gain을 사용한 옛 결과와 일치하는가?

**제외:** 실제 IMU·odom 주행 prior, 위치 추정 오차, gyro bias 누적, NIS gate, EKF 전체 재귀, heading NEES/포함률, 실측 환경. 이것들은 P2에서 별도 실험한다.
