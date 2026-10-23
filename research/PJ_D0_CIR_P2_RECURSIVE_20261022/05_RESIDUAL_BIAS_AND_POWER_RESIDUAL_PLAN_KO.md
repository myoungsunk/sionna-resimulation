# 검증 1·2 계획 (실행 전 고정, 2026-10-23)

## 해석 수정 (사다리 2 보고에 대한 정정)
- 상수 R_s = E[ε²]는 평균 제곱만 맞춘다. E[ε²|q] = Var(ε|q) + E[ε|q]²이므로 분산과 체계적 편향이 섞여 있고, EKF 일관성에는 조건부 평균·분산, 상태 오차와의 상관, 시간상관, Jacobian 근사가 모두 필요하다. 평균 제곱이 맞는다고 NEES≈1을 기대할 수 없다.
- ψ̄ = μ_ε/(Gg)는 g, μ, R이 일정할 때의 단순화다. 패킷마다 다를 때의 선형 근사는 Bias(ψ̂) ≈ Σ g_k μ_k/R_k / Σ g_k²/R_k (부호는 잔차 정의에 따름)이고, R_k는 편향된 패킷의 기여 가중을 바꾸므로 편향에도 영향을 준다. 사다리 2에서 확인된 것은 "κV_s로 가중을 바꿔도 잔여 편향이 충분히 해결되지 않았다"까지다.
- 사다리 2의 CIR_KV→WIDE_KV는 보정 모델과 κ(R 크기)·gate 수용이 함께 바뀐다. 순수 모델 교체 효과는 사다리 1 S3→S4에서 본다. 사다리 2는 arm별 분산 보정을 적용한 실질 필터 성능으로 해석한다.

## 검증 1 — WIDE 잔여 편향의 원인 (분석만, 필터 재실행 없음)
사다리 1(run 39794514674)의 L_BASE, L_CIR, L_WIDE 궤적(세 arm 모두 R = POWER V_s)을 그대로 쓴다. 패킷 k에서 필터에 들어간 정제 관측의 GT 기준 오차를 셋으로 나눈다.
$$\underbrace{z_s-\hat e(d_0^{\text{prior}})-h_s(\mathbf x^{GT})}_{\text{total}}=\underbrace{e-\hat e(d_0^{GT})}_{c_1:\ \text{보정기 잔차(참 상태)}}+\underbrace{\hat e(d_0^{GT})-\hat e(d_0^{\text{prior}})}_{c_2:\ \text{상태 오차 유도}}+\underbrace{s_{LoS}-h_s(\mathbf x^{GT})}_{c_3:\ \text{LUT 불일치}}$$
- c1이 지배적이면 "다중경로 편파 bias를 충분히 제거하지 못함", c2가 지배적이면 "prior 상태 오차를 편파 bias로 오인". BASE는 c1 = e − μ_s, c2 = 0. CIR은 c2 = 0.
- d0의 상태 항 h(GT) − h(prior)를 heading 부분(−g·Δψ_prior)과 나머지(위치 등)로 나눈다.
- 10 s 블록별: c1·c2·c3 평균, accept 조건부 평균, heading prior 오차, d0, FP tap 이동(fp_full − fp_los), 사후 heading 오차.
- 가중 편향식 검증: 블록마다 accept 패킷으로 b̂ = Σ g ε/R / Σ g²/R (R = V_s, g = 그 arm prior의 ∂h_s/∂ψ)를 계산하고, 같은 블록의 실제 평균 heading 오차와 비교(상관·기울기). c1/c2/c3 기여를 같은 식으로 분리.
- FP tap 이동 층별 c1 평균.
- R2 실패 case(R2_aA_m0, R2_aB_m0, R2_aA_m45)를 따로 표로 낸다. GT와 s_LoS는 오프라인 분해에만 쓴다.

## 검증 2 — POWER 보존 잔차 보정기 (사다리 3, 가설 검증)
$$\hat e_s=\mu_{\text{POWER}}(\mathbf q)+\hat\Delta_s,\qquad \Delta_s^{\text{true}}=e_s-\mu_{\text{POWER}}(\mathbf q)$$
- 학습: 학습 route 두 개. μ_POWER는 strict inner OOF(route A의 μ는 route B로만 적합한 POWER). held route는 쓰지 않는다.
- 모델: P1R과 같은 HGB·특징. PCIR = CIR 특징만, PWIDE = CIR 특징 + d0(δ~U(±20°)×3, P1R WIDE와 같은 방식). 목표만 e → Δ로 바뀐다.
- 학습 route 내부 LORO로 Δ 설명력(R², 잔차 평균)과 κ = mean(ε²/V_s)를 보고. LORO에서 route A의 inner μ는 다른 학습 route의 라벨로 적합된 것이므로 κ 추정에는 학습 route 간 약한 의존이 남는다(held route와는 무관).
- 평가(held): μ는 BASE와 같은 OOF POWER, R = V_s. 따라서 L_BASE→L_PCIR→L_PWIDE는 각각 한 요인(Δ̂ 추가, d0 추가)만 다르다. 이어서 L_PWIDE→L_PWIDE_KV(R 크기), 참고로 L_WIDE→L_PWIDE(POWER 대체 vs 보존), L_PWIDE→L_ORACLE.
- QA: L_BASE = P2-A BASE_POWER, L_WIDE·L_ORACLE = 사다리 1 (1e-7).
- 이 구조가 낫다는 것은 가설이며 임계값 판정 없이 크기로 보고한다.

## 그 다음 (검증 3)
평균 잔차가 줄어든 뒤 Var(e − ê | q, prior 품질)의 조건부 구조, 시간상관, 상태 오차와의 상관, prior 의존 관측에 대한 H_s/R_s 유효성을 검증한다.
