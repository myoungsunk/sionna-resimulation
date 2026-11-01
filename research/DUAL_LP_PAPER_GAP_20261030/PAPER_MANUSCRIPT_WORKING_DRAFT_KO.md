# Dual-LP Heading 논문 작업본 v4 — Anchor B의 세 경로·12조건

2026-11-01 | 기존 자료 기반 원고 | 관측 특성 → 모델 구성 → 성능 → 한계

**범위:** `R2_aB_m0`, `R5_aB_m0`, `R4_aB_m0` 각각에 B0/L0/L1/L2를 적용한 **3경로 × 4 gyro-bias 수준 = 12조건**을 모두 사용한다. 앵커 B=(10,0,2.65) m, Mount 0°, 동일 C0 Corridor·SourceFFD 계열·Sensor-v2, sensor/initial seed 0을 유지한다. R4-B도 본문 성능표에 포함하며 결과가 약하다는 이유로 제외하지 않는다.

논문의 중심은 **관측 특성을 반영한 같은 모델이 Heading 추정에 제공하는 이득**이다. 기존 `MB_VAR/self-gate`를 설명 대상으로 선정하고, 어떤 분석이 각 구성요소를 뒷받침하는지 연결한다. 다음 내용은 기존 실험의 근거를 정리한 원고이며, 새로운 실행이나 모델 동결을 뜻하지 않는다. [이전 v3](https://github.com/myoungsunk/sionna-resimulation/blob/c52dc94230c73cfcc1562fdb68c4862a5213d25d/research/DUAL_LP_PAPER_GAP_20261030/PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md)는 Git 이력에 보존한다.

# 1. 관측 특성 분석

## 1.1. 단일 앵커에서 Heading 정보를 제공하는 관측

본 연구는 동일한 실내 복도에서 단일 앵커 B를 사용하고, 수신 안테나 장착각을 0°로 고정한 채 R2, R5, R4의 세 주행 경로를 비교한다. 앵커는 +45° 선형 편파를 송신하고, 로봇은 ±45° 두 수신 포트의 공통 first-path tap 전력으로 편파비를 계산한다.

$$
s_k=\frac{P_{+,k}-P_{-,k}}{P_{+,k}+P_{-,k}},\qquad \mathbf z_k=[r_k,s_k]^T.
$$

거리 관측만으로는 lever arm이 없는 수신기의 yaw를 단일 시점에 직접 제약하지 못하지만, 실제 FFD를 이용한 편파 관측함수는 송수신 방향과 로봇 yaw에 의존한다. 따라서 Heading에 민감한 작동점에서 $H_{s\psi}\ne0$인 편파비를 거리 관측과 함께 사용한다. 다만 Full RF의 편파비는 다중경로에 의해 LoS 응답과 달라질 수 있으므로, Heading 정보를 이용하는 것과 그 관측을 어느 정도 신뢰할 것인지를 함께 다룬다. 동일 pose의 Native LoS는 관측함수 검증과 오프라인 오차 분해에만 사용하며 실제 Full RF 필터에 정답 관측으로 공급하지 않는다. [S5]

## 1.2. Range의 구조적 오차와 편파의 잔여오차를 구분

오프라인 분석에서는 관측모델 불일치를 $\mathbf e_k=\mathbf z_k-\mathbf h(\mathbf x_k^{GT})$, 평균 보정 후 잔차를 $\boldsymbol\epsilon_k=\mathbf e_k-\hat{\boldsymbol\mu}_k$로 구분한다. CIR·근접 tap의 $\Delta s$ 특징을 사용하는 기존 EXDS 회귀는 전체 Range 오차의 조건부 평균을 예측한다. 이 예측값으로 기존 Range 평균 보정을 대체했을 때, 선정한 세 경로 모두에서 보정 후 Range 잔차의 RMS가 감소하였다. [S2, S4]

**Table 1. B0의 같은 BASE 수용집합에서 측정한 보정 후 RF 잔차**

| 경로 | 평가 패킷 수 | Range 잔차 RMS: 기존 평균 → EXDS 평균 (cm) | RMS 감소율 | 유지된 편파 잔차 평균 | 편파 잔차 RMS |
|---|---:|---:|---:|---:|---:|
| R2-B | 822 | 8.19 → 5.16 | 37.0% | +0.00744 | 0.10319 |
| R5-B | 1,236 | 8.41 → 4.63 | 44.9% | +0.00625 | 0.06490 |
| R4-B | 578 | 7.97 → 5.58 | 30.1% | −0.02382 | 0.10584 |

출처는 [S2]의 `E_eps2`, `mean_eps`이다. RMS는 $\sqrt{E[\epsilon^2]}$로 계산했으며 Range만 cm로 환산했다. 표는 **t≥30 s, fixed BASE mask의 동일 수용 패킷**에서 기존 평균과 EXDS 평균을 비교한다. 원시 Range 자체의 RMSE나 추정 위치의 XY RMSE가 아니다. 편파 평균 보정은 두 모델에서 같으므로 편파 잔차 자체도 같다.

이 결과는 세 경로에서 Range 오차를 설명하는 정보가 존재함을 보여준다. 동시에 Range 평균 보정만으로 편파 잔여오차가 제거되지는 않는다. 특히 R4-B에는 R2-B/R5-B와 다른 부호·크기의 편파 잔여 평균이 남는다. 따라서 모델은 Range 평균 처리와 편파 신뢰도 처리를 분리해서 구성한다. 단, RMS 감소가 모든 구간의 signed bias 제거 또는 최종 Heading·XY의 동시 개선을 보장하는 것은 아니다.

## 1.3. 시간·공간적으로 연속된 관측의 정보 이용

편파 잔차는 시간순으로 독립적인 백색 오차와 다른 지속성을 보였다. 같은 세 경로의 B0 전체 유한 패킷을 사용한 기존 진단에서는 아래의 자기상관이 기록되어 있다. [S3]

**Table 2. 편파 잔차의 시계열 지속성**

| 경로 | 전체 패킷 수 | lag-1 상관 | ACF가 1/e 아래로 처음 내려가는 지연 | 해당 지연에서 이동거리 중앙값 |
|---|---:|---:|---:|---:|
| R2-B | 979 | 0.8620 | 1.6 s | 0.32 m |
| R5-B | 1,415 | 0.7623 | 1.0 s | 0.20 m |
| R4-B | 742 | 0.7280 | 0.4 s | 0.08 m |

Table 2는 전체 시간축의 잔차 특성이고, Table 1은 평가구간의 고정 수용집합 통계이다. 서로 다른 분모를 합치지 않는다. 이동거리 열은 같은 시간 지연을 실제 궤적의 이동거리로 표현한 값이며, 독립적인 공간 covariance kernel을 추정한 결과가 아니다. 정적 RT 장면을 이동하며 얻은 잔차의 자기상관만으로 별도의 시간 drift를 입증할 수도 없다.

이 관찰의 설계상 의미는 **개별 패킷의 오차 크기만으로 반복 관측의 신뢰성을 판단하기 어렵다**는 점이다. 또한 혁신에는 RF 잔차뿐 아니라 prior 상태오차가 함께 들어간다.

$$
\boldsymbol\nu_k=\boldsymbol\epsilon_k+\underbrace{\big[\mathbf h(\mathbf x_k^{GT})-\mathbf h(\hat{\mathbf x}_k^-)\big]}_{\Delta\mathbf h_k}.
$$

따라서 편파 업데이트의 신뢰도를 조절하는 모델을 검토하되, 같은 시점 분산을 키우는 것과 시간·공간 상관을 정확한 joint likelihood로 모델링하는 것을 구별한다. 현재 성공 결과가 후자를 완성했다는 뜻은 아니다.

**작성 시 유의:** 관측 특성은 세 경로 각각에서 제시한다. 전체 C0의 다른 앵커·경로 요약 통계를 이 세 사례의 값으로 대체하지 않는다. `E[ε²]`는 평균이 0이 아니면 centered variance와 다르며, Table 2의 상관계수를 곧바로 상태별 유효 Fisher 정보량으로 해석하지 않는다.

# 2. 관측 특성에 근거한 모델 구성

## 2.1. Range 평균 보정과 편파 신뢰도 조절의 결합

본 연구에서 설명할 모델은 기존 4-State $\mathbf x=[x,y,\psi,b_g]^T$와 운동 예측을 유지하고, Range 평균과 편파 관측의 신뢰도만 구분하여 처리하는 `MB_VAR`이다. 모델의 구성과 근거를 다음처럼 연결한다. [S4, S6]

| 관측 분석에서 확인한 특성 | 모델 구성 | 기대하는 역할 |
|---|---|---|
| 세 경로 모두에서 CIR·Δs 기반 Range 평균 교체 후 잔차 RMS 감소 | 기존 Range 평균을 EXDS의 전체 Range 오차 평균으로 대체 | 구조적인 거리 관측오차 처리 |
| 평균 교체 뒤에도 편파 잔차가 남고 공간·기하에 따라 영향이 달라짐 | 기존 편파 분산에 거리 조건별 추가분산을 부가 | 편파 관측이 상태에 주는 신뢰도를 보수적으로 조절 |
| 순서가 있는 관측이 이후 prior·gain·수용집합을 바꿈 | 동일 운동모델 및 각 필터의 자체 NIS gate로 재귀 평가 | 한 번의 보정이 아니라 누적 추정에서의 효용 확인 |

구체적으로 평균과 관측 공분산은 다음과 같다.

$$
\hat{\boldsymbol\mu}_k^M=
\begin{bmatrix}\hat\mu_{r,k}^{EXDS}\\\hat\mu_{s,k}^{B}\end{bmatrix},\qquad
\mathbf R_k^M=\mathbf R_k^B+
\begin{bmatrix}0&0\\0&\sigma_b^2(\hat\rho_k^{lookup})\end{bmatrix}.
$$

여기서 B는 비교 기준선 `BB_ORIG`가 사용한 보정·공분산을 나타낸다. $\hat\mu_r^{EXDS}$는 **기존 CIR+Δs 특징으로 예측한 전체 Range 오차 평균의 교체값**이지, 편파 평균 또는 Heading 각도의 직접 보정값이 아니다. 편파 평균, Range 분산 및 기존 공분산의 나머지 항은 유지한다.

기존 구현은 다음의 경험적 표를 선형 보간하여 $\sigma_b$를 조회한다.

| 수평 거리 ρ (m) | 0 | 1.5 | 3 | 6 | 10 |
|---|---:|---:|---:|---:|---:|
| 추가 편파 표준편차 σ_b | 0.011 | 0.020 | 0.050 | 0.120 | 0.240 |

같은 함수형·표·gate 기준을 세 경로와 네 bias 수준에 모두 사용한다. 이는 관측된 특성에 대응하는 **경험적 설계**이지, Table 1/2에서 유일하게 유도되는 최적 covariance는 아니다. 해당 표는 기존 mount0/B0 통계·시험에서 정한 in-sample 설정이다. 경로별 보정값은 보존된 학습·예측 자료를 사용하므로 ‘동일 구조·하이퍼파라미터’와 ‘모든 경로에 완전히 같은 학습 가중치’도 구별한다. [S6, S7]

## 2.2. 실제 실행과 일치하는 재귀 갱신

갱신은 각 필터의 상태와 공분산에서 계산한 혁신을 사용한다.

$$
\boldsymbol\nu_k=\mathbf z_k-\mathbf h(\hat{\mathbf x}_k^-)-\hat{\boldsymbol\mu}_k^M,\qquad
\mathbf S_k=\mathbf H_k\mathbf P_k^-\mathbf H_k^T+\mathbf R_k^M,
$$
$$
\mathbf K_k=\mathbf P_k^-\mathbf H_k^T\mathbf S_k^{-1},\qquad
\hat{\mathbf x}_k^+=\hat{\mathbf x}_k^-+\mathbf K_k\boldsymbol\nu_k.
$$

공동 NIS가 9.210340371976184 이하인 유한 패킷을 수용하고, 수용 시 Joseph 형태로 공분산을 갱신한다. Heading은 wrap 처리한다. 실제 코드에서 거리별 추가분산은 **해당 motion prediction 이전에 보유한 상태**로 조회한다. 원고에서 이를 현재 predicted prior의 거리로 바꾸어 적지 않는다. 기존 예측 평균을 불러오는 재생과 새 환경에서의 온라인 회귀 실행도 별도의 검증 범위이다. [S4]

**시간·공간 특성과의 연결:** 추가분산은 반복되는 편파 정보에 대한 갱신 강도를 줄이는 실용적 수단으로 해석할 수 있으나, 현재 구현은 시점 간 covariance를 포함하지 않는다. 따라서 ‘상관오차를 정확히 제거한 필터’가 아니라 **잔여 관측오차에 대한 경험적 신뢰도 조절을 결합한 EKF**로 기술한다. 공간·시간 정보 중복의 정량적 설명은 이 설계의 이유를 검증하는 핵심 분석이며, 아직 검증되지 않은 인과관계를 이미 입증된 것처럼 쓰지 않는다.

# 3. 동일 모델의 세 경로·12조건 성능

## 3.1. 비교 조건과 전체 결과

주 비교는 `BB_ORIG/self` 대 `MB_VAR/self`이다. **BB_ORIG는 기존 POWER 계열 보정 기준선이며 고정 R0 Conventional J4가 아니다.** 두 모델의 전체 주행을 t=0부터 재귀 계산한 기존 결과에서 t≥30 s의 오차를 사용한다. 세 경로 모두 B0=0, L0=+0.01, L1=+0.05, L2=+0.20 °/s의 bias 조건을 포함하며, 모두 동일 sensor/initial seed 0이다. [S1, S4]

**Table 3. 12조건 전체 — Heading 및 XY RMSE**

| 경로 | Bias | Heading 기준 → 결합 (°) | Heading 감소율 | XY 기준 → 결합 (cm) | XY 감소율 |
|---|---|---:|---:|---:|---:|
| R2-B | B0 | 1.2047 → 1.0847 | 9.96% | 6.83 → 5.33 | +21.92% |
| R2-B | L0 | 1.1843 → 1.0572 | 10.73% | 6.75 → 5.22 | +22.72% |
| R2-B | L1 | 1.1123 → 0.9675 | 13.01% | 6.48 → 4.91 | +24.18% |
| R2-B | L2 | 0.9467 → 0.8133 | 14.08% | 5.77 → 4.30 | +25.58% |
| R5-B | B0 | 1.0731 → 0.6434 | 40.05% | 8.69 → 4.46 | +48.72% |
| R5-B | L0 | 1.0462 → 0.6346 | 39.34% | 8.52 → 4.45 | +47.75% |
| R5-B | L1 | 0.9428 → 0.6023 | 36.12% | 7.84 → 4.45 | +43.24% |
| R5-B | L2 | 0.7156 → 0.6153 | 14.02% | 6.09 → 4.65 | +23.68% |
| R4-B | B0 | 1.4418 → 1.4312 | 0.74% | 8.54 → 9.43 | −10.50% |
| R4-B | L0 | 1.4388 → 1.4271 | 0.82% | 8.54 → 9.45 | −10.67% |
| R4-B | L1 | 1.4267 → 1.4097 | 1.19% | 8.52 → 9.45 | −10.89% |
| R4-B | L2 | 1.3938 → 1.3584 | 2.54% | 8.53 → 9.54 | −11.80% |

감소율은 원 CSV의 반올림 전 표시값으로 $100(1-\mathrm{RMSE}_{MB\_VAR}/\mathrm{RMSE}_{BB\_ORIG})$를 계산한 것이다. 양수는 개선, 음수는 악화이다. 패킷을 합친 pooled RMSE 또는 시드 평균이 아니다.

### 논문 결과 문장

> Range 평균 보정과 편파 신뢰도 조절을 결합한 동일한 EKF 구성은 Anchor B·Mount 0°에서 R2, R5, R4의 네 gyro-bias 수준 모두에 대해 기존 보정 기준선보다 낮은 Heading RMSE를 보였다. Heading 감소율은 R2에서 9.96–14.08%, R5에서 14.02–40.05%, R4에서 0.74–2.54%였다. 따라서 선정한 12조건에서 Heading 개선의 방향은 일관되었으나 효과의 크기는 경로에 따라 달랐다. XY 오차는 R2와 R5의 8조건에서 21.92–48.72% 감소한 반면, R4의 4조건에서는 10.50–11.80% 증가하였다.

**12/12는 Heading 감소를 관측한 조건 수이며, Heading·XY 동시 개선은 8/12이다.** 이전 두 경로의 동시 개선 주장을 R4까지 그대로 확대하지 않는다. R4의 작은 차이에 통계적 유의성·실용적 우월성이 입증됐다는 의미도 부여하지 않는다.

## 3.2. 구성요소의 기여: 같은 자료의 최소 ablation

**Table 4. B0 대표 비교 — Heading ° / XY cm, 모두 self-gate**

| 경로 | 기준 BB_ORIG | 평균만 교체 MB_ORIG | 분산만 추가 BB_VAR | 평균+분산 MB_VAR |
|---|---:|---:|---:|---:|
| R2-B | 1.205 / 6.83 | 1.616 / 6.80 | 1.122 / 7.54 | **1.085 / 5.33** |
| R5-B | 1.073 / 8.69 | 0.825 / 5.78 | 0.967 / 8.65 | **0.643 / 4.46** |
| R4-B | 1.442 / 8.54 | 1.656 / 11.85 | **1.323 / 7.12** | 1.431 / 9.43 |

R2와 R5에서는 결합 모델이 단독 평균 변경 또는 단독 분산 추가보다 Heading·XY 모두 낮다. 이 결과는 두 요소를 함께 사용하는 설계의 경험적 근거다. 반면 R4에서는 분산만 추가한 모델이 결합 모델보다 두 지표 모두 우수하다. 따라서 **결합 모델이 기존 기준선보다 Heading을 줄였다**는 결과와 **결합 모델이 모든 후보 중 최선이다**라는 주장은 구별한다. 후자는 현재 세 경로 전체에서 성립하지 않는다. [S1]

동일 모델을 비교하기 위해 R4에서만 BB_VAR로 바꾸어 성능표를 완성하지 않는다. 또한 각 arm의 자체 gate를 사용했으므로 ablation에는 이후 수용집합·상태·공분산 변화가 함께 포함된다. 이는 구성 변경에 따른 end-to-end 효과이지 한 항의 독립적 인과기여율은 아니다.

**최종 비교군:** DR, 고정 R0의 단일 앵커 Conventional EKF, ≥3-anchor Range-only EKF와의 동일 설정 비교는 별도 증거가 필요하다. 현재 표를 이 비교군 대비 우위로 이름만 바꾸어 사용하지 않는다.

# 4. 관측 특성에 근거한 한계와 적용 범위

## 4.1. R4-B에서 Heading 개선이 작고 XY가 악화하는 이유

R4-B는 본문에서 제외할 실패 사례가 아니라, **동일 모델의 효과가 제한되는 조건**을 보여준다. Section 1의 분석과 연결하면 다음까지 설명할 수 있다.

첫째, EXDS 평균 교체는 R4-B에서도 Range 잔차 RMS를 7.97 cm에서 5.58 cm로 줄였으나(Table 1), 평균만 바꾼 재귀 모델의 B0 XY RMSE는 8.54 cm에서 11.85 cm로 커졌다(Table 4). 즉 관측 Range 잔차의 감소가 위치 상태오차 감소로 바로 이어지지 않는다. 원시 RF 오차, 평균보정 후 잔차, 최종 상태오차가 서로 다른 대상이라는 구분이 필요하다.

둘째, Range 평균 보정은 R4-B의 편파 잔여 평균 −0.02382를 변경하지 않는다. 이는 R2-B의 +0.00744, R5-B의 +0.00625와 다르다. 현재 모델의 편파 분산 추가는 관측의 가중치를 바꾸지만 **편파 평균을 직접 제거하지 않는다.** 남은 편향과 상태결합이 위치 갱신에 영향을 줄 가능성을 제시하되, 이 부호 차이 하나를 유일 원인으로 단정하지 않는다.

셋째, 기존 혁신 분해는 R4-B의 prior-state 오차가 보고된 관측공간 분산보다 크게 남아 있음을 보여준다. B0·fixed BASE mask의 같은 패킷에서 다음 두 진단량을 비교한다. [S2]

$$
A_s=\frac{E[\epsilon_s^2]}{E[R_{ss}]},\qquad
D_s=\frac{E[(\Delta h_s)^2]}{E[(\mathbf H\mathbf P^-\mathbf H^T)_{ss}]}.
$$

| 경로 | A_s: 기준 → 결합 | D_s: 기준 → 결합 |
|---|---:|---:|
| R2-B | 0.517 → 0.326 | 2.803 → 1.261 |
| R5-B | 0.163 → 0.109 | 2.144 → 0.577 |
| R4-B | 0.897 → 0.544 | 20.956 → 11.572 |

R4-B는 편파 관측분산을 키운 뒤에도 prior-state 오차의 관측공간 투영과 예측 공분산 사이의 차이가 크다. 따라서 ‘편파 잡음분산을 충분히 늘리면 모든 상태오차가 해결된다’는 설명은 적절하지 않다. 이 표는 **fixed-mask 진단**이고 Table 3은 **self-gate 성능**이므로 직접적인 일대일 인과 증명이 아니라, 같은 원자료에서 해석을 뒷받침하는 별도 진단으로 사용한다. $D_s$를 state NEES로 부르지 않는다.

Table 2에서 R4-B의 편파 자기상관은 세 경로 중 가장 낮지만 Heading 이득 역시 가장 작다. 따라서 단일 lag-1 값이나 상관 길이 하나만으로 개선량을 설명할 수 없다. 기하 민감도·잔여 평균·prior 상태·수용 이력의 상호작용은 추가 구분이 필요하다. Table 4가 입증한 범위는 **R4-B에서는 평균 교체를 함께 넣는 것이 분산만 조절하는 것보다 불리하다**는 구성 수준의 결과이며, 세부 물리 원인이 모두 확정된 것은 아니다.

## 4.2. 점추정의 개선과 불확실성 신뢰도의 차이

Heading RMSE가 낮아져도 보고된 covariance가 정확해졌다는 뜻은 아니다. 예를 들어 R4-B B0의 자체 gate 결과에서 nominal 95% Heading 구간의 실제 포함률은 기준 20.61%, 결합 모델 19.93%에 그쳤다. XY 포함률 역시 53.21%에서 52.53%였다. 따라서 이 모델의 12조건 Heading 감소를 **12조건의 불확실성 calibration 성공**으로 확대하지 않는다. [S1]

또한 현재 편파 추가분산은 cross-time covariance나 잔차의 r–s 결합을 새로 학습한 모델이 아니다. 관측오차의 시간·공간 연속성과 결합 구조는 Section 1에서 분석하지만, 현재 구현으로 완전히 해결되었다고 주장하지 않는다.

## 4.3. 공간·시드·학습 범위의 한계

주장은 **같은 Corridor, Anchor B, Mount 0°, 기존 seed 0의 세 경로·네 bias 조건**으로 제한한다. 네 bias 수준은 같은 경로의 RF 패킷을 재사용하므로 12개의 독립 환경이 아니다. 분산표 역시 기존 mount0/B0 자료에 의존해 선택됐으며, 독립 holdout에서 검증한 최적 모델이 아니다. 관측 특성에 따른 설명 순서와 실제 연구의 사후 분석 이력은 구분한다. [S6, S7]

다른 초기화에서 R5-B의 큰 오차가 보고된 사실과, 앵커 A에서 같은 종류의 보정이 재귀적으로 악화한 기록은 이 성공 범위의 외삽 한계로 남긴다. 따라서 ‘같은 종류의 관측 보정인데 왜 어떤 조건에서는 이득이 유지되고 다른 조건에서는 무너지는가’는 **본 성공 모델의 적용 범위를 설명하는 후속 한계 질문**으로 다룬다. 본문을 실패 원인 목록으로 확장하거나, 이 결과를 제외하기 위해 주 12조건의 구성을 바꾸지 않는다. [S7, S8]

---

## 데이터 위치와 계산 추적

아래 `6c7200091028fd3f0e55aa83b777d0f10b7cf063`은 읽은 근거 스냅샷이다. 각 실험의 실행 source SHA·입력 hash·run ID는 해당 보고서의 provenance를 따른다. 새 EKF/RT 실행은 수행하지 않았으며, 이번 수치 계산은 저장된 CSV의 RMS 변환·조건별 감소율·개선 개수 확인에 한정된다.

- **S1 — 전체 성능·ablation·coverage:** [D2_GATE_SCORES.csv](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv). Git blob `efe55ff9b13b6c6c70f2820e26bacc88ca460d26`. `case∈{R2_aB_m0,R5_aB_m0,R4_aB_m0}`, `bias∈{B0,L0,L1,L2}`, `gate=self`, `arm∈{BB_ORIG,MB_VAR}`를 비교한다. Table 4는 B0에 `MB_ORIG,BB_VAR`도 포함한다. Heading/XY 점수 열은 `head_rmse,xy_rmse_cm`이다.
- **S2 — 보정 후 RF 잔차와 혁신 분해:** [D3_DECOMPOSITION.csv](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D3_DECOMPOSITION.csv). Blob `721ea9f3db5d70d11b546d75ae94d29fe381c4ae`. B0의 같은 fixed mask에서 Table 1은 `comp=r,E_eps2`의 BB_ORIG/MB_ORIG와 `comp=s,mean_eps,E_eps2`를 사용한다. Section 4.1은 `comp=s,ratio_eps2_R,ratio_dh2_HPH`의 BB_ORIG/MB_VAR를 사용한다.
- **S3 — 동일 세 경로의 시간순 잔차:** [D3_EPS_TEMPORAL.csv](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D3_EPS_TEMPORAL.csv). Blob `b10088a0bd83b61a7846adf3757ea98fb156e5ae`. Table 2는 `background=MB,comp=s`의 `lag1_r,acf_1e_s,acf_1e_m,n`을 사용한다. BB와 MB의 편파 평균이 같아 s 잔차 특성도 같다.
- **S4 — 실행 정의:** [diag_mbvar.py](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code/diag_mbvar.py), [exp_pb.py](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py), [EXDS가 Range 평균 교체임을 정의한 X1 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/x1/RESULTS_KO.md). 문서의 수식은 코드의 거리 조회 시점·fixed/self 구분·평가 mask를 보존한다.
- **S5 — RF·LoS 관측과 데이터 계열:** [BLOCK_C Full/LoS 원본](https://github.com/myoungsunk/sionna-resimulation/tree/6c7200091028fd3f0e55aa83b777d0f10b7cf063/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C), [SourceFFD 검증](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md). 선택한 세 case의 H·SAMPLES와 기존 timeline을 대응시킨다. 원 H의 바이트 검증을 이번 문서 작성에서 새로 수행한 것은 아니다.
- **S6 — 동일 모델의 파라미터·개발 범위:** [PROTOCOL_PB.md](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/PROTOCOL_PB.md). 경험적 분산표의 in-sample 성격과 원래 fixed-mask 계약을 확인한다. Table 3의 self-gate 결과는 후속 S1/S4에서 읽는다.
- **S7 — 통계 정의·일반화·Gate:** [MB_VAR 모델링 전 진단](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/README_KO.md). 전체 경로 통계를 선택한 세 경로의 통계로 바꾸어 쓰지 않는다.
- **S8 — 정정 및 초기상태 한계:** [E2/E5 재검증과 R5-B 초기상태 교차](https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_e2_e5_revalidation_20261029/README_KO.md). 이전 잘못된 정보행렬 정규화에 근거한 해석은 사용하지 않는다.

**개정 범위:** 기존 원고 문서 한 개만 수정한다. 원 RF·기존 실행 결과·코드·동결 계약은 변경하지 않는다. 이번 12조건의 Heading 개선은 저장된 수치에 대한 확인이지, 신규 실험·독립 감사·최종 모델 승인에 해당하지 않는다.
