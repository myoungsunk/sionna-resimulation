# Δs 분산 조정의 heading–ranging trade-off 경로 분석 (실행 전 고정, 2026-10-21)

## 질문
- Q4: 편파 분산을 Δs로 조정(특히 DEFL_S)하면 heading은 나빠지고 ranging은 좋아진다. 그 경로는 무엇인가?
- Q6: heading 개선 case와 ranging 개선 case가 arm마다 다르므로, 두 채널 조정을 조합(INFL_R + DEFL_S)하면 이득이 합쳐지는가?

## 이미 확인된 사실 (results_ranging, Full 14 case-bias, 대 BASE)
| arm | heading 비 (개선/>10%악화) | range 비 (개선/>10%악화) |
|--|--|--|
| INFL_S | 1.038 (5/3) | 1.042 (3/1) |
| DEFL_S | 1.267 (5/7) | 0.939 (10/0) |
| INFL_R | 0.994 (8/1) | 0.975 (11/0) |
| DEFL_R | 0.980 (10/1) | 1.077 (6/5) |
교차 패턴: 한 채널을 하향(더 믿음)하면 그 채널이 주로 보는 차원(s→heading, r→radial)은 나빠지고 다른 차원은 좋아진다.

## 방법
Arms: BASE, INFL_S, DEFL_S, INFL_R, DEFL_R, MIX_IR_DS(= range 상향 + 편파 하향). τ·κ는 기존과 동일(train 80분위). 조건 Full B0, Full L2.

1. 오차 경로 분해(D1과 같은 정확 선형 분해): \(\tilde x_k^+=(I-a_kK_kH_k)(F_k\tilde x_{k-1}^+-w_k+q_k)+a_kK_ku_k+\ell_k\). 성분 INIT, PROCESS(odometry/gyro 잡음), LIN(선형화), U_R(range 측정오차가 주입한 것), U_S(편파 측정오차가 주입한 것). U_R·U_S는 두 방식으로 나눈다: (a) 2 s 이동평균 기준 저주파/고주파, (b) Δs 게이트(|Δs₊₁|≥τ)/비게이트 패킷.
2. 정확한 가산 귀속: 각 성분 c의 기여 \(\overline{q_c\cdot q_{\rm tot}}\) (q = heading, radial, tangential), 합이 전체 MSE와 같다. arm 대 BASE의 기여 변화로 경로를 판정한다.
3. 이득 경로: prior에서 1σ innovation이 만드는 보정량 — \(|K_{\psi,r}|\sqrt{V_r}\), \(|K_{\rm rad,r}|\sqrt{V_r}\), \(|K_{\psi,s}|\sqrt{V_s}\), \(|K_{\rm rad,s}|\sqrt{V_s}\) (중앙값, 수용 패킷, t≥30 s), prior \(\sqrt{P_{\psi\psi}}\), \(\sqrt{P_{\rm rad}}\), 상관 \(\rho_{\rm rad,\psi}\).
4. QA: 기존 run과 heading RMSE 재현(|Δ|<1e-9), 분해 closure.

## 해석 기준 (미리 정함)
- DEFL_S의 heading 악화가 U_S(비게이트) 기여 증가로 설명되면 "깨끗한 패킷 편파 편향 누적" 경로.
- DEFL_S의 radial 개선이 U_R 기여 감소 + \(|K_{\rm rad,r}|\) 변화와 함께 나타나면 "heading을 편파가 고정 → range innovation이 위치로 배분" 경로. U_S의 radial 기여 감소로 나타나면 "편파 직접 위치 보정" 경로.
- MIX가 INFL_R의 heading 이득과 DEFL_S의 range 이득을 함께 보이면 조합이 맞고, DEFL_S의 heading 손실을 그대로 가져오면 조합은 trade-off를 해소하지 못한다.
