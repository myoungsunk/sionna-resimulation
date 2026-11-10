# B-only prior 오차와 공분산 과신 — 코드·데이터 원인 감사

**기준:** 2026-11-10 (KST). `sionna-resimulation`, B0 Full seed10 R2/R4/R5, B_FROZEN 및 B_BIAS_COV, 3,136 물리 시점×2 조건=6,272행.  
**상태:** 저장된 GitHub Actions #42600632209 추적과 기존 Full/LoS 원본 특성표의 읽기 전용 재산술 PASS / 신규 RF 재시뮬레이션·신규 폐루프 EKF·모델 변경 **미실시**.  
**핵심 판정:** Heading prior는 이전 RF posterior와 RF가 학습한 gyro-bias 상태를 포함한다. 현재의 낮은 Heading·bias 포함률은 관측된다. 오차·P 전파식 자체는 저장 결과와 수치적으로 일치한다. 따라서 **소스의 행렬 전파 버그는 확인하지 못했다.** **상관·편향된 RF 관측, gyro-bias 상태 흡수, 고정 bias 과정잡음, 약한 상태 구별성**은 결합된 위험 경로다. 각 물리적 기여율이나 유일한 근본 원인은 아직 미분리다.

## 1. 실제 EKF prior는 어떻게 만들어지는가?

원본 `core.py` 운동식과 `online.py`의 W0 재귀가 정의한 상태는 \(x_k=[p_x,p_y,\psi,b_g]^T\)이다. 매 시점 k에서

\[
\begin{aligned}
\psi_k^-&=\operatorname{wrap}(\psi_{k-1}^++g_k-\hat b_{g,k-1}\Delta t_k),\\
\hat b_{g,k}^-&=\hat b_{g,k-1}^+ ,\\
\nu_k&=z_{B,k}-h(\hat x_k^-)-\mu_k,\\
\hat x_k^+&=\hat x_k^-+K_k\nu_k. 
\end{aligned}
\]

따라서 이번 gyro를 읽기 전에 **지난 RF가 위치·Heading·gyro bias에 남긴 상태**가 이미 시작값이다. 현재 RF를 아직 사용하지 않은 prior라도 RF와 독립인 것은 아니다.

실제 Heading error \(e_k=\operatorname{wrap}(\hat\psi_k-\psi_k^{GT})\)에 대해 wrap 분기를 고려한 누적 항등식은

\[
 e_k^-=e_{k-1}^+ +\underbrace{(g_k-\Delta\psi_k^{GT})}_{\text{raw gyro 회전 증분오차}}-\underbrace{\hat b_{g,k-1}\Delta t_k}_{\text{현재 추정한 bias의 회전 보정}},\quad
 e_k^+=e_k^-+\underbrace{K_{\psi,r}\nu_r+K_{\psi,s}\nu_s}_{\text{RF 보정}}.
\]

**중요한 구분:** 위 −\(\hat b_g\Delta t\)는 *bias 추정 보정의 대수적 항*이다. 실제 gyro bias \(b_g^*\)가 0이 아니면 gyro 측정오차에 실제 bias 효과도 포함되므로, 일반 상황에서 ‘bias 보정항 전체가 잘못됐다’라고 말하면 안 된다. 본 B0에서는 실제 gyro bias가 0이라는 입력 설정이 전제된다.

**재현 확인:** 6,272행에서 gyro/이동거리 증분을 저장 prior·previous posterior와 원본 transition의 역산으로 회복. 원본 F, G, Q로 예측한 P와 저장 Pprior 차이 최대 \(2.08\times10^{-17}\). Joseph posterior, RF gain 오차 계수, gyro-bias 평균의 예측·갱신도 항등식 PASS. 원본 `online.npz` gyro 바이트를 이번 실행에서 직접 읽은 것은 아니므로, 이 검증은 원본 predictor와 기록의 일치 검증이다.

## 2. prior 오차와 95% 포함률의 실제 크기

|루트|보정|Prior Heading RMSE|Prior Heading 평균오차|\(\pm1.96\sqrt{P_{\psi\psi}}\) 실제 포함률|B0에서 bias \(\pm1.96\sigma_b\) 실제 포함률|
|---|---|---:|---:|---:|---:|
|R2|B_FROZEN|2.168°|−1.721°|**54.0%**|59.8%|
|R2|B_BIAS_COV|0.948°|−0.227°|94.9%|90.4%|
|R4|B_FROZEN|1.273°|+0.195°|**55.5%**|69.9%|
|R4|B_BIAS_COV|1.366°|+0.308°|**47.6%**|62.9%|
|R5|B_FROZEN|1.146°|−0.596°|87.8%|94.3%|
|R5|B_BIAS_COV|0.802°|+0.076°|92.9%|95.8%|

R2의 4분기 마지막 245시점은 prior95 포함률 **0%**다. R4 B 원본의 2분기(186시점)는 **4.8%**, B 통계보정의 3분기(185시점)는 **0%**다. 이는 루트 전체 평균보다 중요한 **연속적인 국소 불일치**다. 단, 동일 주행의 인접 표본은 독립 추출이 아니므로 비율을 명목적인 독립 신뢰구간 검정으로 해석하지 않는다.

R2 B 원본의 prior95 최장 연속 실패는 **269표본≈53.8초**, R4 B 통계보정의 최장 실패는 **283표본≈56.6초**다. 오염된 RF가 그 시간 동안 지속됐다는 뜻은 아니며 **추정 상태가 명목 불확실성 범위를 벗어난 지속시간**이다.

그림: [R2 원본 prior 및 bias](figures/R2_B_FROZEN_prior_bias_RF.png), [R4 원본 prior 및 bias](figures/R4_B_FROZEN_prior_bias_RF.png), [R4 통계보정](figures/R4_B_BIAS_COV_prior_bias_RF.png), [포함률 비교](figures/coverage_and_bias_confidence.png).

## 3. bias 값은 실제로 어떻게 생기는가 — 코드 수준 확정 원인

코드는 과정잡음 \(Q_b=0\)을 사용한다. 예측에서는 \(\hat b_g\)와 \(P_{bb}\)가 그대로 전파된다. bias 평균이 바뀌는 유일한 코드 경로는 RF가 수용될 때의

\[
\Delta\hat b_{g,k}=K_{b,r,k}\nu_{r,k}+K_{b,s,k}\nu_{s,k}
\]

이다. 실제 6개 stream에서 **전체 bias 증분이 정확히 위 두 채널 합과 일치**했다. 이 진술은 코드 경로에 대한 사실이며, 어떤 개별 반사파가 잘못된 bias 추정의 유일 원인인지 증명하는 것은 아니다.

| B 원본|Bias 마지막 추정|마지막 보고 \(\sigma_b\)|처음/마지막 \(P_{bb}\) 비|최장 bias95 이탈|
|---|---:|---:|---:|---:|
|R2|+0.01216°/s|0.00353°/s|**804배**|**49.2초**|
|R4|−0.00382°/s|0.00449°/s|**496배**|20.2초|
|R5|−0.00489°/s|0.00342°/s|**857배**|14.0초|

시작 \(\sigma_b=0.1°/s\)에서 끝의 값으로 감소했다. **B0의 실제 bias가 0인 조건이라서 0에서 벗어난 추정은 오차**지만, 이를 RF만의 물리적인 원인으로 확정하려면 clean RF/모델 일치 관측·같은 gyro·같은 시작상태의 전체 재귀 대조가 필요하다.

**적대적 관찰:** 한 루트의 최종 bias가 작은 이유가 그 과정 전체가 정확했기 때문일 수는 없다. R2 B 원본은 range 갱신의 bias 누적 **+0.12689°/s**와 \(s\) 갱신의 누적 **−0.11473°/s**가 **상쇄**되어 최종 +0.01216°/s가 됐다. 이는 frozen 공동 gain의 대수적 분해이며, 한 채널을 끄고 재실행했을 때의 실제 인과효과는 아니다.

## 4. P와 실제 오차가 어긋나는 메커니즘

### 4.1 공분산 행렬 전파의 오류인가?

원본 상태전파 Jacobian에서 \(F_{\psi,b}=-\Delta t\)이므로

\[
P_{\psi\psi,k}^-
=P_{\psi\psi,k-1}^+-2\Delta t P_{\psi b,k-1}^+
+\Delta t^2P_{bb,k-1}^++q_{g,k}.
\]

실제 저장 P와 위 분해가 전수 일치한다. **수학적 분산 전파 코드의 단순 오류는 현재 증거로 보이지 않는다.** 또한 같은 모델 하에서 RF를 수용하면 bias 분산 \(P_{bb}\)는 보통 감소한다. \(Q_b=0\)이므로 과정에서 이를 회복시키는 항이 없다. **실제로 b가 시간에 따라 변한다면** 이 가정은 부적절하지만, B0의 센서 진짜 bias가 일정한 0이라는 사실만으로 \(Q_b=0\) 자체를 버그라고 부를 수 없다.

### 4.2 무엇이 모델 가정에 맞지 않는가?

**A. 상태로 흡수 가능한 RF 관측오차:** 실제 Full B의 FP 부근 편파왜곡은 위치·자세에 따라 달라진다. 오래 유지되는 같은 부호의 편파 편향과 위치–Heading 관측 혼동이 있을 때, 필터는 \(x,y,\psi,b_g\)를 변경해 혁신을 작게 만들 수 있다. H의 bias 직접미분은 0이지만 \(P_{b\psi},P_{bp}\) 때문에 \(K_b\neq0\)이다.

**B. 잔차의 시간상관:** 기존 \(s\) 잔차 lag-1은 R2/R4/R5 각각 약 0.913/0.674/0.875. 이번 원본 residual/standardized innovation 재계산에서도 큰 상관이 유지됐다. 모델은 반복 RF 관측의 유효 독립정보량을 지나치게 크게 가정할 수 있다. 다만 공간·heading에 따라 연속적으로 변화한 결정론적 오차와 고유 시간동역학은 **아직 분리되지 않았다**.

**C. 과신의 자기강화:** 잘못된 bias와 자세를 반영한 prior로 다시 \(h(x^-),H,R\)를 계산한다. RF 갱신이 반복되면 \(P_{bb}\), \(P_{\psi\psi}\)가 줄어들어 주어진 모델에서는 확신이 증가하지만, 실제 bias/pose는 그만큼 가까워지지 않을 수 있다. 실측 NIS가 작아도 NEES가 큰 현상과 연결될 수 있다. 이 경로가 코드를 통해 가능하다는 것은 확인됐지만 유일한 원인이라는 결론은 아니다.

**D. 관측가능성/모델 불일치:** SourceFFD의 비선형 관측값은 \(s\)가 위치와 Heading을 함께 반영하고, B의 tap 선택은 FP 부근 간섭 및 전역 peak 문턱 변화에 영향을 받는다. 경로별 Heading 민감도와 상태-편향 구별성이 달라진다. 이 메커니즘의 개별 기여는 H/P/환경 구간을 조건화한 추가 인과 대조가 필요하다.

### 4.3 단순 ‘R이 작아서’라는 원인은 증명되지 않았다

예를 들어 B 원본의 **평균 2D NIS**는 R2/R4/R5에서 약 **0.896/1.330/1.237**로 2보다 작다. 반면 R4 B 원본 prior Heading coverage는 55.5%, pose95는 약 20.8%다. \(R\) 과소설정이 유일한 원인이었다면 이 조합을 충분히 설명하지 못한다. **혁신과 실제 상태오차의 일관성 실패**이며, 평균·공분산·상관·상태 혼동이 결합할 가능성이 높다. NIS와 NEES는 서로 다른 분포량이고, 이번 시계열은 독립 표본이 아니다.

**강한 근거가 아닌 것:** R2/R4/R5 간 단일 평균 차이만으로 환경 전환 모드 존재를 선언; Qb=0만을 버그로 단정; Pxy/psi/b 각 분산만 보고 교차공분산을 무시; 기여 항 합계의 차이를 장래 비활성화 효과로 읽는 것.

## 5. 실제 진행 가능한 원인 분리 검증 계약

|번호|반증 대상|가장 작은 일관된 대조|판정 범위|
|---|---|---|---|
|E1|RF 오차가 bias 학습을 유발하는가?|동일 gyro/초기상태·동일 SourceFFD로 `z_full_B` vs `z_ideal=h(GT)+μ` vs `z_LoS_B`를 **전체 재귀** 비교|편파/탐지/모델일치 오차의 조건부 인과 대조. model-ideal은 물리적 LoS가 아님|
|E2|bias가 오차를 지탱하는가?|같은 RF로 b 자유/측정시 b-freeze/true b=0 oracle, 동일 Q·H 등 분리실행|gyro bias 흡수의 재귀적 손익; 초기 bias 회복비용도 보고|
|E3|Qb0 과신인가?|Qb=0 vs 독립 gyro calibration을 반영한 작은 Qb>0, 상태 초기오차·실제 bias ramp 별개|실제 다른 bias에서의 추적력; 단순 Qb 확대는 RF bias 흡수를 늘릴 수 있음|
|E4|시간상관/조건부 오차인가?|동일 포즈 재방문/경로 근접쌍, 공간·heading·CIR 특징 조건화 후 RF residual whiteness 재평가|공간 패턴과 독립 시간기억 구분, 유효표본수와 R 의미 결정|
|E5|선형화/상태혼동인가?|같은 prior로 GT yaw-only, XY-only, P-only, μ-only를 바꿔 h/H/gain 갱신 검증|어느 오차가 Heading과 bias 갱신을 변화시키는지 구분|
|E6|실제 heading prior 회복 가능한가?|gyro-only 초기참값/오염 초기값, 정상 RF 복귀, 향후 1/5/10/20초 재귀|좋은 RF 회복과 오래된 잘못된 기준의 의존성 구분|

사용한 truth/clean은 오직 evaluator와 oracle intervention에서만 사용한다. 새 정책 검정은 route/scene/seed를 분리하고 주행 5Hz의 코드 지연과 coverage를 확인한다. 현재 R2/R4/R5 자료는 이미 공개·분석된 단일 복도 B0·seed10이라 최종 독립검증이 아니다.

## 6. 판정: 설계의 어디가 잘못됐는가?

**확정된 프로세스:** B가 만든 range/\(s\) 잔차가 K의 gyro-bias 행으로 bias를 바꾼다 → 그 bias를 운동예측에 다시 사용한다 → Qb=0·다수 RF 갱신으로 bias 불확실성이 줄어든다. 이 세 코드 경로와 실제 값은 확인됨.

**실증된 통계적 부적합:** Heading 95% 구간의 루트별 47.6–94.9% 포함률, B0 bias 95% 구간의 59.8–95.8% 포함률, 시간상관된 RF 잔차. 명목 모델의 confidence가 모든 경로에 맞지 않는다.

**아직 확정되지 않은 원인 분배:** FP 복소간섭·tap 전환, RF/모델 평균 편향, Q/R 부적절, 누적 선형화 오류, 초기오차, 상태 식별불가 중 각각이 실험 성능에 차지하는 반사실 기여. **따라서 수학적 EKF 구조가 '버그'라고 확정하는 단계는 아니다. 오염모델과 상태-오차 해석을 충분히 표현하지 못하는 설계상 한계로 진단하는 것이 정확하다.**

**권고:** 우선 E1/E2를 독립적으로 재귀 대조해 bias 학습 경로를 확정하고, 이어 E4/E5로 오차 구조를 분리한다. 원인이 확정되기 전에 무조건 Qb·R을 키우거나 Heading 클리핑을 도입하지 않는다.

## 7. 코드 및 데이터 출처

- Original model: `research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/research/EKF4_RANGE_S_STAGED_20261014/core.py`, pinned `c141839093d1a2e4a76f91eea632cb6467163e28`.
- Original online W0: `research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/research/MBVAR_PRR_001_20261103/S1/online.py`, same pinned commit.
- Original recorded baseline: GitHub Actions [#42600632209](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209), three route archives; SHA in `AUDIT_RECEIPT.json`.
- RF Full/LoS reference: previously published `FP_DISTORTION_CHARACTERIZATION_20261109/PRIMARY_3136.csv`, SHA `59f0c0068e76215b8958f3cd62e0fbf8add183035d1d43fb0b3ce5303e4b859b`.
- Related results: [B_MCG_V1](https://github.com/myoungsunk/sionna-resimulation/tree/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/B_MCG_V1_20261109), [s–Heading feasibility](https://github.com/myoungsunk/sionna-resimulation/tree/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/B_S_HEADING_FEASIBILITY_20261110).

**이번 파일은 기존 저장 추적에 대한 감사다.**  새 RF 계산·새 폐루프 필터·실시간 하드웨어 측정은 하지 않았다.