# Δs 분산 조정의 heading–ranging trade-off 경로 결과 (2026-10-21)

실행: [run 39563292062](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39563292062). 계획 `05_TRADEOFF_PLAN_KO.md`. QA: 이전 run과 heading RMSE 2.2e-13, range RMSE 3.3e-13 이내 일치. 분해 closure 8.1e-14.

## 1. 구현
- arm: BASE, INFL_S, DEFL_S, INFL_R, DEFL_R, MIX_IR_DS(range 상향 + 편파 하향). τ·κ 기존과 동일. Full B0·L2 14 case-bias.
- 오차 분해(정확, D1 방식): 성분 INIT, PROCESS, LIN, U_R(range 측정오차가 주입), U_S(편파 측정오차가 주입). U_R·U_S를 Δs 게이트(|Δs₊₁|≥τ) / 비게이트 패킷, 그리고 2 s 기준 저주파/고주파로 나눔.
- 가산 귀속: 성분 c의 기여 \(\overline{q_c\,q_{\rm tot}}\), 합 = 전체 MSE. 표의 값 = (arm 기여 − BASE 기여) / BASE 전체 MSE의 14 case-bias 중앙값. 괄호는 증가/감소 case 수.
- 이득: prior에서 1σ innovation이 만드는 보정량 중앙값과 prior 표준편차.

## 2. 점수 (Full 14 중앙값, 대 BASE)
| arm | heading비 (개선/>10%악화) | 거리오차비 (개선/>10%악화) | radial비 | tangential비 | NEES |
|--|--|--|--|--|--|
| INFL_S | 1.038 (5/3) | 1.042 (3/1) | 1.027 | 1.111 | 5.4 |
| DEFL_S | 1.267 (5/7) | 0.939 (10/0) | **0.998** | 0.989 | 12.7 |
| INFL_R | 0.994 (8/1) | 0.975 (11/0) | 0.972 | 0.996 | 4.1 |
| DEFL_R | 0.980 (10/1) | 1.077 (6/5) | 1.064 | 1.027 | 4.3 |
| MIX_IR_DS | 1.167 (4/7) | **0.884 (14/0)** | 0.968 | 1.027 | 12.4 |
주의: 거리오차(\(\|\hat p-a\|-\|p-a\|\))와 radial 위치오차가 DEFL_S에서 어긋난다. R2 A M0 B0: 거리오차 0.89배인데 radial 1.29배, tangential 2.62배. 거리오차는 radial을 \(\rho/d\)(수평거리/3D거리)로 가중하고 tangential 2차항을 포함하므로, heading이 크게 나빠지는 case에서는 위치 개선을 대표하지 못한다.

## 3. 경로 (BASE 대비 기여 변화 / BASE MSE, 중앙값)
| arm | heading 주경로 | heading 상쇄 | radial 주경로 | radial 상쇄 |
|--|--|--|--|--|
| DEFL_S | U_S 비게이트 **+0.653** (12↑/2↓) | U_R 비게이트 −0.043, PROCESS −0.039 | U_R 비게이트 **−0.085** (0↑/14↓) | U_S 비게이트 +0.040, 게이트 +0.013 (10↑) |
| DEFL_R | U_S 비게이트 **−0.067** (1↑/13↓) | U_R 비게이트 +0.029 | U_R 비게이트 **+0.190** (14↑/0↓) | U_R 게이트 −0.036 |
| INFL_R | U_R 게이트 −0.033 (10↓) | U_S 게이트 +0.045 (14↑) | U_R 게이트 **−0.111** (0↑/14↓) | – |
| MIX_IR_DS | U_S 비게이트 **+0.526** (12↑) | U_R −0.091 | U_R 게이트 −0.111, 비게이트 −0.059 (14↓) | U_S +0.055 |
DEFL_S heading의 U_S 증가는 저주파 +0.264, 고주파 +0.339로 둘 다.

이득 경로(중앙값, 대 BASE): DEFL_S prior σψ 0.465→0.381°(0.75배), range→heading 이득 \(|K_{\psi,r}|\sqrt{V_r}\) 0.67배, 편파→radial 이득 1.05배. 편파→heading 이득은 1σ 기준 0.82배이나 \(\sqrt{V_s}\)가 0.60–0.79배로 줄었으므로 실제 오차 단위로는 1.04–1.37배. INFL_R 게이트 패킷 range→radial 0.65배, range→heading 0.63배.

## 4. 해석 (식)
\[P^{+\,-1}=P^{-\,-1}+\frac{H_r^\top H_r}{V_r}+\frac{H_s^\top H_s}{V_s}\]
- 편파 정보는 heading 방향이 97–99%. 비게이트 패킷 \(V_s\)를 줄이면 \(P_{\psi\psi}\)가 줄고(σψ 0.75배):
  1. \(K_{\psi,s}\) (실제 오차 단위) 증가 → 깨끗한 패킷의 지속 편파 편향이 heading에 더 주입 (+65%).
  2. \(K_{\psi,r}\propto P_{\psi,\cdot}H_r^\top\) 감소(0.67배) → range 오차의 heading 누설 감소, odometry를 거친 위치 누적 감소 (radial −8.5%).
  3. \(K_{{\rm rad},s}\) 증가(1.05배) → 편파 오차가 위치를 더 밈 (+5.3%) → radial 순변화 ≈0.
- 같은 구조의 거울상이 DEFL_R(range를 더 믿음 → radial +19%, heading −6.7%).
- 일반 규칙: 한 채널을 더 믿으면 그 채널의 지속 편향이 그 채널이 보는 차원에 더 누적되고, 다른 채널 오차가 그 차원으로 새는 것은 줄어든다.
- INFL_R은 오염된 range 패킷의 주입만 줄이므로(14/14) 다른 경로의 손실이 거의 없다.
- MIX: range 쪽 이득은 합쳐지지만(radial −6.4%, 거리 14/14), heading의 U_S 비게이트 경로(+52.6%)는 range 조정과 무관하게 그대로 남는다.

## 5. heading 개선 case의 분리
DEFL_S heading 개선: R4 B, R5 A(기준 heading 1.44°, 4.35°: 편향 지배). INFL_R heading 개선: R2 세 case, R5 B(기준 0.95–1.84°). 겹침 1 case(R5 B B0). ranging(거리오차) 개선은 7 case-bias가 겹침.
