# 전 상태 오차 예산 v4 + d0 재귀 피드백 (실행 전 고정, 2026-10-23)

목적: heading 중심이던 v2/v3 분석을 위치 성능까지 확장한다. 이번 실행은 진단만 하고, 기존 arm(BASE, CIR, WIDE_NOES, PWIDE_NOES, ORACLE)은 바꾸지 않는다. GT는 분해와 GT 진단 arm에서만 쓴다.

위치 오차는 참값 위치 기준의 앵커 좌표계로 나눈다. u_r = (p_GT − a)_xy / |·|, u_t = [−u_r,y, u_r,x]. radial 오차는 e_r = u_rᵀ δp, tangential 오차는 e_t = u_tᵀ δp이다.

## 스크립트

- `p2_fullbudget.py`: P1, P2, P3, P5. case마다 seed 0–11을 쓴다(seed 규약은 `p2_mc.py`와 동일). B0/L2, 5 arm.
- `p2_d0feedback.py`: P4.

## P1 — 12-seed 위치 성능

창은 0–10, 10–30, 30–60, 60–90, 90–120, 120–180, 180 s 이후, 그리고 30 s 이후 전체다.

| 지표 | 정의 |
|---|---|
| heading·XY·radial·tangential | RMSE와 평균 |
| XY NEES | δpᵀ P_pp⁻¹ δp, 이상값 2 |
| 95 % 포함률 | XY는 χ²₂ 5.991, radial·tangential·heading은 χ²₁ 3.841 |
| range 오차 | 3D 거리 오차 |
| 비교 | 1 s 시계열, BASE 대비 seed별 비와 악화 seed 수 |

## P2 — 4-state 원천 예산

v3와 같은 고정 이득 재귀로 원천 i의 4-state 오차 D_i,k를 구하고, heading·radial·tangential에 투영한다.

d⁻_k = F_k d⁺_{k−1} + G_k w_k + r_pred,k,  d⁺_k = (I − K_k H_k) d⁻_k + K_k ε_k + K_k r_meas,k

- 몫 = E[y_i e]/E[e²]이며 부호가 있다.
- BASE 대비 격차는 원천별 MSE 단위(몫 × MSE)로 나눈다.

## P3 — Heading → Position 경로

**(a) 진입 성분 분해.** 모든 주입(초기 오차, Gw, r_pred, Kε, K r_meas)을 들어가는 상태 성분(위치, heading, bias)으로 나눈 뒤 같은 F, K, H로 전파한다.

- 편파 잔차가 위치에 주는 기여를 셋으로 나눈다:
  - pol|pos: K_p,s ε_s로 직접 위치에 들어간 몫
  - pol|head: heading으로 들어간 뒤 위치로 넘어간 몫
  - pol|bias: bias를 거친 몫
- 세 몫의 합은 원천 합과 정확히 같다.

**(b) 증분 회계.** F_pp = I이므로 위치 오차는 아래처럼 정확히 망원(telescoping) 합으로 분해된다.

δp_t = δp⁻_0 + Σ F_p,ψ δψ⁺_{k−1} + Σ F_p,b δb⁺_{k−1} + Σ (Gw + r_pred)_p − Σ K_p,r H_r d⁻_k − Σ K_p,s H_s d⁻_k + Σ (Kε + K r_meas)_p

- 둘째 항(F_p,ψ δψ⁺ 합)이 heading 오차가 이동하며 누적된 몫이다.
- 다섯째·여섯째 항은 range와 편파 innovation이 위치를 되돌린 몫이다.
- 마지막 항은 측정 잔차가 위치에 직접 주입된 몫이다.
- 이 분해는 원천별로도 계산한다. 결과는 고정 선형화 아래의 회계 분해로만 기술한다.

## P4 — d0 prior 민감도와 재귀 피드백

**A. GT 주변 innovation 곡선.** seed와 무관하며 전 case에 적용한다.

- 섭동: heading ±10° (0.5° 간격), tangential ±0.3 m (2.5 cm 간격).
- innovation: ν(δ) = s_F − ê(CIR, s_F − h_s(x_GT+δ)) − μ_s − h_s(x_GT+δ)
- 지표:
  - κ_phys = −Δν/(g δ): g는 해석 기울기
  - κ_rel = Δν/Δν_BASE = 1 − Δê/Δd0
  - 정보가중 평균(가중치 g²/R_s)
  - κ ≤ 0 프레임 비율
  - ν의 근 |δ*|와 다중근 비율
  - |δ| ≤ 2° 안의 ê 점프와 h_s 점프
- HGB는 구간별 상수라서 미분 대신 유한차분을 쓴다.

**B. 짝지은 재실행.** 같은 RF와 같은 seed 운동 잡음을 유지하고, 초기 heading에 −10, −5, −2, 0, 2, 5, 10°를 더한다. P0는 그대로 두며 σψ = 5°이다. seed는 0, 3, 5, 7, 8, case는 7개 전부다.

| arm | ê 계산 방식 |
|---|---|
| BASE | ê = 0 |
| PWIDE_CL | 배치 그대로, 자기 prior의 d0 사용 |
| PWIDE_OB | 같은 run에서 BASE prior의 d0 사용(자기 피드백 제거) |
| PWIDE_GT | 참값 d0 사용(GT 누출, 진단 전용) |
| ORACLE | ê = s_F − s_L |

- 기록: 창별 점수, 마지막 10 s 평균 heading, 0° 대비 gate 결정 변화율, 0° 대비 ê 변화와 d0 변화, PWIDE_CL·BASE prior 주변의 국소 κ_rel(±1, ±2°; offset 0, ±5°에서), 1 s 시계열.

## P5 — 시간 지연별 영향 커널

c_b(t) = Σ_{k: t−t_k ∈ b} e_cᵀ Φ(t,k) K_k ε_k

- 성분 c: heading, radial, tangential
- 지연 구간 b: 0–10, 10–30, 30–60, 60 s 이후
- 입력: 편파 전체, c1, range
- 지표: 부호 있는 몫(그 입력 성분 대비, 전체 MSE 대비), 구간 간 교차항 행렬, 절대 가중치 질량
- 커널 합은 P2의 원천 전파와 일치해야 한다(QA).

## QA (계산 무결성 확인용이며, 기전 증명이 아님)

- 원천·진입·증분 closure < 1e-9·max|d|
- 커널 합과 전파의 일치 < 1e-9·max|d|
- BASE, PWIDE_NOES, ORACLE의 12 seed: v2 MC(`MC_ALL.csv`)와 heading·XY RMSE 차이 < 1e-6
- CIR, WIDE_NOES의 seed 0: ladder 4와 차이 < 1e-6
- P4 offset 0: MC와 차이 < 1e-6

판정 임계값은 두지 않고 크기로 보고한다. seed는 운동 잡음과 초기 자세만 바꾸고 RF 입력은 같으므로, 12개의 독립 환경이 아니다.
