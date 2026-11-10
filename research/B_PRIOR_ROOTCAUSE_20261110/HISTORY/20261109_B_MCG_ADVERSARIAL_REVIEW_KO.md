# B-MCG v1: 코드·데이터 적대적 감사와 직접 Heading 제어 검토

**작성:** 2026-11-09  
**판정:** `NUMERIC_REPLAY_CONSISTENT / HEADING_GUARD_DESIGN_NEEDS_REVISION / ADOPTION_HOLD`  
**감사 고정 소스:** 연구 실행 `e3ddc9fa4371d899a08a2a873d2ee5cf32074a01`, 공개 저장 상태 `2971b5a174b918303810819fae6af4eeef95f366`, Actions #42600632209.  
**실행 범위:** 기존 데이터·저장 추적 전수 재산술, 원본 synthetic/API 단위시험 재실행, 동일 prior에서 고정한 action의 1회 갱신 대조. **새 RF 생성, 새 재귀 필터, 정책 재학습, GitHub 수정은 없음.**

## 1. 핵심 결론

사용자의 지적은 설계 목적과 실제 작동의 차이를 정확히 짚었다. 현재 가드는 Heading 오차의 방향·갱신량을 직접 심사하지 않고, 과거 RF로 정렬한 운동 경로가 현재 range/s를 설명하는지 판단한다. 그 판단에 따라 관측공분산만 바꾼다. 따라서 이 가드의 실패를 곧바로 ‘운동정보로 Heading 갱신을 제어하는 모든 접근의 실패’로 해석하면 안 된다.

동시에 ‘Heading을 건드리지 않는다’는 표현은 원래 EKF에 대해서는 사실이 아니다. EKF는 s와 range로 Heading 및 gyro bias를 매번 수정한다. **직접 Heading을 제어하지 않는 것은 가드의 제어변수이며, 추정기의 갱신 대상이 아니다.** `mcg.covariance_update()`는 전체 4상태를 `prior+K@innovation`으로 갱신하고, Heading은 wrap만 한다.

실제 CI의 ACTIVE_RS는 두 채널을 감쇠할 수 있도록 구현됐지만, 유효한 s 점수는 모두 문턱 2보다 낮아 s 감쇠가 0회였다. 실제 23개 개입은 range만 약화했다. 이는 s 분기를 닫아둔 구현이 아니라 **현 점수·유효성·불확실성 scale·과거 정렬 방식의 선택 결과**다. ‘range만을 통해 편파를 보정하기로 검증됐다’는 의미가 아니다.

## 2. 확인한 코드·데이터와 검산 범위

|영역|검토 내용|결과/한계|
|---|---|---|
|원본 계보|CI route별 metadata·trace 24파일 SHA, runtime source 9회 대조|일치|
|재현|6개 OFF stream과 archived B baseline|1e-10 기준 통과|
|수치 연산|OFF/ACTIVE 전체 12,544개 행의 K, 상태, Joseph P|독립 재산술 일치|
|관측 정합|route/k/pose_id/time, B tap→range, s, 동일 RF의 strata 간 비교|수치 일치|
|손익|6,272 donor prior의 가중/비가중 결과와 case CSV의 same-prior 손익|Heading 최대 차이 4.44e-16 deg², XY 3.55e-14 cm²|
|Heading 채널 경로|H의 range/yaw와 모든 RF/bias 직접미분, K와 innovation|H_range,yaw=0; H_rf,bias=0; 하지만 교차공분산을 통한 gain은 0이 아님|
|기본 구현 시험|보존된 test_mcg.py|27개 synthetic/API 시험 PASS|
|실험 독립성|IMU는 prior/posterior transition을 역산한 값|독립 센서 기록 검증이 아님|
|표본 독립성|3,136 physical timestamps ×2 calibration strata|6,272개의 독립 RF 사건이 아님|
|506 case selection|왜곡·손실·UNKNOWN 등을 기준으로 사후 선별|발생률·정책 학습의 무편향 표본이 아님|
|신규 모델 검증|고정 prior에서 action별 1회 갱신만 계산|새 재귀 성능·회복·coverage를 검증하지 않음|

최대 Joseph P 차이는 1.08e-19, K 차이는 2.78e-17이다. 이는 산술·저장 정합성의 통과이지, 관측모델이나 가드의 판단이 옳다는 증거는 아니다.

## 3. 코드상 Heading과 편파의 연결

상태와 관측은 다음과 같다.

\[
x=[p_x,p_y,\psi,b_g]^\top,\qquad z=[r,s]^\top.
\]

\[
\delta\psi=K_{\psi,r}\nu_r+K_{\psi,s}\nu_s.
\]

- s의 관측모델에는 실제 `H[s,yaw]`가 존재한다. s는 Heading을 직접 갱신한다.
- range의 관측모델은 Heading 직접미분이 0이다. 그러나 `P[yaw,position]` 및 joint innovation covariance를 통해 `K[yaw,range]`가 0이 아닐 수 있다.
- RF 관측의 gyro-bias 직접미분은 0이어도 `P[bias,pose]`를 통해 RF가 gyro-bias 추정치를 바꿀 수 있다. 이후 그 bias가 운동 예측을 바꾼다.
- 관측공분산의 range 성분을 키우면 range열뿐 아니라 joint solve를 통한 다른 gain도 변할 수 있다. ‘beta_s=1’은 s 측정분산을 직접 바꾸지 않았다는 뜻이지, s가 Heading을 수정하지 않았다는 뜻이 아니다.

현재 `weights()`의 입력에는 target heading correction, main gain, main Pprior가 없다. monitor에 prior state는 들어가지만 main covariance 전체나 실제 trial correction을 이용해 결정하지 않는다. `trial_delta`는 기록되지만 ACTIVE_RS의 weight 결정에 사용되지 않는다. 따라서 실제 제어 목표는 ‘Heading correction harm’이 아니라 ‘관측 설명 불일치’다.

**중요한 한계:** K열×innovation의 분해는 같은 선형화·joint gain에서의 산술 기여다. K 자체가 두 채널·공분산·선형화에 의존하므로 이를 각 RF 경로의 독립적인 물리 인과기여로 부르지 않는다.

## 4. 왜 s 감쇠가 한 번도 없었는가

|루트/보정|전체 행|s 판단 유효 행|유효 s 최대 점수|실제 range 감쇠|실제 s 감쇠|
|---|---:|---:|---:|---:|---:|
|R2 B_FROZEN|979|134|0.6067|1|0|
|R2 B_BIAS_COV|979|134|0.2742|0|0|
|R4 B_FROZEN|742|145|1.1420|2|0|
|R4 B_BIAS_COV|742|129|1.5212|0|0|
|R5 B_FROZEN|1415|271|0.3434|9|0|
|R5 B_BIAS_COV|1415|236|0.3521|11|0|

실제 CI의 tau_s=2이며 enable_s=true이다. s 점수가 2를 넘은 R4 k729는 두 보정 모두 `PROFILE_AT_BOUND`로 UNKNOWN 처리됐으므로 가드가 bypass됐다. 총 UNKNOWN은 5,163/6,272=82.32%, 양 채널 유효판정은 1,049=16.73%, warmup은60이다.

이는 두 단계의 선택 문제다.

1. **유효성에서 대부분 탈락:** boundary, 낮은 비용 후보 미해결, 비선형 미수렴 등의 이유로 개입하지 않는다. UNKNOWN을 정상판정 또는 나쁜 RF 성공차단으로 세면 안 된다.
2. **유효한 s는 score 문턱 미달:** `min_theta |s-h_s(theta)-mu_s| / sigma_monitor`를 계산한다. past RF로 공통 yaw·position·bias를 정렬하고 여러 허용 후보 중 가장 잘 맞는 예측을 고르므로, 실제 오염이 있어도 작은 score가 나올 수 있다.

현재 s의 base 표준편차 중앙값은 약 0.130–0.153이다. 여기에 motion envelope가 더해진다. tau=2는 해당 scale에서 대략 0.26–0.31 수준의 관측공간 차이이며, pose 후보 중 최소 residual을 택한다. 단, 이 수치를 ‘올바른 문턱이 아니다’라는 단독 근거로 사용할 수는 없다. scale·minimization·validity가 각각 얼마나 작용했는지는 구성요소 분리 실험이 필요하다.

**높은 heading 민감도와 작은 s-score는 모순이 아니다.** 작은 yaw 이동으로 관측을 설명할 수 있으면 nuisance fit는 오히려 낮은 residual을 얻을 수 있다. 그 설명이 실제 yaw 수정인지 RF 왜곡 흡수인지 식별되지 않으면, ‘잘 설명된다’가 곧 정확하다는 뜻이 되지 않는다.

## 5. 왜 실제 가드가 실패했는가: 같은 prior에서 분해

### 사례 A: range 기여가 실제 Heading 오차를 키운 성공 사례

R5 B_FROZEN k435, 87.0초. GT Heading +1.26180°, ACTIVE donor prior −0.49482°.

|Heading 갱신량|무가중 B (같은 prior)|실제 가드|
|---|---:|---:|
|range 기여|−0.14867°|−0.03897°|
|s 기여|+0.02207°|+0.02208°|
|합계|−0.12660°|−0.01689°|
|갱신 후 Heading|−0.62142°|−0.51171°|

prior는 이미 GT보다 작다. range가 더 작은 방향으로 밀고 s는 큰 방향으로 조금 되돌린다. range를 약화하면 해로운 기여가 감소한다. Heading 제곱오차는 0.40118deg², XY 제곱오차는 43.25995cm² 감소한다.

### 사례 B: 가드가 좋은 기여를 약화한 실패 사례

R4 B_FROZEN k492, 98.4초. prior Heading 오차는 +0.66296°.

|Heading 갱신량|무가중 B (같은 prior)|실제 가드|
|---|---:|---:|
|range 기여|**−0.02235° (오차 감소 방향)**|−0.01493°|
|s 기여|**+0.02713° (오차 증가 방향)**|+0.02713°|
|합계|+0.00478°|+0.01220°|

range와 s가 서로 상쇄하고 있었는데, 가드는 range를 불일치로 판단해 **오차를 줄이는 기여만 약화**했다. 같은 prior에서 Heading 제곱오차 +0.009966deg², XY +1.801834cm²의 손해가 발생했다.

이 사례에서 필요한 판단은 ‘range residual이 크다’뿐 아니라, **현재 상태에서 각 관측의 Heading·XY 기여가 무엇인가**였다. 현 score→R 감쇠 구조에는 그 판단이 없다. 이것이 목표와 action 사이의 직접적인 불일치다.

### 실패의 다른 층위

- 오염된 history가 현재의 공통 정렬을 잘못 만들 수 있다. immutable anchor와 current-target exclusion만으로 이 경로는 차단되지 않는다.
- finite nuisance search가 허용해를 놓치면 실제로 호환 가능한 target도 conflict로 분류될 수 있다. 과거 감사의 R4 k212 model-ideal 복귀 반례는 이 문제를 보였다. 이는 이번 자연 Full B k212 행과 다른 대조 실험이다.
- 운동과 일관된 절대 heading 편향은 motion consistency만으로 구별할 수 없다.
- 이미 primary 정책은 OFF로 동결됐다. ACTIVE_RS_tau2는 성능이 입증돼 채택된 정책이 아니라 진단용 개입이다.
- 유효 판정의 부족과 작은 개입 수는 모든 오염을 성공적으로 제거했다는 뜻이 아니다. 23회만 바꾼 재귀 결과의 작은 개선으로 전체 접근을 정당화할 수 없다.

## 6. 이전 설명·분석 코드에서 발견한 수정 사항

### F1 — 이전 R5 비교표의 prior/posterior 조건 혼용

이전 채팅은 ACTIVE prior와 OFF의 실제 posterior를 같은 표에 넣었다. OFF와 ACTIVE는 이미 다른 과거를 거쳐 현재 prior가 다르므로 그 전후 차이는 한 번의 갱신량이 아니다. 같은-prior case CSV 손익은 정상적으로 계산돼 있었다. 잘못된 것은 해당 설명 표였다.

|R5 k435|B_FROZEN|B_BIAS_COV|
|---|---:|---:|
|ACTIVE donor prior Heading|−0.494822°|+0.715871°|
|같은 ACTIVE prior에서 가드 없이 B 갱신|−0.621423°|+0.587751°|
|실제 ACTIVE 가중 갱신|−0.511714°|+0.674012°|

위 ACTIVE priors의 차이는 **1.210693°**, 위치 차이는 **30.9584cm**다. 앞서 제시한 **1.309526°/31.8213cm**는 OFF priors끼리의 비교에서 나온 수치다. 두 비교를 섞지 않는다. 같은 RF에 대한 상태·P·μ/R·H가 다른 것은 사실이지만, 이 자료로 ‘heading 차이 하나가 원인’이라고 확정할 수 없다.

### F2 — analyze_cases.py의 5초 운동 진단에 1표본 초과 포함

원래 코드:

```python
sum(gyro[max(1, k-25):k+1])
yaw[k] - yaw[max(0, k-25)]
```

k>=26에서 첫 줄은 26증분(5.2초), 둘째 줄은 25증분(5초)을 비교한다. 정정:

```python
sum(gyro[max(0, k-25)+1:k+1])
```

초과한 한 표본의 회전 크기는 각 경로에서 최대 약 5.02°/4.78°/5.02°다. **현재 FULL_ENRICHED 내보내기와 그림은 이 계산열을 쓰지 않으며, 실제 MCG 제어에도 들어가지 않는다.** 따라서 이 버그를 현 가드 실패의 원인으로 과장하면 안 된다. 이후 운동 비교에 재사용하면 중대한 진단 오류가 되므로 별도 패치 파일과 QA를 제공했다. GitHub 원본은 변경하지 않았다.

### F3 — joint 충돌에서 enable_r/enable_s가 무시되는 코드 결함

`weights()`의 marginal 감쇠는 enable_r/enable_s를 검사하지만, joint 충돌 분기는 `beta[:]`에 두 값을 함께 쓴다. `enable_s=False` 및 ACTIVE_RS에서 marginal score=(1,1),joint score=4인 합성 반례를 넣으면 **원래 beta=(0.5,0.5)**가 되어 비활성화한 s도 감쇠된다. `beta[enabled]`로 수정하면 **(0.5,1.0)**으로 바뀐다.

80개 flag×mode×score 조합을 검증하고 원래27개 단위시험도 수정본에서 다시 통과했다. **현재 CI는 두 enable 모두true이고23개 개입에는joint 감쇠도 없으므로 이번 결과의 원인은 아니다.** 다음 채널별 ablation의 설정 신뢰성을 위해 필요한 수정이다. 로컬 수정 사본과 patch만 생성했고 GitHub source는 그대로 보존했다.

### F4 — IMU 증거의 독립성

casebook의 gyro 증분은 각 저장된 previous posterior와 next prior에서 원본 transition을 역산해 복원했다. 여러 stream에서 1.62e-15rad 이내 일치하는 것은 계산계보 정합성 검증이다. **별도의 센서 로그가 그 필터를 독립적으로 검증했다는 뜻이 아니다.** 실제 입력 online.npz gy/ds와의 바이트 및 수치 재대조는 이번 작업에서 수행하지 않았다.

### F5 — 선별 사례의 인과·확률 해석

506개는 사후 손해·큰 왜곡·큰 NEES·UNKNOWN 등을 보고 선택한 catalog다. 발생률 추정·정책 임계값 선택·새 환경 효과 검증에 그대로 쓰면 selection bias가 생긴다. 물리 RF 3136회를 2strata로 처리한6272행은 독립6272회가 아니다. clean/GT 특징은 evaluator에만 사용되어야 한다.

## 7. 직접 Heading 제어를 피했던 이유와 재검토

기존 설계가 출력 Heading clipping을 피한 이유는 타당하다. 추정치를 8°→5°로 고친 것은 로봇이 −3° 회전한 것과 다르고, 상태만 잘라놓고 P를 원래 갱신대로 유지하면 모순이 생긴다.

그러나 이것은 ‘Heading 상태의 갱신량을 직접 제어하면 안 된다’는 근거가 아니다. **출력 clipping을 피해야 한다는 주장을 관측 R 조절만 허용해야 한다는 주장으로 확장한 것은 설계상 제한**이다. 상태별 partial update와 일관된 covariance 전파는 직접 검토할 수 있다. 관측불확실성은 measurement-space, 상태별 보정 허용량은 state-space라서 서로 다른 연산이다.

### 가장 작은 직접 대조: Heading 행 및 gyro-bias 행의 partial update

명목 gain K에 대해

\[
D=\operatorname{diag}(1,1,\gamma_\psi,\gamma_b),\qquad \widetilde K=DK
\]
\[
\hat x^+=\hat x^-+\widetilde K\nu,
\quad P^+=(I-\widetilde KH)P^-(I-\widetilde KH)^\top+\widetilde K R\widetilde K^\top.
\]

이렇게 하면 현재 XY 평균의 보정은 유지하면서 Heading 보정은 직접 제한할 수 있다. gyro-bias 행도 별도로 다뤄야 RF가 bg를 바꿔 다음 gyro 적분을 왜곡하는 우회 경로를 검사할 수 있다. 단, 실제 bias가 존재할 수 있으므로 영구히 bg를0으로 고정하는 운용 모델을 권하지 않는다.

고정된 선형화와 결정론적인 D, 표준 최적 K에 대해서 다음 항등식이 성립한다.

\[
P_D=P_K+(I-D)KSK^\top(I-D)^\top.
\]

추가항은 PSD다. 이번에6272개 donor prior에서 gamma_psi=gamma_b=0.25로 확인했으며 최대 항등식 오차는 3.47e-18이다. 이는 **일관된 대수 구현이 가능하다**는 확인이고, adaptive gamma의 참 posterior나 새 재귀 정확도를 보증하는 결과는 아니다.

관련 원전: Ramos et al., *Observability Informed Partial-Update Schmidt Kalman Filter*, FUSION2021, DOI10.23919/FUSION49465.2021.9626946. 원논문은 상태별 업데이트 비중을 부분·전체·0으로 제어하고 관측가능성 기반 가중치를 논의한다. 현재 UWB 편파 오염에 대해 검증된 방법이라는 뜻은 아니다.

더 세분하면 Heading 행의 range/s 기여를 각각 제어할 수 있다. 그러나 임의의 개별 gain 조절은 covariance를 반드시 다시 계산해야 하며, 대각 D 구조의 PSD 순서 항등식과 동일한 보장을 자동으로 주장하면 안 된다. 최초 검증은 상태행 단위로 단순하게 시작하는 것이 해석에 유리하다.

## 8. 직접 제어도 무조건 좋은가: 같은 prior의 신규 고정 action 대조

기존6272개 ACTIVE donor prior에 현재 입력/H/ν와 원래 shadow mask를 고정했다. 미리 정한 range분산×4, s분산×4, Heading gain행25% 등을 각각 한 번 계산했다. **새로운 궤적을 재귀 실행하거나 policy를 학습하지 않았다.**

표의 값은 원래 joint full update 대비 Heading 제곱오차 변화(deg²)이며 음수는 개선이다.

|실제 시점/원본B|range R×4|s R×4|Heading행25%|
|---|---:|---:|---:|
|R5 k435,87.0초|−0.406445|+0.063084|−0.348610|
|R4 k492,98.4초|+0.022602|**−0.026674**|**−0.004772**|
|R2 k523,104.6초|−0.016211|**+1.190865**|**+1.181348**|

R4에서 직접 Heading/편파 쪽 action은 현재 range 감쇠보다 나은 반사실을 만든다. 하지만 R2 k523은 큰 물리적 s왜곡(Full−LoS 약+0.73)에도 s갱신이 기존 heading오차를 줄이는 상황이다. s나Heading을 무조건 약화하면 좋은 보정을 잃는다.

Heading행만 바꾼 경우 세 시점 모두 **즉시 XY 평균은 불변**이다. range/s분산만 바꾸면 XY까지 동시에 바뀐다. 예컨대 R4 k492의 s분산×4는 XY제곱오차도1.4574cm² 줄였지만, R2 k523에서는133.2327cm² 늘렸다. 이런 차이가 measurement-space와 state-space 제어를 분리해 비교할 이유다.

전수 고정 Heading25% 계산도 모든 표본에서 이득이 나지 않았다. 이 집계는 frozen donor priors의 결과이므로 새 필터 RMSE로 제시하지 않는다. 미래에는 변경된 P와state가 다시 예측·관측모델로 들어가므로 실제 재귀 평가가 별도로 필요하다.

## 9. 다음 구조를 평가할 때의 요구사항

1. **진단 목표를 명확히 분리:** 관측 오염 점수, 관측 모델의 관측가능성, 실제 heading 보정량, gyro-bias 보정량, posterior uncertainty는 서로 다른 양이다.
2. **더 직접적인 state-space 가드:** 후보 보정 [δpx,δpy,δpsi,δbg]의 시간적 일관성을 검사한다. global yaw offset을 수정하는 좋은 보정과 motion relative shape를 왜곡하는 보정을 구별한다. gyro step보다 δpsi가 크다는 이유만으로 거부하지 않는다.
3. **채널×상태 영향 기록:** Kψrνr/Kψsνs, Kbgrνr/Kbgsνs 및 P의 cross terms를 남긴다. 수용 여부만으로 정상 라벨을 만들지 않는다.
4. **상태 방향의 신뢰도 평가:** |∂s/∂ψ|가 크다는 사실만 보지 말고 위치·bias를 함께 고려한 조건부 Heading 정보와 비선형 역산의 모호성을 본다. s→heading 단일 역함수는 위치 불확실성과 다중해 때문에 일반적으로 보장되지 않는다.
5. **교차실험:** 기존 원본/현재 가드, s가중치, heading-row partial update, heading+bg-row partial update를 같은 기준에서 비교한다. 한 단계검사 후 실제 own-state 재귀와 기존 holdout 계약으로 평가한다.
6. **원인 분리 조건:** heading만 바꿔 비교할 때 h/H/ν도 원본 SourceFFD로 다시 계산해야 한다. state의heading만 바꾸고 이전 H를 그대로 쓰는 비교는 완전한 non-linear heading intervention이 아니다. 이번 audit는 이 교환 실험을 수행하지 않았다.
7. **승인 범위 유지:** 현재primary policy OFF,독립환경 미검증,보정 strata 역전,계산시간 미달이라는 기존 HOLD 근거를 유지한다. 새 직접제어가 이를 해결했다고 주장하지 않는다.

## 10. 원본·재검산 자료와 상태

원본 코드:
- https://github.com/myoungsunk/sionna-resimulation/blob/2971b5a174b918303810819fae6af4eeef95f366/research/B_MCG_V1_20261109/mcg.py
- https://github.com/myoungsunk/sionna-resimulation/blob/2971b5a174b918303810819fae6af4eeef95f366/research/B_MCG_V1_20261109/experiment.py
- https://github.com/myoungsunk/sionna-resimulation/blob/2971b5a174b918303810819fae6af4eeef95f366/research/B_MCG_V1_20261109/CASE_GALLERY_20261109/analyze_cases.py
- https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209

방법 관련 원전:
- https://ieeexplore.ieee.org/document/9626946/ — state-wise partial update와 관측가능성
- https://engagedscholarship.csuohio.edu/enece_facpub/23/ — 상태 제약과 단순 projection의 차이

동봉물:
- AUDIT_EVIDENCE.json: numerical checks,sourceSHA,score별 유효성·개입 통계
- CHANNEL_HEADING_DECOMPOSITION_23.csv: 실제23개 개입의 Heading 채널기여와 손익
- ROW_LEVEL_AUDIT_6272.csv: 전수 row-level 검사
- FROZEN_PRIOR_ALTERNATIVES.csv / SELECTED_DIRECT_ALTERNATIVES.csv: 동일prior 고정action 대조,NOT_RECURSIVE
- PARTIAL_GAIN_COVARIANCE_CHECK.json: state-selective gain covariance 항등식 검산
- analyze_cases_5s_window_fixed.py / patch / WINDOW_DIAGNOSTIC_FIX_QA.json: 제한된 로컬수정과 영향범위
- mcg_joint_enable_flags_fixed.py / patch / JOINT_ENABLE_FLAGS_QA.json: 채널 enable flags 준수 수정 및80개 조합검사
- audit_direct_heading.py / UNIT_TEST_REEXECUTION.log: 검산코드·원본 단위시험 재실행

**최종 판단:** 산술·저장데이터의 핵심 손익은 재현된다. 그러나 현 가드는 Heading 보정의 안전성·유용성을 직접 제어하는 검증을 대체하지 못한다. 직접 Heading partial update는 적법한 비교 후보이나, 좋은 절대보정 보호·원인식별·재귀 정합성을 별도로 검증해야 한다. GitHub 원본·기존 결과·policy는 변경하지 않았다.