# B-MCG v1 — ADOPTION_HOLD 원인 감사 및 채택 재검토 조건

**근거 기준:** 2026-11-09, 커밋 [`3902aba5`](https://github.com/myoungsunk/sionna-resimulation/commit/3902aba5d31e629e7db0e2f07f2b46ec7147a352), [GitHub Actions #42600632209](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209).  
**과학적 상태:** `CODE_IMPLEMENTED / NUMERICAL_AND_BASELINE_PARITY_PASS / PRIMARY_POLICY_NOT_SELECTED / ACTIVE_DIAGNOSTIC_TESTED / ADOPTION_HOLD`.  
**해석 원칙:** Workflow가 녹색이라고 유용성이 입증된 것은 아니다. `ACTIVE_RS_tau2`는 채택된 정책이 아니라 사전에 정한 **진단용 감쇠 대조군**이다. 원본 B 검출기·기존 shadow gate·K1/K2 제외 조건은 유지했다.

## 1. 채택 보류의 핵심

**ADOPTION_HOLD는 단일 오류가 아니라 독립된 다섯 근거가 겹친 판정이다.**

| 중요도 | 사유 | 직접 증거 | 의미 |
|---|---|---|---|
| **결정적** | **사전 정책 선택 불성립** | 주 기준 B_FROZEN의 R2/R4/R5 모두 `OFF` 선택. R2·R5는 엄격한 near-pose/시간 purge 후 일부 필수 train 분할이 공백, R4는 12개 후보 중 train/dev 양축 순이득 조건 미통과 | 일반화 가능한 능동 문턱·가중치에 대한 근거 부족 |
| **결정적** | **보정 B에서 실제 성능 악화** | B_BIAS_COV pooled Heading 0.99921→1.00062°, XY 10.13085→10.32721cm, Pose95 30.325→28.221% | 기존 B 전용 평균·분산 보정 위에 가드를 쌓는 것이 검증상 이득이 아님 |
| **중대** | **정상 관측 복귀를 잘못 억제하는 반례** | SourceFFD R4 k212에서 오염 history가 정렬기준을 만들고 현재 model-ideal RF를 감쇠; 보다 충분한 constrained search에서 누락된 허용해 발견 | 좋은 절대보정을 보호한다는 필수 요구에 반례 |
| **중대** | **운동과 일관된 잘못된 RF를 판별 불가** | SourceFFD·synthetic coherent-bias 반례. motion-compatible 값이 가드를 통과해 해로운 heading/XY 갱신 발생 | 현재 입력만으로 식별 불가능한 오염 영역 존재 |
| **독립적 운영 장애** | **5 Hz 실시간 처리 예산 초과** | ACTIVE_RS의 p99 전체 처리시간 R2 446ms / R4 422ms / R5 335ms; 5Hz 주기 200ms 초과 | 현 구현을 5Hz 로봇 주경로에 그대로 넣기 어려움 |

**추가 한계:** 같은 복도의 R2/R4/R5·단일 B0/seed10에 한정된다. 독립 환경·RF seed에서의 장기 성능이나 confidence calibration은 입증되지 않았다.

## 2. 사전 유용성 검증이 왜 통과하지 못했는가

정책 선택은 [PRIMARY_PRECHECK_REPORT.json](../PRIMARY_PRECHECK_REPORT.json)과 [POLICY_LOCK.json](../POLICY_LOCK.json)에 따라 **B_FROZEN을 주 판단 기준**으로, R2/R4/R5의 leave-one-route-out과 두 나머지 경로의 train/dev 양쪽을 요구했다. 선언 후보는 τ={1.5,2,3,4}×{R-only,S-only,RS}=12개다. 각 경로에서 양축 Heading/XY의 양의 순손익, 수용된 관측에 대한 실제 감쇠 활동, 좋은 갱신 이득 상실률 ≤5%를 모두 요구했다.

- **R2 홀드아웃:** R4의 train은 370개 중 모두 purge돼 0개. R5 train은 298개 남았지만 **두 훈련 루트의 각 train/dev가 모두 비지 않아야 한다**는 사전 규칙을 만족하지 못했다. 선택은 `OFF`.
- **R4 홀드아웃:** R2 train 47개·R5 train 349개 등 필요한 분할은 남았다. 하지만 **12개 후보 중 train/dev 두 축을 동시에 통과한 정책이 없었다**. 선택은 `OFF`.
- **R5 홀드아웃:** R2 train 0개·R4 train 0개로 필수 훈련 분할이 비었다. 선택은 `OFF`.

**중요한 구별:** 고정된 `ACTIVE_RS_tau2`를 사후 같은 prior에서 비교하면 R5에는 Heading·XY 순손익이 양수인 표본들이 있었다. 그렇지만 **R5의 분리된 훈련 집합 자체가 성립하지 않아** 해당 결과를 학습·선택 완료된 정책의 검증이라고 부를 수 없다. 반대로 R2·R4에서는 `ACTIVE_RS_tau2`가 두 축의 양의 순손익을 동시에 보이지 않았다.

따라서 **3개 fold 모두 `OFF`라는 사실은 ‘운동–RF 정합성 아이디어가 절대로 유용하지 않다’는 반증이 아니다.** 이 데이터의 분할 조건과 후보 정책에서 **채택 근거를 확보하지 못했다**는 정확한 판정이다. 결과를 보고 purge 조건이나 문턱을 완화하면 사전검증의 의미를 잃는다.

## 3. 전체 재귀 시험의 성능: 첫 보정 상태에 따라 우열이 달라짐

**전체 3,136시점:** 결과는 시점별 제곱오차를 표본수로 가중 풀링한 후 RMSE를 구했다. 모든 수치는 [POOLED_METRICS.csv](POOLED_METRICS.csv)에서 검산 가능하다.

| 기준 B 보정 | 가드 | Heading RMSE | XY RMSE | NEES3 평균 | Pose95 | 실제 감쇠 시점 |
|---|---|---:|---:|---:|---:|---:|
| B_FROZEN | OFF | 1.55664° | 12.80901cm | 25.123 | 46.11% | 0 |
| B_FROZEN | ACTIVE_RS | **1.53558°** | **12.65169cm** | **24.806** | **47.58%** | 12/3,136 |
| B_BIAS_COV | OFF | **0.99921°** | **10.13085cm** | **14.484** | **30.33%** | 0 |
| B_BIAS_COV | ACTIVE_RS | 1.00062° | 10.32721cm | 14.729 | 28.22% | 11/3,136 |

B_FROZEN에서는 pooled Heading RMSE 약 **1.35%**, XY 약 **1.23%** 감소했지만, **R4에서는 두 오차가 모두 증가**했다(1.26229→1.26291°, 10.62253→10.64730cm). 또 3,136회 중 실제 감쇠가 12회뿐이므로, 전체적으로 광범위한 오염을 다뤘다는 근거는 아니다.

**B_BIAS_COV에서는 반대 결과**다. pooled Heading 약 **0.14%**, XY 약 **1.94%** 증가했고 Pose95 포함률도 약 **2.10%p 감소**했다. 특히 R5 XY 9.562→10.017cm(약 **4.76% 악화**), Pose95 28.13→23.46%(**4.66%p 감소**)가 결정적 반례다. R2·R4의 B_BIAS_COV에서 가드는 실제 감쇠를 하지 않아 값이 같았다.

따라서 **어떤 보정 상태에서도 B-MCG가 안정적으로 개선한다고 주장할 수 없다.** B_BIAS_COV는 이전 통계보정 매개변수를 고정해 재사용한 2차 민감도 시험이지, 이번 가드 실험의 독립적인 nested heldout 학습은 아니다.

## 4. 원인 감사: ‘틀린 운동 기준을 더 믿는’ 실패의 실제 구조

### 4.1 오염된 RF history가 기준 정렬을 오염시킨다

B-MCG는 현재 RF를 역사 적합에 포함하지 않아 자기 사용을 막고, 구간 내 DR/IMU 상대 궤적은 RF를 재주입하지 않는다. 그러나 **과거 RF를 이용해 공통 위치·heading 정렬값을 맞추는 과정**은 여전히 오염될 수 있다. 이 상태에서 정상 RF가 복귀하면 ‘틀린 과거 정렬’과 충돌해 좋은 측정을 약화한다.

원본 SourceFFD를 사용하는 **R4 k212, 모델 정합 현재 관측** 대조에서, 같은 current 관측과 같은 main prior를 고정하고 history만 model-ideal로 교체하자 range/s score가 **2.74075/3.02678 → 0.00022/0.00991**로 내려갔고 감쇠가 사라졌다. anchor pose를 참값으로 바꾸거나 anchor gyro bias만 0으로 바꾸는 시험에서는 감쇠가 유지됐다. 즉 해당 반례의 주요 설명은 단일 anchor 상태 하나가 아니라 **과거 RF가 프로파일의 공통 정렬을 결정하는 경로**다.

더욱 중요한 것은 **동일한 τ=2 조건에서는 원래 B full update가 같은-prior Heading 제곱오차를 0.00516022 deg² 줄였는데, 가드는 오히려 B full보다 0.03088012 deg²만큼 손실을 키웠으며 skip보다도 0.02571990 deg² 나빴다**는 사실이다. 감쇠 전에는 서로 반대 방향으로 작용하던 range와 s의 업데이트가 감쇠율 변화로 다르게 합성되는 사례이므로, ‘덜 믿으면 반드시 더 안전하다’가 성립하지 않는다.

이 사건은 **실제 clean CIR가 되돌아오는 빈도**를 측정한 것이 아니라 `h_SourceFFD(truth)+muMB`로 구성한 *모델 정합 관측의 회복 대조*다.

### 4.2 전역 적합 성공과 전체 허용해 탐색 성공은 다르다

같은 R4 사건에서 runtime best history cost는 **0.01078058**, 더 충분한 bounded 최적화는 **0.01078047**로 거의 같다. 그러나 **history 제약을 만족하는 다른 위치·방향 해**가 존재했고, runtime 유한 후보 집합이 그 해를 누락했다.

τ=3에서 정확 feasible 진단의 range/s score는 **2.803565/2.803565**, joint **3.964840**으로 허용범위에 있었다. 반면 runtime은 s **3.026782**, joint **4.264187**로 conflict를 선언했다. 즉 **최적해 근방으로 수렴한 것만으로 허용집합 전체를 찾았다는 보증이 없었다.** P3/U3의 후보 coverage에는 미통과 반례가 남는다.

단, **τ=2에서는 발견된 허용 후보도 통과하지 못했다.** 따라서 `τ=2`의 오판 전체를 유한 탐색 문제로만 돌리는 것은 부정확하다. 역사 기준의 신뢰성, 허용 문턱, 탐색 coverage는 서로 다른 원인이다.

### 4.3 일관된 잘못된 RF는 현재 센서 집합으로 구별되지 않는다

좋지 않은 RF가 몇 초간 일관된 위치·방향 정렬을 지지하면, 운동 변화량과 양립할 수 있어 motion-consistency score를 통과할 수 있다. SourceFFD/R2 coherent wrong 관측과 synthetic 반례에서 이를 확인했다. **운동과 모순되지 않는 것과 절대 pose가 올바른 것은 다르다.** 이 모델이 해결하지 못하는 구조적 사각지대이며 단순 threshold 조절로 해소됐다고 주장할 수 없다.

### 4.4 다만 ‘모든 정상 복귀 시험이 실패’라고 하면 안 된다

최종 소스에서 27개 unit/API 시험이 통과했고, 이전 R5 k707 유한 후보 누락은 τ=3에서 수정돼 모델 정합 현재 관측의 좋은 heading 이득 상실이 0으로 회복됐다. 105개 SourceFFD 스트레스에서는 τ=3 기준 VALID 63개, UNKNOWN 42개, 감쇠 0개였다. 42개 UNKNOWN을 ‘정상 보호 성공 42건’으로 세면 안 된다.

사전에 지정한 **선정된 두 회복 episode**의 heading 회복시간은 OFF와 가드 모두 R4 **9.6초**, R5 **9.2초**로 **구간 회복시간 기준은 통과**했다. R4 τ=2의 구간 전체 좋은 갱신 이득 상실도 heading **0.3056%**, XY **0.6371%**로 5% 한도 이내다. 그러나 그 구간 안의 개별 정상 관측에는 위와 같은 큰 상대 손실이 있었다. **구간 평균의 통과와 개별 반례가 동시에 참일 수 있다.** XY·joint 회복시간은 baseline 자체가 관측 구간 안에 회복하지 않아 `NOT_ESTIMABLE_BASELINE_CENSORED`이며 PASS가 아니다.

근거: [SOURCE_STRESS_AUDIT.md](../SOURCE_STRESS_AUDIT.md), [INDEPENDENT_CODE_AUDIT.md](../INDEPENDENT_CODE_AUDIT.md).

## 5. 별도의 운영 장애: 5Hz 계산시간 초과

5Hz는 관측 간격이 약 **200ms**다. GitHub Actions Ubuntu runner에서 관측된 ACTIVE_RS의 전체 처리시간 **p99**는 다음과 같다.

| 경로 | OFF p99 | ACTIVE_RS p99 | 5Hz 예산 |
|---|---:|---:|---:|
| R2 · B_FROZEN | 6.66ms | **446.10ms** | 200ms |
| R4 · B_FROZEN | 6.54ms | **421.94ms** | 200ms |
| R5 · B_FROZEN | 4.90ms | **335.47ms** | 200ms |

보정 B_BIAS_COV의 ACTIVE_RS p99도 R2 약 **437.59ms**, R4 **425.08ms**, R5 **334.02ms**다. **운영 장치가 아닌 GitHub runner의 측정**이므로 실제 TurtleBot의 지연을 확정하지는 않지만, 현재 구현이 5Hz 예산을 만족했다는 증거는 없다. 오히려 현재 환경에서는 명확히 초과했다. 계산 병렬화·캐시·저비용 근사 또는 비동기 실행을 별도 검증해야 한다.

## 6. 이미 통과한 항목과 아직 채택 불가인 항목

| 항목 | 상태 | 설명 |
|---|---|---|
| Python/API 단위시험 | **PASS (27개)** | 정합성·PSD·Joseph·입력 인과성 등 선언한 범위에서 통과 |
| 원본 Native/B 및 B 보정 기준선 | **PASS** | 기존 B와 B_BIAS_COV의 재귀 출력이 고정 기준과 일치 |
| GitHub Actions R2/R4/R5 실행 | **PASS (3/3)** | SourceFFD·입력 SHA·코드·저장 결과 무결성 확인 |
| SourceFFD 알려진 R5 탐색 반례 수정 | **조건부 PASS** | τ=3 특정 사건 회복, 전체 허용집합 증명 아님 |
| 사전 정책 선택 | **HOLD** | 3경로 모두 OFF, R4 무효용·R2/R5 분할 부족 |
| 정렬 후보 coverage | **FAIL 사례 존재** | R4 k212의 실제 허용해 누락 |
| 안정적인 두 보정층 성능 이득 | **FAIL** | B_BIAS_COV 전체 및 R5 악화 |
| 5Hz 실시간성 | **미달** | runner p99 335–446ms > 200ms |
| 새 환경·RF seed에서 일반화 | **미검증** | 동일 복도 B0 seed10, 이미 노출된 데이터 |

## 7. 재검토 조건 — 임계값을 완화해서 ‘합격’시키지 않는다

**최소 선행조건:**

1. 동일 운동·RF 기준에서 현재 profile의 잘못된 정렬 선택을 더 잘 구별할 방법 또는 충분한 허용집합 표현을 검증한다. R4 k212의 `τ=3` 실현가능 해 누락이 재발하지 않아야 하며, 정상 RF 복귀 시의 손익을 개별 사건과 구간 모두에서 보고한다.
2. source of trust 문제를 분리한다. 오염된 역사 RF에 의해 형성된 정렬 기준과 실제 움직임을 구별할 **독립적인 운동/환경 단서 또는 명시적인 편향 불확실성 모델**이 필요할 수 있다. 구별할 정보가 없다면 `UNKNOWN`으로 처리하고 잘못된 확신을 출력하지 않아야 한다.
3. 중복 궤적 분할을 유지한 채 각 평가 fold의 **필수 train/dev가 실제로 구성되도록 새로운 경로·환경 실현**을 확보한다. 홀드아웃 결과를 보고 purge 폭이나 후보 문턱을 바꾸어 과거 실험을 재채점하지 않는다.
4. 기준선 B_FROZEN과 B_BIAS_COV에서 **경로별 Heading·XY 개선 및 Pose95/NEES·신뢰영역 크기를 함께** 확인한다. 한쪽 지표·한 환경만 개선되면 채택하지 않는다. 좋은 RF 보정 보호와 coherent-error 미검출 비율도 함께 평가한다.
5. 최종 대상 로봇에서 **5Hz 지연·메모리·데이터 누락**을 재측정해 통과한다. 200ms 초과가 반복되면 실시간 갱신이 아닌 비동기 경로로 분리하되, 그때의 latency effect도 검증한다.

**결론:** 현재 최선의 결정은 **`ACTIVE_POLICY.enabled=false`를 유지하고, `ACTIVE_RS_tau2`를 연구용 비교군으로만 보존하는 것**이다. `ADOPTION_HOLD`는 코드 실패가 아니라 데이터 지지·확률적 신뢰도·회복 보호·실시간성의 **채택 기준 미달**이다.

## 증거 링크

- [원본 요약·반복 실행 결과](SUMMARY.json), [전체 집계](POOLED_METRICS.csv), [R2 기록](R2/CI_ROUTE_SUMMARY.json), [R4 기록](R4/CI_ROUTE_SUMMARY.json), [R5 기록](R5/CI_ROUTE_SUMMARY.json)
- [정책 선택 원장](../PRIMARY_PRECHECK_REPORT.json), [잠금된 정책](../POLICY_LOCK.json), [기본 OFF 설정](../ACTIVE_POLICY.json), [분할·유사 pose purge](../SPLIT_GEOMETRY_RECEIPT.json)
- [스트레스·회복 감사](../SOURCE_STRESS_AUDIT.md), [독립 코드 감사](../INDEPENDENT_CODE_AUDIT.md)
- [GitHub Actions #42600632209](https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209)

**이 문서는 기존 결과의 사후 설명 보고서다. 추가 학습, 새 RF 재시뮬레이션 또는 신규 실험 없이 2026-11-09에 공개된 고정 산출물을 설명했다. 원본 수치·정책·기존 보고서를 변경하지 않았다.**