# POWER_JOINT: 리뷰어 반증 기반 수정 검증 계획 (2026-10-16)

**상태: 검증 계획이며 새로운 실험 결과가 아니다.** 현재 연구의 동결 baseline과 데이터 아카이브를 수정하지 않는다.

## 0. 고정된 사실·명칭·Claim Boundary

원본: [N4-B](https://github.com/myoungsunk/sionna-resimulation/blob/research/r5-n4b-joint-rs-errors-20261015/research/R5_N4B_20261015/n4b_rf_errors.py), [N4-C](https://github.com/myoungsunk/sionna-resimulation/blob/research/r5-n4c-joint-sr-recursive-20261015/research/R5_N4C_REPORT_20261015/RESULTS_KO.md), [N4-Q](https://github.com/myoungsunk/sionna-resimulation/blob/research/n4q-geometry-integrity-staged-20261015/research/N4_Q_GEOM_RF_20261015/EXECUTION_REPORT_KO.md), [Q4-R](https://github.com/myoungsunk/sionna-resimulation/blob/research/n4q-q4r-prior-calibration-20261015/research/N4_Q4R_20261015/RESULTS_KO.md).

- N4-C Full RF B0, Mount0, Joint4: Heading RMSE 7.490→1.773°, Gyro Bias **RMSE** 0.08862→0.02160°/s, Pose NEES 2591.16→12.38, Pose 95% 포함률 17.1→46.2%.
- 실제 B0 Gyro Bias 0°/s, 기존 J4 Bias 추정 시계열 **시간평균** −0.05841°/s, 최종 +0.01432°/s; POWER 평균 −0.00537°/s, 최종 +0.00157°/s. 0.089°/s를 항상 양의 가짜 Bias로 오해하지 않는다.
- Full RF L2 J4: Mount0 Heading 7.521→1.991°, Mount45 0.848→0.727°. POWER 후에도 Pose95 Mount0 45.7%, Mount45 12.3%; 확률적 일관성 미달.
- N4-B RF 잔차의 Joint 95% 포함률 POWER 94.51%는 **측정오차 수준**; N4-C의 Pose 95%와 동일한 통계량 아님.
- R2 평가 POWER는 R4/R5 Mount0에서만 학습, R2 Mount45는 미학습 각도 외삽. 동결 R2는 단일 복도, seed0이며 반복 관찰되어 독립 hidden test가 아니다.
- Q4-R2는 **state prior covariance P⁻에 PSD 항을 실제 재귀 추가**했다. 관측공분산 R(q)를 키운 실험이 아니다. 따라서 'R을 키워 Bias 정보가 감소했기 때문에 Q4-R이 실패했다'는 단정 금지.
- 본 POWER q-only 3-bin 모델의 실효 수치: 전력 기울기 2, 3bin×2 평균 절편 6, 3bin×3 대칭 공분산 원소 9, 분위수 경계 2 = **19개 스칼라 기술량**. 이 숫자는 독립적으로 최적화한 19개 물리 파라미터/통계 자유도를 의미하지 않는다.
- 정확한 현행 명칭은 **경험적 First-path power-conditioned signed RF correction**. 확률적으로 정규화된 Bayesian likelihood, full RF에서 완전히 복원된 Dual-LP Heading, statistically consistent posterior 또는 여러 scene generality를 주장하지 않는다.

## 1. State-coupled contamination 연구 가설

상태 $x=[x,y,\psi,b_g]^T$, 관측 $z=[r,s]^T$. 직접 RF Jacobian의 $b_g$열은 모두 0이다. 그러나 운동모델에서 $\partial\psi_{k+1}/\partial b_g \simeq-\Delta t$이고, recursive $P_{b_g,\{x,y,\psi\}}\neq0$가 생긴다.

$$
K_{b_g,:}=P^-_{b_g,\{x,y,\psi\}} H_{\{x,y,\psi\},:}^{T}(H P^-H^T+R)^{-1},\quad
\Delta\hat b_g=K_{b_g,r}\nu_r+K_{b_g,s}\nu_s.
$$

이 식은 RF 오차가 약관측 Gyro Bias 추정으로 전이되는 **가능한 경로**다. 개선의 독립 원인은 아직 구분되지 않았다.

**실험 가설**
- M1: Signed $\mu_s$ 감소가 가짜 $b_g$ 갱신을 줄임.
- M2: Range $\mu_r$ 및 XY–Heading cross covariance가 간접 bias 오염을 줄임.
- M3: $C_{rs}$를 반영하면 동일 패킷 Range와 편파의 중복 오염을 바르게 결합함.
- M4: Mean/cov 대신 Gate 완화나 범용 상수 $R$ 확대만으로 대부분의 성능이 재현됨.
- M5: High-power $R(q)$ 축소가 과신을 증폭함.
- M6: G4에서 gain/gate tail이 pointwise NLL 우세를 recursive 실패로 바꿈.

M1–M6는 **확정된 메커니즘이 아니라 반증 대상으로 지정한 가설**이다. 특히 양의 $C_{rs}$가 원인이라고 미리 결론 내리지 않는다.

## 2. RV0: 소스 감사와 음성 대조

- 동결 raw RF/Native LoS/FFD LUT/gyro/wheel/Joint4/SR4/S4/DR4/POWER 자료의 SHA256, time/pose ID, RF tap detector source/parity 검사.
- 실제 사용할 19개 기술량 readback: q cutpoints, bin mean slopes/intercepts, full 2×2 SPD covariance와 N4-B OOF 예측 출력 일치.
- 원본 B0 gyro bias trajectory의 signed mean, RMSE, extrema, endpoint, confidence, prior/post status를 따로 재현.
- synthetic zero-multipath, port1/port2 swap, zero-bias, Native LoS 보정 없이 원본 보존하는 negative controls.
- GT/oracle와 future packet을 온라인 predictor에 넣지 않음.
- **Gate:** 원본 state/P/Gate/RF 관측 정합 전 실험 중단.

## 3. RV1: Bias leakage와 Dual-LP 편파의 직접 정보 가치

동일 사전 상태·공분산과 동일 RF 패킷에서 One-step $K$ 행을 보존하고 다음을 비교한다.

| 후보 | 사용 정보 | 핵심 반증 |
|---|---|---|
| DR4 | Gyro+Wheel only | RF 없이 Heading·Bias drift |
| Range-only 4state | r only | q 또는 r만으로 Heading/Noise Bias 수정 가능한 수준 |
| S4 | s only | Dual-LP만의 추가 Heading 제약 |
| Joint4 R0 | r+s | 다중경로 상태오염 |
| POWER full | r+s with q calibrator | Bias leakage 완화 |
| No-s + q | r and q calibrator, without s observation | q가 s를 대체할 수 있는지 |
| No-r + q | s and q calibrator | Range 기하가 필요한 정도 |

동일 Gate/동일 prior에서 $\delta b_g=K_{b_g,r}\nu_r+K_{b_g,s}\nu_s$ 분해; 또 $\nu=e_{\mathrm{MP}}+e_{\mathrm{LUT}}+e_{\mathrm{pose}}$를 GT scoring으로 분해하고 각 성분의 반사실적 기여 기록. 직접 bias 측정의 정보량이 없음을 확인하고 시간 누적에 따른 상태 교차공분산 전개를 측정.

**PASS:** B0 fake bias와 Full s/R contamination의 연결을 time/Gain 항으로 입증. Range-only 역시 cross-state 때문에 Heading에 간접 영향을 줄 수 있으므로 's 이외에 Heading 정보가 절대 없다'는 주장 금지.

## 4. RV2: POWER Mean / Cross-Cov / Gate 주효과 요인분해 — 제1우선 실행

같은 $x^-,P^-$에서 one-step, 이어 **각 방법 자체의 natural Gate 재귀**를 둘 다 수행한다. 조합:

| ID | 평균 $\mu_r,\mu_s$ | 공분산 $R$ | Gate |
|---|---|---|---|
| A | 0,0 | R0 | original 99% |
| B | 0,0 | 4R0 | natural |
| C | 0,0 | R0 | relaxed/no gate |
| D | 0,0 | 4R0 | relaxed/no gate |
| E | POWER μr only | R0 | natural |
| F | POWER μs only | R0 | natural |
| G | POWER μr+μs | R0 | natural |
| H | 0,0 | POWER diag(Vr,Vs) | natural |
| I | 0,0 | POWER full R | natural |
| J | POWER both | POWER diag | natural |
| K | POWER both | POWER full R | natural / original frozen |
| L | POWER both | POWER full R | **original R0 common Gate** (offline counterfactual) |

반드시 추가 **직접 교차항 테스트**: K의 동일 $V_r,V_s,\mu_r,\mu_s$ 유지하고 $C_{rs}\rightarrow 0$만 바꾼 실험. 이로 인해 각 $\mu_s$, $\mu_r$, $C_{rs}$의 독립 기여를 계산할 수 있다. 원래 Joint4와 decorrelated SR4는 올바른 원 covariance whitening을 사용해야 한다.

측정: bias time trace/signed bias RMSE; Heading RMSE, XY, conditionalXY NEES, Pose NEES/95%, gain 항 $K_{b,s/r}$, $\|K\|$, accepted packets, pre-gate NIS, 0.2s 연속 기각 길이/시점, FP tap switching. 공통 prior+common mask와 자연 재귀를 **다른 인과 추정 단위**로 보고한다.

**반증:** B–D가 K를 재현하면 복잡한 POWER의 고유 기여 주장을 축소; $C_{rs}=0$에서도 K와 동일하면 covariance coupling을 독립 contribution에서 제거; μs-only가 별도 Bias leakage 개선을 보이지 않으면 메커니즘 주장 재검토.

## 5. RV3: Native LoS 안전성, Power/Range confounding, gain drift

- 이미 확인된 normal LoS에 Full μ 적용시 A/m0 Range RMSE 0.0461→0.0822m, A/m45 0.0491→0.0926m 오보정의 재귀 영향 검증.
- $q=\log_{10}(P_1+P_2)$ vs 3D distance, TX/RX FFD, Rx port absolute gain, FP detection 과정을 모델과 분리. $\Delta q = q_{\mathrm{obs}}-\hat q_{\mathrm{LoS}}(\hat x^-,m,a)$를 비교. GT로 계산한 $\hat q$는 offline ceiling으로만 보관.
- Gain +/−3,6 dB perturbation; 일반적인 공통 gain 변화에서 $s$는 유지되고 $q$는 이동하므로 boundary/invariance 확인. Side-port swap에서는 s→−s, q 동일; $\mu_s$의 signed covariance transform parity 필요. 반대 방향 주행에서 s 오염 부호가 반드시 반전한다는 주장은 하지 않는다.
- 정상 LoS와 Full을 구별하는 contamination score의 calibration과 false LOS correction/falsely rejecting clean s 전력 region; mount 0°와 45°를 각각 분리.
- **Gate:** 모든 Full 성능 유지 + 정상 LoS의 Range/s 및 heading/bias 오보정 억제. 장면 독립 검증 없으면 scientific GO 보류.

## 6. RV4: High-power variance 클램핑과 bin boundary 연속성 — R 전용 반증

**Q4-R에서 바꾼 것은 state covariance $P^-$이지 $R$이 아니었다.** Kalman Gain $K=PH/(H^2P+R)$의 scalar 사례에서 $P$ 확대와 $R$ 확대는 일반적으로 Gain에 반대 방향으로 작용한다. 따라서 Q4-R 실패를 'R 증가→Bias 수렴 지연'으로 설명할 수 없음.

비교:
1. 원 POWER $R(q)$.
2. **High bin만** $R_{\mathrm{high}}\succeq R_0$로 PSD floor.
3. 모든 bin에 같은 PSD floor.
4. $V_r$만 floor, $V_s$만 floor(2x2 covariance SPD/Schur 조건 보장).
5. High bin 원래 $R$, Gate만 완화/고정.
6. 평균·분산을 train-only 연속 회귀로 보간, 분위수 경계 도약과 NIS/Gain chattering 비교.

$C_{rs}\ne0$에서는 단순한 diagonal element clamp만으로 $R\succeq R_0$가 보장되지 않는다. Whitening eigenvalue 방식:

$$
A=R_0^{-1/2}R(q)R_0^{-1/2}
=U\operatorname{diag}(\lambda_i)U^T,\quad
R_{\mathrm{floor}}=R_0^{1/2}U\operatorname{diag}(\max(1,\lambda_i))U^TR_0^{1/2}.
$$

**R0는 실험용 분산이고 명목 clean-LoS thermal variance가 아님.** Floor는 물리적으로 확립된 하한이 아니라 명백한 반증용 control임을 표시. High power의 undercoverage를 원인으로 인정하려면 Q4 posterior를 고치는 $P$ 변화가 아니라 **R-only 실제 재귀**에서 Mount45 Heading accuracy/NEES/coverage가 함께 개선돼야 한다.

경계: R2 low→mid μr +2.67cm, mid→high μr −2.40cm discontinuity. 전력 변화가 작은 시점의 q-bin 변경 시 s/r mean jump, eigen_R, NIS, K, covariance contraction 및 error harm 조건부 평가.

## 7. RV5: G4의 NLL 우세와 재귀 역전의 물리 기전

원래 N4-B 9,519개 관측의 heldout NLL: G4 −1.7038, POWER −1.5898. 하지만 Full L2 J4: M0 G4 Heading **1.845° vs POWER 1.991°** (여기서는 G4가 조금 더 좋음); M45 G4 1.133° vs POWER 0.727° (여기서는 POWER 우세). M0 Pose NEES G4 33.36 vs POWER 12.89.

따라서 'G4는 모든 조건의 Heading이 나쁘다'는 과장 금지. 실제 관찰은 'best pointwise NLL ≠ best recursive calibration and cross-Mount accuracy'다.

동일 pre-RF x,P 및 동일 trajectory/FP tap에서:
- G4의 detector-s threshold-span 기반 bin과 POWER의 log-FP-power bin 선택 차이.
- $\mu_r,\mu_s$, $V_r,V_s,C_{rs}$, eigen_min/R condition number, $\|K\|$, $K_{\psi,s},K_{b,s}$, pre-gate NIS, natural/common Gate, consecutive wrong-high-info packet count, step harm.
- G4 mean + POWER R, POWER mean + G4 R 교차 재생; G4 feature 그룹만 바꾸고 covariance bin은 고정하는 대조.
- $K$ spike나 covariance undershoot가 실제로 관찰되지 않으면 'G4 과적합→Gain Spike' 가설 폐기; Gate selection/harm sign 또는 장착각 extrapolation으로 대체 설명.
- 181.6–195.6s 기존 N4-A 과신 구간에서 원인 식별; 무조건 G4 원인으로 연결 금지.

## 8. RV6: Measurement coverage와 recursive NEES 단절, 시간상관 가설

원래 N4-B POWER 측정잔차의 공동 95% 포함률 94.51%와 N4-C Pose 포함률 M0 ~46%, M45 ~9–12%는 서로 **다른 추정 대상의 통계**다. 차이가 심각하지만, 그 원인을 시공간 자기상관 하나로 단정할 수 없음. 관측 Bias misspecification, state-dependent likelihood, process error, Gate, 높은 power covariance, H derivative, single-scene confounding도 후보.

- $r/s$ 오차에서 거리/입사각/Heading 작동점/Power/FP 조건부 mean을 제거한 뒤 잔차 ACF, innovation whiteness, pre-gate NIS, site-fixed vs moving vs static yaw, repeated path/seed 조건을 분리.
- 확률적 temporal correlation은 독립 scene or independent RF realization/site revisit이 확보됐을 때만 stochastic colored-noise로 선언.
- temporal bias model, sliding-window effective sample accounting, correlated-time batch factor와 stationary site effect 분리.
- 상태 RF bias term을 추가하면 $b_g,\psi,x,y$와 식별성 문제가 생길 수 있으므로 augmented observability matrix SVD/rank 먼저 수행.
- posterior NEES/95%가 개선된 대조에서도 Heading/Bias RMSE와 sharpness/logdet 비악화를 요구.
- temporal whitening 가설이 독립 데이터에서 반증되면 다른 동역학·관측 misspecification 원인으로 전환.

## 9. RV7: 독립 Full RF, Mount·경로·HW 전이

- 동결 R2/R4/R5는 동일 corridor, 단일 RF 장면. R2는 반복 확인됐으므로 final unseen test가 아님.
- 새 실제 Full complex 2-port RF와 대응 Native LoS, 시간열 $t_s$, Gyro/Wheel Controls, GT scoring-only. 직선·역방향·곡선·정지 yaw scan; Mount0/45 및 새 angle; Anchor 방위/높이; 여러 독립 multipath scene/receiver gain/hardware seed.
- 실제 30% common first-tap vs 3tap neighborhood sum, short window FP energy, threshold 20/30/40%, port group delay/AGC step. LoS LUT yaw 회전만으로 Full RF를 생성한 척 금지.
- 최소 독립 장면 3개를 train/validation/final test로 분리하는 설계 목표; paired sensor seeds 등은 사전 고정하고 scene을 통계 단위로 사용.
- Final: B0/L0/L1/L2, +/−gyro bias, RMSE Heading/Bias/XY, Gate, Pose/ConditionalXY/Full4 NEES, 95% coverage, false LoS correction, packet-power scale sensitivity, per-scene/mount failure tails; correlation/coverage model likelihood validity.
- 새 scene 학습·평가 자료가 없으면 'consistent','hardware-ready','generalizable' 주장 금지.

## 10. R0–Q5–Q7 연구 진행 게이트

| 순서 | 기술 수행 가능성 | 새 모델 채택 조건 |
|---|---|---|
| RV0/1 | 현 archive 즉시 | Bias leakage/dual-LP 기전 확인 |
| **RV2** | **가장 먼저 실행** | $4R_0$/Gate-only가 아닌 $\mu_s$ 및 $C_{rs}$의 추가 기여 |
| RV3 | 기존 LoS 관측부터 실행 | 정상 LoS 오보정의 실제 재귀 영향과 안전한 모델 |
| RV4 | 기존 R2 재귀로 직접 실행 | $R(q)$ floor vs R0/POWER 대비 RMSE/NEES/coverage 균형 |
| RV5 | 기존 R2 재귀로 직접 실행 | G4 variance/gain/gate 원인 중 무엇이 지배적 |
| RV6 | 진단 즉시, 확정은 독립 RF scene 이후 | temporal origin vs geometry confounding 구별 |
| RV7 | 신규 Full RF 입력 준비 우선 | 장면/경로/마운트 독립 결과로 최종 주장 확정 |

**Q4-R 기존 FAIL은 지우지 않는다.** RV1–RV6의 인과 반증/학습 없이 수행한 파일럿은 기존 증거 강화용이며, Q5의 정규화된 quality likelihood와 Q6 Bayesian recursive 모델 배포는 독립적인 prior consistency와 LoS protection이 확인될 때까지 HOLD.

모든 단계: source auditor→autonomous invalid-results fix→re-audit→math/negative controls→frozen parity→paired experiments→independent review. 실패 run 기록 유지, 기존 branch/report 덮어쓰지 않기.
