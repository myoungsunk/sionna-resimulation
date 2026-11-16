# G1-INT-SIGNED-COV-001 — signed a_i a_j 기반 느린 편파 오차 공분산 검증 사양서

**상태: PROPOSER / PLAN_ONLY / NOT_RUN / DIAGNOSTIC_ONLY.** 본 문서는 물리적 잔차의 오프라인 기전 검증 계획이다. EKF를 새로 채택하거나 M7 Stage 1의 실행·판정을 변경하지 않는다. G-T2/G-V 봉인 유지, S2′ STOP 및 Step 3 HOLD 유지.

- 대상 저장소: myoungsunk/sionna-resimulation.
- 출발 기준: research/g1-sweep-heading-floor-spec-20261113, 커밋 c404b3901357c596dc886efae128d19bd3d397b1(2026-11-16). 이 문서의 commit SHA는 게시 후 고정한다.
- 데이터 1차: BLOCK_C R2/R4/R5 × anchor B × mount 0 × B0 Full, 기존 RF/LoS·truth 및 D3 진단 배열. anchor A, CHAR-001 RT G-T1의 TEACH/REPEAT·yaw sweep은 2차 독립 지원/기하 확인에만 사용한다.
- 기존 운영 M7은 별도 [PLAN_M7_FINAL_MODEL_STAGE1_KO.md](PLAN_M7_FINAL_MODEL_STAGE1_KO.md). 본 검증에 M7 점수를 사용해 공분산 모델을 선택하지 않는다.
- 기존 참고: [M6 K1′·K2](gm_theta_m6/characterization_tables/attempt_02/REPORT_KO.md), [M6 전체](gm_theta_m6/attempt_02/results/REPORT_KO.md), [D2/D3](continuation_d2_d3/REPORT_KO.md), [M1–M4](exposure_m1_m4/run_01/REPORT_KO.md), [Stage 0](final_model_stage0/REPORT_KO.md), [CHAR-001](../../../../CHAR_001/REPORT_KO.md).
- 지침: 기존 RESEARCH-GOVERNANCE-v1을 준수한다. source/evaluator/모형/모수 SHA는 실행 계약 동결 단계에 채운다. 계획 게시 자체는 실행 승인 아님.

## 0. 연구 질문과 반증 가능성

목적은 단순히 느린 분산의 로그 기울기 k=2 여부를 다시 검사하는 것이 아니다. **같은 기하·거리·시간상관 조건에서 잔차 쌍의 부호 있는 공분산이 signed a_i a_j에 따라 설명되는지**를 검증한다. 여기서 a_i = ∂h_s(x_i,y_i,ψ_i)/∂ψ [s/rad]이고 g_i=|a_i|이다.

- H_S (s 영역만): 잔차 공분산이 기하 및 경로상관 kernel K_s로 설명된다. a_i a_j를 추가해도 미지 자료의 설명력이 늘지 않는다.
- H_θ (heading 등가 공통 상태): 시간/이동/yaw 조건부로 C_ij의 일부에 θ·a_i a_j K_θ, θ=σ²_θ>0이 존재한다. a_i a_j<0인 쌍에서 동일 크기의 양수 쌍과 다른 부호 구조가 나타날 수 있다.
- H_|a| (unsigned 반증 대조): a_i a_j의 부호 없이 |a_i a_j| K_θ를 사용해도 똑같이 잘 설명된다. 이 경우 'signed heading형'으로 귀속할 증거가 부족하다.
- H_mix: θ·a_i a_j K_θ와 q_s K_s가 함께 필요하다. 두 성분이 통계적으로 식별되지 않으면 '혼합형이 증명됐다'고 하지 않는다.

**관측상 signed 연관이 있더라도 물리적 yaw 편향의 존재를 입증하는 것은 아니다.** 결정론적 복도 RF 공간장과 yaw/벽 기하가 공변할 수 있다. 이 연구의 최대 주장은 지정된 오차 정의·장면·지지 기하에서의 signed 공분산 구조에 대한 조건부 증거다.

## 1. 먼저 분리할 기존 사실과 경쟁 설명

| 기존 결과 | 지지하는 해석 | 아직 지지하지 않는 해석 |
|---|---|---|
| R4 B0 E0-LORO Heading95 21.7%, NEES3 17.97 | 현재 독립 갱신의 R4 과신 | R4의 원시 e_s가 모든 경로 중 가장 큼 |
| D3 B/B0 R4 느린 성분 제거: heading95 55.4→84.8%, RMSE 1.31→0.53°; 빠른 제거는 59.0% | 해당 국소 느린 성분이 과신과 연계 | D3 지원 480/742 밖 전체 인과 확정, 또는 anchor A로 이전 |
| R2/R5 E0-LORO Heading95 87.7/96.8%, R4 21.7% | 동일 필터의 궤적별 차이 | R2/R5의 시간상관 부재 |
| R5 0–20 s 적분 자기상관 9.62 packet | R5도 유색 잔차 존재 | R5가 백색이므로 성공 |
| K1′ 공통 k=0.329 [0.104,0.581]; R4 기술 k=2.381, 공통 기여 1.09% | 공통 g² 분산 크기 모델이 충분치 않음 | signed 쌍 공분산 H_θ의 반증 |
| K2 공통 지지 셀 0 | 궤적 공통 σ_θ 미식별 | 약 2°가 물리적으로 일정 |
| M6 G1 R4 회복, G1 R5 열화, G1+KI 일부 개선 | signed 적재를 사용한 EKF 구조의 운용 효과 | signed RF 오류 생성 기전의 증명 |
| Stage 0 centered residual/R_ref: R2 0–3 m 0.0698, R4 0.6542, R5 0.0738; 3–10 m 0.4372/1.1847/0.1738 | R_ref의 여유·기하 노출·상관이 필터 동작을 다르게 할 수 있음 | 주변분산 비만으로 누적 무결성 설명 |

CHAR-001의 5 m 창 '느린 공간장 3–14%'와 D3의 '국소 느린 성분 35.2%'는 다른 평활 척도이다. 두 지표를 같은 latent θ의 분산으로 취급하지 않는다.

## 2. 측정량, 진실값 사용 및 표본의 통계 단위

**2.1 물리적 1차 잔차.** CHAR-001 정의의 noise-free 동일 위치·동일 관측 체인 e_s,RF = s_full(O30) − s_LoS(O30)를 사용한다. 같은 pose_id·anchor·mount의 full/LoS tap 및 LoS 합성 parity를 검사한다. 데이터에서 noise-free RF와 thermal/noisy packet을 구분할 수 없으면 1차 증거를 대체하지 말고 UNSUPPORTED_INPUT으로 중단한다. packet noise가 있는 경우에는 별도 e_s,truth = z_s−h_s(x_true)−μ_MB,s로 계산하여 2차 외적 타당성 지표로 보고하되 noise-free 정의와 합치지 않는다.

**2.2 signed 감도.** a_i^truth = ∂h_s(x_true,i)/∂ψ는 source bank와 정해진 ψ·mount·좌표계로 계산한다. g_truth와 a_truth의 절댓값 일치, rad/deg 변환, SourceFFD 유한차분(ψ±0.1°,±0.01°) parity를 검사하고, tap 불연속 및 bank cell 경계의 비매끄러운 pose는 별도 수로 보고한다. M6의 a_ref=H_sψ(prior)는 **운용 가능성 진단**에만 사용하며 1차 물리 모형과 혼합하지 않는다. s/degree와 s/rad 단위 혼용 금지.

**2.3 D3 보조 잔차.** D3 지원 플래그의 slow_s 및 route_mean_s는 재현·기전 보조 통계다. D3 로컬 평균은 인접 창이 겹쳐, 독립 백색 오차에서도 산출물 자체가 양의 자기상관을 가질 수 있다. 따라서 slow_s의 직접 자기공분산을 '원시 RF에서 느린 공통 상태가 존재한다'는 단독 증거로 쓰지 않는다. 원시 e_s,RF로 1차 통계를 만들고, 백색 합성 입력을 D3 평활 알고리즘에 통과시킨 null 분포, 비중첩 창/교차 적합 진단을 필수 대조로 한다.

**2.4 독립성.** 다수 (i,j) 쌍은 원본 pose와 RF 실현을 공유한다. n_pairs는 독립 표본 수가 아니다. route×10 s 연속 구간을 최소 resampling cluster로 기록하고, 교차 경계의 쌍은 두 cluster 중 하나에만 귀속한다. 동일 RF 시뮬레이션의 wheel/gyro seed 10–14는 독립 RF 실현 수 증가가 아니다. TEACH↔REPEAT의 같은 위치 RF는 독립 학습/검증으로 나누지 않는다.

## 3. 고정 pair 및 커널 정의

- 1차 pair: 동일 route/anchor/mount 내 시간 간격 0.4–5.0 s; i<j, 둘 다 유효 물리 잔차와 signed a 존재. D3의 기존 지지 mask와 E0 gate는 '지원 조건의 민감도'로 각각 따로 집계하고 기본 물리 모집단에서는 gate를 사용하지 않는다.
- 주 거리 층: truth horizontal ρ ∈ [0,1.5), [1.5,3), [3,6), [6,10) m; 쌍 양쪽이 같은 층일 때만 같은 층 표로 집계한다. 3D d와 혼동하지 않는다.
- g 절댓값: 연속값을 유지한다. |a_i|·|a_j|의 분포와 pair sign ±를 보고한다. |a|<0.1 rad⁻¹를 1차 signed 식별 구간에서 제외하고, 전체값은 별도 민감도로 보고한다. 0.1은 식별을 위한 사전 탐색 하한이며 원래 K2의 1.0과 다른 기준이다.
- 기본 커널 K_θ,ij = exp(−|L_i−L_j|/1 m − |Y_i−Y_j|/rad(10°)); L은 누적 |ds|, Y는 누적 |Δψ|, 같은 route 시작점 기준. 진실값 궤적 누적으로 원시 기전 검사를 정의하고, 오프라인 진단에만 사용한다. 같은 시계열의 packet truth yaw와 wheel 누적 yaw 차이도 보고한다.
- s 영역 대조 K_s는 원칙적으로 같은 K_θ를 사용한다(가장 불리한 식별조건에서 signed a 차이만 평가). 보조로 0.5/2 m 및 yaw 5/20°에 대한 동결 sensitivity grid를 모두 보고하되 성능이 좋은 커널만 골라 판정하지 않는다.
- 2차 pair: 같은 RF 장면의 TEACH/REPEAT yaw sweep에서 signed sign-change가 있는 동일/인접 station pair를 별도 분석한다. 동일 pose 재방문은 한 RF site로 묶는다. BLOCK_C 진단과 G-T1 RT 진단을 섞어 하나의 p-value를 만들지 않는다.

## 4. 경쟁 covariance 모형과 식별성

각 시간 블록의 잔차 벡터 e에 대해 다음 대칭 행렬을 구성한다. D_white는 같은 관측 정의에서 독립 열잡음/양자화로 정해진 고정 대각 행렬이다. noise-free RF일 때 존재하지 않는 독립 관측 잡음 분산을 편의상 추가하지 않는다. 수치 계산용 nugget은 따로 표시하고 학습할 물리 분산으로 해석하지 않는다.

- **S0 (s 영역만):** C_0 = D_white + q K_s.
- **S1 (signed θ+s):** C_1 = D_white + q K_s + θ diag(a) K_θ diag(a), q≥0, θ≥0.
- **S2 (unsigned 대조):** C_2 = D_white + q K_s + u diag(|a|) K_θ diag(|a|), q≥0, u≥0.
- **S3 (heading형만):** C_3 = D_white + θ diag(a) K_θ diag(a). 비교용이며 s 영역 오차 부재 가정은 하지 않는다.

각 covariance는 모든 모수 및 반복에서 PSD여야 한다. kernel의 거리·yaw 정의는 1차원 누적 증가 좌표 차이의 Laplace kernel의 곱이며 PSD다. 비음수 계수와 diagonal congruence를 적용한다. e의 평균 보정은 각 donor의 학습 fold에서만 고정하며, holdout의 진실 평균을 빼는 oracle centering은 주 점수에 금지한다. donor별 평균·route 평균을 뺐을 때의 변화는 보조 민감도로 보고한다. 편파 μ_MB의 사용 유무는 물리 RF와 EKF truth residual 정의별로 분리한다.

적합은 한 번 정한 weighted covariance composite loss 또는 행렬 기반 Gaussian log-score 중 **실행 전 계약에 하나를 primary로 확정**한다. 권장 primary: held-out 연속 블록의 평균 log predictive score −0.5(logdet C + eᵀ C⁻¹ e + n log(2π)), 동일 블록 길이/잔차 정의/수치 nugget 사용. score는 packet 수로 나누고 route별 평균을 별도로 낸다. Gaussian 점수는 중꼬리·noise-free 실현의 예측 진단이지 진실 분포가 Gaussian이라는 선언은 아니다. 보조로 pair product의 signed contrast와 robust winsorized score를 낸다.

**수치 안정성:** D_white=0인 RF noise-free case에서 covariance가 특이하면 진단용 εI를 모든 arm에 같은 규칙으로 넣는다: ε=10⁻⁸ × max(median(diag(C_0)), 10⁻⁶). ε·condition number·Cholesky 실패 수를 기록하며 ε를 결과에 맞춰 키우지 않는다. 행렬 길이가 너무 길면 시간 블록 단위로만 평가하며 누락 packet을 선택적으로 제거하지 않는다.

## 5. 식별을 위한 필수 지원 검사 (점수 확인 전에 실행)

**사전 지원표:** 각 route×ρ층에서 (i) signed a 양/음 pose 수, (ii) signed a_i a_j 양/음 pair 수, (iii) 10 s cluster 수, (iv) |a_i a_j|·거리·yaw 차이 분포, (v) |a_i a_j|K_θ 열과 K_s 열의 표준화 설계 행렬 condition number를 계산한다.

- 1차 판별이 가능하려면 pair sign 양/음 각각에서 *최소 3개의 서로 다른 10 s cluster*, 각 sign에서 서로 다른 원본 pose를 포함한 pair ≥30, 두 sign의 ρ·|a_i a_j|·lag 분포가 공통 support로 match되어야 한다.
- sign이 한쪽만 존재하거나 매칭 후 한쪽 cluster가 3 미만이면 NO_SIGN_SUPPORT; 절댓값이나 규모만 사용한 분산 fit은 descriptive로 남긴다.
- S1과 S0 열이 사실상 공선성이면 (표준화 설계의 condition number >30) NON_IDENTIFIABLE이다. threshold는 실용적 식별 지원 문턱이며 검정 유의확률이 아니다.
- route-held-out fold에서 test의 거리×|a|×sign support가 donor 범위 밖이면 EXTRAPOLATION으로 표시하고 주 일반화 점수에서 제외한다. 제외 건수와 위치는 전부 보고한다.
- NO_SIGN_SUPPORT/EXTRAPOLATION은 H_θ 기각이 아니라 검증 불가다. 특히 기존 K2는 세 route 공통 g×거리 지원 셀이 0이므로 route 이전 성공을 전제하지 않는다.

## 6. 분할, 교란 대조, 보정

1. **Development split:** route별 10 s cluster 기준 시간 블록 2개 이상의 간격을 둔 train/validation split을 먼저 SHA로 동결한다. D3를 쓰는 보조 분석은 로컬 ±5 s 윈도우의 overlap이 서로 다른 split에 생기지 않게 5 s guard를 추가한다. RF pose/revisit site가 겹치면 동일 그룹으로 묶는다.
2. **Route LORO:** R2 holdout ← R4·R5 donor, R4 ← R2·R5, R5 ← R2·R4. donor에서만 평균·q·θ를 추정한다. holdout에는 고정 kernel·변수·모수를 적용한다. 개발 split의 heldout block/route 점수는 모델 재선택에 쓰지 않는다.
3. **Null controls:** (N0) θ=0, (N1) unsigned |a_i a_j|, (N2) a_i의 부호를 route×거리×|a| 층 안에서 **10 s contiguous block 단위**로 재배열한 pseudo-signed a, (N3) 원본 e_s 순서를 같은 지원층의 cluster 단위로 교환, (N4) 독립 백색 합성 e를 동일 D3 평활·pair extraction에 통과. N2/N3는 conditional diagnostic이며 교환가능성이 검증되지 않으면 정확한 randomization p-value라 주장하지 않는다.
4. **Signed contrast:** 매칭한 sign+와 sign− pair의 e_i e_j를 비교하고 sign 차이가 S1의 예측 방향과 일치하는지 보고한다. raw e의 평균이 nonzero이거나 물리적으로 기하와 상관된 경우, 단순 부호 차이는 공통 b_θ의 인과 증거가 아니므로 held-out S1–S0/S2 예측 점수와 결합한다.
5. **Bootstrap:** 10 s cluster를 2,000회 재표집(seed=20261116); pair 개별 재표집 금지. 같은 sampled cluster index를 모든 경쟁 모형에 사용한다. 5/20 s cluster 감도 분석도 수행하되 결론은 10 s 주 판정으로 한다. RF 한 실현의 bootstrap CI로 다른 장면을 대표한다고 말하지 않는다.
6. **공분산 크기 및 꼬리:** mean-zero 가정 위반, noise-free/thermal 섞임, Student-t heavy tails를 기술한다. Gaussian log-score와 winsorized pair contrast에서 방향이 어긋나면 CONFLICTING_EVIDENCE로 남긴다. 무리한 winsorize 문턱 탐색 금지(보조 민감도는 |e|의 donor p99 고정).

## 7. 결과 판정 (실행 전 동결)

**Primary paired score:** 지원 있는 route-held-out/시간-held-out 블록에 대해 ΔL_10 = L(S1)−L(S0), ΔL_12 = L(S1)−L(S2) [단위: held-out packet당 nats]를 계산한다. CI는 cluster paired bootstrap 95% 구간이다. theta_hat=0 경계해 비율 및 두 모형의 유효 모수 수를 보고한다. S1은 S0보다 모수 하나가 많으므로 in-sample 우세를 증거로 쓰지 않는다.

- **SIGNED_ASSOCIATION_SUPPORTED:** sign support를 만족하는 holdout route ≥2개에서 ΔL_10과 ΔL_12의 95% CI 하한 모두 >0이고, 매칭한 signed contrast가 사전 방향과 일치하며 bootstrap CI가 0을 제외할 때. 해당 route와 장면에 한정한 조건부 signed 구조 지지다.
- **ROUTE_SPECIFIC_SUPPORT:** 위 기준을 충족하는 route가 1개뿐이거나 R4에서만 성립하면 'R4 조건부 연관'으로 표시하고 공통 구조를 선언하지 않는다.
- **NOT_SUPPORTED:** 충분한 sign/matched 지원에서 S1의 held-out 개선이 재현되지 않고 S0 또는 unsigned가 우세하면, 이번 범위의 signed heading 공분산 모형은 지지되지 않는다. H_θ가 물리적으로 불가능하다는 뜻은 아니다.
- **INCONCLUSIVE:** CI가 0을 포함하거나 bootstrap cluster 수가 부족하거나 null 대조에서 유사 패턴이 나오는 경우.
- **NO_SIGN_SUPPORT / NON_IDENTIFIABLE / EXTRAPOLATION / UNSUPPORTED_INPUT:** 자료 부족 또는 설계 실패. 결과를 임의로 모아서 PASS하지 않는다.

**R4에 대한 별도 판단:** R4의 물리적 오차가 heading형이라는 문구는 *R4 holdout에서 충분한 signed support + ΔL_10/ΔL_12 조건 + 누락된 confound 대조를 통과한 경우*에만 '이 자료에서 heading 등가 signed 구조와 부합'까지 허용한다. R4가 고감도이고 EKF에서 G1이 성공했다는 사실은 이 조건을 대체하지 않는다. 반대로 지원 부족이면 R4의 signed 구조는 미식별이다.

모델 유효성 판정과 연구 데이터·스크립트 재현 감사 판정은 별도로 기록한다. 사용자가 요청하기 전에는 M7 arm/모수 수정, G-T2/G-V 해제, 새 RF 생성, EKF 재생을 실행하지 않는다.

## 8. 검증용 최소 합성 사례와 적대적 감사

**데이터 생성과 실행 전에 독립 감사자가 확인할 합성 테스트:**

- T00: a=(+a,+a,+a), e=a b+u에서 양의 pair 공분산.
- T01: a=(+a,−a,+a), e=a b+u에서 상대 부호가 다른 pair의 기대 공분산 음수. unsigned 대조가 서명된 기대치를 재현할 수 없어야 한다.
- T02: e=u_s(heading 성분 없음), 동일 양의 short kernel. S1의 θ_hat이 0 경계 또는 추정 불확실성을 반영해야 한다.
- T03: a가 한 부호만 존재/모든 행이 비례 → NO_SIGN_SUPPORT 또는 NON_IDENTIFIABLE이어야 하고 S1 개선만으로 heading형 결론 불허.
- T04: e=route 평균+백색, 또는 백색 e를 D3 overlapping smoothing에 투입 → 중심화 누설과 인공 양의 공분산을 검출.
- T05: 동일 좌표 재방문, 같은 RF realization; train/test 누설 차단, 반복 pose를 독립 샘플로 세지 않음.
- T06: 모든 a 단위를 degree↔rad 변환했을 때 θ 값만 일관되게 단위 변환되고 log-score·판정 불변.
- T07: 현재/미래 진실값 또는 holdout e 교란 → donor 적합·선택 결과가 변하지 않아야 함; holdout e 변화는 오직 점수에만 영향.
- T08: K_θ 및 diag(a) K diag(a) PSD, Cholesky, θ=0에서 S0 parity, signed/unsigned synthetic sign discrimination.
- T09: GT raw 잔차와 M6 raw_s가 정의가 다르면 오류로 중단; 파일·pose_id·t alignment, gate-accepted-only 분석은 2차로만 보고.

독립 Auditor는 계획 SHA, 입력·코드 SHA, 모형·모수·fold 누설, negative-control 구현, 판단 재계산을 확인한다. 합성/정보 차단 검사가 실패하면 실제 signed 결과를 VALID라고 발표할 수 없다.

## 9. 단계·중단 조건과 산출물

| 단계 | 작업 | 반드시 남길 결과 | 중단 기준 |
|---|---|---|---|
| P0 | 입력 가용성·측정 정의·FFF/LoS parity·signed Jacobian 및 support | INPUT_INDEX.json, SOURCE_HASHES.json, SUPPORT.json | 원본 RF·truth mismatch, signed deriv 부정확, source 불명 |
| P1 | exact pair/cluster 생성, sign 지원·identifiability·분할 동결 | PAIR_INDEX.csv, SPLITS.json, PRE_REGISTERED_CONTRACT.json | 시간·경로 누설, sign/지원 미달 시 해당 fold만 NO_SUPPORT |
| P2 | synthetic 및 null 대조 | TESTS.json, NULL_CONTROLS.json, CHECKS.json | 어느 필수 테스트라도 실패 |
| P3 | donor 적합, held-out route/block 예측, 2,000회 cluster CI | FITS.json, HOLDOUT_SCORES.json, SIGN_CONTRAST.csv | holdout 사용한 적합·모델 재선택 |
| P4 | anchor A·G-T1 비봉인 RT의 별도 지지/미지 자료 점수 | SUPPORT_EXTERNAL.json, EXTERNAL_SCORES.json | 관측체인 또는 RF 실현 불일치 시 분리 보고 |
| P5 | 재집계·독립 감사·논문 문구 판정 | DECISION.json, AUDIT_KO.md, REPORT_KO.md, SHA256SUMS | 해시·수치·support·정보 차단 불일치 |

출력 예정: 이 경로 아래 SIGNED_AA_SLOW_COV_001/attempt_01/. 모든 입력과 출력의 SHA256, 계약·구현 commit, 명령, Python/numpy, 재현 seed, 첫 실패 및 수정 기록을 남긴다. P0–P5는 본 파일 게시만으로 실행되지 않는다.

## 10. 허용되는 논문 문구의 상한

- 가능(현재): 'R4에서는 느린 편파 잔차의 반복 반영이 heading 과신과 연계된다. 그러나 물리적 오차가 signed ∂s/∂ψ 적재를 따른다는 것은 아직 검증되지 않았다.'
- P3 지원 시: '시험한 RF 장면/기하의 matched signed-support 구간에서 느린 편파 잔차의 교차공분산이 signed a_i a_j 모형과 일관되며, s 영역·unsigned 대조보다 held-out 예측력이 높았다.'
- 불가: '모든 다중경로가 물리 yaw 편향이다', 'g²가 느린 분산을 보편적으로 결정한다', 'g가 작은 구간은 백색이다', 'σθ≈2°가 다른 장면에도 일정하다', 'GM-θ가 원시 오류의 참 성분을 복원했다', '한 RF 실현의 블록 bootstrap이 RF 일반화를 보장한다'.

**전달 상태: 계획서 작성·게시까지만.** 사용자 지시 없이 실데이터 실행이나 봉인 해제/모수 선택으로 확장하지 않는다.
