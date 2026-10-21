# Δs가 큰 패킷에 대한 필터 설계 — (A) 게이트 보정, (B) 게이트 불확실도 상향 (계획, 2026-10-21)

실행 전 계획. 승인 후 사전등록으로 고정하고 실행한다.

## 1. 배경 (지금까지의 사실)
| 사실 | 수치 | 출처 |
|--|--|--|
| Δs 고유 heading 개선은 \(|\Delta s_{+1}|\) 상위 20%에 집중 | Q5 평균 +4.4°, 중앙값 +1.8°, 개선 비율 0.67; Q1–Q3 ≈0 | Δs 양상 분석 |
| Δs 고유 ranging 개선은 전 구간 소폭, |Δs|와 함께 증가 | Q1 +0.32 cm → Q5 +1.01 cm | 동일 |
| |Δs| 큰 패킷 = 강한 다중경로 오염 | Q5: \(|e_s|\) 0.216, \(|e_r|\) 15.7 cm (Q1: 0.032, 5.9 cm) | 동일 |
| POWER 분산이 |Δs|에 따라 반대로 틀림(train) | 상위 20%: 실제/모델 분산 s 2.7–3.7, r 1.8–3.3; 나머지: s 0.36–0.63, r 0.61–0.70 | 본 계획 계산 |
| 모든 패킷에 Δs 평균 보정(방법 A) | 측정 개선, 재귀 1.25–2.06배 악화 | 방법 A |
| 재귀 개선/악화 결정 요인 | 평균 보정의 heading 이동 < 기준 필터 오차 ⇔ 개선 (14/14, 사후) | 민감도 분석 |
| 크기 특징으로 분산 조건화 위험 | SEP(detector_s_span 층화) 악화: 정렬 불리 | 분리모델 실험 |

## 2. 게이트 (온라인 계산 가능, GT 불필요)
\(\gamma_k=\mathbb 1[|\Delta s_{+1,k}|\ge\tau]\). τ = train route Full 패킷 \(|\Delta s_{+1}|\)의 80분위(1차), 70·90분위(민감도). held route 값(미리 계산): R2 0.052, R4 0.052, R5 0.060 (p70 0.035–0.041, p90 0.084–0.097). LoS 기준선(중앙값 0.005–0.013)보다 충분히 크다.

## 3. 방향 A — 게이트 보정 (편향을 추정해 뺀다)
\[\hat\mu_{c,k}=\begin{cases}f_c(\text{기존 특징},\Delta s_k) & \gamma_k=1\\ \hat\mu_c^{POWER1} & \gamma_k=0\end{cases}\quad c\in\{s,r\}\]
\(f_c\): route-heldout HGB(기존 16 + Δs 8, 방법 A와 같은 설정), 라벨 \(e_c\).
| arm | 내용 |
|--|--|
| A_S | heading 차원: 편파 평균만 게이트 보정 |
| A_R | ranging 차원: range 평균만 게이트 보정 |
| A_SR | 둘 다 |
| A_SR_V | A_SR + 게이트 패킷 분산을 보정 후 잔차분산(train OOF, 게이트 부분집합)으로 교체 |
| A_SR_ALL | 같은 모델을 모든 패킷에 적용(게이트 효과 분리용) |
예측(식): heading 오차 \(\delta\psi\approx\sum_kc_k(e_k-\hat\mu_k)\). 게이트는 보정을 편향이 큰 20%에만 적용 → 보정 이득(편향 제거)이 보정 오차가 만드는 이동보다 큰 패킷에 한정. 사후 규칙 "이동 < 기준 오차"를 **사전 예측**으로 시험: 게이트 arm의 이동(Δμ/g 구간 WLS)이 ungated보다 작고, 그만큼 악화 case가 줄어야 한다.

## 4. 방향 B — 게이트 불확실도 상향 (편향을 몰라도 덜 믿는다)
\[V_{c,k}\leftarrow\begin{cases}\kappa_c^{\rm hi}V_{c,k}&\gamma_k=1\\ V_{c,k}&\gamma_k=0\end{cases}\]
\(\kappa^{\rm hi}_c\) = train 게이트 패킷의 \(\overline{r_c^2/V_c}\)(POWER1 잔차의 패킷 calibration 비). held route 값(p80): R2 s 2.74/r 3.25, R4 2.90/2.88, R5 3.71/1.78.
| arm | 내용 |
|--|--|
| B_S | 편파 분산만 상향 |
| B_R | range 분산만 상향 |
| B_SR | 둘 다 |
| B_SR_2LVL | B_SR + 비게이트 패킷을 \(\kappa^{\rm lo}_c\)(0.36–0.70)로 하향(2단 calibration) |
예측(식): 이득 \(K\propto 1/V\)이므로 오염 패킷이 주입하는 오차 \(c_ke_k\)가 \(1/\kappa\) 수준으로 줄고, 그 패킷의 정보는 원래 질이 낮아 손실이 작다. 최적 가중이 \(1/(V+b^2N_{\rm eff})\)라는 이전 식(H-B)의 게이트판. 위험: (i) SEP처럼 분산 조건화가 이득–잔차 정렬을 바꿀 수 있음, (ii) 2LVL은 깨끗한 패킷을 더 믿어 시간상관 과잉확신이 커질 수 있음, (iii) 하향은 L2 bias 학습에는 유리, 상향은 불리할 수 있음.

## 5. 민감도·기준
- τ 민감도: A_SR, B_SR을 p70, p90으로 반복.
- 기준: BASE(POWER_DIAG), REF_POWER1.
- 총 15 arms × 7 case × {Full B0, Full L2, LoS B0}, η=1, κ(bias 이득)=1, gate는 패킷 R.

## 6. 보고 (모든 값 크기로)
- 재귀: Full 14의 heading RMSE비·개선/악화·최악, NEES·coverage, xy RMSE비(ranging 효과가 나타나는 곳), L2 bias비. LoS는 진단.
- 측정: 게이트/비게이트 부분집합별 heading 환산 오차, range 잔차, 패킷 s95/r95(분산 calibration).
- 메커니즘: arm별 평균 보정의 heading 이동 RMS와 기준 오차의 비 → 사후 규칙의 사전 검증.
- 비교 축: A 대 B(보정 대 할인), 게이트 대 전체(A_SR 대 A_SR_ALL), heading 차원 대 ranging 차원(S 대 R).

## 7. 한계
한 복도, 같은 seed. Δs 모델과 κ는 train route에서만 정하지만, 게이트 패킷 비율(20%)과 분위 선택은 이번 분석을 보고 정한 것이라 완전한 독립검증은 아니다. GT 기반 민감도 g는 메커니즘 분석에만 쓰고 필터 입력에는 쓰지 않는다.
