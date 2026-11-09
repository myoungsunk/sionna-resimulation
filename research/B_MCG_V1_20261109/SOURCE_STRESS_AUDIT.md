# SourceFFD 적대적 진단: 반례의 직접 원인까지 추적

상태: 초기 finite-profile 실패부터 수정본 재검증까지의 감사 기록. 1–5절은 초기 구현, 6절은 중간 수정본, **7–8절이 최종 소스와 추가 재귀 회복의 결과**다. 초기 결과를 최종 성능으로 인용하지 않는다.

## 범위

`stress_source.py`에서 105개 profile을 실행했다. 실제 online controls, 기존 B prior/P, 원본 SourceFFD 및 R45 B shadow를 사용했다. 이상적 현재 관측은 `h_SourceFFD(truth)+muMB`이며, 이는 **실측 LoS/clean CIR가 아니라 평가용 모델 정합 관측**이다. coherent-history 사례도 참 궤적을 rigid transform하여 원본 observer로 생성한 관측 대조이며 새로운 RF propagation simulation은 아니다.

현재 target는 실제 monitor history fit에 넣지 않았다. 원래 raw B shadow의 직전 posterior에서 predict한 후 현재 counterfactual의 gate를 재계산했고, 각 사건의 원래 raw current gate와 archived mask의 일치도 확인했다. monitor history를 바꾸는 대조는 shadow history까지 바꾼 전체 폐루프가 아니다.

| 대조군 | profile 수 | 양 채널 유효 | UNKNOWN | 감쇠 |
|---|---:|---:|---:|---:|
| raw history + model-ideal 현재, 5개 one-factor 대조 | 60 | 37 | 23 | 0 |
| reference만 yaw/position/bg 변화, ideal history/현재 | 36 | 21 | 15 | 0 |
| 원본 observer의 coherent history/현재·복귀 대조 | 9 | 7 | 2 | 1 |

앞의 96개에서 감쇠가 없다는 사실을 모두 보호 성공으로 세면 안 된다. 38개는 UNKNOWN bypass였다. 사건은 사전 규칙으로 경로별 최대 anchor |bg| 창과 25/50/75% index를 선택했다. 빈도 추정 표본이 아니다.

## 1. 실제 SourceFFD에서 재현된 잘못된 억제

R5, k=707의 coherent-history→model-ideal 현재 복귀에서:

- anchor pose는 참값, anchor bg=0이었다.
- profile은 유효하다고 판단했고 current s-score=3.46066이었다.
- τ=3에서 βs=0.751493이 적용됐다.
- 원래 shadow는 현재 model-ideal 관측을 수용했다.
- 같은 main prior에서 원래 B의 좋은 heading 이득은 2.76890 deg²였다.
- guard는 그 좋은 이득의 18.8718%를 상실했다.
- XY는 오히려 약간 개선되어, 두 축을 합산하지 않고 별도로 유지해야 한다.
- history만 ideal로 교체하면 β=(1,1), 이득 상실 0이었다.

이 단계까지만 보면 correlated history가 정상 복귀를 막은 현상으로 보인다. 그러나 여기서 조사를 끝내면 **solver의 과소탐색을 구조적 식별 불가로 잘못 설명할 위험**이 있다.

## 2. 정확한 허용해가 누락되어 있었음

생성에 사용한 알려진 rigid alignment는 bounds 안에 있다. 같은 원본 SourceFFD, 같은 raw controls, 같은 robust history cost로 검산한 결과:

| 경로 | 초기 finite search의 best cost | 알려진 generating alignment의 exact cost |
|---|---:|---:|
| R2 | 0.110540 | 0.011405 |
| R4 | 2.201640 | 0.013657 |
| R5 | 1.851291 | 0.013823 |

R5는 finite candidate의 target spread가 0이었지만, 그 이유가 완전한 식별성은 아니었다. 낮은 비용의 다른 허용해가 후보 목록에 들어오지 않았다. 따라서 작은 후보 spread만으로 유효하다고 선언한 것이 과신의 통로였다.

## 3. 현재를 설명하는 누락해도 존재하는가?

`audit_source_alignment.py`에서 R5 한 사건에 한정하여 추가 진단했다. 이때만 현재 target를 **평가용 feasible-set 탐색 목적함수**에 사용했다. 이 후보를 runtime이나 calibration으로 보내지 않았다.

먼저 과거 history만으로 bounded nonlinear cost를 최소화했다. 알려진 generating alignment와 초기 runtime best 두 시작점 모두 cost 약 0.01171224의 동일한 해로 수렴했다. 허용 slack은 기존과 동일한 2.5이므로 history ceiling은 2.51171224였다.

그 제약 안에서 current target를 설명하는 후보를 탐색하여 다음을 원본 observer로 검산했다.

- exact history cost: 2.51171224 이하(수치 허용차 1e-7)
- range score: 약 0.491
- s score: 약 2.757
- joint score: 약 2.801
- 기존 τ=3 및 joint τ=√2×3보다 모두 낮음
- nuisance bounds 안이며 y와 bg는 상한 경계 근처

즉 **기존 history 비용과 bounds 규칙을 그대로 만족하면서 현재 ideal RF도 통과시키는 후보가 실제로 존재한다.** 이 사건의 직접적인 감쇠 원인을 “정상 관측을 구별하는 정보가 없어서 필연적으로 실패했다”고 결론내릴 수 없다. **유한 후보 탐색이 허용 nuisance 집합을 과소표현하고, 그 작은 집합에 과도한 신뢰를 부여한 구현 문제가 확인됐다.** 경계 후보의 ambiguity를 UNKNOWN으로 처리하는 것도 검토 가능한 정합적 동작이다.

이 진단은 global optimum 또는 모든 허용해를 찾았다는 증명이 아니다. 다만 한 개의 정확한 feasible witness만으로도 “호환 가능한 후보가 없다”는 초기 판정은 반증된다.

## 4. 남아 있는 별도 구조적 한계

위 finite-search 오류와 별도로, coherent RF bias 자체가 운동 모양과 일치하는 사각지대는 남는다. R2의 coherent wrong history와 current를 함께 유지한 대조에서는 작은 score로 guard가 통과했고 legacy shadow도 수용했다. 같은 main prior에서 그 관측은 heading과 XY 양쪽을 악화시켰다. 이 사건은 model-constructed stress이며 실제 발생률로 해석하지 않는다.

따라서 최종 정리는 두 가지여야 한다.

1. **수정 가능한 직접 결함:** history optimizer 수렴·후보 coverage·target uncertainty를 충분히 검증하지 않아 정상 복귀를 억제한 경우.
2. **별도 정보의 필요성이 남는 설계 한계:** 운동에 일관된 coherent 왜곡이 정상으로 보이는 경우.

## 5. 수정 후 필수 재검증

- best profile의 exact nonlinear cost와 normalized projected gradient를 확인한다.
- 개별 SVD 방향뿐 아니라 target 예측에 영향을 주는 nuisance의 결합 방향을 조사한다. current target 없이 h_target 자체의 극값 방향을 탐색할 수 있다.
- finite search 실패, 경계 의존성, 폭을 충분히 검증하지 못한 경우는 UNKNOWN으로 남긴다.
- 동일 R5 복귀 사건에서 억제가 남는지 또는 UNKNOWN으로 정직하게 유보하는지 확인한다.
- exact-cost/후보 변경 뒤 기존 full profiles, calibration, active recursion 결과를 재사용하지 않는다.
- 처리시간 증가가 있다면 목표 지연 기준의 실패로 그대로 보고한다.

근거: `SOURCE_STRESS_SUMMARY.json`, 경로별 `*_SOURCE_STRESS.json`, `SOURCE_STRESS_ROWS.csv`, `EXACT_KNOWN_ALIGNMENT_DIAGNOSTIC.json`. 재현 코드는 `stress_source.py`, `audit_source_alignment.py`다.

## 6. 첫 수정본 재실행: 수렴·target probe 보강과 과도한 경계 유보

`mcg.py` SHA `4c9f02595b77103c6b46a5596a5275c6f580c7bb2555ff7d831cb42a23f0c437`에서 동일한 105개 profile을 다시 실행했다. 결과는 `source_adversarial_v1`에 보존했다. 추가한 세 회의 제한된 exact refinement와 projected-gradient 검증, current 관측을 보지 않는 target 예측 방향 probe가 포함됐다.

알려진 R5 복귀 사건은 current s-score가 3.46066에서 **2.96663**으로 내려갔다. τ=3보다 낮으므로 추가된 causal 후보만으로도 초기의 잘못된 감쇠 조건은 해소됐다. 이는 현재 target를 fit에 넣어서 얻은 결과가 아니다.

그러나 이 수정본은 **모든 105개에서 UNKNOWN**이었다. 92개는 `PROFILE_BOUNDARY_SUPPORT`, 5개는 `NONLINEAR_FIT_NOT_STATIONARY`, 8개는 `UNRESOLVED_LOWER_PROFILE_CANDIDATE`였다. 따라서 추가 보호 동작이 유용해졌다고 판정할 수 없다.

독립 검토에서 blanket boundary 규칙의 과도함이 확인됐다. 예를 들어 R5 k707의 ideal history는 target span이 range 약 0.076σ, s 약 0.172σ로 작았는데 nuisance 후보가 물리 bound 부근에 있다는 이유만으로 양 채널이 UNKNOWN이 됐다. 이런 결과는 “데이터에 target 식별정보가 없다”는 증거가 아니다. **nuisance 자체의 불확실성과 target 예측의 불확실성을 구분하라는 설계서 6.4의 취지와 다른 보수적 규칙**이 작동한 결과다.

이 규칙은 수치 계산 오류는 아니지만, 제안한 target-aware 설계를 충실히 검증하려면 수정 또는 명시적인 구현 한계 표시가 필요하다. best-fit가 경계에 닿은 경우와, 다른 nuisance 후보가 경계에 닿지만 target 예측은 안정적인 경우를 구분해야 한다. 기존 동결 target-span 기준을 재사용할 수 있으며, 새 영향 문턱을 추가한다면 별도의 정책값이라는 사실을 기록해야 한다.

독립 unit/API 검사는 이 시점 27개 모두 통과했다. 이 통과는 finite search의 전역 coverage나 실제 가드의 유용성을 증명하지 않는다.

## 7. 최종 target-aware 경계 처리와 재검증

최종 소스 SHA는 `8f58b7c412e54ca5fa308e61aa16c59c0fec30f05e482c505cb5cdea11099faf`이다. boundary 후보의 존재 자체를 veto로 사용하던 규칙만 제거했다. best-fit-bound, 동결된 2σ target span, projected-gradient, minimum candidate count, nonlinear exact 검사와 target 예측 방향 probe는 유지했다. 새로운 문턱은 추가하지 않았다.

동일 105개 진단을 `source_adversarial_final`에 다시 실행했다. 실행 시작과 종료의 runtime SHA 일치도 확인했다.

| 대조군 | 수 | 양 채널 VALID | UNKNOWN | 감쇠(τ=3) |
|---|---:|---:|---:|---:|
| raw history + model-ideal 현재 및 one-factor 대조 | 60 | 27 | 33 | 0 |
| reference만 yaw/position/bg 변화 | 36 | 27 | 9 | 0 |
| coherent source-model 대조 | 9 | 9 | 0 | 0 |
| 합계 | 105 | 63 | 42 | 0 |

UNKNOWN 42개는 best fit bound 29개, nonstationary fit 5개, 해결되지 않은 낮은 비용 후보 8개였다. 따라서 105개 모두 좋은 보정을 판별하여 보존했다고 표현하면 안 된다. 42개는 판단을 유보하여 원래 B를 사용했다.

### 알려진 R5 반례

R5 k707 복귀의 최종 profile cost는 0.01237134, normalized projected gradient는 0.0289633, 허용 후보 수는 9개였다. 현재 점수는 range 0.300816, s 2.966628, joint 2.994759로 τ=3에서 모두 호환된다. β=(1,1)이고 좋은 heading 이득 상실은 **0**이다. 원래 B shadow도 해당 현재 관측을 수용한다.

초기 finite candidate span=0의 과신을 수정한 효과는 이 사건에서 확인됐다. 다만 finite search가 모든 허용해를 찾았다는 보증은 여전히 없다.

### 사전에 선언한 τ 후보의 민감도

최종 profile을 고정하고 기존 계약에 있던 τ={1.5,2,3,4}만 적용했다. profile 재학습이나 threshold 선택은 하지 않았다. `audit_stress_policy.py`가 정확한 같은-prior 손익을 계산하며 결과는 `R5_CLEAN_RETURN_TAU_SENSITIVITY.json`에 있다.

| τ | βs | 좋은 heading 이득 상실 |
|---:|---:|---:|
| 1.5 | 0.255656 | 67.3073% |
| 2.0 | 0.454500 | 45.8538% |
| 3.0 | 1.000000 | 0% |
| 4.0 | 1.000000 | 0% |

이 반례를 이용해 threshold를 골랐다는 주장을 하지 않는다. 중요한 결론은 **numerical 탐색 수정과 좋은 보정의 정책적 보장은 별개**라는 것이다. τ=2로 수행한 ACTIVE 실험에는 이 보호 실패를 함께 보고해야 한다.

### 남는 coherent 왜곡 사각지대

R2의 steady coherent wrong history와 현재 대조는 최종 guard와 legacy shadow 모두 통과했다. 같은 prior에서 원래 skip 대비 heading 제곱오차가 약 25.09051 deg², XY 제곱오차가 약 0.0105941 m² 증가했다. compatible이라는 판정을 정확성으로 해석할 수 없음을 직접 보여준다.

### 최종 독립 판정

27개 unit/API 검사는 최종 소스에서 통과했다. 알려진 finite-search 오류의 회귀 검사는 τ=3에서 통과했다. UNKNOWN 빈도·threshold 의존성·coherent 왜곡 통과는 남았다. 이 진단의 실행 성공은 ACTIVE 가드의 실데이터 성능 채택을 뜻하지 않는다.

## 8. 추가 재귀 회복 시험의 R4 반례: 최종 finite coverage 한계 확인

위 R5 사건의 수정이 모든 복귀 사례를 해결한다는 뜻은 아니다. 최종 동결 소스로 수행한 별도의 재귀 회복 시험에서 R4 원래 index 212(episode index 26, 첫 model-ideal 복귀)가 추가 반례가 됐다. 원본 code나 정책을 재수정하지 않고 한 사건에 한정하여 원인을 조사했다.

### 고정된 현재 상태에서의 history 개입

독립 one-factor 진단(`recovery_cause/RESULTS.json`)은 current RF, main prior/P/H/nu/R, legacy gate, raw controls를 고정했다.

| 변경 요소 | range score | s score | τ=2 판단 |
|---|---:|---:|---|
| 원래 coherent history | 2.740753 | 3.026782 | 두 채널 감쇠 |
| history만 model-ideal로 변경 | 0.000219 | 0.009909 | 감쇠 없음 |
| anchor pose만 참값으로 변경 | 2.690228 | 3.032324 | 감쇠 유지 |
| anchor bg만 0으로 변경 | 2.743066 | 3.063897 | 감쇠 유지 |

이 사건의 monitor 오판은 anchor pose/bg 하나만 바로잡아 사라지는 오류가 아니었다. 과거 RF가 profile 정렬을 설정하는 경로가 핵심 원인임을 이 대조가 뒷받침한다. 다만 one-factor 원인 귀속과 finite 후보 탐색의 완전성은 별도 문제다.

원래 B full update의 같은-prior heading 이득은 0.00516022 deg²였지만 τ=2 가드는 full보다 손실을 0.03088012 deg² 늘렸고 skip보다도 0.02571990 deg² 나빴다. τ=3의 약한 s 감쇠도 full보다 0.00500430 deg² 나빴다. 분모가 작은 이득 비율만 과장하지 않고 이 절대값을 함께 보고한다.

### Exact feasible-set 진단

`audit_recovery_feasibility.py`는 같은 25개 history, 동일 monitor covariance, 동일 bounds/slack을 복원했다. 현재 관측은 평가용 minimax feasibility 목적함수에만 사용했다. runtime score가 저장된 값과 1e-10 이내에서 재현되는 것을 먼저 검사했다.

- runtime best history cost: **0.01078057999**
- 더 충분한 bounded history 최적화 cost: **0.01078047192**
- 차이: 약 **1.08×10⁻⁷**

따라서 이번에는 best fit의 미수렴이 직접 원인이 아니었다. 최적점 근처에서 허용한 전체 nuisance 집합을 후보 몇 개로 대표하는 단계가 문제였다.

두 시작점의 constrained minimax 진단은 아래의 동일한 허용 후보를 찾았다.

- exact history cost: **2.51078047192**, 곧 best cost + 기존 slack 2.5 이내
- range score: **2.80356513**
- s score: **2.80356513**
- joint score: **3.96483983**
- nuisance bounds 안이며 y/bg 상한에 위치

이는 **τ=3에서 현재를 허용하는 history-feasible 후보가 존재한다는 직접 증거**다. 하지만 runtime의 finite 후보 score는 s=3.02678, joint=4.26419여서 τ=3에서도 작은 conflict를 선언했다. 즉 target 방향 probe를 추가한 최종 소스에도 **허용 집합의 coverage 부족이 남아 있다.** 단위시험 통과나 작은 projected gradient는 이 문제를 해결하지 않는다.

τ=2에서는 이번 유한 탐색으로 호환 후보를 찾지 못했다. 발견한 최선 후보가 필요로 하는 최소 τ는 약 2.80357이었다. 이는 두 시작점과 선언한 예산에서의 결과이며, **글로벌 비호환성 또는 실패의 불가피함을 증명하지 않는다.**

### 최종 판정의 범위 수정

R5의 알려진 numerical 반례는 τ=3에서 수정됐지만, 모든 profile coverage가 해결됐다는 주장은 반증됐다. 최종 구현은 연구용 bounded approximation으로 남으며, U3/D14의 충분한 허용집합 coverage는 이 R4 반례에 대해 FAIL이다. 정책 채택은 별도 P4 및 폐루프 기준으로 판단한다.

사전에 정한 P5의 회복시간·구간 이득 보존 예산은 별도로 판정한다. 두 선정 episode의 heading 회복 확인시간은 OFF와 τ=2/3 모두 R4 9.6초, R5 9.2초여서 guard/OFF 비율 1.0으로 1.1 이하를 통과했다. R4 τ=2의 clean 구간 좋은 이득 상실은 heading 0.3056%, XY 0.6371%이고, τ=3은 heading 0.04973%, XY 0%다. R5에서는 양 문턱·양 축 모두 0%다. 따라서 **선정 구간의 이들 수치 gate는 PASS**이며, 한 프레임의 큰 상대 손실을 이유로 구간 예산의 합격 기준을 바꾸지 않는다.

두 episode 모두 XY와 joint는 OFF 자체가 9.8초의 관측 범위 안에 회복하지 않았다. 그 회복시간 비율은 **NOT_ESTIMABLE_BASELINE_CENSORED**다. 10초는 50개 clean sample의 명목 길이이며 첫 clean sample부터 마지막까지의 실제 경과시간은 9.8초다. 이 자료가 모든 정상 복귀의 보호, 실제 clean CIR 복귀율, 더 긴 시점의 회복을 입증하지는 않는다.

원리적으로는 history로 정한 허용 집합을 고정한 뒤 현재 관측에 가장 가까운 feasible 예측을 찾는 연산이 설계서의 score 정의와 일치한다. 현재를 historical loss/허용집합의 정의에 추가하는 것과는 다르다. 그러나 평가용 최적화를 그대로 runtime에 넣어도 전역 negative certificate가 생기지 않으며, 계산 지연과 양쪽 오판을 다시 평가해야 한다. 이번 실험에서는 runtime을 변경하거나 결과를 보고 문턱을 재튜닝하지 않았다.

근거: `recovery_feasibility/R4_FIRST_CLEAN_FEASIBILITY.json`, `recovery_cause/RESULTS.json`, 최종 재귀 회복 trace. SourceFFD 기반으로 구성한 관측 대조이며 실제 clean CIR 발생률을 뜻하지 않는다.
