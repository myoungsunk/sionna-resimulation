# 잘못된 prior의 11,095개 지지구간 배제 — 원인 및 E1-02 진입 제안

질문 ID: FP-SC-PRIOR-FAILURE-ANALYSIS-R1. 역할: PROPOSER, 사후 분석 및 동일 작업자 자체검사.
기준 SHA: b8cc7ee731d61ac747cc99d7203ddcce28de962c.
기존 동결 계약/실패 기록/VAB 주안을 그대로 유지한다. 이 문서의 새 수정·검증 기준은 제안이며 구현·동결·통과한 결과가 아니다.
분석 입력은 DYNAMIC_MAPPING_R1_20261105의 기존 NOMINAL.csv/STRESS.csv 및 canonical online 입력이다.
원본 실행 영수증의 두 CSV SHA와 canonical 입력 SHA를 확인했다. 적용 공통 계약/PROPOSER 해시는 SUMMARY.json에 기록했다.
새 SourceFFD 모델 질의, 실데이터 후보 생성/select/detect, E1-02, E2, EKF 실행은 모두 0회다.

## 1. 판정

주원인은 중심이 잘못된 prior에 작은 공분산을 적용하여 만든 **좁지만 잘못된 detector 거리 구간**이다.
이는 7점 mapping 산술 오류가 확인된 것이 아니며, nominal 20방향 probe 통과와 모순되지 않는다.
probe 검사는 주어진 prior 주변의 유한 집합을 검사했고, prior 중심이 실제 위치와 맞는지는 보증하지 않았다.

11,095는 43,904 packet-stress 행의 수다. 독립 RF 11,095개나 실제 오정정 횟수가 아니다.
하나 이상의 stress에서 영향을 받은 case/packet은 5,787개이며 Full/Native_LoS를 별도 행으로 센다.

**중요한 의미 구분:** 이 결과는 reference가 `native_support`의 low/high 밖이라는 뜻이다.
`prepare_candidate_set()`의 VAB eligibility는 CIR 지지/selection_eligible로 정하며 prior 범위로 후보를 삭제하지 않는다.
따라서 후보 도달성 실패 11,095건이라는 표현은 잘못이다. 다만 prior 점수로 불리해질 수 있고,
실제 select 경로에는 최상위 후보 prior/motion residual >1이면 보류하는 별도 조건도 있다.
이번 분석에서 실데이터 선택 결과나 실제 오탐률을 계산하지 않았다.

## 2. 전수 재집계

모든 stress의 분모는 각각 6,272이며 공분산은 모두 원본의 0.01배다.

| 개입 | 좁은 구간 참조 배제 | 설명 |
|---|---:|---|
| 공분산만 0.01배 | 0 | 중심이 원래대로면 이 데이터에서는 참조 포함 |
| x +0.5m | 5,493 | 위치 중심 오차 + 과신 |
| x -0.5m | 5,520 | 위치 중심 오차 + 과신 |
| y +0.5m | 69 | 위치 중심 오차 + 과신 |
| y -0.5m | 13 | 위치 중심 오차 + 과신 |
| yaw +15도 | 0 | 이 유한 범위에서만 배제 없음 |
| yaw -15도 | 0 | yaw 무해성 일반화 불가 |
| 합계 | 11,095 / 43,904 | 25.27%, 스트레스 혼합 비율이며 운용 실패확률 아님 |

- x 개입이 11,013/11,095건(99.26%)을 차지한다.
- 모든 stress 구간 폭은 0.30~0.449552m, 중앙값 약 0.30m다. 1.5m 최대폭 HOLD는 0건이다.
- x 배제의 구간 밖 거리: 중앙값 0.298657m, 최대 0.448209m.
- y 배제의 구간 밖 거리: 약 0.149105m.
- Full 정상 3,572, Full one-tap 1,791, Full large-error 174, Native_LoS 정상 5,558건이다.
- Full large-error 174는 기존 87개 모두가 x+ 및 x-에서 각각 배제된 것이다.
- 정상 raw=reference 행도 9,130건 배제된다. 이 중 6,817건은 아래 prior 항만으로 2를 넘는다.
  이는 분석용 산술이며 실제 detection/selection 실행의 오류율이 아니다.

## 3. 코드와 수학으로 확인한 원인

`selection.py:native_support`는 x 및 x±2 sqrt(P)의 고유축 7점 native detector range를 사용한다.
구간은 [최솟값-0.15m, 최댓값+0.15m]이며 prior bias나 prior integrity 상태는 입력에 없다.
P를 0.01배 하면 표준편차/고유축 이동은 0.1배가 된다. 중심 ±0.5m 이동을 이 작은 탐색 범위가 포괄하지 않는다.

SourceFFD는 1028 FFT 후 strongest-port 30% first-path detector를 사용한다.
tap 간격은 0.1495522588m다. 작은 위치 perturbation이 같은 tap에 머물면 native min=max가 되어
구간폭은 slack 두 배인 0.30m로 유지된다. 그러므로 폭이 좁다는 것은 정확한 prior라는 증거가 아니다.

canonical prior에서 anchor=(10,0,2.65), robot z=0.45를 사용해 기하 거리 민감도를 재계산했다.
6개 case의 |dr/dx| 중앙값은 0.889~0.909, |dr/dy|는 0.045~0.084다.
따라서 x±0.5m가 y±0.5m보다 큰 거리 이동을 만드는 것은 이 경로 기하와 일치한다.
이는 방향별 차이의 기하적 근거이지, 모든 native detector 비선형 변화의 완전한 인과 분해는 아니다.
현재 stress에는 '위치 이동 + 원래 P' 대조가 없으므로 위치 bias 단독 효과와 P 축소의 상호작용을 수치적으로 분리할 수 없다.

detector-domain residual p = max(low-r, r-high, 0)/0.15.
현재 점수는 0.7*(-log(RF support)) + 1.0*max(p,m)^2다.
x 배제 행의 참조 prior 벌점 p²는 중앙값 3.9643, 최대 8.9285다.
정상 raw가 참조와 같아도 큰 prior 벌점을 받을 수 있으므로 이를 'FP가 틀렸다는 확률'로 해석할 수 없다.
PM은 max 결합이므로 P와 M을 독립 증거처럼 해석해서도 안 된다.

`detection.py:RawDetectionHistory.observe_raw`도 좁은 prior와 residual<=1을 bootstrap 조건으로 사용한다.
M의 중심은 현재 native_offset에 의존한다. 따라서 P 점수만 끄고 M을 무조건 독립적인 보호로 남기면 충분하지 않다.
현재 코드에서 실패한 관측은 streak만 0으로 만들며 기존 trust 표본은 나이 제한까지 남을 수 있다.
이력 오염이 실제 발생했다고 주장하지는 않지만, 별도 합성 반례 검사와 정책 명시가 필요한 연결이다.

## 4. E1-02 전에 권고하는 수정 — 아직 미구현

1. **mapping과 prior 신뢰 상태 분리.** Support가 유효한 수치 구간이라는 사실과 prior가 믿을 만하다는 판정을 분리한다.
   `prior_integrity = VALID / UNKNOWN / INVALID`, 출처·timestamp·나이·공분산 상태·검사 사유를 별도 기록한다.
   좁은 폭/PSD 통과만으로 VALID로 승격하지 않는다. 과거 위치/DR 연속성 등 인과적 검사도 지속적인 일정 bias를 전부 탐지하지는 못한다.
   신뢰 근거가 없으면 UNKNOWN으로 유지한다. 현재 CIR과 prior 불일치만으로 어느 쪽이 틀렸는지 판별할 수 없다.
2. **진단 점수와 사용 가능한 탐지 판단 분리.** C의 RF 점수, P residual, M residual, integrity, hold 사유를 각각 출력한다.
   UNKNOWN/INVALID의 P 및 그 mapping에 의존한 M은 진단값으로 기록할 수 있으나 FP 오류 선언의 근거로 사용하지 않는다.
   `PRIOR_CIR_CONFLICT` / `INSUFFICIENT_PRIOR_INTEGRITY`를 FP_WRONG과 구별한다.
   C-only로 돌아가면 mode_effective=C로 표시하고 P/PM 성능으로 집계하지 않는다. HOLD를 정상 음성으로 치환하지 않는다.
   원본 score도 비교용으로 보존한다. 모든 E1-02 행은 selected_tap=raw_tap을 유지한다.
3. **이력 오염 경로 차단.** UNKNOWN/INVALID prior 또는 mapping conflict에서 trusted history를 새로 bootstrap/refresh하지 않는다.
   기존 trust의 reset/만료 정책을 명시하고 stale 표본이 재사용되지 않게 한다. M native_offset도 같은 integrity 검사를 적용한다.
   원래 raw 관측 보관과 trusted history 갱신을 구분한다. GT/LoS는 오프라인 평가에서만 접근한다.
4. **입장 계약 세분화.** contracts.py의 단일 mapping_reviewed/PASS_DYNAMIC_MAPPING_REVIEW를 켜는 것만으로 끝내지 않는다.
   numerical mapping, prior integrity, detection-only scope를 각각 receipt와 코드/입력 SHA로 묶는다.
   검출 전용 진단의 수용은 FP 정정 안전성 승인이 아님을 명시한다. E2 실행권한은 계속 비활성이다.

0.15m slack, sigma 배수, P floor를 이번 11,095건에 맞춰 키우는 수정은 권고하지 않는다.
추후 integrity 모델을 보완할 때 필요하면 물리적 오차 근거와 별도 개발/검증 분할로 제안한다.
현재 후보 규칙, VAB 주안, eligible 정의는 수정 대상이 아니다.

## 5. 새 버전에서 동결할 검증 기준 제안

이 표는 다음 구현/실행 전에 새 계약으로 동결할 제안이다. 기존 R1의 G4는 완전성 검사였으며 안전성 PASS로 바꾸지 않는다.

| 검사 | 제안 수용 기준 | 범위 |
|---|---|---|
| 기존 증거 재현 | nominal 6,272 / stress 43,904 exact join, 11,095 배제 재현, source/출력 해시 확인 | 수정 전 기준선 고정 |
| 후보 불변 | VAB 전체 후보/eligible 집합과 기존 reach 기록 일치; prior 변경만으로 후보 삭제 0 | mapping과 후보 지지 분리 |
| UNKNOWN/INVALID 격리 | 그런 prior의 P/의존 M이 최종 오류선언에 기여한 행 0; trusted refresh 0 | 합성 검사와 향후 paired replay |
| 검출 전용 불변 | raw 변경 0, select 호출 0, corrected-history 갱신 0, EKF 호출 0 | sentinel로 강제 검사 |
| 이력 반례 | 초기 잘못된 raw, 일정/점프 bias, 누락·stale·시간 역전·reset·복구 검사; 금지된 refresh/reuse 0 | 합성 검사, reset 기준 사전 고정 |
| 참조 누설 방지 | evaluator/GT 변경 시 온라인 mapping/점수/history 불변 | 합성 및 입력 경계 검사 |
| nominal 보존 | 기존 G0~G3 재검증; 참조 포함 AND 폭<=1.5m 전체/비어 있지 않은 층 >=95% 유지 | 기존 mapping 수치 관문 보존 |
| 운용 가능성 공개 | 모든 case/mode/정상·오류별 VALID/UNKNOWN/INVALID/HOLD/C-fallback 분모와 탐지 coverage 공개 | 모두 HOLD해서 안전성을 과장하지 않음 |
| static 48 | C-only, prior/시간 이력 생성 0, 동일 입력 SHA, output 48행 보장 | dynamic 6,272와 분리 |
| 권한 | 새 receipt/manifest/code/policy/input SHA 일치, E1-02 단일단계 권한만 별도 확인 | 이 문서는 실행승인 아님 |

**성능 기준과 준비 기준을 구분한다.** UNKNOWN을 격리하는 구현은 위 구조 기준을 통과할 수 있지만,
P/M의 실용적 coverage를 입증한 것은 아니다. 사전 선언한 coverage 목표를 만족하지 못하면 P/M 준비 미완료로 남긴다.
그 목표의 숫자는 현재 자료만으로 임의 설정하지 않는다. C 진단과 P/M 수용을 분리하고 성능 탐색 이후 성공 기준을 바꾸지 않는다.

후속 mapping 전용 paired stress 제안: 원래 P와 0.1P/0.01P 각각에 이동 0, ±0.1, ±0.25, ±0.5, ±1.0m를
radial/tangential 방향으로 적용하고 yaw 0/±15도를 분리한다. 우선 한 요인씩 비교한 뒤 사전 지정한 결합 반례를 검사한다.
이는 아직 실행하지 않았으며 새 RF 생성이 아니라 고정 모델 mapping 검사 계획이다.
원래 P 대조가 있어야 중심 bias와 covariance 과신 효과를 분리할 수 있다.

기존 11,095를 포함한 전체 43,904행을 실패 corpus로 보존하되, 이것만 맞춘 보호 규칙은 채택하지 않는다.
6,272 nominal 전수와 48 static, 별도 분리한 stress/시간 반례에서 평가한다.
이미 노출된 R2/R4/R5를 route-heldout으로 나눠도 완전 미노출 외부 검증이라고 부르지 않는다.
향후 일반화/안전성 주장은 새 미노출 데이터가 필요하다.

## 6. 진입 판단

현재: 원인 분석 완료 / 수정 제안 완료 / 수정 미구현 / 새 기준 미동결 / E1-02 HOLD / E2 미실행.
E1-02 전에 필요한 것은 모든 잘못된 prior를 마법처럼 식별하는 것이 아니라, 불확실한 prior의 갈등을
FP 오류 판정·이력 갱신으로 자동 승격하지 않는 검출 전용 계약과 그 검증이다.
진단용 E1-02를 허용하는 별도 범위 수용이 성립해도 E2 정정 안전성은 별도 검증 대상으로 유지한다.

## 산출물 및 검산

- analyze.py: 기존 CSV/입력만 읽는 재현 분석기. 새 경로에 결과를 생성하며 원본을 변경하지 않는다.
- SUMMARY.json: 집계·geometry sensitivity·출처 SHA·governance SHA.
- DIAGNOSTIC_ROWS.csv: 43,904행 exact join, 구간 밖 거리/벌점/정상·오류층.
- SECONDARY_CHECK.json: 별도 재집계 및 정상/large-error 보조 확인.
- 본 문서: 코드 분석 및 미구현 제안. 분석 자체는 독립 감사가 아니다.
- 기존 코드/정책/결과 변경, 파일 이동/삭제 없음. 이번 요청 범위에서는 GitHub에 추가 게시하지 않았다.
