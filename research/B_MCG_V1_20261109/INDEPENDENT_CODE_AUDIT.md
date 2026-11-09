# B-MCG v1 독립 코드 감사와 반례

## 검토 범위

`mcg.py`의 covariance adapter, motion path, history profile, current score, weight policy, Monitor API를 검토하고 `test_mcg.py`를 독립 작성했다. 원본 SourceFFD의 재현 및 R2/R4/R5 폐루프 유용성은 이 검사 범위에 포함하지 않는다. 별도의 baseline/precheck/recursive 결과로 판단해야 한다.

초기 24개 API·대수·인과성 시험 이후, nonlinear refinement와 target 안정성 검사를 추가하여 **최종 27개 모두 통과**했다. 최종 소스 SHA는 `8f58b7c412e54ca5fa308e61aa16c59c0fec30f05e482c505cb5cdea11099faf`이며 실행 entry/exit의 hash 일치를 확인했다. 최종 로그는 `results/independent_unit_audit_final/UNIT_TESTS.json` 및 `UNIT_TESTS.log`에 있다. 초기 결과는 별도로 보존했다.

## 검출 후 수정·재검증된 결함

1. WARMUP 판정이 finite/시간순서 검증보다 먼저 발생하여 잘못된 시각이 이력에 저장될 수 있었다. Monitor 입력에서 단조 시각, control dt 일치, 초기 dt=0, control/state 형상·유한값 검사를 추가한 뒤 테스트했다.
2. 위 검증 순서 수정 과정에서 단일 timestamp의 `max(diff(t))`가 빈 배열 연산 오류를 낼 수 있었다. n>1 경계 보호를 확인하고 단일행 WARMUP 시험을 통과했다.
3. 유효하지 않은 RF/관측 공분산을 정상 warmup으로 통과시키거나 다음 profile에 넣을 수 있었다. 현재 sample은 INVALID, 다음 이력은 INVALID_HISTORY_RF로 분리하는 동작을 검증했다. 비대칭·비양정·NaN 공분산 반례를 포함했다.
4. 모든 historical fit가 나빠도 target span만 좁으면 유효한 profile로 판단할 수 있었다. 수정본의 historical cost 제한을 확인했다. 이 제한 자체는 임상적/통계적 confidence가 아니라 고정 연구 설정이다.

## 통과한 구체적인 구현 불변식

- 독립적인 작은 선형계 대수 계산과 full/single-channel/skip Joseph 업데이트가 일치한다. R의 cross covariance가 존재하는 경우를 포함한다.
- β=0은 해당 행을 제거한 업데이트와 일치한다. full K의 열을 0으로 만드는 방식과 다름을 반례로 확인했다.
- 같은 prior에서 R의 대각 PSD 추가, posterior PSD, full/attenuated/prior 사이의 covariance PSD 순서를 검증했다.
- 입력 x/P/H/nu/R/β, anchor와 controls는 진단 계산에서 변경되지 않는다.
- legacy 거절이면 x/P는 prior 그대로이고 실제 K=0이다.
- 공통 yaw 정렬은 상대 XY 위치 경로도 회전시킨다. 초기 control의 이중 적용, 누적 bias 단위, ±π wrap을 검사했다.
- 현재 RF를 바꿔도 historical profile의 후보·비용·theta는 동일하고 현재 score만 변한다.
- 이전 입력 객체나 미래 sample을 변경해도 저장된 anchor/history가 바뀌지 않는다.
- history에 accepted mask를 입력하지 않고 모든 raw packet을 보존한다.
- runtime API가 truth/clean/route/evaluator 필드를 받지 않는 경계를 확인했다. 이는 저장소 전체의 숨은 데이터 계보를 자동으로 증명하는 검사는 아니다.
- 채널별 최소 residual이 각각 0이어도 동일 nuisance로 joint fit가 불가능한 반례에서 joint conflict를 검출한다.
- UNKNOWN은 β=1 research bypass로 남고 정상·정확 판정으로 바뀌지 않는다.

## 해결되지 않은 가장 위험한 구조적 반례

`synthetic_adversarial.py`는 SourceFFD가 아닌 명시적이고 미분 가능한 synthetic range/s observer를 사용한다. 18개 실험을 실행했다. 실제 환경의 오염 빈도·크기 또는 R2/R4/R5 효과로 해석하면 안 된다.

clean history에 대해서 anchor yaw ±5/10/20°와 위치 오차 대조는 좋은 현재 관측을 억제하지 않았다. 한 위치 대조는 비선형성 때문에 UNKNOWN이 되었고 연구 bypass로 원본 B를 유지했다. 이는 이 synthetic 조건에서의 동작만을 확인한다.

반면 다음 조건에서는 보호 실패가 재현됐다.

- anchor는 참값이다.
- 상대 controls는 정확하다.
- 과거 25개 RF만 하나의 coherent rigid offset(0.3m, 0.3m, 0.3rad)에 해당하는 synthetic 관측으로 구성한다.
- 현재 RF는 참 경로의 정확한 관측으로 복귀한다.

가드는 history를 내부적으로 잘 설명하는 틀린 nuisance 정렬을 얻었다. 최종 소스에서 동일한 18개 사례를 다시 실행했으며, 현재 clean RF의 range score는 약 9.450이 되어 βr=0.25, βs=1로 감쇠됐다. anchor를 참값으로 바꾸거나 운동을 정확하게 바꾸는 oracle은 이미 그 조건이 만족돼 있으므로 결과를 바꾸지 않았다. **과거 RF만 clean으로 바꾸면 β=(1,1)로 복구됐다.** 결과는 `results/synthetic_adversarial_final`에 있다.

같은 main prior·같은 current clean RF에서 얻은 XY 손익은 다음과 같다. 각각 독립적인 same-prior 1회 갱신 비교이며 재귀 회복시간은 아니다.

| prior XY 분산 (각 축 m²) | B가 얻을 좋은 XY 이득 중 guard가 상실한 비율 |
|---:|---:|
| 0.003 | 39.70% |
| 0.010 | 14.25% |
| 0.030 | 3.19% |

heading 손실은 별도로 계산했다. 위 사례에서 heading은 약간 개선되므로, XY 실패를 heading과 임의로 합산해 지워서는 안 된다. 실험은 default research configuration과 synthetic model에 대한 반례다. 경험적인 일반 발생률이나 실제 데이터에서의 손실 수치가 아니다.

### 원인

immutable anchor는 창 안에서 main posterior가 reference로 다시 주입되는 경로를 막는다. current-target exclusion은 현재 sample이 자신의 fit에 들어가는 경로를 막는다. **두 통제 모두, 상관된 과거 RF가 절대 정렬을 잘못 학습하게 하는 경로는 막지 못한다.** 정상 target와 오염된 과거가 충돌할 때 어느 쪽이 틀렸는지 단일 시점의 motion/RF 비교만으로 알 수 없는 경우가 있다.

그러므로 본 구현을 “좋은 절대 보정을 보장하여 보존한다” 또는 “compatible이면 오염이 없다”고 표현할 수 없다. 이 반례를 해소하려면 독립 정보, history 변화에 관한 추가 모델 또는 근거 있는 ambiguity 정책을 검토해야 한다. 추가 모델 없이 threshold만 바꾸어 반례를 숨기면 다른 정상·오염 사례의 구분력도 바뀐다.

## 남은 구현·성능 한계

- profile은 세 yaw chart와 유한한 SVD 방향 probe다. 전역 허용해를 모두 탐색한 것은 아니다.
- 다중 mode/target span/선형성·cost 통제는 진단 휴리스틱이다. P나 score를 참 posterior/χ² 확률로 해석하지 않는다.
- 현재 정책은 명시적인 상태 기억형 recovery hysteresis를 구현하지 않는다. 최종 설계서의 support·release 규칙을 완성했다고 주장하면 안 된다.
- covariance adapter와 synthetic algebra 시험만으로 online calibration·coverage를 증명할 수 없다.
- ACTIVE의 유용성은 고정된 heldout 정책의 실제 own-state recursion과 좋은 갱신 이득 보존, 경로별 XY/heading, coverage·sharpness, 회복, 처리시간 결과가 모두 있어야 판단할 수 있다.
- finite config 값은 연구 candidate다. calibration lock 및 채택 gate를 통과하기 전 운영 승인으로 간주하지 않는다.

## SourceFFD의 알려진 numerical 실패 수정 검증

원본 observer를 사용하는 105개 evaluator-only 스트레스에서 초기 구현의 정상 복귀 억제를 발견했다. 누락된 history-feasible 후보를 exact constrained 진단으로 찾아, 초기 오판이 불가피한 구조적 한계가 아니라 **finite 후보 집합의 과소표현**이라는 점을 확인했다. 수렴 검사·target 예측 방향 probe와 target-aware validity 수정을 거친 최종 소스에서 동일한 105개를 다시 실행했다.

최종 τ=3 결과는 VALID 63개, UNKNOWN 42개, 감쇠 0개다. 기존 R5 복귀 사건의 좋은 heading 이득 상실은 18.8718%에서 0으로 줄었다. 이는 τ=3의 이 특정 반례에 대한 수정 검증이며 전체 유용성 증명이 아니다. 사전 후보 τ=2에서는 같은 최종 profile에서도 좋은 heading 이득의 45.8538%를 상실한다. 임계값에 무관한 보호를 주장할 수 없다.

R2의 steady coherent wrong 관측은 최종 guard와 원래 shadow를 통과해 heading/XY 양쪽에 해로운 갱신을 만든다. 이 사각지대는 그대로 남았다. 자세한 수치·실행 범위·원인 분해는 `SOURCE_STRESS_AUDIT.md`와 `results/source_adversarial_final`에 기록했다.

## 독립 판정

검토한 API·수치·시간 인과성 구현은 명시한 27개 시험 범위에서 통과했다. SourceFFD의 알려진 finite-search 반례는 τ=3에서 수정됐지만, threshold 민감도와 coherent-bias 사각지대가 남았다. **실제 ACTIVE의 유용성·성능 채택은 P4 및 own-state 재귀 평가로 별도 판단해야 하며 이 감사만으로 통과시키지 않는다.** 모델로 구성한 반례를 실제 CIR 데이터의 발생률로 해석하지 않는다.

추가 재귀 회복의 R4 k212 사건에서는 최종 소스에도 후보 coverage 부족이 남아 있음을 확인했다. Runtime best cost는 충분히 수렴했지만, 같은 bounds/history slack 안에서 τ=3 현재 관측을 허용하는 후보를 runtime이 누락했다. Exact evaluator 진단의 feasible 후보는 range/s=2.803565, joint=3.964840인데 runtime은 s=3.026782, joint=4.264187로 conflict를 선언했다. **따라서 U3/D14의 충분한 허용집합 coverage는 이 반례에 대해 FAIL이다.** 이는 수치 API 시험과 구분된 알고리즘적 한계다. τ=2의 글로벌 비호환성을 증명한 것은 아니다.

다만 이 단일 사건을 근거로 사전 선언한 P5 구간 지표 전체를 FAIL로 바꾸면 안 된다. `recovery_final/RESULTS.json`의 두 선정 episode에서는 heading 회복 확인시간의 guard/OFF 비율이 1.0으로 1.1 이하이고, clean 구간의 좋은 갱신 이득 상실도 양 축 모두 5% 이하다. R4 τ=2의 구간 이득 상실은 heading 0.3056%, XY 0.6371%다. **이 제한된 구간·지표는 PASS**다. XY와 joint 회복시간은 OFF 자체가 관측 구간 안에 회복하지 않아 **NOT_ESTIMABLE_BASELINE_CENSORED**이며, PASS나 guard의 FAIL로 바꾸지 않는다. 개별 정상 복귀를 항상 보호한다는 보장은 반례로 부정되지만, 이것은 기존 구간 예산을 사후에 새 합격 기준으로 대체하지 않는다. 자세한 원인 분해와 검산은 `SOURCE_STRESS_AUDIT.md` 8절 및 `audit_recovery_feasibility.py`에 있다.
