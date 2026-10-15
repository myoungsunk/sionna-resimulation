# N4-Q: Heading 관측가능성(Geometry)과 RF 관측 오염(Integrity)의 분리 검증 계획

- 작성: 2026-10-15
- 성격: **실험 설계 / 사전 등록용 계획서**. 이번 작업에서는 GitHub 코드 수정·실험 실행을 하지 않음.
- 기존 기준: N4-B, N4-B POL-V1, N4-C의 성공·실패 사례를 원본 그대로 보존하고 추가 가설을 검증.
- 중심 질문: **"현재 편파 관측이 Heading을 구별할 수 없는가?"**와 **"Heading을 구별할 수 있는데 실제 RF가 LoS 모델에서 오염되었는가?"**를 서로 구별할 수 있는가?

## 0. 이미 확인된 결과와 해석상 주의

| 기존 실험 | 확인된 결과 | 이번 검증에서의 역할 |
|---|---|---|
| N4-B POL-V1, R2 AnchorA | Mount0 median \|Hψ\|=0.516 rad⁻¹, Port Balance=0.317; Mount45 median \|Hψ\|=1.639 rad⁻¹, Balance=0.865 | 물리적 관측가능성 차이의 출발 가설 |
| N4-B POL-V1 | Mount45 nominal Iψ=318.5, Mount0=32.1 | 실제 추정기 정보량이나 Full RF의 정답과 동일시하지 않을 것 |
| N4-B POL-V1 | Simple+FFD feature는 전반적 held-out NLL 악화, G5+FFD pooled NLL 개선이나 R2 모든 평가 조건에서 악화 | 피처를 추가했다는 사실만으로 성능 우위 주장 금지 |
| N4-B POL-V1, R2 Original J4 prior | Mount45 oracle Geometry joint95≈87.7%, actual pre-RF J4 prior Geometry≈79.7–80.2% | GT oracle과 온라인 pre-update estimator를 분리 검증 |
| N4-C | POWER_JOINT는 16개 frozen Full RF 기준선 비교에서 모두 비악화/개선했으나 L2 Pose95는 M0 45.7%, M45 12.3% | 동결된 유력 후보 및 covariance calibration 실패 대조 |
| N4-A | Pose NEES 과신의 지배항은 조건부 XY의 작은 고유축 | Heading만 좋아져도 Pose 정합이 실패할 수 있음 |

**중요:** 지금의 H와 LUT는 고정된 2° FFD angular grid; 입사각, 두 방위각 및 각도 seam/kink가 존재한다. 동일 복도 내 R2/R4/R5는 독립적인 multipath 환경들이 아니다. R4/R5 학습 구간에는 Mount45가 없다.

## 1. 연구 가설: 각각 성립·실패하는 조건을 별도로 규정

- **G-H1 (기하):** `|Hψ|`, 유한 yaw sweep에서의 `Δh_s`, prior-conditioned Heading 정보량으로 LoS heading 구별능력을 분류할 수 있다. Mount45 작동점이 대체로 유리하되 다른 경로/입사각에서는 절대 보장하지 않는다.
- **G-H2 (오염):** Native Full−Native LoS RF 차이는 정상 LoS 기하 정보량과 별도로 Range/편파의 **signed bias·dispersion·FP/CIR 오염**을 정량화한다. 높은 정보량이 반드시 깨끗한 RF를 의미하지 않는다.
- **G-H3 (직교 분리):** 높은/낮은 Geometry 정보량과 높은/낮은 RF 오염의 2×2 분류는 어느 한 축만 사용하는 분류보다 Heading 갱신의 위해성과 신뢰도 오판을 더 잘 설명한다.
- **G-H4 (온라인 가능성):** GT에서 계산한 기하 피처의 이점은 실제 RF 업데이트 직전 `x^−,P^−`로 만든 피처에서 약화될 수 있다. 불확실도 marginalization 및 OOD 검출 없이는 전역 적용이 불가하다.
- **G-H5 (성능 전이):** Geometry + RF integrity의 분리가 실제 Joint4/SR4의 Heading/Gyro Bias/XY/NEES·coverage를 모두 개선할 때만 N4-C의 신규 신뢰도 모델로 채택한다.

## 2. 측정·상태 및 물리 모델: 원본을 고정

원 상태: `x=[x_m,y_m,ψ_rad,b_g_rad/s]`.

원 관측: `z=[r_m,s]`, `s=(P1−P2)/(P1+P2)`.

LoS 모델: `h(x)=[h_r(x,y),h_s^LUT(x,y,ψ;m,anchor)]`.

방위/고각을 기존 코드와 동일하게 사용:

- `u=x−ax, v=y−ay, h=az−z_robot, ρ=hypot(u,v)`
- `θ_elev=atan2(ρ,h)`
- `φ_tx=atan2(−v,u)`
- `φ_rx=wrap(atan2(−v,−u)−ψ−m)`

TX +45° LP, RX ±45° LP의 전파방향별 패턴이 FFD LUT에 포함되어 있으므로, `ψ + Mount − TX45°`는 **이상적인 참고 상대각일 뿐**이며 LUT 계산에서 앵커 편파 45°를 다시 빼서 보정하지 않는다. TX/RX 두 LP 포트축은 π/2 간격이며 π 간격이 아님.

### 2.1 Geometry/Heading 정보량 축 `Q_geom`

서로 다른 물리량을 구분한다:

- `s_LoS= h_s^LUT(x^−)` — 기대되는 signed normalized LP 비율.
- `M1=(1+s_LoS)/2, M2=(1−s_LoS)/2`, `B=1−s_LoS²`, `D=max(M1,M2)` — 같은 `s_LoS`의 *결정론적 변환*, 독립 측정이나 절대 수신전력이 아님.
- `Hψ = ∂h_s/∂ψ` 및 `Hxy=[∂h_s/∂x, ∂h_s/∂y]` — 원 LUT Jacobian. 경계·grid-cell 교차·방위 seam 검증.
- `D_s(δ)=h_s(x,y,ψ+δ)−h_s(x,y,ψ)` — δ=±2°,±5°,±10°의 finite-angle 구별능력. `Hψ δ`만으로 대체하지 않음.
- `LUT Hessian` 또는 인접 finite difference(곡률·비대칭) 및 사전 Heading 탐색구간 내 복수 극값/동일 s 다중해. `|Hψ|`가 커도 전역적으로 유일한 Heading을 뜻하지 않음.

**정보량 계산은 두 개로 분리:**

1. `I_geom` (기하만): 고정된 동일 레퍼런스 `R_s,ref=0.0081`와 **동일하게 고정한 기준 사전공분산**에서 계산. `Q_geom` label이 다중경로 모델의 Rs에 종속되지 않도록 한다.
2. `I_op` (실제 융합용): RF 오차모델과 실제 예측공분산을 반영한 정보량. 이 값은 Q_geom와 Q_RF를 결합한 뒤 별도로 평가하며 독립 축의 정의에 사용하지 않는다.

`η=[x,y,b_g]`, `P^-_{η|ψ}=P^-_{ηη}−P^-_{ηψ}(P^-_{ψψ})^{-1}P^-_{ψη}`; `Hη=[H_x,H_y,0]`인 경우:

`Hψ_eff = Hψ + Hη P^-_{ηψ}/P^-_{ψψ}`

`Iψ|prior = Hψ_eff²/(R_s,ref + Hη P^-_{η|ψ} Hη^T)`.

이 식은 **스칼라 s로부터 얻는 국소·prior-conditioned 정보량**이며, Range까지 포함하는 joint 모델에서는 `R_rs`와 Range의 정보 중복을 별도로 처리해야 한다. 단일 시점 s 하나만으로 `[x,y,ψ,b_g]` 네 상태가 전부 관측가능해지는 것은 아니다.

### 2.2 RF Integrity/모델 오차 축 `Q_RF`

오프라인 기준, pose/time/Anchor/Mount 일치한 Native LoS/Full packet:

`e_MP = z_Full − z_LoS_native` (두 성분 r, s 각각).

`e_LUT = z_LoS_native − h(x_GT)` (FFD/LUT 보간·원 Range offset/observer residual 포함).

`e_pose = h(x_GT) − h(x^−)` (현재 추정오차의 LUT 투영).

`ν_Full = z_Full − h(x^−) = e_MP + e_LUT + e_pose` (동일 원 관측기·단위/packet 정합 시 성립).

오염 평균/중심 공분산(`e_MP`, `e_total` 모두 따로):

`μ=(μ_r,μ_s)`, `Σ=[[V_r,C_rs],[C_rs,V_s]]`, `μ_s(q)`, `μ_r(q)`, FP tap switch, strongest-port branch, CIR early/late/delay spread, log FP power, threshold sensitivity G4.

여기서 `e_MP`는 Native LoS 대비 Full에서 발생한 채널/검출기 차이이다. **정답 GT가 없다면 일반 온라인에서 직접 알 수 없다**. RF 품질 proxy는 관측가능한 전력·CIR·검출기 반응을 이용하되, RF 출력과 같은 packet에 기댄 `p(e|q)`를 곧바로 정규화된 EKF `p(z|x)`로 오인하지 않는다.

### 2.3 최종 품질 출력은 1개 숫자가 아닌 **분리된 변수들**

`Q = {I_geom, ambiguity, geometry_ood, μ_r, μ_s, V_r, V_s, C_rs, RF_outlier_score, quality_uncertainty}`.

`Q_geom ≈ 0`은 *정보 부족*을, `Q_RF` 불량은 *오염*을 의미하며 두 축의 threshold는 별도로 검증·고정한다. 어느 것도 독립 검증 없이 직접 Hard Reject 여부로 쓰지 않는다.

## 3. 단계별 필수 검증 (원인 → 모델 → 실제 효과)

| 단계 | 핵심 질문 | 필수 실험 | PASS/다음 단계 조건 |
|---|---|---|---|
| **Q0. 감사·고정** | 원본 FFD·Angle·추정기·센서 자료가 정확한가? | 원 RF SHA/관측 parity, LUT 2° grid/seam/kink, Hψ finite difference, 기존 N4B/N4C 수치 재현, train/eval 누설 감사 | 원본 binary/source hash/경로·방법 정합; 수치 예외는 FAIL/INDETERMINATE 분리 |
| **Q1. LoS 기하 정보량** | Full 오염이 없어도 어떤 작동점에서는 Heading을 구별하기 어려운가? | LoS-only, mount0/45×ψ 스캔×앵커 방향·고각; `Hψ`,`I_geom`,`Δs(2°,5°,10°)`, posterior profile 다중해; prior vs GT 비교 | 오염이 없을 때 고/저 정보량이 Heading 판별력에 일관되게 대응; flat/kink·다중해 검출 |
| **Q2. Full RF 오염 분해** | 기하가 좋거나 나쁜 조건에서 실제 r/s 오염이 다른가? | Paired Full/native LoS, `e_MP`, `e_LUT`,`e_pose`, signed means, centered covariance, FP/CIR/port switch; LoS false alarm | 오염과 위치·Heading 오류를 분리하고 holdout에서 오염 score 교정 확인 |
| **Q3. 2×2 교차 판별** | 기하 정보 부족과 RF 오염을 혼동하는가? | 저/고 `I_geom` × 저/고 `MP` 4분면, 같은 Anchor/mount/거리 매칭, LoS/null synthetic negative controls; 혼동행렬·conditional NLL | Geometry-only, RF-only보다 잘못된 신뢰도를 더 적게 출력; 각 셀 표본 충분성 확인 |
| **Q4. 실제 RF 사전 상태** | GT 기준 효과가 실제 EKF prior에서도 유지되는가? | B0/L0/L1/L2 `x^-,P^-`; 통일 DR-only prior·원 Joint4 prior 두 대조, sigma points/Monte Carlo heading prior uncertainty, gate 전후 비교 | 사전 state uncertainty·OOD를 반영한 신뢰도 향상; M45 prior 악화 재현/통제 |
| **Q5. 품질 모델 비교** | 결합 모델이 각 축을 분리하면서 추가 성능이 있는가? | G0/전력, CIR/G4, POWER_JOINT, Geometry-only, RF-only, two-head 분리모델, 일괄 score, G5+FFD 연구용 ceiling | 사전 정의한 heldout NLL·캘리브레이션·Heading 유익성 지표의 증분 확인; 양 Mount 훼손 방지 |
| **Q6. 재귀 적용 검증** | 좋은 분리 점수가 실제 EKF의 Heading/Bias/위치 추정을 개선하는가? | Frozen Joint4/SR4, LO S/Full, Bias별, common gate/time matched, no-double-count; heading/bias/XY RMSE, NEES/coverage | RMSE 개선 + posterior consistency가 동시에 검증돼야 모델 채택. R0·POWER_JOINT 대비 평가 |
| **Q7. 새로운 경로·RF 환경** | 직선경로와 mount 0/45 밖에서도 유효한가? | 별도 궤적(회전·곡선·역방향), mount 추가, anchor direction, 독립 scene/multipath/noise seeds | 독립 환경에서 조건별 성능 유지. 없으면 `BLOCKED_INPUT`이며 외삽 성공 주장 금지 |

**순서:** Q0 완료 후 Q1/Q2 병렬 → Q3 → Q4 → Q5 → (성능 기준 통과 시) Q6 → Q7. Q1/Q2/Q3의 수치적 결과가 부족하면 복잡한 Q5/Q6 모델로 진행하지 않는다.

## 4. Q1: Flat/Steep 작동점의 구별능력 — 단순 Hψ 외에 필요한 항목

1. 기존 `R2_aA_m0`과 `R2_aA_m45` 동일 pose/route에서 actual LUT 평가; 강한 포트, balanced 두 포트, 높은 Hψ가 일치하는지 통계 확인.
2. Anchor A/B와 TX/RX 상대 azimuth/elevation을 바꿔 Hψ 기울기 map. 샘플 없는 yaw에서 LoS LUT만 재평가하는 것은 **Geometry 검증만 가능**, 해당 Full RF를 실제 계산한 것처럼 취급하지 않는다.
3. `D_s(δ)`는 실제 3D LUT에서 δ=±2,±5,±10°, prior σψ에 맞춰 평가. 2° grid cell 경계·seam 통과 여부·interpolation step discontinuity 기록.
4. Prior heading credible interval 내 `h_s(ψ)`가 단조인지, 같은 s를 만드는 두 개 이상 heading mode가 존재하는지 탐색. `|Hψ|≈0`에서는 1/Hψ 역산 Heading을 금지하고 `NO_INFORMATION` 또는 `AMBIGUOUS` 반환.
5. `I_geom`은 fixed nominal covariance, `I_op`은 causal pre-update covariance로 구별. `R_s(q)`를 I_geom에 넣어 RF 오염의 영향이 Geometry label을 바꾸지 않도록 한다.
6. LoS 외 오염이 없는 조건에서도 예상 정보량이 높은 곳이 실제 Heading posterior를 좁히지 못하면 Hψ/FFD 모델 또는 구조적 모호성 반례로 판정.

## 5. Q2: RF 오염은 Range·s로 분리하되 상관관계를 유지

- 원래 14,502개 P3 관측 parity 유지, Full/LoS matched ID/pose/Anchor/Mount/원 observer의 선행 감사.
- `e_MP`, `e_LUT`, `e_pose`의 Range·s 성분별 분포, signed bias, quantile, FP tap/branch change 전후, 시간상관을 위치·Yaw sweep와 이동 구간으로 분리.
- `Σ_rs`는 Mount/Heading 작동점/Anchor별로 부호와 크기를 기록; PSD/eigen 검사 후 동일 모델의 diagonal/non-diagonal NLL ablation.
- 평균을 보정한 후 `Var(e|q)=E[e²|q]−μ(q)²` 중심 공분산을 재학습/평가. `E[e²]`를 무조건 Rs로 사용하지 않는다.
- 순수 `e_MP`와 실제 LoS EKF가 보는 `e_total=zFull-h(xGT)`를 별도 target으로 평가해 외관상 RF 오염과 detector/LUT mismatch를 구분.
- 강한 MP에 의해 `s`가 거의 바뀌지 않는 반례와, MP가 거의 없는데 `Hψ`가 작아 Heading 정보가 없는 반례를 고정 Negative Controls로 포함.

## 6. Q3의 핵심 판별 실험: 4분면 교차표

| LoS Heading 기하정보 | RF Integrity 좋음 | RF Integrity 나쁨 |
|---|---|---|
| **높은 정보량** | ① 정상·유용한 Heading RF | ② 유용해 보여도 RF 오염으로 Heading 위해 가능 |
| **낮은 정보량** | ③ **오염은 없지만 Heading 보정 정보가 부족** (불필요한 MP 경보 금지) | ④ 정보 부족과 오염이 함께 존재 (단일 Heading pseudo-observation 금지) |

- High/Low threshold를 R4/R5 Train/Validation에서 **사전 고정**. R2 테스트나 L2 RMSE를 보고 threshold 변경하지 않음.
- RF Integrity label은 paired Full/native LoS **오프라인 정답에서만** 계산. 온라인 분류기는 전력·CIR·FP tap/G4 등 실측 가능한 q 및 prior innovation을 기반으로 학습/추론.
- 구간 분리는 연속값 Hψ 하나로 하지 말고 I_geom, D_s(δ), multimodal 여부를 교차 확인한다.
- 4개 영역에서 `P(MP)`, `E[|e_r|,|e_s|]`, Heading one-step error change, Gyro Bias update error, False RF reject를 각각 보고한다.
- 효과 비교 시 anchor distance, φtx/φrx, theta elevation, estimated prior uncertainty, 강한 RX port의 품질을 stratify/match한다. Mount 0°와 45°가 같은 장면을 단지 기하만 바꾼 순수 실험이 아님을 명시한다.
- 한 셀에 충분한 독립 scene·location이 없으면 `INDETERMINATE`; 패킷 수가 많다는 이유로 독립 표본이라고 주장하지 않는다.

## 7. Q4: Oracle과 실제 pre-RF 추정 사이의 갭

기존 N4-B POL-V1: R2/M45 B0의 oracle conditional NLL −1.0564 → 실제 J4 prior 조건 −0.7575, joint95 87.74%→79.67%로 악화. 이 갭을 핵심 Negative Control로 보존.

**3개 입력 수준을 분리**:

| 입력 | 생성 | 용도 |
|---|---|---|
| Oracle geometry | GT pose / true relative orientation | 순수 물리 가설을 검증하는 upper bound |
| Frozen reference prior | 원 DR-only 또는 원 Joint4의 동일 시점 pre-RF x^−,P^− | GT 비주입 온라인 가능한 참조 실험 |
| Proposed estimator prior | 후보가 누적 생성한 자신의 x^−,P^− | Feedback/self-reinforcing 위험 포함한 closed-loop 실험 |

P^-의 Heading·Position 상관을 sigma-point/Monte Carlo로 propagating해 `s_LoS`/Hψ/I_eff의 불확실도와 다중해 확률을 추정. 단일 점값만 쓰는 방법과 비교한다. 이 방법도 prior Gaussian 근사가 충분한지 검증해야 하며 FFD kink, null, wrap seam을 보존한다.

**측정과 모델의 같은-packet 중복 문제:** q가 r/s와 결정적으로 관련 있으면 `p(e|q)`의 NLL 개선이 곧 `p(z|x)` likelihood의 정당화가 아니다. 온라인 모델 구현 전 `p(z,q|x)` 공동 모델 또는 올바른 conditional normalization/selection likelihood 논리를 수립해야 한다.

## 8. Q5/Q6: 비교군과 성능판정

**기존 기초 비교군:** Frozen R0 Joint4/SR4; N4-C POWER_JOINT; N4-B Simple Diag; G4; G5 (simulation oracle ceiling). **새 비교군:**

1. `GEO_ONLY`: 실제 LUT/FFD 기하 I, D_s, ambiguity 기반 **정보성 예측만**; pollution estimator 없음.
2. `RF_ONLY`: 전력·CIR·FP/G4 기반 pollution/covariance prediction, geometry feature 제외.
3. `GEO+RF_SEPARATE`: Geometry information axis와 pollution mean/cov quality axis를 독립 출력으로 학습·검증, 최종 업데이트에서 결합.
4. `GEO+RF_SINGLE_SCORE`: 기하와 RF를 무차별로 합친 단일 점수의 부정 대조군.
5. `POWER_JOINT+GEOM_INFO`: 동결 후보의 평균/공분산을 지키며 geometry information/OOD를 의사결정에 더하는 추가 검증군.

Q5에서는 모델 목적별로 별도 metric을 유지:

- Geometry-only: LoS heading likelihood precision, local/global identifiability, Q_geom calibration, ambiguous-mode rate.
- RF-only: e_MP residual regression/NLL, MP proxy Brier, LoS false alarms, FP transitions.
- Combined: `P(harmful Heading update)` calibration, signed ΔHeading-error², bias correction benefit, one-step error risk, risk-coverage curve. Oracle harm label은 오프라인 평가용.
- 4state recursion: Heading RMSE, signed error, Gyro Bias RMSE/bias95, XY RMSE, Heading/Pose NEES+coverage, conditional-XY NEES, accepted packet count, OOD/multimodal rate, mount0/mount45 and bias L0/L1/L2. B0는 기계적 메커니즘 점검용.

**PASS 게이트:** 이전 Joint4/SR4·POWER_JOINT 대비 (a) Heading/Bias/XY가 소수 Mount에서 좋아지는 선택적 장점과 (b) 정상 LoS/M45에서의 손실이 모두 명시적으로 평가돼야 한다. (c) Mean Pose NEES 개선만으로 충분하지 않으며 95% posterior 포함률과 tail wrong-confidence를 함께 개선할 것. (d) LoS native control과 독립 scene에서 유지되지 않으면 연구 후보만 보존하고 최종 융합에 미채택.

## 9. 독립 경로 확장 계획 (Q7)

- 기존 R2/R4/R5의 직선·Yaw sample과 별도로 **직선, 회전/곡선, 원호, 왕복 역방향** 경로를 다루는 완전한 Full RF/Native LoS paired 원본이 필요함. 기존 한 프레임의 LUT yaw만 바꿔 새로운 Full RF packet처럼 간주하지 말 것.
- Mount0/45는 필수. 가능하면 중간 각도 15/30°, 대칭/반대 방향 추가; Anchor LP 각도/Anchor 위치 및 입사각의 변화도 분리.
- Geometry-equivalent but MP-different 및 MP-equivalent but geometry-different 조건을 구성해 정보 부족 vs 오염 원인분해의 식별성을 강화.
- 서로 독립적인 Multipath scene/seed와 RF receiver noise/FP detector noise realization이 반드시 필요. 현재 동결 RF 원 H는 noise-free이며 `sensor seed0`가 RF multipath 독립 시드가 아니다.
- 공간/site/trajectory/time 블록 부트스트랩 외 독립 환경별 검증을 추가; Monte Carlo/route sample count를 제공하기 전 외부 일반화 성립을 주장하지 않는다.

## 10. 감사·출력 계약

**실행 전:** 원 code/input SHA 동결 → Hψ 및 `s`/Power 포트 순서 감사 → FFD finite-diff(2° knot/seam 포함) → LoS/Full pairing → feature computation at GT vs pre-RF prior → label/same-packet-leakage audit → 실행.

**새 필수 산출물**:

- `Q0_INPUT_PARITY.json`: commit, LUT hash, observer parity, angle convention, mounted antenna/anchor config, noise assumptions, train/test partition.
- `Q1_GEOMETRY_INFORMATION.csv`: case/pose/heading/mount/anchor, B, Hψ, I_geom/I_op, D_s(δ), knot/seam, multimodal label, oracle-vs-prior gap.
- `Q2_FULL_VS_NATIVE_LOS_RF_ERRORS.csv`: r/s paired pollution, LUT-model residual, prior-geometry residual, μ/V/Crs, FP/CIR, confidence.
- `Q3_2X2_CONFUSION.csv` + `Q3_LABELED_EXAMPLES.csv`: 4분면, threshold/source, false-alarm and RF-harm stratification.
- `Q4_PRIOR_UNCERTAINTY_REPORT.json`: prior covariance propagation, I-score stability and mode count, mount45 degradation.
- `Q5_HELDOUT_MODEL_SCORES.csv`: baseline vs separation score NLL/Brier/harm target/coverage and independent bootstrap.
- `Q6_RECURSIVE_COMPARISON.csv` + full `x,P,gate,NIS` NPZ: R0, POWER_JOINT, separate-score model, joint/SR4 full LoS/FULL × biases × mounts.
- `FINAL_DECISION.json`: `TECHNICAL_PASS | SCIENTIFIC_PARTIAL | FAILED | BLOCKED_INPUT`와 각 가설 H1~H5의 PASS/FAIL/INDETERMINATE, 남은 근거·오라클/실측 구별.

## 11. 추천 첫 실행 묶음과 절단 조건

**1차(Q0–Q3)에서는 학습 기반 새로운 EKF를 만들지 않는다.** 동결 RF/LUT 데이터에서 (i) LoS 기하 정보량, (ii) Full−LoS MP contamination, (iii) Pose prior error를 분해하고 2×2로 구분할 수 있는지 정량 검증한다.

**2차(Q4–Q5)에서는 GT oracle의 상한과 온라인 pre-update prior의 실용성을 비교**하고, Geometry-only, RF-only, 분리 모델이 단일 혼합 점수보다 실제 Heading 위해성 calibration에 증분 이익이 있는지 평가한다.

**3차(Q6–Q7)는 앞 단계에서 의미 있고 재현 가능한 분리 신호를 얻었을 때만 수행한다.** 이미 검증된 POWER_JOINT를 덮어쓰지 않고, 다른 Mount/경로와 posterior 공분산 품질을 엄격한 통과 조건으로 설정한다.

**최종 성공의 정의:** 나쁜 RF를 걸러내는 모델도, LoS 기울기를 설명하는 모델도 각각 충분하지 않다. *어떤 조건에서 Heading 정보가 존재하고 그 정보가 얼마나 오염되었으며, 이 둘을 분리했기 때문에 실제 4-state 추정 정확도·신뢰도가 더 좋아졌음*을 독립된 검증으로 입증해야 한다.

## 기존 검증 자료

- N4-B POL-V1: https://github.com/myoungsunk/sionna-resimulation/blob/research/r5-n4b-polar-geometry-20261015/research/R5_N4B_POL_V1_20261015/RESULTS_KO.md
- N4-C Joint4/SR4: https://github.com/myoungsunk/sionna-resimulation/blob/research/r5-n4c-joint-sr-recursive-20261015/research/R5_N4C_REPORT_20261015/RESULTS_KO.md
- 원 FFD LUT/Jacobian: https://github.com/myoungsunk/sionna-resimulation/blob/research/r5-n4b-polar-geometry-20261015/research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py
