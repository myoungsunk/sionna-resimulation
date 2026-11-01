# Dual-LP 물리 관측과 관측 신뢰도 조절을 이용한 단일 앵커 4상태 EKF — 논문 작업 초안

**초안 범위:** R2-B, R4-B, R5-B × B0/L0/L1/L2 = 12조건. 기존 C0 Corridor, Anchor B, Mount 0°, 동일 RF 및 센서 seed 0. **자료의 성격:** 기존 자료의 회고적 재현 결과; 새로운 RT·온라인 학습·외부 환경 확증 없음. 구성은 요청에 따라 **물리 관측 → 물리 관측에 근거한 모델 → 결과**의 세 부분으로 제한한다.

## 1. 물리 관측: Dual-LP의 방향 민감도와 잔여 관측오차

단일 앵커의 거리 관측은 동일 시점에서 로봇의 평면 회전각을 직접 측정하지 못한다. 본 연구는 송신 안테나의 +45° 선형편파와 로봇에 설치한 ±45° 직교 선형편파 수신 포트를 이용해, 앵커와 로봇의 상대 위치 및 방향에 따른 차등 안테나 응답을 추가 관측으로 구성한다. 각 포트의 복소 원거리 전계 패턴(Far-Field Distribution, FFD)을 송수신 기하에 맞게 변환하여 주파수별 응답을 계산하고, 이를 채널 임펄스 응답(Channel Impulse Response, CIR)으로 변환한다. 기존 관측기는 두 수신 포트 중 최대 응답이 큰 포트를 기준으로 30% leading-edge의 첫 경로 tap을 선택하고, **같은 tap 인덱스**에서 두 포트의 전력을 평가한다. 이때 거리 관측과 signed 정규화 편파비는 다음과 같다.

\[
\mathbf z_k=\begin{bmatrix}r_k&s_k\end{bmatrix},\qquad
P_{\pm,k}=|g_{\pm,k}(n_{0,k})|^2,\qquad
s_k=\frac{P_{+,k}-P_{-,k}}{P_{+,k}+P_{-,k}}.
\tag{1}
\]

편파비는 두 포트에 동일하게 작용하는 복소 스칼라 변화에는 불변이지만, 입사방향·로봇 회전에 따른 차등 응답이나 다중경로의 포트별 복소 중첩에는 영향을 받는다. SourceFFD 기반 직접경로 관측함수 \(h_s(\mathbf x)\)를 사용하면, 검출 tap과 보간 branch가 유지되는 구간에서 상태변수 \(u\in\{x,y,\psi\}\)에 대한 민감도는

\[
\frac{\partial h_s}{\partial u}=
\frac{2\left(P_-\,\partial_u P_+-P_+\,\partial_u P_-\right)}
{(P_++P_-)^2}
\tag{2}
\]

로 주어진다. 따라서 거리 관측의 순간 Heading 미분은 0이지만, 편파 관측의 \(H_{s\psi}\)는 일반적으로 0이 아니다. 한편 \(H_{sx},H_{sy}\)도 존재하므로 편파비는 독립적인 순수 각도센서가 아니라 **위치와 Heading이 결합된 물리 관측**이다. 이는 4상태 전체의 단일 packet 관측가능성을 증명하는 식은 아니다.

실제 Full 채널에서 얻은 관측과 직접경로 기반 \(h(\mathbf x^{GT})\)의 차이를 분석하여, 전파·검출·관측모델 불일치가 추정기에 남기는 영향을 확인하였다. 평균모형 \(a\)를 적용한 오프라인 잔차를 \(\boldsymbol\epsilon_k^{(a)}=\mathbf z_k^{Full}-\mathbf h(\mathbf x_k^{GT})-\boldsymbol\mu_k^{(a)}\)로 정의한다. B0의 **동일한 BASE 고정 수용집합**에서 기존 거리 평균을 EXDS 평균으로 교체하면, R2-B, R5-B, R4-B 모두 거리 잔차 RMS가 감소하였다. 반면 편파 평균모형은 유지되므로, 편파 잔차는 그대로 남았다.

**표 1. B0, 평가구간(t≥30 s)의 동일 BASE 수용집합에서의 관측 잔차**

| 경로 | 수용 packet | 거리 잔차 RMS: 기존 → 평균 교체 (cm) | 평균 교체 뒤 편파 잔차 평균 | 편파 잔차 RMS |
|---|---:|---:|---:|---:|
| R2-B | 822 | 8.19 → 5.16 | +0.00744 | 0.10319 |
| R5-B | 1,236 | 8.41 → 4.63 | +0.00625 | 0.06490 |
| R4-B | 578 | 7.97 → 5.58 | −0.02382 | 0.10584 |

편파의 상태 민감도와 잔차 크기는 동일하지 않았다. 별도의 **게이트 비선택 t≥30 s 표본**에서 \(|H_{s\psi}|\)의 중앙값은 R2-B 0.461, R5-B 0.405, R4-B 1.775 rad\(^{-1}\)였고, 평균 교체 후 편파 잔차 RMS는 각각 0.107, 0.093, 0.123이었다. 이 수치는 표 1과 표본집합이 다르므로 한 행의 동일 packet 통계로 취급하지 않는다. 특히 R4-B는 Heading 민감도가 작아서 개선이 미미했다는 설명에 부합하지 않는다. Heading 오차로의 실제 전달은 민감도뿐 아니라 잔차의 부호, 사전 상태오차, 공분산 및 Kalman gain에 의해 결정된다.

또한 B0 전체 시간축에서 편파 잔차의 lag-1 자기상관은 R2-B 0.8620, R5-B 0.7623, R4-B 0.7280으로 나타났다. 이는 이동 로봇이 정적 RF 장면의 공간적으로 연속된 오차를 시간순으로 관측할 수 있음을 보여준다. 그러나 단일 정적 장면의 주행기록만으로 독립적인 시간 drift 또는 전역 공간 covariance kernel을 식별할 수는 없다. 본 연구는 이 특성을 **관측 신뢰도 조절의 동기**로 사용하며, 시간 간 상관을 완전히 제거한 관측모델을 구성했다고 주장하지 않는다.

## 2. 물리 관측에 근거한 4상태 Joint EKF 모델

로봇의 상태는 \(\mathbf x_k=[x_k,y_k,\psi_k,b_{g,k}]^T\)로 정의한다. 휠 오도메트리와 자이로 입력으로 \((\hat{\mathbf x}_k^-,\mathbf P_k^-)\)를 예측하고, 거리와 Dual-LP 편파비를 공동 갱신한다. 기존 물리 관측함수 \(\mathbf h(\mathbf x)=[h_r(\mathbf x),h_s(\mathbf x)]^T\)와 Jacobian \(\mathbf H_k=\partial\mathbf h/\partial\mathbf x|_{\hat{\mathbf x}_k^-}\)를 유지한다. 직접경로 SourceFFD가 편파비의 위치·Heading 의존성을 제공하며, 기존 거리 예측은 원래 구현의 **연속 기하거리 bridge**를 보존한다. 따라서 저장된 정수 first-edge 거리의 완전한 이산 확률우도를 새로 식별한 것으로 해석하지 않는다.

표 1에서 확인한 관측오차의 역할을 분리하기 위해, 기존 기준선 \(BB_{\rm ORIG}\)의 평균 \(\boldsymbol\mu_k^B\)와 관측공분산 \(\mathbf R_k^B\)에서 다음 두 개입을 정의한다.

\[
\boldsymbol\mu_k^M =
\begin{bmatrix}
\hat\mu_{r,k}^{\mathrm{EXDS}}\\
\hat\mu_{s,k}^{B}
\end{bmatrix},\qquad
\mathbf R_k^M=\mathbf R_k^B+
\begin{bmatrix}0&0\\0&\sigma_b^2(\rho_k^{\rm lookup})\end{bmatrix}.
\tag{3}
\]

첫 번째 개입은 기존 CIR 및 인접 tap 편파 특징을 사용해 저장된 **거리 관측오차의 조건부 평균 예측값**을 교체한다. 여기서 인접 tap의 \(\Delta s\)는 거리 평균을 예측하는 특징이며 **EKF에 독립적으로 추가된 세 번째 관측이 아니다**. 두 번째 개입은 편파 평균을 바꾸지 않은 채, 물리적으로 Heading에 민감한 편파 관측이 상태 갱신에서 차지하는 신뢰도를 조절한다. 기존 관측공분산의 다른 항과 운동모델은 유지된다.

추가 편파 표준편차는 수평거리 \(\rho=\|[x,y]^T-[x_a,y_a]^T\|\)에 대해, \(0,1.5,3,6,10\) m에서 각각 \(0.011,0.020,0.050,0.120,0.240\)으로 정의한 경험적 표를 선형 보간한다. 실제 구현에서 \(\rho_k^{\rm lookup}\)는 **현재 패킷의 운동 예측 이전에 저장된 상태**에서 조회한다. 이 표는 포트별 FFD에서 유일하게 유도한 물리 noise covariance가 아니라, 기존 개발 자료를 이용해 정한 **거리 조건부 추가분산**이다. 모든 선택 경로·gyro-bias 조건에는 같은 표와 필터 구조를 사용한다.

갱신 과정은 다음과 같다.

\[
\begin{aligned}
\boldsymbol\nu_k&=\mathbf z_k-\mathbf h(\hat{\mathbf x}_k^-)-\boldsymbol\mu_k^M,\\
\mathbf S_k&=\mathbf H_k\mathbf P_k^-\mathbf H_k^T+\mathbf R_k^M,\qquad
\mathbf K_k=\mathbf P_k^-\mathbf H_k^T\mathbf S_k^{-1},\\
\hat{\mathbf x}_k^+&=\hat{\mathbf x}_k^-+\mathbf K_k\boldsymbol\nu_k.
\end{aligned}
\tag{4}
\]

수용된 packet의 공분산은 Joseph 형태로 갱신하고 Heading은 wrap 처리한다. 실제 성능 비교에는 각 arm의 자체 공동 NIS gate(2차원, 임계값 9.21034)를 적용한다. 원본 BB 기준선은 이미 기존의 평균·분산 보정을 사용하는 Joint EKF이며, 고정 \(R_0\)의 conventional EKF와 동일한 비교군으로 명명하지 않는다.

이 모델에서 **물리 기반 부분**은 실제 복소 FFD와 기하를 반영한 \(h_s,\mathbf H\)이고, **경험 기반 부분**은 EXDS 평균 교체와 \(\sigma_b(\rho)\)에 의한 신뢰도 조절이다. 동일한 prior와 Jacobian을 고정하면 편파 추가분산은 편파 관측의 Kalman-gain 열을 축소하지만, 그 과정에서 원하지 않는 모델오차 갱신과 필요한 상태오차 교정이 함께 감소할 수 있다. 이를 보이기 위해

\[
\boldsymbol\nu_k=
\underbrace{\mathbf z_k-\mathbf h(\mathbf x_k^{GT})-\boldsymbol\mu_k}_{\boldsymbol\epsilon_k}
+
\underbrace{\mathbf h(\mathbf x_k^{GT})-\mathbf h(\hat{\mathbf x}_k^-)}_{\delta\mathbf h_k},
\qquad
\Delta\mathbf x_k=\mathbf K_k\boldsymbol\epsilon_k+\mathbf K_k\delta\mathbf h_k
\tag{5}
\]

로 분해하였다. 이 식은 동일-prior shadow 갱신에서 거리와 편파의 **signed** 기여를 기록하기 위한 대수적 분해다. 실제 재귀 필터에서는 이전 관측이 다음 prior·공분산·gate를 변경하므로, (5)의 한 시점 개선이 최종 RMSE 감소를 보장하지 않는다. 현재의 \(\mathbf R_k^M\)은 시점 간 covariance나 잔여 편향의 동역학을 직접 모델링하지 않는다.

## 3. 결과: 관측오차 처리의 구성 효과와 경로별 적용 범위

동일 C0 Corridor에서 Anchor B=(10,0,2.65) m, Mount 0°인 R2-B·R5-B·R4-B를 평가하였다. 자이로 bias 수준은 B0=0, L0=+0.01, L1=+0.05, L2=+0.20 °/s이고 센서·초기화 seed는 동일하다. 각 설정을 주행 처음부터 재귀 계산하고 \(t\ge30\) s의 전체 평가 시점에서 Heading·XY RMSE를 구했다. 모두 **하나의 RF 장면에서 반복한 12조건**이며 독립적인 물리 환경 12개는 아니다.

**표 2. 선택한 12조건의 기존 BB_ORIG와 결합 MB_VAR (각 arm의 self-gate)**

| 경로 | Gyro bias | Heading RMSE: BB → MB (°) | XY RMSE: BB → MB (cm) |
|---|---|---:|---:|
| R2-B | B0 | 1.2047 → 1.0847 | 6.8269 → 5.3303 |
| R2-B | L0 | 1.1843 → 1.0572 | 6.7535 → 5.2194 |
| R2-B | L1 | 1.1123 → 0.9675 | 6.4821 → 4.9149 |
| R2-B | L2 | 0.9467 → 0.8133 | 5.7717 → 4.2952 |
| R5-B | B0 | 1.0731 → 0.6434 | 8.6882 → 4.4551 |
| R5-B | L0 | 1.0462 → 0.6346 | 8.5193 → 4.4517 |
| R5-B | L1 | 0.9428 → 0.6023 | 7.8384 → 4.4488 |
| R5-B | L2 | 0.7156 → 0.6153 | 6.0882 → 4.6468 |
| R4-B | B0 | 1.4418 → 1.4312 | 8.5363 → 9.4325 |
| R4-B | L0 | 1.4388 → 1.4271 | 8.5382 → 9.4491 |
| R4-B | L1 | 1.4267 → 1.4097 | 8.5178 → 9.4454 |
| R4-B | L2 | 1.3938 → 1.3584 | 8.5319 → 9.5383 |

선정한 12조건 모두에서 MB_VAR의 Heading RMSE가 BB_ORIG보다 낮았다. 감소율은 R2-B 9.96–14.08%, R5-B 14.02–40.05%, R4-B 0.74–2.54%였다. 반면 XY RMSE는 R2-B·R5-B의 8조건에서 21.92–48.72% 감소했으나, R4-B의 4조건에서는 10.50–11.80% 증가했다. **Heading 개선 12/12와 Heading·XY 동시 개선 8/12를 구분**하며, R4-B의 작은 차이를 통계적으로 유의한 개선으로 해석하지 않는다.

평균 교체와 추가분산의 역할을 분리하기 위해 B0에서 네 모델을 비교하였다. BB_ORIG는 기존 평균·분산, MB_ORIG는 거리 평균만 교체, BB_VAR는 편파 추가분산만 적용, MB_VAR는 둘을 결합한 설정이다.

**표 3. B0, 구성요소 및 상수분산 대조 (Heading ° / XY cm, self-gate)**

| 경로 | BB_ORIG | MB_ORIG | BB_VAR | MB_VAR | MB_CONST |
|---|---:|---:|---:|---:|---:|
| R2-B | 1.205 / 6.83 | 1.616 / 6.80 | 1.122 / 7.54 | **1.085 / 5.33** | 1.625 / 10.77 |
| R5-B | 1.073 / 8.69 | 0.825 / 5.78 | 0.967 / 8.65 | **0.643 / 4.46** | 1.429 / 12.53 |
| R4-B | 1.442 / 8.54 | 1.656 / 11.85 | **1.323 / 7.12** | 1.431 / 9.43 | **1.137 / 5.49** |

R2-B와 R5-B에서는 결합모델이 단독 평균 교체와 단독 분산 추가보다 Heading·XY 모두 낮았다. 반면 R4-B에서는 분산만 추가한 BB_VAR가 MB_VAR보다 두 지표 모두 우수하였다. 더 나아가 분산만 추가한 BB_VAR도 선택한 12조건 모두에서 기준선보다 Heading을 낮추므로, **12/12 개선이라는 빈도만으로 평균 교체의 추가 기여가 증명되는 것은 아니다.** 결합 모델의 가치는 R2-B·R5-B에서 단독 개입보다 추가로 얻는 성능과, R4-B에서 확인된 부정적인 상호작용을 함께 통해 평가해야 한다.

같은 BB prior에서 계산한 평균×분산 2×2 shadow 갱신에서는 R2-B·R5-B의 8조건 모두에서 **조건별 평균 즉시 Heading MSE가 평균-only 설정에서 더 작았다.** 그러나 전체 재귀 Heading RMSE는 결합 MB_VAR가 더 작았다. 따라서 최종 개선을 추가분산이 매 packet의 방향오차를 즉시 감소시킨 결과라고 설명할 수 없다. 동일 prior에서 평균 교체는 innovation을, 추가분산은 gain과 posterior covariance를 바꾸며, 이러한 차이는 이후의 상태·공분산·관측 수용 이력을 따라 누적된다. 다만 개별 구간의 최종 개선 기여율은 별도 누적인과 실험을 수행하지 않았으므로 확정하지 않는다.

추가분산의 **거리 조건 자체**가 유효한지 확인하기 위해, 평가 경로를 제외한 다른 두 경로의 B0 자료에서 미리 정한 상수 추가분산 MB_CONST와 기존 lookup을 비교하였다. MB_VAR의 거리 lookup은 R2-B·R5-B의 8조건에서 상수보다 Heading·XY 모두 낮았지만, R4-B의 4조건에서는 상수가 더 낮았다. B0에서 R4-B의 MB_CONST는 1.1369° / 5.4898 cm로 MB_VAR의 1.4312° / 9.4325 cm보다 우수하였다. fixed-mask에서도 같은 우열이 나타났으므로, 이 차이를 수용 packet 집합 변화만으로 설명할 수 없다. 그러나 각 필터의 재귀 prior는 서로 달라지므로 이것이 전체 인과효과의 완전한 분해는 아니다. 특히 본 연구가 사용하는 상수는 최적화된 상수도 아니며, 거리 lookup의 **보편적 우월성**은 지지되지 않는다.

R4-B의 약한 Heading 이득과 XY 악화는 관측 민감도와 상태 추정 정확도의 차이를 보여준다. R4-B는 세 경로 중 true-pose 편파 Heading 민감도가 가장 크고, 거리 평균 교체로 잔차 RMS도 감소했지만 최종 XY는 악화했다. 잔여 편파 평균, 상태오차가 관측공간에 투영되는 정도, 이중 관측의 gain, 수용 이력은 모두 가능한 영향 경로이나 **어느 하나가 R4-B 악화의 단일 원인이라고 검증한 것은 아니다**. 현재 자료에서 확정할 수 있는 것은 이 경로의 결합모델이 분산 단독 모델보다 불리하다는 점이다.

마지막으로 점추정 오차 감소를 불확실성 교정으로 확대하지 않는다. 예를 들어 R4-B/B0의 자체 gate에서 Heading의 명목 95% 포함률은 기준 20.61%, 결합 19.93%, XY 포함률은 각각 53.21%와 52.53%였다. 또한 세 경로와 네 gyro 조건은 동일한 정적 RF 장면과 seed를 공유하고, 거리 추가분산은 기존 개발 자료에서 선택되었으며, 저장 평균 예측값의 계보는 재현됐지만 학습 회귀기의 새로운 입력에 대한 fresh inference는 검증되지 않았다. 따라서 이 결과는 **선택한 12조건에서 물리 기반 Dual-LP 관측을 경험적으로 가중하는 방식의 효과와 한계**를 보여주며, 독립 환경으로의 일반화나 정확한 시공간 상관우도의 구현을 입증하지 않는다.

---

**근거 스냅샷 및 데이터 연결(논문 보충자료용)**

- SourceFFD와 기본 관측기: https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/FFD_P0P3_20261016/RESULTS_KO.md
- 기존 12조건 점수와 2×2 비교: https://github.com/myoungsunk/sionna-resimulation/blob/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv
- 관측 잔차·시간상관: https://github.com/myoungsunk/sionna-resimulation/tree/6c7200091028fd3f0e55aa83b777d0f10b7cf063/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/results
- 물리–shadow–gate 재구현 및 R1–R5 보완: https://github.com/myoungsunk/sionna-resimulation/tree/ca8cb43777100a0f5fae53978c0e4096d49701ff/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_REPAIR_V2_20261102
- R4 QA V3 별도 AI 감사: https://github.com/myoungsunk/sionna-resimulation/blob/a0ce36e8bb2a3f331b07775d9454bfb743030437/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_R4_QA_V3_INDEPENDENT_REAUDIT_20261102/FINAL_AUDIT_VERDICT.json

**작성 및 주장 경계:** R4 QA 결함 3건은 별도 재계산 감사에서 종료되었으나, 원본 누락 커밋 \(15503350\ldots\)의 복원, 외부 사람의 감사 서명, 원래 전체 누적인과 검증(V4), 신규 물리 환경 일반화는 해당되지 않는다. 본 원고는 재검산된 회고적 결과의 범위 내에서 작성하였다.
