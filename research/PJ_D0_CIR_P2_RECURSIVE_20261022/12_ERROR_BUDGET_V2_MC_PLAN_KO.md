# 오차 예산 v2 + Monte Carlo seed (실행 전 고정, 2026-10-23)

## 오차 예산 v2 (원 seed, 7 case × Full B0/L2 × BASE/CIR/WIDE_NOES/PWIDE_NOES/ORACLE)
v1(11번)의 항등식 분해에 다음을 더한다.
1. 원천 간 공분산 C_sj 전체(몫만으로는 상관된 원천의 기여가 모호함).
2. 교차 전파: arm A의 입력을 BASE의 실현 가중치(K, H, F, G)로, BASE의 입력을 A의 가중치로 전파해 gap = 입력 효과 + 전파 효과로 나눈다(두 순서 모두 보고). 실제 필터가 아니라 고정 가중치 선형 반사실이다.
3. 편파 영향 커널 W(t,k) = e_ψᵀ Φ(t,k) K_k e_s: 절대 가중 합, 음의 가중 비율, 평균 나이, 반가중 나이, 10·30 s 이전 비율, 편파 신호 통과율 Σ W g.
4. **잔차 시간상관**: c1, c2, 편파 전체, range 잔차의 ρ1, 적분 상관시간, e-folding 시간, 정보 과대평가 계수 1+2Σρ(첫 영교차까지). AR(1) 검사: ρ=0.5에서 3.03(이론 3.0), ρ=0.9에서 25(이론 19, 추정 잡음으로 과대).
5. **입력 오차 대 q**: odom·gyro 입력 오차 w의 실제 분산 / 필터 q (q_ds = 2e-5|ds|, q_ψ = (0.015°)²dt), 그리고 w의 ρ1.
6. **gyro bias 경로 몫**: 같은 실현 이득에서 전이 F의 bias 열만 0으로 둔 선형 반사실과의 차이(원천별, 전체), 그리고 bias 경로가 없을 때의 heading RMSE.
7. **기억 몫**: 현재 heading 오차 중 10 s·30 s 이전의 상태 오차가 동차 전파로 남은 몫과 그 RMS.
8. 단계별 배열(K, H, F, G, 상태, ε, c1, c2, 나머지 항) 저장.
QA: closure ≤ 1e-6°, 사다리 4 heading RMSE parity ≤ 1e-6.

## Monte Carlo seed
- case당 12 seed(index 0 = 원 seed, 나머지는 gyro·odom 잡음과 초기 pose만 바뀜, RF 패킷 동일), Full B0/L2, BASE / PWIDE_NOES / ORACLE, R = POWER V_s, NOM 공분산.
- 원 seed는 이전 결과와 1e-7 parity.
- 보고: case별 arm 평균·표준편차, paired 비 PWIDE/BASE의 평균·표준편차·10/90 분위·PWIDE 우세 비율, 효과 크기(차이 평균/차이 표준편차), 원 seed 비가 분포의 어디에 있는지, route 중앙값 비의 seed 분포, 0–10·10–30 s 구간.
- 판정: 임계값 없이 seed 변동 대비 arm 간 차이의 크기로 보고. 3 route·7 case의 개발 결과이므로 일반화 주장 없음.
