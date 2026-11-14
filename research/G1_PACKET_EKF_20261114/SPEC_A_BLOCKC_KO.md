# G1-DIAG-003 — 기존 RT(BLOCK_C 연속 주행)에서 packet 단위 EKF의 구조 사전 시험과 integrity 실패 기전 분리 사양서

- 작성: 2026-11-14 KST. 상태: **SPEC_DRAFT / NOT_RUN / DIAGNOSTIC_ONLY**. **S2′ STOP (FULL_6) · Step 3 보류**
- 갈래: **기존 데이터 갈래.** 새 RT 갈래는 [SPEC_B_NEW_RT_KO.md](SPEC_B_NEW_RT_KO.md)(G1-MODEL-003)다.
- 배경: G1-FLOOR-001 → G1-MODEL-001/002는 sweep 전체로 station heading 1개를 맞추는 추정기를 썼다. 원래 접근(packet 단위 재귀 EKF)과 다르다. S2′ STOP, K1–K6, K9/K10, E1/c_L은 이 사양의 근거로 쓰지 않는다. K7·K8·tap 진단의 **기전**만 가설로 이월한다.
- 주장 경계: 모든 결과는 `DIAGNOSTIC_ONLY`다. 여기서 얻은 수치(분산, 상관길이, 편향, 표 값)는 G1-MODEL-003의 모수로 옮기지 않는다. 이 사양의 결과는 G1-MODEL-003의 **arm 우선순위와 S2 특성화 항목**을 정하는 데만 쓴다.

실행 전 현황과 근거는 [G1-DIAG-003 계획](DIAG003_PLAN_KO.md)에 기록한다.

## 0. 이 검증의 목적

**목적: 새 RT에서 확인하기 전에, 기존 데이터로 "integrity와 정확도를 함께 얻을 수 있는 구조"의 후보를 하나로 좁힌다.** 결과는 BLOCK_C 안에서 모수를 맞춘 in-sample 결과라서 Goal 1의 판정이 아니다. 판정은 G1-MODEL-003이 새 RT의 봉인 데이터에서 한다.

원래 J4(백색 R)는 Full RF·mount 0에서 heading 7.5°, 95% 포함률 16%였다. 같은 조건의 DR은 B0 0.48°, L0 1.69°, L1 6.59°, L2 24.97°다. 아래 세 가설을 시험한다.

| 가설 | 내용 | 시험 | 기각되면 |
|---|---|---|---|
| H1 (integrity) | 실패 원인은 s 오차를 packet마다 독립인 백색 잡음으로 둔 것이다. 실제 s 오차는 이동거리와 yaw를 따라 상관되고, 오래 지속되는 성분을 가진다 | D4로 구조를 재고, D7(J-C)에서 포함률이 회복되는지 본다. D1–D3로 원인을 분해한다 | 상관 모형으로도 회복되지 않는다. 지속 평균 성분이 지배하면 Goal 1 범위에서는 분산을 키우는 것 외에 방법이 없다 |
| H2 (정보원) | s 평균은 편향되어 있어도, 회전 중 s가 변하는 모양(차분 정보)은 공통 편향의 영향을 덜 받는다. 상관 모형은 이 정보를 살리고 절대 수준의 정보는 덜 믿게 만든다 | D7에서 직진 구간과 회전 구간의 heading 갱신 기여를 나눠 본다. D4의 yaw 상관길이 ℓ_ψ를 잰다 | ℓ_ψ가 회전 폭보다 짧으면 편향이 yaw마다 달라 차분 정보도 오염된다. 정확도 바닥이 생긴다 |
| H3 (DR 대비) | integrity를 맞춘 구조가 DR보다 정확한 조건이 있으며, gyro bias 수준과 horizon으로 표현된다 | D7을 B0/L0/L1/L2 × 부호 ±로 실행하고 DR과 짝 비교한다 | 어떤 수준에서도 우위가 없으면 BLOCK_C 기준 Goal 1 정확도는 불성립이다 |

### 0.1 예상 결과와 그 의미 (사전 기록)

| 결과 | 의미 | G1-MODEL-003으로 넘기는 것 |
|---|---|---|
| J-C에서 integrity 회복 + L1 이상에서 DR 우위 | 상관 오차 모델이 1차 구조 | J-C(또는 J-CS)를 1차 후보로, ℓ_d·ℓ_ψ·σ_b(ρ)를 S2 특성화 필수 항목으로 |
| J-C에서 integrity 회복 + 모든 수준에서 DR 대비 우위 없음 | 정직한 모델에서는 편파 정보가 약하다 | 정확도 주장 범위를 사전에 좁히고 S2-F를 엄격히 적용 |
| J-C에서도 미회복, D3 큰 창에서만 회복 | 지속 평균 성분이 지배 | Goal 1의 한계로 기록. +K(consider) arm 필수, 정확도는 DR 수렴 예상 |
| J-V(분산만)로 회복 | 상관보다 크기 문제 | J-V를 1차 후보로 |

### 0.2 세부 질문

| Q | 질문 |
|---|---|
| QA1 | 원래 J4(백색 R)의 Full RF integrity 실패는 **packet 간 상관을 독립으로 센 것**인가, **경로 길이만큼 지속되는 s 평균 편향**인가, 둘 다인가? |
| QA2 | s 오차 e_MP = s_full − s_LoS의 공간 구조는 어떤가? 이동거리 상관길이, 회전(yaw) 상관, 장거리(≥ 5 m) 평균 성분의 몫은? |
| QA3 | range만 쓰는 4-state(R4) 대비 J4의 차이, 즉 편파의 순수 기여는 얼마인가? |
| QA4 | 분산만 키우는 Goal 1 처리(거리 의존 편파 분산, MB_VAR의 분산 부분)로 integrity가 회복되는가? |
| QA5 | 오차 상관을 상태로 표현한 구조(J-C)에서 integrity가 회복되는가? 회복된다면 DR 대비 정확도는 어느 bias 수준부터 앞서고, 그 정보는 직진과 회전 중 어디에서 오는가? |

## 1. Goal 1 경계 (연구자 확정, 2026-11-14)

| 허용 (Goal 1) | 제외 (Goal 2) |
|---|---|
| ranging multipath 완화: 첫 경로 검출 규칙, range 평균 보정 | s 평균 편향 보정(μ_s 학습·차감, BB_ORIG/POWER 계열의 편파 평균) |
| 오차의 불확도 표현: 상관 상태, Schmidt/consider, 분산 스케일, 거리 의존 분산, 꼬리 | 반사 경로를 명시한 편파 관측 모델 |
| ranging 규칙을 **거리 오차만으로** 고르고 s를 그 tap에서 읽기 | 오염 감지에 기반한 s 가중·기각, heading/s 오차로 tap 규칙 선택 |

이 사양의 oracle 항목(D3)은 원인 분리용이며 어느 쪽 모델로도 채택하지 않는다.

## 2. 입력 (고정)

| 항목 | 위치 | 비고 |
|---|---|---|
| R2 EKF4 코드 | 실행 커밋 `81cdffbdedf43b318ebf8eddb4fcbac1fd30d878`의 `research/EKF4_RANGE_S_STAGED_20261014/` | S0는 원본 코드와 환경을 쓴다. D1–D6 arm은 회귀 확인 후 flag로 추가한다. |
| R2_aA 연속 주행 RF | Actions artifact `11782748118`의 PC·Snowball 보관본, SHA-256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63` | 실제 사용본의 ZIP 해시를 실행 전에 확인한다. |
| R2 결과 기준 | run `38664617622`의 원본 보고서. 결과 ZIP `11940333419` 만료 | §4 S0의 `REPORT_LEVEL_PASS`를 적용한다. |
| Anchor B JOINT4 | 실행 커밋 `5dd61292538c3e95858c9050a60c4d4ddb03a214`의 `research/PJ_SEPARATE_RS_20261020/experiment.py`, Actions run `39376076166` | 원본 매니페스트의 RF로 R4-B·R5-B를 재현한다. 결과 artifact `12243278686`(case별 `12243228864`, `12243741168`)은 아직 만료 전이므로 **즉시 내려받아 Snowball·LFS에 보관한다** |
| mount | **0°만** (연구자 결정). 원래 자료의 mount 45 행은 회귀 대조로만 재현하고 해석에 쓰지 않는다 | |

실행에 필요한 고정 RF, 코드, 관측 설정 또는 Anchor B 원본 입력·증거를 확보하지 못하면 `INPUT_MISSING`으로 중단한다. R2 기준 결과 ZIP의 만료에는 §4 S0의 보고서 수준 비교를 적용한다. 원본 생성 코드로 RF를 다시 만드는 것은 별도 승인 항목이다.

## 3. 공통 설정

- 추정기: 원래 4-state [x, y, ψ, b_g] 재귀 EKF, Joseph 갱신, heading wrap. gate는 원래 값(S: χ²₁ 99%, J: χ²₂ 99%).
- DR 시나리오: Sensor-v2 B0/L0/L1/L2 = 0, +0.01, +0.05, +0.20 °/s.
  - S0 회귀는 원래대로 sensor seed 0, 양의 부호만 쓴다.
  - D1–D7은 sensor seed 0–19와 부호 ±를 쓴다. 단, L 수준 정의는 바꾸지 않는다. 같은 RF에 대한 조건부 반복임을 결과에 표시한다.
- 평가: t ≥ 30 s. frame 지표와 함께, 고정 checkpoint(§3.1)에서의 ensemble 지표를 낸다.
- 지표: heading(1 dof), XY(2 dof), b_g(1 dof)를 따로 낸다. 각각 RMSE, 평균 NEES, 명목 95% 포함률, gate 기각률을 낸다.

### 3.1 checkpoint와 독립 단위

- checkpoint는 경로를 따라 1 m 간격으로 둔다(시각은 가장 가까운 frame).
- 독립 단위(site): 1 m 구간. 같은 site 안의 checkpoint는 하나의 군집으로 본다.
- CI는 sensor seed와 site를 함께 재표집하는 2단계 bootstrap(B = 2,000)으로 낸다.

## 4. 진단 항목

### S0. 회귀 재현 (선행, 실패 시 전체 중단)

R2의 원본 RF ZIP SHA-256을 확인하고 커밋 `81cdffb`의 코드·환경·동결 워크플로로 서로 다른 출력 폴더에서 두 번 실행한다. 새 프레임별 수치 산출물(x, P, 참조 상태 및 관측·gate 로그 등)은 생성 시각·경로를 담은 실행 메타데이터와 구분한다. 대응하는 프레임별 수치 NPZ와 두 점수 CSV(`R2_BIAS_METRICS.csv`, `R2_BIAS_CONTRASTS.csv`)의 파일 바이트가 두 실행에서 같아야 한다. 시각이 포함된 `FINAL.json` 등 실행 메타데이터는 실행별로 보존한다. 바이트 비교 대상과 각 SHA-256을 남긴다. R2는 원본의 979개 전체 프레임과 `t ≥ 30 s`의 829개 평가 프레임을 맞춘다. 센서 seed는 0이며, bias는 B0 및 양의 L0/L1/L2를 사용한다. Anchor B는 별도 원본 입력과 실행법에서 B0 Full mount 0° JOINT4를 확인한다.

| 항목 | 원본 기준 |
|---|---|
| R2_aA B0 DR-only x·P | 입력 RF ZIP에 동결 기준 x·P가 있으면 최대 차이 **0**을 요구한다. 기준이 없으면 해당 없음(`N/A_REFERENCE_ABSENT`)으로 기록한다. |
| R2_aA mount 0° DR L0/L1/L2 heading RMSE | 1.69 / 6.59 / 24.97° |
| R2_aA mount 0° J4 LoS L0/L1/L2 heading RMSE | 0.50 / 0.40 / 0.24° |
| R2_aA mount 0° J4 Full L0/L1/L2 heading RMSE | 7.50 / 7.54 / 7.52°. B0 대조는 7.49°다. |
| R2_aA mount 0° J4 Full L2 | heading RMSE 7.521°, 명목 95% 포함률 16.3%, 평균 heading NEES 86.37 |
| Anchor B JOINT4 Full B0 mount 0° | R4-B heading RMSE 1.323° / 포함률 40.0%, R5-B 2.541° / 22.1% |

R2_aA의 L2 최종 gyro bias 추정은 원본 표의 네 조건에서 S4와 J4의 posterior 평균·표준편차를 맞춘다. 단위는 °/s다. mount 45°는 S0 회귀 대조에만 쓴다.

| mount / RF | S4 b̂ ± σ_b | J4 b̂ ± σ_b |
|---|---:|---:|
| 0° / LoS | +0.1953 ± 0.0039 | +0.1996 ± 0.0022 |
| 45° / LoS | +0.1989 ± 0.0033 | +0.2017 ± 0.0019 |
| 0° / Full | +0.1041 ± 0.0050 | +0.2087 ± 0.0026 |
| 45° / Full | +0.2065 ± 0.0036 | +0.1993 ± 0.0019 |

R2는 모든 적용 가능한 항목이 원본 보고 자릿수까지 일치하고 두 재실행이 바이트 단위로 일치할 때 `REPORT_LEVEL_PASS`다. 과거 R2 결과 ZIP과의 프레임별 일치 여부는 미검증으로 기록한다. Anchor B도 원본 보고 자릿수까지 모두 일치해야 S0 전체가 통과한다. Anchor B 원본 프레임 자료가 있으면 참조와 대조한다. 적용 항목에서 하나라도 불일치하면 `FAIL`을 기록하고 D1–D6을 중단한다.

### D1. heading 오차의 평균 편향과 시간 상관 분해 (QA1)

- J4 Full의 갱신 전 s·range 혁신에 대해 프레임·이동거리별 자기상관과 유효 쌍 수를 보고한다. $F=1+2\sum_{\tau\ge1}\rho(\tau)$는 표본평균의 분산 팽창 참고값으로 남긴다. 실측 heading NEES는 별도 지표로 보고한다.
- case·bias 수준·부호별 동일 평가 checkpoint에서 wrap된 heading 오차의 평균 $\bar e_\psi$, 편향 제곱 $B=\bar e_\psi^2$, 중심화 분산 및 $\operatorname{mean}(e_\psi^2)=B+\operatorname{var}(e_\psi)$를 기록한다. 표본평균과 제곱평균에는 같은 가중치와 분모를 쓴다. 서로 다른 부호나 case의 편향을 합쳐 상쇄시키지 않는다.
- 시간 상관이 heading에 전달되는 정도는 참 pose에서 계산한 range·s 관측 오차와 J4 기준 재귀에서 기록한 상태 전이·Jacobian·이득·수용 mask를 사용해 고정 선형화에서 평가한다. 같은 프레임 내 range–s 공분산을 유지한다. 각 checkpoint에서 관측 오차의 heading 전달 민감도를 행벡터로 모아 $G$로 두고, 관측 오차 공분산 $\Sigma$의 전달 분산 $G\Sigma G^\top$을 계산한다. $\mathcal V_\text{full}$은 시간 간 교차공분산을 포함해 전달한 분산, $\mathcal V_\text{diag}$는 서로 다른 프레임의 교차공분산만 0으로 둔 분산이다. 동일 checkpoint와 가중치를 쓰고 초기 상태·과정 잡음 조건도 두 계산에서 동일하게 둔다. RF는 경로 안에서 시간 의존성을 추정하며 sensor seed를 독립 RF 반복으로 세지 않는다.
- 실측 heading MSE의 세 항목은 편향 제곱 $B$, 시간 교차항 $C=\mathcal V_\text{full}-\mathcal V_\text{diag}$, 나머지 $\operatorname{var}(e_\psi)-C$다. 세 값의 합과 실측 MSE를 대조한다. 나머지에는 같은 프레임의 관측 오차, DR·초기 상태, 선형화 오차 등 미분해 성분이 포함될 수 있다. 두 전달 분산, 실측 분산과 전달 분산 간 차이, 표본 수 및 교차항 부호를 함께 낸다.
- 세 항목 중 실측 heading MSE의 **60% 이상**을 차지하는 항목이 하나면 그 항목을 주원인 후보로 기록한다. 해당 항목이 없으면 `혼합`이다. 시간 교차항이 음수면 상쇄 효과를 부호와 함께 기록한다. 음수 성분 때문에 60% 이상인 항목이 여러 개이거나 나머지 분산이 음수인 경우, MSE가 0인 경우, 공분산 추정이 성립하지 않는 경우는 `유보`로 기록한다. 수치 검산에서는 시간 간 교차항이 없는 입력에서 $C=0$이 되는지 확인한다.

### D2. s 갱신 솎기 (QA1)

- 원래 packet 번호 i를 기준으로 `i mod m = p`에서만 원래 J4 range·s 공동 갱신(χ²₂ 99%)을 쓴다. m은 1, 2, 5, 10, 20, 50이며 p = 0, …, m−1을 모두 계산한다. s를 건너뛴 packet은 range-only 갱신과 χ²₁ 99% gate를 적용하고 원래 R의 range 분산을 쓴다. 유지한 packet의 공동 gate가 거부한 경우에는 원래 J4 처리를 따른다. range 관측 기회, RF, 센서 난수, 초기값과 평가 checkpoint를 고정한다.
- 위상별로 heading RMSE·포함률·NEES, range와 s의 제안·수용 갱신 수를 보고한다. m별 결과는 각 위상의 지표를 같은 가중치로 평균하고 위상별 범위를 같이 낸다. m=1, p=0에서 동결 J4를 재현한다. 위상 수를 독립 RF 표본 수에 포함하지 않는다.
- 상관길이에 대응하는 갱신 간격에서 위상 평균 포함률이 0.90 이상이면 상관된 갱신 반복 가설을 뒷받침하는 지표로 쓴다. m=50에서도 0.80 미만이면 회복 부족을 기록한다. 솎기는 s 정보량과 range gate를 함께 바꾸므로 D1·D3, RMSE와 실제 수용 횟수를 함께 해석한다.

### D3. oracle 평균 제거 (QA1, 원인 분리 전용)

- D4와 같은 잡음 없는 $e_\mathrm{MP}$의 이동거리 평균 $\bar e_W$를 s 관측에서 뺀다. W는 중심 창의 전체 폭이며 최소 2 m를 적용한 유효 집합은 **2, 5, 10 m**다. 초판의 1 m 항목은 이 하한에서 2 m와 겹친다.
- 누적 이동거리 $u$에서 $[u-W/2, u+W/2]$를 경로 범위로 자른다. 끝에서 폭이 2 m보다 작으면 경로 안쪽 방향으로만 2 m까지 늘린다. 유효 경로 길이가 2 m 미만이거나 창 안에 유효 pose가 없으면 해당 조건을 미평가로 기록한다. 같은 pose의 반복 packet은 창마다 한 번만 센다. pose 키는 원본의 위치 좌표와 wrap한 yaw이며, 같은 위치의 서로 다른 yaw는 개별 pose로 둔다. 평균과 실제 창 폭, 유효 pose 수를 기록한다.
- D2의 모든 m·위상에서 같은 범위, RF·센서 난수, 초기값 및 원래 갱신 기회를 써서 제거 전후를 짝 비교한다. m=1이 원래 J4 대조다. range 관측과 잡음·공분산 설정을 유지하고, oracle 보정이 공동 gate 결과에 미친 변화도 집계한다. W별 RMSE·포함률·NEES 및 수용 갱신 수를 보고한다. 작은 W에서만 회복되면 단거리 성분에, 5–10 m에서도 회복이 남으면 장거리 지속 성분에 부합하는 증거로 사용한다.
- 참 pose의 LoS를 쓰는 oracle 개입은 원인 분리용이다.

### D4. e_MP의 공간 구조 (QA2)

- 전 프레임에서 $e_\mathrm{MP}=s_\mathrm{full,clean}-s_\mathrm{LoS,clean}$을 계산한다. 잡음 없이 같은 첫 경로 tap 규칙을 적용한다.
- 이동거리 variogram과 지수 적합 상관길이 $\ell_d$, 회전 구간의 yaw 변화 대비 상관, 유효 표본쌍 수를 낸다.
- D3의 5 m 창과 같은 끝 처리·pose 중복 제거로 $\bar e_{5m}$을 계산한다. 같은 유효 평가 pose와 가중치로 $e_\mathrm{MP}$ 및 $\bar e_{5m}$의 signed 평균·중심화 분산·0 기준 제곱평균을 기록한다. 중심화 분산비 $V_\mathrm{long}=\operatorname{var}(\bar e_{5m})/\operatorname{var}(e_\mathrm{MP})$와 0 기준 제곱평균비를 모두 보고한다. 분모가 0인 비율은 미정의로 기록한다.
- heading 환산 바닥은 $\sigma_{\psi,\mathrm{floor}}=\sqrt{\operatorname{mean}(\bar e_{5m}^2)}/\operatorname{median}|\partial s/\partial\psi|$로 계산한다. 동일 평가 pose의 LoS 관측 Jacobian을 쓰며, 각도 단위 변환 및 기울기 분포를 기록한다. 분모가 0이면 미정의로 보고한다. 이 환산값은 D4 진단 지표로 사용한다.
- D7 입력용으로 다음을 추가로 낸다.
  - yaw 상관길이 ℓ_ψ: 회전 구간에서 yaw 변화량 대비 e_MP 상관의 지수 적합
  - 거리 의존 크기 σ_b(ρ): 수평거리 절점 0, 1.5, 3, 6, 10 m에서 e_MP의 RMS, 구간 선형
  - range 잔차의 이동거리 상관길이와 분산
  - 직진·회전 구간별 |∂s/∂ψ| 분포
- R2_aA, R2_aB, R4_aB, R5_aB별로 낸다. RF가 없는 case는 미평가로 표시한다.

### D5. range-only arm (QA3)

- 같은 4-state에서 range만 갱신하는 R4 arm을 추가한다.
- J4 − R4의 heading·XY RMSE 차이와 포함률 차이를 bias 수준별로 낸다.

### D6. 거리 의존 편파 분산 (QA4)

- J4에 MB_VAR의 분산 부분만 넣는다: R_s ← R_s + σ_b(ρ)². 원래 표(0.011/0.020/0.050/0.120/0.240 at ρ = 0/1.5/3/6/10 m)를 쓴다.
- μ_s(편파 평균 보정)와 range 평균 교체는 넣지 않는다.
- 원래 표는 BLOCK_C mount 0/B0에서 in-sample로 정한 값이다. 그래서 이 결과는 "in-sample 분산으로도 회복되는가"의 상한 진단이다.
- 출력은 D5와 같은 표다.

### D7. 상관 오차 상태 J-C (QA5, 구조 시험의 핵심)

- 상태를 [x, y, ψ, b_g, c_s, c_r]로 확장한다.
  - c_s: 편파 오차 상태. packet 사이 전이 φ = exp(−Δd/ℓ_d − |Δψ|/ℓ_ψ), 정상 분산 σ_b(ρ)², 과정잡음 σ_b(ρ)²(1 − φ²)
  - c_r: range 오차 상태. 같은 형식이며 상관길이와 분산은 D4의 range 잔차 값
  - 관측: s = h_s(x, y, ψ) + c_s + ε_s, r = h_r(x, y) + c_r + ε_r. ε는 원래 열잡음 분산
- 모수(ℓ_d, ℓ_ψ, σ_b(ρ), range 상관)는 D4 값을 그대로 쓴다. in-sample이며 BLOCK_C 안에서만 해석한다.
- 변형 J-C+K: D4의 0 기준 제곱평균(ē_5m²)을 분산으로 하는 consider bias를 추가한다. 추정하지 않고 교차공분산만 유지한다.
- 수치 검산: ℓ_d, ℓ_ψ → 0이면 J-V(D6, D4의 σ_b(ρ) 사용)와, σ_b → 0이면 J4와 같은 결과가 나오는지 확인한다.
- 출력:
  - §3 지표 전체를 bias 수준 × 부호 × seed로 낸다
  - DR, R4, J4, J-V와 같은 checkpoint에서 짝 비교(heading·XY RMSE 차이와 CI)
  - heading 갱신량 Σ|K_ψ ν|를 직진 구간과 회전 구간으로 나눠 낸다
  - D1과 같은 오차 분해를 J-C에도 적용한다

## 5. 해석 규칙 → G1-MODEL-003에 주는 영향 (사전 고정)

| 결과 | G1-MODEL-003 영향 |
|---|---|
| D1 시간 교차항이 60% 이상이며 D2·D3가 상관된 반복 사용 가설에 부합 | J-C(유색 잡음 상태)와 J-CS(Schmidt site 기억)의 특성화 우선순위를 높인다. |
| D1 편향 제곱이 60% 이상이며 D3의 큰 W 제거에서 회복하고 D2도 이 해석에 부합 | 장거리 평균 성분 가설을 지지한다. G1-MODEL-003 S2-F에서 이 성분을 우선 특성화한다. |
| D1–D3 결과가 엇갈리거나 gate·수용 갱신 수 변화로 기전 분리가 어려움 | 원인 귀속을 유보하고 관측된 결과를 각각 보고한다. |
| D6에서 포함률 ≥ 0.90 회복 | 거리 의존 분산 arm(J-V)이 1차 후보에 오른다 |
| D6에서도 < 0.80 | J-V는 대조군으로만 둔다 |
| D5에서 J4 − R4가 0을 포함 | 편파의 순수 기여가 BLOCK_C에서 확인되지 않음. G1-MODEL-003 정확도 판정에서 J − R4를 필수 항목으로 둔다 |
| D4의 0 기준 heading 환산 바닥이 같은 평가 조건의 DR RMSE보다 큼 | 해당 bias 수준을 G1-MODEL-003 S2-F의 우선 검토 항목으로 기록한다. |
| D7(J-C)의 pooled heading 포함률 ≥ 0.90, heading·XY·b_g 평균 NEES ∈ [0.5, 2.0] | H1 지지. J-C를 1차 구조 후보로 |
| D7 미회복, J-C+K에서 회복 | 지속 평균 성분 표현이 필요. +K를 1차 후보에 포함 |
| D7·J-C+K 모두 미회복 | Goal 1 범위의 구조로 integrity를 얻지 못함. G1-MODEL-003 착수 전 구조 재검토 |
| D7 heading 갱신량의 70% 이상이 회전 구간 | H2 지지. MODEL-003에서 직진·회전 기여 보고를 필수로 |
| ℓ_ψ가 회전 구간 yaw 폭의 절반보다 짧음 | H2 약화. 회전 구간에도 정확도 바닥이 생길 수 있음 |
| D7이 integrity를 만족한 bias 수준에서 DR 대비 paired heading RMSE CI가 0 아래 | H3 지지(그 수준). MODEL-003 정확도 판정의 우선 수준 |

## 6. 출력

`research/G1_PACKET_EKF_20261114/DIAG_A/` 아래:

```text
code/          (복사 코드, CODE_SHA256.txt)
out/S0_REGRESSION.json  (판정 수준, 보고서 대조, 두 재실행 바이트 비교, 적용/N/A 항목)
out/D1_AUTOCORR.json  …  out/D6_DISTVAR.json  out/D7_JC.json
out/checkpoint_rows.csv  (case, bias, sign, seed, arm, checkpoint, site, 오차·P·포함 여부)
REPORT_KO.md   (§0.1과 §5 표 채움, 첫 줄 DIAGNOSTIC_ONLY)
MANIFEST.json  (입력 SHA, 명령, seed, 시각, 패키지)
```

## 7. 실행 순서

S0 전체 통과 → D4(필터 없이 관측만) → D5 → D6 → D7 → D1 → D2 → D3. D3 창·중복 처리와 D4의 0 기준 RMS를 D4 시작 전에 적용한다.

## 8. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-14 | 초판. 추정기 불일치 확인 후 packet 단위 EKF 기준으로 기존 데이터 진단을 재정의. Fable 2026-11-14 답변의 C1–C3를 D1–D3로 반영 | Claude |
| 2026-11-14 | 실행 전 개정. S0 REPORT_LEVEL_PASS, D1 60% 분해, D2 전 위상과 range-only gate, D3 최소 2 m 창과 반복 pose 처리, D4 0 기준 RMS, 기전 판정 유보를 반영. | Codex |
| 2026-11-14 | 목적과 가설 H1–H3·예상 결과(§0), QA5, 구조 시험 D7(J-C, J-C+K)과 해석 규칙 추가. D4에 D7 입력(ℓ_ψ, σ_b(ρ), range 상관) 추가. Anchor B artifact 즉시 보관 명시 | Claude |
