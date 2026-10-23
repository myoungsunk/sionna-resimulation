# P2 사다리 2 — R_s 규칙만 교체 (실행 전 고정, 2026-10-23)

사다리 1(run 39794514674, 결과 90288dc)에서 R_s를 packet별 V_s → 상수로 바꾼 것이 P2-A의 가장 큰 단일 손실(R2 1.85–1.94배, R5 1.68배)이었다. 상수 R_s는 P1R의 arm별 LORO MSE에서 넘어온 설정으로, 평균적으로는 맞지만 재귀에서 패킷 간 상대 가중 $w_k=g_k^2/R_k$를 없앤다. 반대로 보정 arm에 POWER V_s를 그대로 쓰는 것(사다리 1의 L_CIR, L_WIDE)은 다른 잔차($e-\mu_s$)의 분산이라 크기가 맞지 않는다.

## 규칙 (모든 arm에 같은 규칙)
$$R_{s,k}^{X}=\kappa_X\,V_{s,k},\qquad \kappa_X=\frac{1}{N}\sum_{i\in\text{train LORO}}\frac{\varepsilon_{X,i}^2}{V_{s,i}}$$
- ε_X: arm X가 필터에 넣는 관측의 잔차. BASE는 $e-\mu_s$, CIR는 $e-\hat e_{CIR}$, WIDE는 $e-\hat e_{WIDE}$.
- LORO 잔차 행은 P1R `calib_R`과 같은 모델·시드·행. 이 행들의 평균 제곱이 저장된 상수 R_cal과 1e-12 이내로 같아야 한다(QA).
- V_s(학습 route r): 다른 학습 route 하나로 적합한 POWER(strict inner teacher). held route는 어디에도 쓰지 않는다.
- packet 간 V_s의 상대 구조는 유지하고 크기만 맞춘다. V_s 순위가 보정 후 잔차에 대해서도 정보가 있는지 Spearman(ε², V_s)으로 함께 보고한다.

## 사다리 (각 X ∈ {BASE, CIR, WIDE})
| 단계 | arm | 갱신 R_s | gate R_s | 이전 단계와 다른 것 |
|---|---|---|---|---|
| a | L_X | V_s | V_s | 사다리 1과 같음 (parity 1e-7) |
| b | L_X_KU | κ_X V_s | V_s | 갱신 가중만 |
| c | L_X_KV | κ_X V_s | κ_X V_s | gate 판정까지 |

그 다음 같은 규칙끼리 비교: L_BASE_KV → L_CIR_KV → L_WIDE_KV, 그리고 L_BASE_KV → L_WIDE_KV. 참고: L_BASE → L_WIDE_KV, L_WIDE_KV → L_ORACLE.

## 고정
입력·모델·초기값(NOM)·Full B0/L2·채점 구간·μ_r/V_r·gate 종류 모두 사다리 1과 같다. B0와 L2는 따로, 구간은 0–2, 2–10, 10–30, 30+ s 따로 보고. 임계값 판정 없이 크기와 방향을 route×조건×구간별로 보고한다.
