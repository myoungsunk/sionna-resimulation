# P1R: Heading prior가 크게 틀려도 복구할 수 있는가 — P1 수정판 (실행 전 고정)

2026-10-22. P1(run 39744971158, commit 59b8d2e)의 결과는 보존하고, 원래 질문에 답하지 못하게 만든 설계 문제를 고쳐 다시 실행한다.

## P1에서 고치는 것

| # | P1 | 문제 | P1R |
|---|---|---|---|
| 1 | 모든 δ에서 σψ=3° 고정 | 실제 오차가 10°·20°인데 필터는 3°라고 가정. Oracle조차 10°의 23%만 줄여 "복원기 능력"과 "gain 부족"이 섞임 | **주 분석 σψ=max(\|δ\|,1°)** (prior 공분산이 실제 오차 크기와 일치하는 필터). σψ=3°는 부 분석 |
| 2 | prior 위치에서 1회 선형화(EKF) | ±10°·±20°에서 LUT 비선형성 때문에 갱신이 덜 됨/넘침 | **주 분석 IEKF**(같은 패킷으로 Gauss-Newton 반복 + MAP 비용 halving line search, 최대 30회). EKF는 부 분석 |
| 3 | 모든 arm σs=0.1 | RAW·CIR_ONLY·CIR_PLUS_D0의 실제 잔차가 서로 다른데 같은 R | **주 분석 R=학습 route 내부 leave-one-route-out 잔차 MSE**(arm별). Oracle은 CIR_ONLY의 R을 써서 "같은 필터, 완전한 LoS"로 둔다. R=0.1²은 부 분석 |
| 4 | ±1° 학습 모델만 평가 | 실패가 원리적 한계인지 학습 범위 한계인지 구분 불가 | **단계 1** `CIR_PLUS_D0`(기존 ±1° protocol 그대로, 외삽) / **단계 2** `CIR_PLUS_D0_WIDE`(학습 route에서만 δ~U(−20°,20°) 3회 복제로 재학습). 평가 route는 두 단계 모두 학습에 쓰지 않음 |
| 5 | 신뢰도 지표 없음 | heading RMSE가 좋아도 필터가 과신할 수 있음 | NEES(e⁺²/P⁺), 95% 포함률 추가 |

## 그대로 두는 것
- Full/LoS 원본 RF, GT 위치(P1은 heading만 흔드는 진단; 위치·gyro 누적은 P2), SourceFFD 안테나 모델, HGB 구조·특징·하이퍼파라미터, held route R2/R4/R5.
- GT는 prior 구성과 채점에만 사용. 복원기 입력에 GT pose·LoS를 넣지 않는다.
- ê_s는 Full−LoS 전체 편파 오차를 추정하므로 μ_s를 따로 빼지 않는다.

## LUT 계산
- 각 패킷의 GT 위치에서 heading offset −30°…+30°(1° 간격)마다 SourceFFD를 직접 평가해 s와 analytic ∂s/∂ψ를 저장한다. 평가 δ={0,±1,±2,±5,±10,±20}은 모두 격자점이므로 정확값이다.
- IEKF 반복점과 WIDE 학습 prior처럼 격자 사이 값은 s와 ∂s/∂ψ를 쓰는 cubic Hermite 보간으로 얻는다.
- QA: 격자 0,±1° = 저장된 `sMGT/sMGTp1/sMGTm1` (≤2e-5). 보간 오차는 held route에서 ±2.5°, ±7.5°, ±12.5° 정확값과 비교해 보고한다.

## 비교군
`PRIOR_ONLY`, `RAW`, `CIR_ONLY`, `CIR_PLUS_D0`(단계 1), `CIR_PLUS_D0_WIDE`(단계 2), `D0_DIRECT`(음성대조, 항상 |δ|), `ORACLE_LOS`(참고 기준).

## 판정 (주 분석: σψ 일치 + R 보정 + IEKF)
- **주 지표:** route별 RMSE(ψ̂⁺−ψ_GT) < RMSE(ψ̂⁻−ψ_GT)=|δ|. 특히 ±5°, ±10°.
- 함께 보고: q95/q99 절대오차, 개선된 패킷 비율, NEES 평균, 95% 포함률, Oracle 대비 위치, CIR_ONLY 대비 차이.
- 임계값 하나로 성공/실패를 선언하지 않는다. route 3개 × δ 부호별로 크기를 그대로 보고한다.
- 해석 규칙(사전): 단계 1이 ±5/±10°에서 prior를 거의 못 줄이고 단계 2가 줄이면 → 학습 범위 한계. 둘 다 못 줄이고 Oracle은 줄이면 → d0 순환(원리적 한계). Oracle도 못 줄이면 → 단일 패킷 관측성 한계(RF 측정 자체가 아닌 재귀/다수 패킷 문제).

## 재현 QA
- σψ=3°, R=0.1², EKF, local Jacobian에서 ±1° CIR_PLUS_D0 RMSE가 P1 `LOCAL_3DEG` QA와 1e-6 이내로 같아야 한다. GT-reference gain 경로도 P1 `GTREF_3DEG`와 같아야 한다.
- `D0_DIRECT`는 모든 모드에서 RMSE=|δ|.

## 제외
실제 IMU·odom 재귀, 위치 오차, gyro bias, gate, XY·range 지표 → P2.
