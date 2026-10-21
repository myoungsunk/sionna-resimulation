# Step 2 — 시간상관을 모델에 직접 넣었을 때 현재 상태·관측 변수에서 유효한가 (사전등록, 2026-10-21)

결과를 보기 전에 등록한다. inflation(η)과 무관하게, 기준 필터(η=1)에 측정 편향의 시간상관을 확률모델로 넣는다. 상태 \(x=[x,y,\psi,b_g]\), 관측 \(z=[r,s]\), 평균 POWER1, 패킷 분산 POWER 대각은 그대로 둔다. RF 재학습 없음.

## 1. 측정오차 모델: white + Gauss-Markov
whitened 단위 편향 \(\tilde\beta_c\) (c∈{r,s})를 두고
\[ z_c=h_c(x)+\mu_c+\sqrt{V_{c,k}}\,(\tilde\beta_{c,k}+\tilde n_{c,k}),\quad \tilde\beta_{c,k+1}=\phi_c\tilde\beta_{c,k}+\omega_{c,k} \]
\(\mathrm{Var}(\tilde\beta)=f_c\), \(\mathrm{Var}(\tilde n)=1-f_c\), \(\phi_c=e^{-\Delta/\tau_c}\), \(\mathrm{Var}(\omega)=f_c(1-\phi_c^2)\). 전체 패킷 분산은 \(V_c\)로 보존(패킷 calibration 유지).
파라미터: D1의 whitened 잔차 ACF(POWER_DIAG, Full B0)에 \(\rho(t)=f\,e^{-t/\tau}\)를 t∈{0.2,0.5,1,2,5,10} s(ρ>0.02)에서 로그 최소제곱 적합 → **train route case들의 중앙값**(held route 미사용).
| held | \(f_r\) | \(\tau_r\) s | \(f_s\) | \(\tau_s\) s |
|--|--|--|--|--|
| R2 | 0.238 | 4.62 | 0.774 | 2.80 |
| R4 | 0.347 | 6.48 | 0.800 | 2.39 |
| R5 | 0.238 | 5.78 | 0.800 | 1.82 |
(적합 RMSE 0.02–0.18: 단일 지수는 근사다. range는 빠른 감소 후 긴 꼬리.)

## 2. 필터 구현 (6-상태 공통 구조)
\(x_a=[x,y,\psi,b_g,\tilde\beta_r,\tilde\beta_s]\).
- 예측: \(P_a^-=\begin{bmatrix}FP_{xx}F^\top+GQG^\top & FP_{x\beta}\Phi\\ \Phi P_{\beta x}F^\top & \Phi P_{\beta\beta}\Phi+Q_\beta\end{bmatrix}\), \(Q\)는 기존과 동일, \(Q_\beta=\mathrm{diag}(f_c(1-\phi_c^2))\).
- 관측: \(H_a=[H,\ \mathrm{diag}(\sqrt{V_r},\sqrt{V_s})\,M]\), \(R_a=\mathrm{diag}((1-f_r)V_r,(1-f_s)V_s)\), \(\nu=z-h(x)-\mu-\mathrm{diag}(\sqrt V)\hat{\tilde\beta}\). M: 모델에 포함된 채널 마스크.
- gate: \(\nu^\top(H_aP_aH_a^\top+R_a)^{-1}\nu\le\chi^2_2(.99)\). 정상상태에서 \(f V+(1-f)V=V\)이므로 기존 패킷 gate와 같은 크기.
- 업데이트: \(K_a=P_aH_a^\top S^{-1}\), Joseph.
- **Consider (Schmidt)**: \(K_a\)의 β 행을 0으로 둠(β 추정 안 함, 평균 0 유지). 교차공분산 \(P_{x\beta}\)는 정확히 전파 → 시간상관을 일관되게 반영하되 관측성 불필요.
- **Augment**: β까지 추정(β를 빼서 편향 제거 시도). 관측성: \(\partial s/\partial\psi=g\), \(\partial s/\partial\tilde\beta_s=\sqrt{V_s}\) → g가 변할 때만 분리 가능.
- 초기: \(\hat{\tilde\beta}=0\), \(P_{\beta\beta}=\mathrm{diag}(f)\)(정상분포).
- 모든 β 채널 f=0이면 기존 4-상태 필터와 같다(QA).

## 3. Arms
| arm | 내용 |
|--|--|
| BASE | f=0 (= POWER_DIAG η=1) |
| REF_POWER1 | 원래 POWER1 |
| GMC_S | consider, s만 |
| GMC_RS | consider, r·s |
| GMA_S | augment, s만 |
| GMA_RS | augment, r·s |
| GMC_RS_T05 / GMC_RS_T2 | consider r·s, τ×0.5 / ×2 (민감도) |
| GMA_RS_T05 / GMA_RS_T2 | augment r·s, τ×0.5 / ×2 (민감도) |
조건 7 case × {Full B0, Full L2, LoS B0}, 평가 t≥30 s.

## 4. 보고 (모든 값 크기로; 참조 수준은 해석용)
Full 14 case-bias: median NEES(참조 0.67–1.5), median coverage(참조 ≥0.85), |ln NEES| 개선 개수, RMSE비(대 BASE) 중앙값·개선·>10% 악화·최악, L2 bias비, xy RMSE비. LoS B0는 진단(측정 정보 손실 여부)으로만 보고.
Augment 진단: β 추정 품질 = corr(\(\sqrt{V_s}\hat{\tilde\beta}_s\), 실제 \(u_s\)의 2 s 이동평균), 사후/사전 β 분산비(작을수록 관측됨), heading 오차 변화와의 관계.
QA: BASE와 REF_POWER1이 기존 점수 재현(|ΔRMSE|<1e-9).
