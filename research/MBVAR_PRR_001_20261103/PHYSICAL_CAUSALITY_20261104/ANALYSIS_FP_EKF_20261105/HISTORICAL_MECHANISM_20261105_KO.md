# MBVAR — FP/편파 오염 → EKF prior 오차 누적·혁신 상쇄·공분산 과신

**상태:** `HISTORICAL_OBSERVATIONAL_MECHANISM_PASS / RELATIVE_BIAS_DYNAMICS_PASS / C2_TRUE_INTERVENTION_NOT_RUN`  
**수준:** `NONINDEPENDENT_EXPLORATORY`. 과거 원본을 수정하지 않으며, C1과 C2의 인과 주장 구분을 유지한다.

## 1. 원본 및 재계산 범위

- [원본 자연 재귀 POWER1 Full/LoS, B0, R4/R5 · Actions #39376076166](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166), `POWERJOINT_SEPARATE_RS_FINAL_VALIDATION_39376076166`에서 원본 `OBSERVATION_FEATURES_LABELS.csv.gz`, `OOF_PARAMETERS.csv.gz`, `TRACE.npz`, `UPDATE_ORIGINS.csv.gz`.
- [first-path C0-A · Actions #41783949902](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41783949902); 신규 ray 수집 [Actions #41958274374](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41958274374).
- POWER1 Full/B0 0.4초 갱신 기점 **1,079개** (R4=371, R5=708). 0.2초 전체 재귀 상태 R4=742, R5=1,415 (**2,157개**).
- 원본 OOF `mu`, `R`, NIS 및 gate를 재귀 trace와 일치시키고, `nu=epsilon+delta_h` 항등식 재계산. `JOINT4`의 UPDATE_ORIGINS는 trace와 NIS 불일치가 있어 **이 분석에서 제외**.
- 입력 아카이브 SHA256: `265b586283cbd3e50333530463ad1578a41bd0f7932b94b3728dfd87355dd4c1`. Original Heading prior variance 복원에서 S-root가 두 개인 6개 시점은 불확실성 보존.

## 2. 관측이 정상처럼 보이는 현상

\[
\nu_s=\underbrace{s_F(x_{GT})-h_s(x_{GT})-\mu_s}_{\epsilon_s}
+\underbrace{h_s(x_{GT})-h_s(x^-)}_{\delta h_s}.
\]

`delta_h_s`는 **XY와 yaw를 모두 포함**하는 관측공간 상태오차다. 다음 모두 저장된 원본 값과 재계산이 일치한다.

| 사례 | \(\epsilon_s\) | \(\delta h_s\) | \(\nu_s\) | Heading 오류 prior → posterior | σψ prior → posterior | NIS |
|---|---:|---:|---:|---:|---:|---:|
| R4 t=0.4 s | +0.1426 | −0.1280 | +0.0146 | +4.621°→+4.675° | 2.178°→2.124° | 0.117 |
| R4 t=38.0 s | +0.1306 | −0.0893 | +0.0412 | −3.290°→−3.317° | 0.521°→0.516° | 0.211 |
| R4 t=100.0 s | −0.0529 | +0.0524 | **−0.0005** | +1.390°→+1.388° | 0.211°→0.211° | **0.070** |
| R5 t=32.4 s | −0.0082 | +0.0146 | +0.0065 | −3.496°→−3.474° | 1.779°→1.774° | 0.025 |

R4 t=100초에는 실제 Heading 오류가 약 **6.59σ**인데도 NIS=0.070; 관측 잔여 `epsilon`과 틀린 prior가 생성한 `delta_h`가 상쇄되었다. 이것은 **state error의 관측가능성 실패 사례**이지 특정 오염 순간 하나의 장기 인과효과를 증명하는 것은 아니다.

## 3. 새로운 잘못된 갱신이 시작되는 곳

- **R4 t=0 s:** 실제 Heading과 prior 차이 +0.461°. 편파 보정 +3.491°, 거리 보정 −0.656°가 수용되어 오류가 **+3.296°**가 됨. 한 번의 Joseph update에서 σψ는 **5.000°→2.709°** (yaw 분산 약 **70.65% 감소**). FP 이동 +1 tap, 편파 전체 변화 +0.1821이지만 FP selection 성분 −0.0261, 동일 tap 복소 변화 +0.2082: FP만 바꾸는 것은 오히려 오염을 확대할 수 있다.
- **R4 t=33.6/34.4 s:** 편파 오염 +0.3422/+0.3288 (FP 이동 +2/+1 tap). 편파 Heading 갱신 −0.3277°/−0.2787°가 음의 prior 오류를 더 악화. 이후 38초 경로 최댓값 −3.317°는 이 반복 수용과 양립하지만 오직 두 시점만의 장기 인과로 환산할 수 없다.
- **R4 t=105.2 s:** NIS=97.11로 거절, 수용 이전부터 존재한 Heading 오차 +1.318°는 남는다. **Gate는 새 오염 유입 방어이지 과거 state/P 복원 장치가 아니다.**
- **R5 t=196.4 s 반례:** Full−LoS 편파 오차 +0.5875, FP selection +0.4780, 그러나 Kψ,s≈0.0155 °/signed-s이고 편파 Heading 변화는 +0.0091°뿐. 큰 물리 오염이 모두 과신/상태오차를 초래하지 않는다.

## 4. 경로 전수 집계 — 30초 이후 (0.4초 갱신시점)

| 지표 | R4-B | R5-B |
|---|---:|---:|
| 갱신 시점 | 296 | 633 |
| Heading RMSE | 1.509° | 1.058° |
| Heading95 | **12.8%** | **97.5%** |
| Heading NEES mean | **21.43** | 1.40 |
| NIS<1이지만 Heading95 밖이며 갱신이 수용된 시점 | **101** | 12 |
| mean of `delta_h_s²/(S_ss-R_ss)` | **20.09** | 2.96 |
| ratio of means `E[delta_h_s²]/E[S_ss-R_ss]` | **23.20** | 2.15 |
| 보정 후 편파 잔여 lag1 (0.2초) | 0.6995 | 0.7523 |

연속 시점의 상관 때문에 독립 표본으로 간주하거나 p-value를 계산해서는 안 된다. R5의 높은 lag1만으로 R4 과신의 원인을 설명할 수 없으며, 상태오차/기하/모델 잔여오차와의 결합이 중요하다.

## 5. EKF 과신이 생기는 수학적 이유

\[
e_k^+\approx(I-K_kH_k)e_k^-+K_k\epsilon_k,\quad
e_k^-\approx F_ke_{k-1}^++\eta_k.
\]
\[
P^+=P^--P^-H^T(HP^-H^T+R)^{-1}HP^-.
\]

`P+`는 **수용된 갱신의 혁신 수치 자체에는 의존하지 않는다**(같은 H/P/R로 고정한 조건). 따라서 `nu≈0`이라도 수용되면 공분산이 줄며, 실제 오차는 줄지 않을 수 있다. 반복되는 잔차 바이어스·시간상관이 독립·제로평균 가정에 반영되지 않으면 **상태는 틀린 채 covariance만 작아지는** 불일치가 커진다. 예측 단계 FPFᵀ+GQGᵀ는 분산을 늘릴 수 있으므로 '모든 시점에 P가 감소한다'는 표현은 틀리다.

## 6. [ψ, gyro-bias] 결합의 추가 경로: 실제 재귀 두 채널의 차이

공통 sensor controls, 같은 초기 state로 실행한 기록에서:
\[
\delta\psi_k^- = \delta\psi_{k-1}^+-\delta b_{k-1}\Delta t,\qquad
\delta\psi_k^+ = \delta\psi_k^-+\delta u_{RF,k}.
\]
여기서 delta는 **Full−LoS 두 기존 자연재귀** 차이이고, delta u에는 서로 다른 **채널별 OOF μ/R와 게이트** 효과도 들어 있다. 따라서 순수 물리 RF-only 인과 효과가 아니다.

| R4 시간 구간 | Full−LoS Heading 격차 변화 | 상대 갱신 누적 | gyro-bias 예측 누적 |
|---|---:|---:|---:|
| 33–38 s | −2.648° | −2.105° | **−0.544°** |
| 38–59.6 s | +4.345° | +5.804° | **−1.458°** |
| 59.6–100 s | +0.529° | −0.178° | **+0.707°** |

B0 실제 bias는 0이지만 R4 t=38 s Full bias 추정 +0.0941°/s, LoS −0.0507°/s; t=100 s Full −0.0297°/s, LoS −0.0065°/s. 양쪽 초기 자이로 제어는 같으므로 이후 추정 `b` 차이가 Heading 예측에 반영됨을 보인다. **이전에 추정된 bias 상태가 잘못되면 정상에 가까운 다음 RF 측정만으로도 즉시 고쳐지지 않는다.**

## 7. 2가지 접근법과 남은 C2 시험

**A. 현재 관측만 정정(C1):** 같은 prior, gain K, 선형화 h/H, 평균 μ/R, 기존 gate를 고정하고 FP tap / s / r만 Full→LoS로 교체한다. 차이는 `Δx+=K Δz`; Joseph P는 동일하므로 장기 공분산 회복을 주장하지 않는다. R4 38초처럼 prior 자체가 −3.29° 틀린 때의 현재 편파 제거는 잔존 오차를 즉시 소거하지 못한다.

**B. 최초 오염 시점부터 자연 재귀(C2):** t=0 단일 패킷, 33–38초, 99–105초를 각각 개입시켜 동일 x0/P0/시드/controls로 **미래 H,K,gate,x,P,b를 모두 재계산**한다. FF/FL/LF/LL/FP-only, mask 고정 vs 재판정, yaw-only/XY-only/bias-only state reset, P-only inflation을 교차. '오염 자체'와 '상태 복구/불확실도 조정'을 분리한다. t=0 baseline Full/FULL 동일 재현, 시점별 pose/μ/R parity와 Joseph PSD, GT oracle 오프라인 전용 조건을 먼저 통과해야 한다.

**C2 미실행:** 로컬 진단에는 원래 FFD 전체 안테나 bank 및 원래 4상태 연산을 새 개입 prior에서 재실행한 완전한 baseline이 없다. 위 Full–LoS 자연재귀 차이와 누적 분해는 새로운 C2 intervention이 아니며, 과거 **특정 FP 오검출 한 건이 t=100초 Heading 오차의 몇 %를 만들었다고 주장할 수 없다.**

## 8. 산출물

국소 재현 코드와 전체 행별 CSV·QA·4개 그림은 대화 첨부 `FP_EKF_HISTORICAL_CAUSAL_MECHANISM_20261105.zip`에 저장. 로컬 계산은 frozen 과거 자연재귀 2,157개, 0.4s origin 1,079개, μ/R/NIS/gate 및 혁신 항등식 검사 통과. Relative yaw 분해 재합성 최대 오차 **3.41×10⁻¹³°**. 원본 수정·Sionna RT 재실행 없음.  
