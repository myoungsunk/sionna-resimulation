# D1 — 잔차 시간상관/지속편향이 재귀 Heading 과잉확신을 설명하는가 (사전등록, 2026-10-21)

결과를 보기 전에 등록한다. 새 모델 학습, 계수/Gate/분산 재조정, 새 EKF 정책 없음. 입력은 기존 run 39376076166의 불변 산출물(TRACE.npz, OBSERVATION_FEATURES_LABELS, OOF 파라미터)과 동일 SourceFFD/제어 생성기뿐이다.

## 이론 (검증 대상 수식)
오차 \(\tilde x=\hat x-x\), 모델평균을 뺀 실제 측정오차 \(u_k=[e_r,e_s]_k-\hat\mu_k\).
- 예측: \(\tilde x_k^-=F_k\tilde x_{k-1}^+-w_k+q_k\) (w: 실제 제어 잡음, q: 예측 선형화 잔차)
- 업데이트: \(\tilde x_k^+=(I-a_kK_kH_k)\tilde x_k^-+a_kK_ku_k+\ell_k\) (a: 실제 gate 결과, ℓ: 관측 선형화 잔차)
q, ℓ은 실제 trace에서 정의되므로 분해는 구성상 정확하다. 성분: INIT, PROCESS, U_R, U_S, LIN. U_R/U_S는 다시 2.0 s 중심 이동평균 저주파(LF)와 나머지(HF)로 나눈다.

측정기인 부분의 필터 신념: \(P^u_k=A_kP^u_{k-1}A_k^\top+a_kK_kR_kK_k^\top a_k\). 측정기인 NEES \(=(\varepsilon^u_\psi)^2/P^u_{\psi\psi}\).

## 대리(surrogate) 입력, 각 M=200, seed 20261021
whitened \(\tilde u_k=L_k^{-1}u_k\) (L: 해당 arm R_k의 Cholesky) 를 만든 뒤 재착색 \(u'_k=L_k\tilde u'_k\).
- ACTUAL: 실제 순서.
- SHUFFLE: 시간 순서 무작위 치환(r,s 쌍 유지) — marginal/패킷 calibration 보존, 시간상관 제거.
- PHASE: 두 채널에 동일 무작위 위상 — auto/cross spectrum(평균 포함) 보존, 특정 위치-정렬 제거.
K, H, F, a는 실제 trace 값으로 고정(이 부분은 gate 피드백을 제외한 선형 응답 분석임).

## 사전등록 판정
- QA0: trace의 prior에서 재계산한 K,H로 posterior를 재현(max|Δx|<1e-8, max|ΔP|<1e-8). 실패 시 해당 조건 해석 금지.
- QA1: LIN 성분 heading RMS가 전체 heading RMS의 30% 이하일 때만 선형 해석을 주장. 초과 조건은 별도 표기.
- H1 시간상관 존재: Full B0, POWER1과 SEP_BIN에서 whitened u_s의 비중심 lag-1 자기상관 >0.5 인 case가 7개 중 5개 이상.
- H2 시간상관이 과잉확신을 설명: Full B0의 (case×arm, JOINT4 포함 63개) 중 과반에서 NEES^u_SHUFFLE ∈[0.5,2] 이면서 NEES^u_ACTUAL >3.
- H2b 2차 통계로 충분한가: 위 조건들에서 NEES^u_PHASE / NEES^u_ACTUAL ∈[0.5,2] 이 과반이면 "spectrum으로 설명", PHASE가 ACTUAL의 0.5 미만이 과반이면 "위치 정렬된 결정적 편향이 추가로 필요".
- H3 R5 A coverage 귀속: Full B0, SEP_BIN 대 POWER1 coverage 변화 중 σ효과 \(C(\delta_P,\sigma_S)-C(\delta_P,\sigma_P)\)가 70% 이상. (δ효과 \(C(\delta_S,\sigma_S)-C(\delta_P,\sigma_S)\)를 함께 보고.)
- H4 R2 B 악화 경로: Full B0에서 POWER1→PWR_MU_SEP_COV heading MSE 증가 중, U_S 성분 heading MSE 증가가 50% 이상.
- 보조: 스칼라 식 \(\gamma=(1+\lambda a)/(1-\lambda a)\) (a: u_s 비중심 lag-1, λ=1−median(a_kK_{ψs}H_{sψ}))과 NEES^u_ACTUAL/NEES^u_SHUFFLE의 Spearman 상관 보고. 판정에 사용하지 않음.

## 범위와 한계
조건: 7 case × {Full B0, Full L2, LoS B0}. 평가 t≥30 s. 하나의 복도, 동일 seed 0. 63개 arm-case는 독립 표본이 아니다. 표본 수에 기반한 유의성 주장 없음. 결과를 본 뒤 기준 변경 금지; 추가 분석은 별도 표기.
