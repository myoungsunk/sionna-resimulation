# 창(window) 관측 가능성 검사 — 계획 (2026-10-26, 실행 전 고정)

## 목적
슬라이딩 윈도우로 오염된 RF 잔차의 체인을 끊는 방향을 검토하기 전에, 윈도우 하나가 위치·Heading·gyro bias를 (그리고 RF nuisance를 함께 둘 때 그것까지) 독립적으로 추정할 정보를 가지는지 확인한다. 윈도우 길이는 고정값(10 s, 20 s)이 아니라 관측 가능성과 오염 지속 시간으로 정한다.

## 입력 (모델·필터 변경 없음, 재실행 없음)
- error budget v3 arrays: run 39950207483(6 case), 39954439738(R2_aA_m0). BASE arm의 실제 F_k(전이 Jacobian), H_k(BASE prior 상태에서의 관측 Jacobian), R_k(POWER), accept mask, P⁻_k, P⁺_k.
- `research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz`: GT±1° 모델 s(관측 Jacobian QA), 부호 Δs, e_s.
- `HP_SERIES.csv.gz`: step k → pose_id 대응.

## 정의
- 결정적 Gramian(제안식): \(\mathcal I_{k,N}=\sum_{i=k-N+1}^{k}\Phi_{i,s}^\top H_i^\top R_i^{-1}H_i\Phi_{i,s}\), \(s=k-N\) (창 시작 상태 기준). accept된 패킷만 합산(필터가 실제 쓴 정보). 구현은 \(\Psi_i=F_i\cdots F_1\), \(\Phi_{i,r}=\Psi_i\Psi_r^{-1}\) 누적합으로 정확히 같은 식(루프 구현과 상대오차 QA).
- RF nuisance: 창 안에서 상수인 편파 편향 \(\beta_s\)(D5s), range+편파 편향 \(\beta_r,\beta_s\)(D6). 관측 Jacobian \([H_i\Phi_{i,s},E]\).
- 보고: 창 시작 기준 rank, scaled 최소 고유값과 그 고유벡터 구성(스케일 x,y 0.1 m, ψ 1°, b_g 0.1°/s, β_r 0.05 m, β_s 0.01), 창 끝 기준 σ_ψ, σ_xy, σ_bg, corr(ψ,β_s), ψ–β_s 정보 cosine \(\mathcal I_{\psi\beta}/\sqrt{\mathcal I_{\psi\psi}\mathcal I_{\beta\beta}}\).
- 확률적 창(S*): 같은 창에서 실현 process noise \(Q_k=P^-_k-F_kP^+_{k-1}F_k^\top\)를 포함한 finite-memory KF, 비정보 prior(x,y 100 m, ψ 10 rad, b_g 1 rad/s, β 10). 결정적 Gramian은 Q를 무시하므로 긴 창에서 정보를 과대평가한다.
- 변형: S4(상태만), S5s(+β_s), S6(+β_r,β_s), S5s_ds(+β_s, Δs 의사관측), *_c(R에 창 길이별 상관 계수 \(1+2\sum_{l<N}(1-l/N)\rho_l\) 적용, ρ는 BASE 실현 잔차).
- Δs 의사관측: 다른 두 route로 학습한 Ridge(Δs 8개 → e_s)의 held 잔차 분산을 β_s 관측 잡음으로 사용.
- 창 길이 L ∈ {1,2,3,5,7.5,10,15,20,30,45,60,90} s, 창 끝은 1 s 간격.
- L*(k): σ_ψ ≤ {1°,2°,5°}를 만족하는 최소 L (t ≥ 30 s의 창 끝).
- 오염 지속: BASE 실현 잔차(편파, range)의 τ_int, 1 s·5 s 평활 후 |값|>RMS인 같은 부호 구간 길이.

## QA
Q의 최소 고유값, Ψ 역행렬 잔차, series 시간 정렬, 실현 H_ψ와 GT 유한차분 g의 상관·비, 누적합 Gramian vs 루프, Q=0 KF vs Gramian σ_ψ(prior 영향만 남아야 함).

## 한계 (사전 명시)
- H는 GT가 아니라 BASE prior 상태에서 평가(필터가 실제로 본 선형화). GT 유한차분과 비교해 QA.
- R은 POWER 대각, 시간상관은 *_c의 근사 계수로만 반영(H가 창 안에서 천천히 변한다는 가정).
- β는 창 안에서 상수로 가정. Δs 의사관측 잡음과 s 잡음의 상관은 무시(Δs 쪽에 낙관적).
- 판정 기준 없음. 기술(descriptive) 분석이며 결과 해석은 별도 문서.
