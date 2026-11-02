# 02. 물리 관측구조와 성능 사이의 검증 명세

계약 `DLP-PHYS-LINK-001`, status **PROPOSED / ALL_NOT_RUN**. 이 파일은 구현 명세이며 구현 코드가 아니다.

## 공통 데이터·분모·수식
RF의 기본 단위는 `(rf_source_sha,scene_id,route,anchor,mount,pose_id,time)`이다. 추정기 단위에는 `(gyro_condition,sensor_seed,arm,gate,prior_reference)`를 추가한다. full trajectory packet은 R2-B 979, R4-B 742, R5-B 1415(3,136 RF rows), gyro 반복을 포함하면 12,544 condition-packet rows다. 실제 입력 키와 일치하지 않으면 숫자를 맞춰 자르지 말고 BLOCKED_INPUT으로 보고한다.

분모는 ①전체 유한 시간축 ②t>=30 유한 관측 ③t>=30 고정 BASE 수용집합 ④각 arm 실제 self 수용집합 ⑤stable branch 진단 부분집합으로 분리한다. 기존 B0 표의 ③은 R2 822/R4 578/R5 1236이며, ①의 ACF 분모와 혼합하지 않는다.

`epsilon=z-h(x_GT)-mu`, `delta_h=h(x_GT)-h(x_prior)`, `nu=epsilon+delta_h`. 오차 제곱에는 mean²와 cross 항이 있으므로 RMS를 centered variance로 부르지 않는다. Full–Direct 전파 차이와 Direct–surrogate 차이를 별도로 기록한다. H_RF(복소채널)와 J(상태 Jacobian)는 다른 기호로 유지한다.

## V0 — 입력 계보·기계적 parity (출처 및 수학 preflight)
원고 v4/SourceFFD/diag_mbvar/exp_pb/core/source bank/학습예측 파일의 정확한 commit·blob·sha256을 잠근다. 원본 12조건의 BB_ORIG/MB_ORIG/BB_VAR/MB_VAR, fixed/self 결과와 source packet을 같은 키로 대조한다. 출력 CSV 반올림 수치의 재현성과 full x/P parity를 구분한다. 원본 full trace가 없으면 독립 legacy 재생으로 baseline을 만들고 그 출처·새 실행을 명시하며, CSV만 보고 상태 parity PASS라고 하지 않는다.

필수 음성 시험: H 또는 packet byte 변조, duplicate/missing key, +/- port 교환, 1 packet 시각 이동, sigma=0, mu_M=mu_B, full finite count=0. frozen source를 바꾸지 않는 격리 fixture로 검사한다. baseline score는 모든 기존 조건을 기록하고 상태 차이가 처음 발생한 packet을 남긴다.

결과: `SOURCE_LOCK.json`, `CASE_LEDGER.csv`, `BASELINE_PARITY.csv`, `NEGATIVE_FIXTURES.json`, `PREFLIGHT_REPORT.md`. 신규 과학 관계 분석은 이 단계에 섞지 않는다.

## V1 — 실제 Dual-LP의 물리 민감도와 잔차
### 질문
거리·방위·자세·포트 power와 J_spsi의 변화가 선택 세 경로의 signed 편파 잔차 및 Heading 갱신에 어떻게 대응하는가? 모든 물리 원인을 한 번에 식별하지 않고, 지지되는 관계와 섞여 있는 관계를 구분한다.

### 연산
같은 complex FFD, source TX+45/RX±45, 257-bin fgrid, 같은 Hann·4N IFFT·공통 strongest-port 30% first-path extractor를 사용한다. LoS의 선택 tap과 Full의 선택 tap을 각각 보존한다. 각자의 선택값 차이와 공통 tap에서 비교한 차이를 두 열로 나눈다. 어떤 비교인지 숨긴 채 두 값을 다중경로 오차로 합치지 않는다.

`Pp=|gp|²`, `s=(P+-P-)/(P++P-)`이고 stable branch에서 `ds/du=2(P- dP+/du-P+ dP-/du)/(P++P-)²`, u=x,y,psi다. Range h_r와 기존 B_OLD, 편파 mean은 원본대로 유지한다. 새 fractional 거리 관측이나 세 번째 EKF 관측을 추가하지 않는다.

핵심 기록: port별 complex response 또는 기존 H 참조, power/total power/power imbalance, selected tap/strong port/margin, rho_true 및 rho_lookup, incidence/bearing/relative yaw, h_s, J_sx/J_sy/J_spsi, e_s_Full−Direct, Direct−surrogate, epsilon_s, source pole/branch 상태.

양쪽 포트·모든 주파수에 동일한 **주파수 독립** complex c를 곱했을 때 signed ratio 및 선택 tap 불변성을 시험한다. 사용 상수는 config 고정. Port swap은 s와 J_s의 부호만 바꾸는 음성/대수 시험이다. 이 시험을 현실의 공통 frequency-selective multipath에 대한 불변성으로 확대하지 않는다.

중앙차분은 source active branch를 확인한다. 전체 valid stable packet을 평가하고 정해진 FD 후보 subset만으로 source math를 검산할 수 있다. FD steps와 half-step, abs+rel tolerance는 config를 사용한다. branch switch·pole·near-zero power는 별도 분모와 원값을 보존하며 실제 필터의 수용집합에서는 제거하지 않는다. singular/cell boundary의 미분 실패를 전파 물리 실패라고 단정하지 않는다.

### 지표·정규화
J_spsi의 rad^-1 단위를 유지한다. `epsilon_s/J_spsi`는 위치를 안다고 가정한 국소 equivalent angle 진단으로만 사용하며 `|J_spsi|<0.05/rad`에서는 NA, 개수를 보고한다. 수치 cutoff는 변화시키지 않고 결과 후 민감도 변경은 amendment 대상이다.

물리 mean 민감도와 오류를 직접 Heading 성능이라고 부르지 않는다. 전 상태 정보는 같은 prior의 precision `Lambda=P^-1+J^T R^-1 J`에서 nuisance n=(x,y,b_g)를 Schur 제거한 `Lambda_eff,psi=Lambda_psipsi-Lambda_psin Lambda_nn^-1 Lambda_npsi`로 계산한다. data-only 정보행렬은 2관측/4상태라 singular할 수 있으므로 역행렬을 강제로 만들지 않는다. 혼합 단위의 raw condition number 대신 config scale로 정규화한다.

결과: `PHYSICS_PACKET_LEDGER.parquet`, `GEOMETRY_SENSITIVITY.csv`, `BRANCH_TRANSITION_LEDGER.csv`, `FFD_FD_CHECKS.csv`; 그림 F1의 직접 증거. 주파수·거리 bin과 축 의미를 figure manifest에 포함한다.

## V2 — 같은 prior의 평균×분산 shadow update
### 질문·통제
R2-B에서는 평균 단독의 Heading 악화를 결합모델이 어떻게 바꾸는가? R5-B에서는 평균 단독 이득에 분산이 어떤 추가 이득을 주는가? R4-B에서는 왜 분산 단독보다 결합이 불리한가?

Primary reference는 각 조건의 original BB_ORIG trajectory이다. 같은 `x_(k-1)^+,P_(k-1)^+`에서 원본 motion을 예측한 `x_k^-,P_k^-`, 같은 z/h/J/R_B/control을 모든 2×2 cell에 공급한다. **lookup rho는 같은 이전 posterior**에서 계산한다. k=0 lookup은 원본 초기 상태다. Secondary MB_VAR prior 기준 반복은 해석 민감도이며 primary를 대체하지 않는다.

4개 shadow cell=(mu_B,lambda0),(mu_M,lambda0),(mu_B,lambda_lookup),(mu_M,lambda_lookup). 예측된 mu는 원래 packet-keyed 파일의 값으로 고정하고 새 state-dependent regression derivative를 슬쩍 넣지 않는다.

### 대수와 산출
`S=J P^- J^T+R`, `K=P^-J^T S^-1`, Joseph P로 계산한다. 같은 prior에서 `K_lambda e_s=(K0 e_s)/(1+lambda e_s^T S0^-1 e_s)`를 검증한다. 이 항등식은 편파 gain column의 축소이지 정보 증가·최종 개선의 보장이 아니다. offdiagonal innovation 때문에 range-column도 달라질 수 있다.

기록: 모든 K 요소, nu_r/nu_s, `K[:,r]*nu_r`와 `K[:,s]*nu_s`, immediate wrapped Heading/XY squared-error change, NIS 및 shadow gate decision, posterior x/P, delta signed correction. Truth는 effect scoring에만 사용한다. RF projection `K*epsilon`와 prior projection `K*delta_h`를 분리하고 합=Knu를 검산한다.

일차 효과는 **same prior + fixed accepted keys**에서 산출한다. self-NIS shadow 결과는 gate가 바뀔 가능성 진단이며, actual self recursive 결과와 별도 저장한다. 고정 mask 전체 재생과 own self 재생은 4-arm 원본과 동일해야 한다. 같은 모형이 아닌 학습·Q·sensor 변경은 금지한다.

`interaction=L_MB_VAR−L_MB_ORIG−L_BB_VAR+L_BB_ORIG`는 같은 packet/상태의 사전 정의 loss 및 최종 점수에 각각 기록한다. 최종 RMSE interaction을 packet별 인과 비율의 합으로 해석하지 않는다. 즉시 gain 기여 합이 최종 오차기여 합과 같지 않음을 표시한다.

결과: `MATCHED_PRIOR_2X2.parquet`, `ONE_STEP_LOSS_CONTRASTS.csv`, `FIXED_SELF_TRACE_INDEX.json`, `FIRST_DIVERGENCE.csv`, `RECURSIVE_12x4x2_SCORES.csv`; 그림 F2와 R4-B 설명의 근거.

## V3 — 거리 lookup의 추가 가치: zero/constant/lookup
### 상수의 사전 정의
held route r의 학습집합은 **나머지 두 anchor-B route**다. 원래 평균 회귀의 학습집합과 혼동하지 않는다. B0 original BB trace의 t>=30 유한 관측 전체에서 이전 posterior rho_lookup를 사용한다. 각 route의 평균 lambda를 같은 가중치로 합쳐

`lambda_const^(r)=mean_over_two_train_routes(mean_k sigma_hand(rho_lookup,k)^2)`

를 정한다. **평균 sigma를 제곱하는 방식이 아니다.** 같은 상수는 held route의 B0/L0/L1/L2 전체에 적용한다. 평가 점수·평가 거리분포에 맞춰 상수를 고르지 않는다. 기존 hand lookup 자체는 역사적으로 in-sample 설계였으므로 이 대조를 prospective test라고 부르지 않는다.

2 mean ×3 variance {zero,constant,lookup} ×2 gate ×12조건 =144 traces. 기존 zero/lookup 96개를 재사용하면 추가 replay는48개다. R_B와 mu_s, mean prediction, f/F/Q, seed, gate threshold는 동일하다. 평균 fit을 다시 학습하거나 lookup knots를 변경하지 않는다.

### 분석
일차는 `MB_LOOKUP−MB_CONST`의 Heading RMSE와 XY RMSE, 두 단독 모델 비교, 12조건 전수 결과다. fixed BASE는 가중치 효과의 진단, self는 시스템 효과다. NIS/NEES/coverage·수용수·최대 미갱신 구간을 병기한다. branch eligibility 추가 금지. lambdaConst의 train route·표본수·값·hash를 score 이전에 기록한다.

lookup이 우수한 결과만 선택하거나 새 상수를 찾아 재시험하지 않는다. 결과가 같으면 generic down-weighting 설명을 유지하고 거리 특별성은 미지지로 보고한다. R4-B는 결과가 약하더라도 제거하지 않는다.

결과: `CONSTANT_VARIANCE_TRAIN_LOCK.json`, `ZERO_CONST_LOOKUP_12_CONDITIONS.csv`, `MASK_POLICY_EFFECTS.csv`; 그림 F3 및 Table3/4 보완.

## V4 — 선택적 투영 상관과 누적 효과
raw ACF는 원래 전체 시간축 통계를 먼저 재현한다. 무효 packet을 빼고 양끝을 붙여 새로운 연속 시간축으로 만들지 않는다. 실제 시간간격과 끊김을 기록한다. 추가 조건부 평균제거는 source routes에서만 적합한 사전 정의 mean을 사용하고 sparse bin은 NA로 남긴다. 새 상관모형을 재귀 필터에 적용하지 않는다.

같은 pose/yaw/anchor/mount 재방문이 없으면 공간 field와 독립 시간 drift의 구분은 NOT_IDENTIFIABLE다. dt lag에 거리만 붙인 표를 새로운 spatial kernel로 부르지 않는다.

`a_k=K_psi,r epsilon_r+K_psi,s epsilon_s`의 signed mean 및 자기상관과, 고정 선형화 reference에서 이후 closed-loop transition을 반영한 `G_(T,k) epsilon_k`의 누적항을 분리한다. 비선형 실제 replay와 선형 근사 closure 오차를 보고한다. lag1 또는 AR1 n_eff를 EKF Fisher 손실계수로 그대로 쓰지 않는다. 시점간 covariance·mean²·cross 항을 필요 범위에 보고하되 single path를 독립 반복 실험으로 세지 않는다.

## V5 — 학습–예측–재생 연결
원고 source의 fold/scaler/coefficients/features와 EXDS prediction hash, 보존 CONTROL의 mu_B/mu_M 관계를 잠근다. 대수 복원 예측과 실제 회귀 inference의 일치 여부를 별도 판정한다. 모델 파일이 없으면 archived-replay만 PASS, fresh-inference는 BLOCKED_MISSING_MODEL이며 새 학습으로 조용히 대체하지 않는다. 선택 seed0를 재현한 것과 multi-seed 통계적 유의성은 분리한다.

## 결과 공통 규약
항상 `status_technical`, `verdict_scientific`, `run_id`, `source/input/config_sha`, `case`, `bias`, `mask`, `t_window`, `n_all/n_finite/n_used/n_stable`, `role_of_truth`를 남긴다. 기계 QA 실패는 과학 반례와 구분한다. 모든 observed degradation·무효·미실행 이유도 결과 표에 보존한다. 결과 사용 규칙은 04 문서에 따르며, 새 결론은 독립 감사 후에만 원고에 반영한다.
