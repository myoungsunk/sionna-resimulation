# SCIENCE_SPEC — POL-XCORR-001 (DRAFT)

각 식에 단위와 추정 성격을 표기한다: **[model-truth]** = 가정한 물리 모델에서의 유도, **[deterministic]** = 학습 없는 관측 함수, **[learned]** = train route에서 적합, **[ORACLE_ONLY]** = 채점·진단 전용.

## 1. 관측 체인

1. H_c[pose, k, rx, tx] (복소, 무차원), k = 257 bins, 6.2504–6.7496 GHz. 주분석 tx = 0(+45).
2. CIR: h_rx(n) = IFFT_{4·257}( H·w_Hann ) · 257, tap 간격 Δt = 1/(4B) = 0.5008 ns. 복소 baseband(대역 하단 기준) [deterministic].
3. 첫 경로 tap n₀: 강한 포트의 |h| 최대값의 30% 이상인 첫 tap; 두 포트 공통 [deterministic, v_replay 동일].
4. s(n) = (|h₊(n)|²−|h₋(n)|²)/(|h₊(n)|²+|h₋(n)|²) [무차원]; s_fp = s(n₀); ds1 = s(n₀+1)−s(n₀).

## 2. 물리 모델 [model-truth]

단일 TX 편파, 두 RX 포트 벡터 h(t) ∈ C²:

h(t) = a·p(t) + Σ_k b_k e^{−j2πf_c δ_k} p(t−δ_k)

- a, b_k ∈ C²: LoS/반사 경로의 RX 포트 투영 Jones(안테나 패턴·자세 포함).
- p(t): Hann 창 대역제한 펄스(실수, 대칭). B_rms² = ∫f²|P|²/∫|P|².
- **F1:** k 없음 ⇒ rank J = 1 ⇒ det J = 0, ε = 0. a의 타원성(φ, S3)과 무관.
- **F2 (2-path, 소 δ):** b̃ = b e^{−j2πf_cδ}, h ≈ (a+b̃)p − b̃δ p′.
  det J = |(a+b̃) ∧ (−b̃δ)|² · det G, G = Gram{p, p′} on W ⇒ **det J ≈ δ²|a∧b|²(E_pE_p′ − |⟨p,p′⟩|²)**, a∧b ≡ a₊b₋ − a₋b₊.
  ε ≡ 4detJ/(trJ)² ≈ 4δ²(2πB_rms)²|a∧b|²/|a+b̃|⁴ (대칭 W에서 ⟨p,p′⟩≈0).
  range bias(첫 경로 tap 이동)는 O(δ), 감지량은 O(δ²).
- **F3:** D = diag(g₊, g₋), h → Dh ⇒ J → DJD^H ⇒ ε_ρ = detJ/(J₁₁J₂₂) 불변. 포트 간 시간 오프셋 Δ: h₋(t) → h₋(t−Δ)는 F2와 같은 구조로 det J > 0 (단일 경로에서도) ⇒ false positive.
- **F4 (이동):** 주행거리 x에 대해 Δd(x) = d_ref − d_LoS.
  - 반송파 위상 ψ(x) = 2πΔd/λ, 공간주기 **Λ = λ/|dΔd/dx|** (λ = 4.61 cm).
  - 포트별 |h_±(n₀)|² ∝ |a_± + b_± e^{−jψ}|² → b₊/a₊ ≠ b₋/a₋ 이면 두 포트가 서로 다른 위상으로 fading. s_fp(x)는 Λ 주기 성분을 가진다.
  - envelope shape(폭·왜도·peak–centroid)는 Λ 주기로 진동, 진폭 ∝ |b/a|·δ/T_p.
  - δ 자체의 변화 스케일 c/(B|dΔd/dx|) = Λ·f_c/B ≈ 13Λ ⇒ "breathing"은 δ→0 접근이 아니라 ψ 회전 현상.
  - LoS 단독에서도 s(x)는 yaw·고도각에 따라 변한다(heading 신호). 따라서 "LoS면 두 편파가 같은 비율로 감소"는 성립하지 않는다.

## 3. 지표

| ID | 정의 | 단위 | 성격 | 위상 동시성 | prior |
|---|---|---|---|---|---|
| M0 | \|ds1\|, log_fp_power | –, log | deterministic | 불필요 | 불필요 |
| M1a | ε_W = 1 − √(1 − 4detJ/(trJ)²), W = n₀+[−2,4] | 0..1 | deterministic | 필요 | 불필요 |
| M1b | ε_ρ = detJ/(J₁₁J₂₂) | 0..1 | deterministic | 이득·위상 오프셋 불변, 시간 오프셋에 민감 | 불필요 |
| M2 | ρ(τ) = R₊₋(τ)/√(R₊₊(0)R₋₋(0)), τ ∈ [−8,8] tap (W 내부 신호); τ* = argmax\|ρ\|, A_k = (\|R(τ*+k)\| − \|R(τ*−k)\|)/(\|R(τ*+k)\| + \|R(τ*−k)\|), k = 1, 2 | tap, – | deterministic | 필요 | 불필요 |
| M3 | 포트별 \|h_±\|² 창 n₀+[−2,6]에서 2차 모멘트 폭 σ_t [ns], 왜도 γ, peak–centroid 오프셋 [ns]; 포트 차 Δ | ns, – | deterministic | 불필요 | 불필요 |
| M4a | 인과 창 L(0.6 m) 안의 s_fp(x)와 log\|pk₊\|−log\|pk₋\| 의 국소분산(창 내 1차 추세 제거) | – | deterministic | 불필요 | 불필요 |
| M4b | 같은 창의 M3 각 성분 국소분산 | ns², – | deterministic | 불필요 | 불필요 |
| M4c | 연속 샘플 간 Stokes 단위벡터 측지거리의 창 평균, \|Δyaw\| < 1°/step 구간만 | rad | deterministic | 필요 | 불필요 |
| M4d | segment의 high-pass s(x) PSD 중 예측 Λ_floor/Λ_wall ±20% 대역 전력 비율 | – | 진단(기하 예측 사용) | 불필요 | 대략적 위치 |

- 참고(비교 제외): d0 = s_Full − h_s(prior) — prior 필요.
- 진단 전용(negative control): φ_fp = arg(h₊(n₀)h₋*(n₀)), S3_fp. 단일 경로에서도 0이 아님을 S0·LoS 채널로 시연.

## 4. Label [ORACLE_ONLY]

- T1 e_s = s_Full − s_LoS, T2 e_r, T3 η_W = Σ_W‖h_F − h_L‖² / Σ_W‖h_L‖² (두 포트, tx=0), T4 경로별 δ_k, |a∧b_k| (R-01 PASS 시만).
- 정적 성분 경고: ceiling 경로(δ ≈ 0.05–0.3 ns, Λ ≈ 10–22 m)는 F2·F4상 M1–M4로 감지 불가. T4로 e_s 중 그 몫을 분해 보고.
- positive class = |T1| ≥ train route q0.80. 창 지표(M4)는 같은 인과 창의 |T1| 평균으로 label.

## 5. 단계별 설계

| 단계 | Gate | 입력 | 내용 | 판정 |
|---|---|---|---|---|
| P0 | G0→G1 | lock 30개 | R-01..R-05 해결, F1·F3 수치 확인 | 모든 tolerance PASS |
| S0 | G2 | 합성 | H1 δ² 기울기, a∥b → 0, 단일 타원 경로 → ε=0·φ≠0, SNR·σ_Δ 별 noise floor | H1 PASS |
| P1 | — | 7 case | E1, E2; drive/turn 분리; LoS 채널 동일 지표 = floor; m0 vs m45 | go rule (PLAN_PARAMETERS) |
| P2 | — | drive segment ≥ 2 m | P2a E3(결정 gate) → P2b 주기 일치 → P2c E4 → P2d turn 대조 | P2a 미달 시 M4a/M4b STOP |
| P3 | — | P1/P2 생존 지표 | 포트 위상·이득 무작위, σ_Δ, SNR, 1.0016 ns 재표본화 | E5 산출(판정 아닌 허용치) |
| P4 | — | VNA 2×2 (외부) | 반사체 vs face-to-face 부호 검정 | 부호만, 정확도 주장 금지 |

## 6. 경쟁 설명과 통제

| 경쟁 설명 | 예측 서명 | 통제/개입 |
|---|---|---|
| LoS 자체 타원성(안테나 cross-pol, 자세) | φ, S3 ≠ 0이지만 ε = 0 | LoS 채널 ε ≤ 1e-8 (R-03) |
| yaw·고도각에 의한 LoS s 추세 | M4a가 LoS 채널에서도 상승 | LoS 채널 동일 지표 = false-alarm floor; turn 구간 대조; P2a |
| ceiling 정지 경로 | e_s 큼, M1–M4 낮음 | T4 분해, 실패가 아닌 원리 한계로 보고 |
| fp tap 전환 | n₀ 변동 시점에 지표 계단 | W 민감도 2종, n₀ 변화 플래그 층화 |
| 포트 시간 오프셋 | 단일 경로에서도 ε > 0 | S0·P3 σ_Δ sweep |
| 공간 aliasing | 예측 Λ와 관측 주기 불일치 | 4 cm 샘플, Λ < 8 cm 비율 ≤ 1% (사전 확인) |
| route/anchor 재사용 | route 간 과대 일관성 | 1 m block bootstrap, scene n=1 명시 |

## 7. 통계

- 단위: route(LORO) 내 ΔAUC, 1 m block bootstrap. scene 독립 단위 n=1 → 과학 판정 상한 `SUPPORTED_RETROSPECTIVE`.
- 다중 비교: primary는 E1(P1), E3·E4(P2) 3개만. 나머지는 secondary/diagnostic으로 표기.
- 검정력: route 3개, 각 수백 m 주행 / 1 m block → route당 유효 block 수를 P0에서 보고하고, 그 수로 감지 가능한 최소 ΔAUC를 bootstrap으로 계산해 FROZEN 전에 기록(F-12).

## 8. 산출물 (FROZEN 이후)

- `results_s0/S0_LAW.csv`: delta_ns, psi, wedge, snr_db, offset_ps, seed, eps_W, eps_rho, phi_fp, S3_fp
- `results_p1/P1_FEATURES.csv.gz`: case, route, pose_id, phase, n0, eps_W, eps_rho, tau_star, A1, A2, sigma_t_±, gamma_±, ds1, log_fp_power, T1, T2, T3, channel(full/los)
- `results_p1/P1_AUC.csv`: heldout_route, arm, phase, auc, auc_lo, auc_hi, delta_auc, n_pos, n_blocks
- `results_p2/P2_PSD.csv`, `P2_PERIOD.csv`, `P2_DETECT.csv`
- `results_p3/P3_ABLATION.csv`: arm, sigma_ps, snr_db, gain_phase_randomized, auc, delta_auc_vs_clean
- `DECISIONS.json`: estimand별 status(PASS/FAIL/BLOCKED/NOT_RUN)와 verdict 분리
- 각 폴더 `MANIFEST.json` (COMMON_CONTRACT V)
