# B-MCG v1 최종 독립 적대적 검토

검토 대상은 2026-11-09의 **연구용 구현과 확보된 실행 증거**다. 이 문서는 기본 OFF 판정을 유지하며, 원래 블루프린트의 모든 기능을 구현·검증했다는 승인을 내리지 않는다. 42개 재귀 대조군의 최종 수치 집계는 별도 `evaluate_delivery.py`의 최종 실행 결과를 우선한다. 이 검토는 그 집계를 중복하지 않고 수치 계약, 원인 귀속, 채택 논리, 구현 범위와 주장 일치를 감사한다.

검토한 최종 runtime SHA:

- `mcg.py`: `8f58b7c412e54ca5fa308e61aa16c59c0fec30f05e482c505cb5cdea11099faf`
- `experiment.py`: `e4abd56b3224782efb2f4c861d61e0bd724e0e3687a8e06d8b81f0520229ed28`

원래 설계서는 `restored/B_MCG_IMPLEMENTATION_BLUEPRINT_20261109/B_MCG_BLUEPRINT_20261109/B_MCG_BLUEPRINT_KO.md`이며, 실행 계약은 `repo/research/B_MCG_V1_20261109/EXPERIMENT_CONTRACT.json`이다. 아래 경로는 작업 루트 기준이다. 최종 보고서에 옮길 때도 해당 원자료·해시와 연결해야 한다.

## 1. 독립 결론

**정확한 대수·인과성 구현과 쓸 만한 정책은 다른 승인 항목이다.** 최종 27개 단위시험은 통과했고, 원본 B 재현·같은 prior 대조·고정 shadow·관측 공분산의 PSD 증가·실제/가상 갱신 분리를 확인했다. 하지만 최종 profile의 충분한 허용집합 탐색은 **직접적인 반례가 남아 FAIL**이다. 최종 primary P4에서는 선택할 active 정책이 없었다. 기본 OFF 및 운영 채택 보류는 확보된 증거와 일치한다. [E1–E4]

또한 실패 원인을 단순히 “gyro 기준이 틀렸다” 또는 “오염된 이력이라 복귀를 배제할 수밖에 없다”로 요약하면 안 된다. 현재 자료에서 서로 다른 두 경로가 확인됐다. 첫째, 원본 B의 RF 혁신이 bias 상태를 갱신하고 그 bias를 운동 참조에 적분하는 경로다. 둘째, coherent한 과거 RF가 history profile의 정렬을 결정하여 새 정상 관측과 충돌하는 경로다. R4 복귀 사례에서는 이 두 번째 경로가 one-factor 개입으로 확인됐고, 동시에 **허용 후보의 탐색 누락**도 별개로 입증됐다. [E5–E7]

그렇다고 단일 반례를 근거로 사전에 정한 모든 회복 지표를 FAIL로 바꾸어서도 안 된다. 두 선정 SourceFFD 회복 episode의 heading 회복시간과 구간 좋은 이득 보존 예산은 통과했다. XY/joint 회복시간은 기준선 자체의 관측 종료 미회복으로 판정 불가다. 이것은 정상 갱신을 항상 보호한다는 보장과 다르다. [E8]

## 2. 판정 용어와 변경 금지 원칙

| 판정 | 이 감사에서의 뜻 |
|---|---|
| PASS | 명시된 실행·수치 기준을 명시된 자료 범위에서 충족했다. 전체 과학적 채택을 뜻하지 않는다. |
| FAIL | 선언한 기준을 실제로 위반했거나, 주장에 반하는 직접적인 양성 반례가 있다. |
| NOT_ESTIMABLE | 필요한 분할·비교 분모·baseline 회복시간 등 추정에 필요한 정보가 없다. 실패율 0이나 PASS로 대체하지 않는다. |
| NOT_VERIFIED | 해당 구현 또는 시험의 완료 증거가 아직 없다. 구현 가능·파라미터 존재만으로 통과시키지 않는다. |
| LIMITED_PASS | 선정 사건·합성 fixture·특정 환경에서만 통과했다. 일반화할 수 없는 범위를 판정에 붙인다. |

한 프레임 손익, 선택 사건의 후속 1/5/10초 분기, 전체 재귀 RMSE, clean 구간 이득 보존율은 서로 다른 평가량이다. 적대적 반례를 발견하면 구조적 위험을 별도로 추가하고, 원래 구간 합격 기준을 결과에 맞추어 변경하지 않는다. τ=2에서 해를 찾지 못한 유한 탐색을 전역 불가능성 증명으로 바꾸지 않는다.

## 3. 구체적인 개발 단위와 현재 합격 판정

아래 D 번호는 최종 evaluator의 개발 단위와 대응시켰다. 최종 42개 trace와 14개 비교군의 독립 평가가 완료된 `results/delivery_evaluation/RESULTS.json`으로 D12/D13을 확정했다. 이 실행·계보 PASS가 정책 선택이나 모든 설계 기능의 승인으로 확장되지는 않는다.

| 개발 단위 | 구체적인 통과 기준 | 독립 판정과 범위 |
|---|---|---|
| D00 입력·원본 B 재현 | 8개 원본 자산과 source SHA 검증, 시간·pose join 일치, 세 route·두 보정 층의 scaled max error ≤1e−10, gate 정확 일치 | **PASS.** NPZ 이름이 online이라는 이유로 evaluator 열을 runtime에 넘기지 않는다. [E1,E5] |
| D01 수치·인과성 API | full/partial/skip Joseph 독립식 일치, R 증가 PSD, input 불변, current fit 제외, 잘못된 시간·R 거부, UNKNOWN 이유 보존 | **PASS, 27개 시험 범위.** global profile coverage와 성능은 이 판정에 포함하지 않는다. [E1] |
| D02 같은-prior 행동 기회 | 실제 legacy 허용/거절을 분리하고, FULL/감쇠/제외/skip의 heading·XY 손익을 별도 기록, forced update를 실제 결과로 세지 않음 | **PASS: 상한 평가의 계산.** oracle을 실제 selector로 쓰거나 축별 최적 action을 단일 joint 승자로 합치지 않는다. [E9] |
| D03 운동입력·P2 | ds는 m, gy는 적분 rad, dt는 s; anchor 다음 증분부터 적분; 실제 배열 재생; 상대오차 envelope 평가 | **PASS: 현재 B0 입력·기술통계.** 외부 seed, 실기기 bias, stationary/straight strata 성능은 미검증이다. [E5] |
| D04 잘못된 bias 기준 경로 | 고정 trace의 RF→bias 항등식과 동일 anchor·controls에서 bias만 바꾼 대조를 모두 충족 | **PASS: 계산 경로 규명.** 생성 bias=0을 미지 하드웨어에도 강제할 근거는 아니다. [E5,E6] |
| D05 range/s 오차 재귀 분해 | 원본 RAW_B parity 후 한 채널씩 model-ideal 대체하여 동일 source로 재귀 실행; gate·state 상호작용 포함 표기 | **PASS: 개입의 실행·분해 범위.** physical multipath만 제거한 실험 또는 실제 clean CIR로 설명하지 않는다. [E6] |
| D06 1/5/10초 후속 분기 | 동일 시작 prior, 최초 action만 변경, 뒤에는 같은 raw B·legacy 조건, FULL branch 원본 재현 | **PASS: 선정 사건 진단.** hindsight 극단 12개 사건의 비율을 전체 발생률로 해석하지 않는다. [E10] |
| D07 시간·near-pose 분리 | history와 future horizon 전체 support의 누출 방지, heldout/반대 partition near-pose 제외, 빈 required partition은 강제 유지 | **PASS: 분리 규칙 실행.** primary R2/R5의 필요 partition 부족은 NOT_ESTIMABLE로 유지한다. [E3] |
| D08 선택 정책 유용성 P4 | train/dev 양쪽에서 heading·XY 순이득>0, 각 축 좋은 이득 상실≤5%, 활동량, required partition 비어 있지 않음 | **미채택.** R4는 선언된 12개 후보 모두 요건 미충족; R2/R5는 strict 분할의 필요 support 부족. 전체 가능한 모델의 불가능성은 입증하지 않았다. [E3] |
| D09 SourceFFD 105개 stress | 같은 source·controls·prior의 one-factor 대조, 실제 shadow 거절과 forced trial 구별, entry/exit SHA 일치 | **실행 PASS / 유용성 승인 아님.** 최종 τ=3 VALID 63·UNKNOWN 42·감쇠 0. UNKNOWN과 무활동을 정상 보호 성공으로 세지 않는다. [E2] |
| D10 재귀 정상 복귀 | OFF 회복이 관측될 때 확인시간 비율≤1.1; 구간 좋은 이득 상실≤5%; censoring 명시 | **선정 episode heading·구간 예산 LIMITED_PASS. XY/joint NOT_ESTIMABLE.** 상세 수치는 4절. [E8] |
| D11 독립 seed·scene 전이 | 새 sensor realization/초기오차와 새 RF·환경을 분리한 잠금 평가 | **NOT_VERIFIED.** 공통 gyro-noise prefix와 같은 초기오차를 가진 세 경로다. [E5] |
| D12 전체 재귀 대조 | 두 보정 층×7 mode×3 route=42개, mode별 3,136행, 자체 previous state 예측, 행 누락 없음, OFF/OBSERVE parity | **PASS: 42개 trace, 14개 complete group.** 총 43,904개 계산행은 원관측 3,136개를 재사용한 값이다. 모든 trace의 독립 수치검사가 통과했고 자체 previous-state 예측의 최대 정규화 오차는 1.404×10⁻¹⁶이다. [E11] |
| D13 결과 provenance | entry/exit runtime SHA, trace/archive/config/source hash, metric 재계산 일치, prototype 제외 | **PASS: 42/42 실행의 기록된 runtime hash와 현재 동결 소스가 일치하고 14개 group 모두 artifact provenance를 통과했다.** 갱신 재검산의 최대 정규화 오차는 0, 보고 metric 재계산의 최대 오차는 4.441×10⁻¹⁶이다. [E11] |
| D14 profile 허용집합 coverage | conflict 판정 시 같은 bounds·history slack 안의 compatible 후보를 놓치지 않았다는 근거; 충분하지 않으면 판정 불가로 처리 | **FAIL: R4 k212의 양성 feasible witness를 최종 runtime이 놓쳤다.** best-fit gradient 작음과 sampled spread 작음은 이 gate를 대체하지 않는다. [E7] |
| D15 복귀 conflict의 원인 분해 | current RF/main prior/P/H/ν/R를 고정한 채 history·anchor pose·anchor bias를 하나씩 개입 | **PASS: 이 한 사건의 원인 귀속.** history만 이상적으로 바꾸면 억제 소멸; pose/bg만 수정하면 유지. 전역 발생률은 미추정이다. [E7] |

전체 재귀 채택 시에는 추가로 각 route의 heading/XY RMSE 비율≤1.05, pooled 양 축 손실 감소, pose/XY/heading 95% coverage 악화≤3 percentage points, 좋은 갱신 이득 보존, 실제 활동량, end-to-end p99<200 ms를 함께 확인해야 한다. guard p95<50 ms는 목표 예산이다. OFF나 사실상 무활동인 정책의 동률을 개선으로 판정하지 않는다. 분산·체적과 경험적 coverage를 함께 보고, P를 크게 만들어 coverage만 높인 결과를 성공으로 승인하지 않는다. [E4,E11]

## 4. “잘못된 기준을 강하게 믿었다”의 직접 원인과 해석 한계

### 4.1 RF가 bias 상태를 바꾼 뒤 운동 참조로 되돌아오는 경로

현재 B0 gyro bias는 생성 설정상 0이고 실제 입력 배열 재생도 이를 확인했다. 반면 추정 bias는 RF 갱신으로 변한다. 원본 trace에서 다음 항등식이 전수 확인됐다.

\[
\hat b_k^- = \hat b_{k-1}^+,\qquad
\hat b_k^+ - \hat b_k^- = K_{b,r}\nu_r+K_{b,s}\nu_s.
\]

같은 anchor·raw control에서 이 bias를 W초간 고정하면 zero-bias 대조와의 상대 heading 차이는 \(-\hat b_a^-W\)다. 따라서 운동 기준이 과거 RF로부터 완전히 독립이라는 주장은 틀리다. 다만 이 항등식은 혁신의 모든 원인을 물리적 multipath 하나로 분리하지 않는다. 기존 평균 보정, 관측 모델, 상태오차와 잡음도 포함된다. [E5,E6]

### 4.2 과거 RF가 정렬을 정하는 경로와 finite 탐색 실패

R4 원래 index 212의 첫 model-ideal 복귀에서 actual history의 range/s score는 2.740753/3.026782였다. history만 ideal로 바꾸면 0.000219/0.009909로 낮아져 감쇠가 사라졌다. anchor pose만 참값으로 바꾸거나 bias만 0으로 바꾸어서는 감쇠가 사라지지 않았다. main 현재 상태와 관측은 모두 고정한 개입이다. [E7]

하지만 이 사실만으로 “오염된 history와 정상 현재의 충돌은 불가피하다”고 결론내릴 수 없다. 최종 runtime best history cost는 0.010780580이고 더 충분한 bounded 최적화는 0.010780472로, 중심의 미수렴은 거의 없었다. 그럼에도 같은 bounds와 history cost ceiling 2.510780472 아래에서 **range=s=2.803565, joint=3.964840**인 후보가 존재했다. τ=3의 채널 문턱과 joint 문턱 \(\sqrt2\tau\)를 모두 만족한다. runtime finite 후보는 이 해를 놓쳤다. [E7]

따라서 최소 두 단계를 구분해야 한다. 과거 RF는 기준을 만드는 원인이며, 이번 τ=3 false conflict의 충분한 직접 반례는 허용집합의 불완전한 표본화다. τ=2에서는 같은 진단 예산으로 compatible witness를 찾지 못했지만, 전역 infeasibility를 증명하지 않았다. 현재 관측을 historical loss에 추가해서는 안 된다. 반면 이미 history로 고정한 허용집합 안에서 현재와의 최소 거리를 계산하는 것은 원래 score 정의와 일치한다. 이를 runtime으로 바꾸려면 coverage 또는 부정 판정의 근거, 양쪽 오판, 계산시간을 새로 검증해야 한다. 이번에 추가 튜닝으로 결과를 바꾸지 않았다.

### 4.3 개별 정상 갱신 손실과 선언된 회복 gate

R4 첫 복귀에서 원래 FULL의 heading 이득은 같은-prior SKIP 대비 0.00516022 deg²였다. τ=2 guard는 FULL 대비 손실을 0.03088012 deg² 늘려 SKIP보다도 0.02571990 deg² 나빴다. 이 프레임은 정상 보정을 항상 보호한다는 주장에 반한다. 작은 분모를 쓴 비율만 강조하지 않고 절대 손실을 함께 남겨야 한다. [E7]

그와 별도로 실제 선언된 **구간** 지표는 다음과 같다. 이득 상실은 각 active arm의 같은-prior FULL과 비교하며, 원래 OFF와의 재귀 인과효과와 동일한 양이 아니다. [E8]

| 선정 episode | 문턱 | heading 회복 확인시간 OFF / guard | 시간 비율 | clean 구간 heading 이득 상실 | clean 구간 XY 이득 상실 | 구간 예산 판정 |
|---|---:|---:|---:|---:|---:|---|
| R4 anchor 186 | τ=2 | 9.6 / 9.6 s | 1.0 | 0.30556% | 0.63706% | PASS |
| R4 anchor 186 | τ=3 | 9.6 / 9.6 s | 1.0 | 0.04973% | 0% | PASS |
| R5 anchor 682 | τ=2 | 9.2 / 9.2 s | 1.0 | 0% | 0% | PASS |
| R5 anchor 682 | τ=3 | 9.2 / 9.2 s | 1.0 | 0% | 0% | PASS |

두 episode 모두 XY와 joint는 OFF도 관측 범위 안에 회복하지 않아 비율을 계산할 수 없다. 해당 판정은 **NOT_ESTIMABLE_BASELINE_CENSORED**다. 50개 clean RF sample의 첫 점부터 마지막 점까지는 9.8초다. 표의 LIMITED_PASS는 선택 사건 두 개의 모델 정합 관측 조건에 한정되며, 실제 clean CIR 복귀 또는 보편적 회복 보호를 입증하지 않는다. R5처럼 guard가 전혀 작동하지 않은 구간의 보존도 유용성의 증거가 아니다.

## 5. P4 분할·누출·독립성 감사

최종 primary는 B_FROZEN이다. 후보는 채널 action 3종×τ 4개=12개이며, final profile과 고정된 support purge를 사용했다. 각 score target의 history [k−5,k]와 평가 horizon [k,k+10] 전체 support를 고려한다. 학습 경로의 시간 분할은 60%/40%, train 종료는 cut−10초, dev 시작은 cut+5초다. near-pose는 XY≤0.25 m와 wrapped yaw≤5°를 함께 만족하는 경우다. heldout과 반대 partition의 support에 닿는 표본을 제거하고, 제거 후 비어도 기준을 완화하지 않는다. [E3]

| Heldout | 제거 후 train / dev target 합계 | 필요한 하위 partition | 결과의 올바른 해석 |
|---|---:|---|---|
| R2 | 298 / 267 | R4 train=0, R5 train은 남음 | **필수 partition 미충족.** 학습 데이터 전체가 0이라는 표현은 부정확하다. |
| R4 | 396 / 413 | 모든 필요 partition 존재 | 선언된 12개 후보에서 train/dev 양 축 조건을 함께 만족한 후보 없음. |
| R5 | 0 / 311 | 두 train=0, R4 dev=0 | **필수 partition 미충족.** 현재 strict 자료로 선택 유용성을 추정할 수 없음. |

`UTILITY_NOT_DEMONSTRATED`와 모든 fold OFF는 이 결과를 요약할 수 있다. 다만 R2/R5를 “충분한 독립 검증에서 효과가 없음을 입증”했다고 쓰면 안 된다. R4도 후보 12개와 현재 exposed corridor에 대한 결과다. [E3]

B_BIAS_COV는 이미 생성된 기존 route fold 보정값을 고정한 민감도 층이다. guard train/dev에 대한 새 nested 학습이 아니다. 원래 보정의 학습 계보까지 고려하면 이를 primary와 동일한 독립 heldout 증거로 취급할 수 없다. 세 route의 gyro-noise는 공통 시퀀스 prefix이며 초기오차도 동일하다. 경로를 분리했다는 사실만으로 독립 noise/초기조건/scene 반복을 세 번 확보한 것은 아니다. [E3,E5]

현재 3,061개 5초 창은 사전에 정한 motion 분류에서 모두 TRANSLATING_ROTATING이다. 이 자료만으로 정지·제자리 회전·거의 무회전인 5초 직선 주행 strata의 감쇠 보호 성능을 주장할 수 없다. 일부 끝점 yaw 차이가 작다는 사실도 누적 회전이 거의 0이라는 뜻이 아니다. [E12]

## 6. 원래 블루프린트와 이번 구현 범위의 차이

### 6.1 8절: 상태 기억과 회복 규칙

| 원래 설계 요구 | 현재 코드·증거 | 판정 및 다음 개발 단위 |
|---|---|---|
| WARMUP/COMPATIBLE/채널 conflict/UNKNOWN 구분 | current score와 validity에서 매 프레임 상태·β를 결정하고 기록 | **구현됨.** UNKNOWN은 baseline 연구 bypass이며 안전 판정이 아니다. |
| 낮은 release 문턱, 유효한 새 support, 지속조건을 가진 재진입 | `weights()`는 이전 상태나 release counter를 받지 않는다. 별도 hysteresis 상태기계가 없다. | **미구현.** B16: 결정론적 상태 전이표·fresh-support 기준·release threshold를 개발 전에 고정하고, 겹치는 창을 독립 증거로 세지 않는 회귀시험 필요. |
| anchor 교체 후에도 이전 CONFLICT/UNKNOWN의 의미 보존 | raw snapshots는 보존되지만 이전 conflict를 다음 정책에 반영하는 상태 기억은 없다. | **부분 구현.** 기록 보존과 정책 기억을 혼동하지 않는다. |
| 2/5/10초 진단 및 누적 왜곡 대조 | span 파라미터는 있으나 canonical profile·active replay는 5초다. 2/5/10 P2는 운동 적분 검사다. | **active 다중 창 미검증.** B17: 단일 창 민감도와 여러 창 결합 규칙을 분리해 사전 고정·실행해야 한다. |
| invalid packet 갱신 금지와 예외 처리 | monitor invalid/reason, adapter의 NaN/형상/PSD 거부 단위시험은 있다. 배치 replay는 오류에서 중단한다. | **fixture PASS / 지속 운용 recovery 미구현.** invalid 후 계속 진행할 운용 정책은 별도다. |

1/5/10초 후속 분기 재생은 미래 손익 평가이지 2/10초 active monitor 또는 회복 hysteresis 검증이 아니다. 현재 기본 OFF는 파일에 명시되고 CLI 기본도 OFF지만, `ACTIVE_POLICY.enabled=false`는 독립적인 운영 활성화 validator로 강제되지 않는다. 연구 CLI는 명시된 active 진단을 실행할 수 있다. 이를 “calibration=null이면 어떤 active 실행도 불가능하다”라고 설명하면 사실과 다르다. 사용자 지시로 수행한 연구 대조와 운영 채택을 구분해야 한다.

### 6.2 11절: 필수 적대적 stress의 확보 수준

| 원래 요구 | 실제 확보한 검증 | 부족한 부분 |
|---|---|---|
| 좋은 RF + yaw ±5/10/20° | synthetic observer 및 SourceFFD에서 reference anchor만 바꾼 one-factor | main 초기오차까지 바꾸는 전체 재귀 회복 sweep은 아님 |
| 잘못된 anchor 위치 | same-prior 위치 perturbation, ideal history/current 대조 | 새 route·환경에서의 빈도·장기 영향 미검증 |
| gyro constant bias | 단위시험의 누적 bias 대수, reference bg ±0.1°/s, 실제 B 추정 bias 기여 분해 | raw gyro에 미지 상수 bias를 주입한 전체 재귀 sweep 미검증 |
| gyro ramp / 느린 coherent ramp | 없음 | **NOT_VERIFIED** |
| ds/gyro 시간지연 | dt·timestamp 불일치 단위시험 | 유한 time lag를 주입한 동기화·정확도 stress는 **NOT_VERIFIED** |
| packet gap | profile gap 한계·timestamp validation 코드, 비단조/불일치 fixture | 실제 gap 후 재진입·연속 재귀 비교는 **NOT_VERIFIED** |
| 실제 제자리 회전 / 정지 | 자료의 5초 motion strata에 없음 | **자료 support 없음 / NOT_VERIFIED** |
| 전진 곡선 | 원자료의 TRANSLATING_ROTATING 창과 전 route 재생 | 별도 독립 curve robustness 분포를 확보한 것은 아님 |
| ±π 통과 | motion/wrap 합성 단위시험 | 실제 SourceFFD 경계 episode의 장기 안정성은 별도 미검증 |
| 한 채널만 오염 | range/s residual-only의 원본 재귀 인과 진단, ACTIVE_R/S 감쇠 대조 | 주입 크기·형태를 통제한 monitor 검출성 sweep과는 다름 |
| 일정한 두 채널 coherent bias | 원본 SourceFFD에 rigid pose transform을 넣은 9개 대조 | 물리적 다중경로 채널 생성·실제 발생률이 아님 |
| history 전체 오염 후 clean 복귀 | 합성 fixture와 SourceFFD 두 selected episode, R4 원인 개입·feasible witness | 모든 기준선 회복·새 환경 또는 실제 clean CIR 복귀를 포괄하지 않음 |
| tap 전환 / FP 국소왜곡 / global peak | 실제 B 입력의 원자료에 존재하며 평가용 RF 설명 열을 보존 | 각 요인만 독립 조작한 monitor stress·조건별 합격표는 미완료 |
| low sensitivity / source multimodality | rank·span·chart·boundary 검사와 일부 exact counterexample | 광역 mode enumeration·정상/유해 false decision 검증 미완료 |

Fixture 통과를 실데이터 검증으로 바꾸거나, 원자료에 어떤 현상이 포함돼 있다는 사실을 그 현상에 대한 독립 stress 합격으로 바꾸지 않는다. coherent SourceFFD 관측은 `h(truth transformed)+muMB`이며 재전파한 CIR가 아니다. `htruth+muMB`도 실측 LoS/clean RF가 아니라 관측 모델 정합 대조다.

원래 11절의 software 불변식 중 Joseph/PSD/nonmutation/current-exclusion/시간/wrap/UNKNOWN은 최종 27개 시험에 있다. SourceFFD scalar-vs-batch 전 영역 동등성, 운영 activation lock, 재시작 checkpoint의 config/source/input mismatch 거부는 이 27개 통과로 인증되지 않는다.

### 6.3 12절: 실행 패키지·재시작·승인 순서

| 요구 | 이번 구현 상태 | 다음 통과 기준 |
|---|---|---|
| 자산 acquisition, 원본 parity, 단계 실패 로그 보존 | pinned Release ID/SHA 및 archived result SHA, stage/parity, 실패 artifact 보존 구현 | 버전·누락·SHA mismatch의 구체 오류를 계속 유지 |
| checkpoint/resume | profile PARTIAL 저장, RUNNING receipt, 완료 결과 재기록 방지, entry/exit hash 검사 | **resume 미구현.** B18: main+shadow+raw history+reference/policy state와 config/source/input SHA 저장·복구; mismatch 거부; uninterrupted trace와 일치 확인 |
| 첫 단계 승인 뒤 active 실행 | P4에서 선택 정책이 없지만 사용자 요청에 따라 고정 τ=2 연구 ablation 실행 | 연구 실행은 허용된 진단이며 운영 채택은 OFF. “사전 유용성을 확인하고 활성 정책 채택”이라고 쓰지 않음 |
| 전체 local suite와 Actions | local 42개 arm, 별도 prechecks/stress/recovery/evaluator; Actions는 route별 두 층 OFF/고정 ACTIVE_RS canary 및 baseline | Actions green을 full P0–P6, 42개 전체 또는 과학적 채택 PASS로 표현하지 않음 |
| 결과·trace 계보 | 최종 artifact의 SHA 및 runtime version 기록; prototype 결과 분리 | runtime trace의 모든 모드/후보 상세가 설계서 필수 열을 완전히 충족한다고 주장하지 않음. Offline profile에는 더 많은 후보 validity 열이 있음 |

Restart checkpoint는 이번 구현의 `PARTIAL.npz`와 다른 기능이다. 후자는 실행 중간의 점수 결과이며 main/shadow/history를 복원해 이어 달릴 수 있다는 증거가 아니다. SHA entry/exit 검사는 실행 중 소스 불변을 확인하지만, 재시작 후 state/config/input 연결의 동일성을 보증하지 않는다.

원래 설계의 “모든 구현 완료”라는 문구 대신 **“B-MCG v1 연구용 monitor·공분산 adapter·재귀 대조 및 주요 사전검증 구현; 회복 상태기계·다중 창 active·운용 restart와 필수 stress 일부는 미완료”**라고 범위를 명시해야 한다.

## 7. README·계약·CI의 주장 감사 및 필요한 정정

확인한 README는 기본 OFF, K1/K2 미사용, B detector 고정, primary와 기존 보정 secondary의 차이, finite search 한계, green CI와 성능 채택의 분리를 명시한다. 이는 증거와 맞는다. `NAIVE_YAW_CLIP`은 이름과 달리 출력 clipping을 하지 않고 prior trial 보정각이 0.2°를 넘으면 두 관측 β를 0.25로 만드는 부정 대조다. 본문에서 실제 동작을 설명한 것은 올바르다. 해당 mode의 지연에는 monitor 계산도 포함되므로 별도 구현의 최소 clipping 비용으로 해석하지 않는다. [E4]

다음 정정을 이번 감사에서 반영했다.

1. `INDEPENDENT_CODE_AUDIT.md`와 `SOURCE_STRESS_AUDIT.md`의 포괄적인 “P5 회복 보호 미통과” 표현을 **선정 구간 수치 gate PASS / XY·joint NOT_ESTIMABLE / profile coverage FAIL**로 분리했다.
2. `AMENDMENT_001_PROFILE_VALIDITY.md`에 R5 k707 τ=3의 알려진 반례 수정만으로 충분한 coverage가 확보되지 않았고, 최종 R4 반례가 남았음을 추가했다.
3. README의 “실제 gyro bias=0”을 생성 설정·배열 재생으로 확인한 현재 데이터의 사실로 명확히 표현했다. 하드웨어의 미지 bias가 0이라는 주장이 아니다.

최종 본문·표에도 다음 사항을 유지해야 한다.

- “R2 학습이 비었다”는 표현은 **R4 train 하위 partition이 비었다**로 구체화한다. R2 fold 전체 train은 298개 남아 있다.
- 27 unit PASS·SourceFFD 105 실행 PASS·Actions 성공·P4 실패/추정 불가·실제 폐루프 채택을 한 개 PASS로 묶지 않는다.
- 원래 모델과 일치하는 평가 관측을 “LoS 실측”, “physical clean CIR” 또는 RF 물리 전파 재현으로 부르지 않는다.
- 참조 오류를 발견했다고 gyro bias를 영구히 0으로 고정하는 변경이 정당화되었다고 주장하지 않는다.
- 현재 finite algorithm에서 compatible은 “검사한 후보·모델과 모순이 작음”이다. 무오염/정확 heading의 인증이 아니다.
- B_BIAS_COV secondary를 독립 nested holdout으로 표시하지 않는다. 세 route·겹치는 창의 표본 수를 독립 반복 수로 바꾸지 않는다.
- 실제 마지막 로컬 재귀 지표는 완성된 final evaluator로 기록한다. 그 전의 partial/prototype 집계는 최종 정확도 표에 혼합하지 않는다.

CI는 source snapshot·의존성을 고정하고 최소 권한으로 자산을 읽으며, 실패에도 artifact를 남기는 구조다. 다만 historical Actions archive는 수명 제한이 있는 외부 입력이다. `--archive`의 동일 SHA 사용자 ZIP fallback은 재현 방법이고, 미래 CI에서 만료 archive를 자동으로 무기한 구할 수 있다는 보장은 아니다. 원격 CI의 최신 완료 상태는 별도 실행 URL·커밋·artifact로 보고해야 하며 본 코드 검토만으로 성공을 선언하지 않는다.

## 8. 다음 개발의 우선순위와 승인 조건

현재 OFF 결정을 뒤집기 위해 먼저 필요한 것은 threshold 확대가 아니라 **D14의 false conflict와 표현 불완전성 통제**다. 양성 feasible witness를 못 찾은 경우에도 곧바로 “관측이 운동과 불가능하게 충돌한다”고 선언하지 않는 알고리즘 계약을 정해야 한다. 한 사건의 최적화 반복 수를 늘려 통과시킨 것만으로 전체 coverage를 승인해서는 안 된다.

그 다음 B16 회복 상태기계, B17 창 민감도/다중 창, B18 재시작 기능을 각각 독립 단위로 설계하고, 위 표의 빠진 stress를 충족해야 한다. 이 새 기능들의 문턱·유예기간·주입 크기는 다음 실행 전에 고정한다. 이번 결과를 보고 새 기준을 만들어 기존 실행을 소급 PASS로 바꾸지 않는다.

실데이터 유용성 검증에는 근접 support purge 이후에도 유효한 학습/검증 partition이 남는 새 자료가 필요하다. 사용자가 제시한 “직선에서는 heading 변화가 거의 없다”는 아이디어는 독립 wheel yaw, 실제 직선·정지·제자리 회전 support, bias·time-lag 조건이 확보된 뒤 다시 평가해야 한다. 지금은 wheel 거리와 gyro 적분만 있어서 해당 가정을 독립적인 방향 센서 검증처럼 적용할 수 없다. 연구용 구현을 제공한 것과 모델의 채택 가능성을 증명한 것을 끝까지 구분해야 한다.

## 근거 목록

- **E1:** `results/independent_unit_audit_final/UNIT_TESTS.json`, `UNIT_TESTS.log`; `results/baseline/*_PARITY.json`; `repo/research/B_MCG_V1_20261109/test_mcg.py`.
- **E2:** `results/source_adversarial_final/SOURCE_STRESS_SUMMARY.json`, `SOURCE_STRESS_ROWS.csv`, `R5_CLEAN_RETURN_TAU_SENSITIVITY.json`; `SOURCE_STRESS_AUDIT.md`.
- **E3:** `results/policy_calibration_final/REPORT.json`, `POLICY_LOCK.json`, `SPLIT_GEOMETRY_RECEIPT.json` 및 repo의 `PRIMARY_PRECHECK_REPORT.json`, `PRIMARY_CANDIDATE_TRAIN_DEV.csv`, `POLICY_LOCK.json`.
- **E4:** `repo/research/B_MCG_V1_20261109/README_KO.md`, `EXPERIMENT_CONTRACT.json`, `ACTIVE_POLICY.json`, `mcg.py`, `experiment.py`, `ci_route.py`; `.github/workflows/b-mcg-v1-20261109.yml`.
- **E5:** `results/precheck_motion/CONTROL_PROVENANCE_AUDIT.json`, `P2_MOTION.json`, `INTEGRATION_CONVENTION_ONLY.json`; `INPUT_AUDIT.md`.
- **E6:** `results/bias_feedback/RESULTS.json`, `results/bias_causal/RESULTS.json`; `audit_bias_feedback.py`, `audit_ideal_residual.py`.
- **E7:** `results/recovery_cause/RESULTS.json`, `results/recovery_feasibility/R4_FIRST_CLEAN_FEASIBILITY.json`; `audit_recovery_cause.py`, `audit_recovery_feasibility.py`.
- **E8:** `results/recovery_final/RESULTS.json` 및 같은 디렉터리의 final traces; `audit_recovery.py`.
- **E9:** `results/precheck_oracle/RESULTS.json` 및 route별 summary/action NPZ; `precheck_oracle.py`.
- **E10:** `results/horizons/RESULTS.json`; `audit_horizons.py`.
- **E11:** `results/delivery_evaluation/RESULTS.json`, `METRICS.csv`, `DEVELOPMENT_UNITS.csv`; `results/active/GRID_primary.json`, `GRID_secondary.json`과 해당 final trace/metadata. 최종 상태는 `COMPLETED_NUMERICAL_DELIVERY_EVALUATION`, 평가 trace 42개·완료 group 14개다. 과거 partial/prototype 산출물은 이 판정을 대신하지 않는다.
- **E12:** `results/projection/PROJECTION_SUMMARY.json`; `P3_PROJECTION_AUDIT.md`, `audit_projection.py`.

