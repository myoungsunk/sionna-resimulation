# B-only Heading·gyro bias 구조 — 병목·원인 재검산과 수정 판단

**기준일:** 2026-11-10 / **범위:** 기존 R2·R4·R5 B0 Full seed10 / **방식:** 읽기 전용 저장 추적 분석

**판정:** 부분 갱신의 수학적 구조는 보존할 수 있다. 그러나 현재 prior–s 허용집합의 교차 규칙을 그대로 부분 갱신 계수의 선택기로 쓰는 것은 지지되지 않는다. prior의 불포함·오염은 중요한 문제지만, 유익/유해 갱신을 구별하지 못하는 유일 원인은 아니다.

## 0. 이번에 무엇을 추가 확인했는가

새 RF 생성·SourceFFD 전수 재평가·가드 구현·재귀 필터/Actions 실행·GitHub 변경은 하지 않았다. 동일 SHA의 기존 OFF/ACTIVE 원본 ZIP 3개와 PRIMARY_3136.csv를 사용하여 다음을 계산했다.

1. 기존 prior의 실제 Heading 포함률, 평균오차, 오차 MSE와 평균 보고 분산의 관계.
2. 참 Heading이 기존 G에 포함된 표본과 그렇지 않은 표본에서, 같은 선형 허용폭 정책의 실제 손익.
3. 해로운 조건부 s 갱신이 잘못된 방향인지, 올바른 방향의 과대보정인지의 정확한 대수 분해.
4. 위치–Heading 교차공분산이 conditional-s Heading gain에 미치는 경로.
5. 기존 궤적에서 Heading 오차를 직전 posterior·운동 증분·추정 gyro bias·현재 RF 갱신으로 계수한 항등식.
6. 현재 s의 Heading/bias 추가 수정만 바꾼 뒤 같은 기록 gyro로 1/5/10초 **RF 없이** 전파한 고정 시작상태 진단. 이는 새 폐루프 정책 결과가 아니다.

원본 archive SHA 및 pose/time join을 확인했다. 모든 수학 검산은 audit_bottlenecks.py에 있으며 제곱오차 비교는 각도 wrapping을 포함한다. 3,136시점 중 기존 게이트 수용은 3,125시점이다. 동일 복도의 노출 데이터이므로 독립 환경의 성능·유의성을 주장하지 않는다.

## 1. 기존 결론을 한 단계 정정한다

이전 결론은 “참 Heading을 충분히 포함하지 못하는 prior를 기준으로 삼는 것이 근본적인 병목”이었다. 이번 재검산으로 이를 다음처럼 한정한다.

> 잘못된/과신된 prior는 좋은 복귀 보정을 배제하는 중요한 경로다. 그러나 G가 참 Heading을 포함한 표본만 남겨도 현재 허용폭 검사는 순손실을 만든다. **기준 불확실성과 의사결정 목표의 불일치가 함께 존재한다.**

새 증거는 선형 위치고정 width10의 집단 분해다. 비선형 width10의 916건 집계와 혼합하지 않는다.

| G의 참 Heading 포함 여부 | 기존 수용 표본 | 원래 유익/해로운 s | 유익 s 배제 | 해로운 s 배제 | 배제 시 Heading SSE 변화 |
|---|---:|---:|---:|---:|---:|
| 포함 | 2,175 | 1,164 / 1,011 | 324 | 268 | **+10.9904 deg²** |
| 불포함 | 950 | 571 / 379 | 231 | 117 | **+52.6845 deg²** |
| 전체 | 3,125 | 1,735 / 1,390 | 555 | 385 | **+63.6749 deg²** |

양수는 원래 range+s 대신 range-only를 썼을 때 손실 증가다. 전체 손실증가의 82.7%가 G 불포함 집단에서 나타났지만, 이것은 관찰된 집단별 산술 기여이지 “오류의 82.7%가 prior 때문에 발생했다”는 인과 기여율이 아니다. 두 집단은 같은 물리 표본이 아니며 위치·RF 조건도 다르다.

이 규칙이 제거한 해로운 갱신에서 절약한 SSE는 45.0227 deg², 제거한 유익 갱신에서 상실한 이득은 108.6976 deg²였다. 단순 검출 건수가 아니라 **비용의 크기**가 불리하다.

## 2. 가장 직접적인 손실 원인: 대부분은 overshoot가 아니라 오차를 더 키우는 방향의 보정이다

range-only 이후 Heading 오차를 e_r, 조건부 s가 추가하는 Heading 보정을 dψ라 두면,

`ΔLψ = (e_r + dψ)² − e_r² = 2 e_r dψ + dψ²`.

원래 유익/해로움 라벨과 이 대수식이 수치상 일치함을 확인했다.

| 해로운 s의 종류 | R2 | R4 | R5 | 전체 |
|---|---:|---:|---:|---:|
| 기존 오차를 더 키우는 방향 (e_r·dψ ≥ 0) | 459 | 309 | 607 | **1,375** |
| 오차 반대 방향이나 지나치게 넘어감 | 3 | 5 | 7 | **15** |
| 합계 | 462 | 314 | 614 | **1,390** |

즉 **98.92%는 방향이 문제**이고, 1.08%만 반대 방향의 과대보정이다. 유익한 조건부 s 갱신의 |dψ| 중앙값은 0.00957°, 해로운 갱신은 0.00781°로 작다. “큰 Heading 보정만 줄이면 대다수 문제가 해결된다”는 근거는 없다.

하지만 e_r는 실제 운영 중 알려져 있지 않다. 이 표는 참값을 쓰는 사후 진단이며, 새 온라인 방향 판별기나 oracle을 정책으로 제안한 것이 아니다. 또한 최적·정상적인 잡음 추정에서도 한 표본의 realized error가 증가할 수 있으므로, 개별 harmful 라벨을 곧 물리적 RF 이상으로 취급하지 않는다.

## 3. prior 불확실성의 실제 상태와 생성 경로

### 3.1 prior는 독립 gyro 기준이 아니라 과거 RF가 만든 재귀 상태다

| 루트 | B 원본 G 포함률 | B 통계보정 G 포함률 | B 원본 Heading prior RMSE | B 통계보정 prior RMSE |
|---|---:|---:|---:|---:|
| R2 | 54.03% | **94.89%** | 2.1684° | 0.9482° |
| R4 | 55.53% | **47.57%** | 1.2732° | 1.3655° |
| R5 | 87.77% | **92.86%** | 1.1458° | 0.8020° |

평균 Heading prior 분산은 R2에서 2.158→2.115 deg², R4에서 0.593→0.616 deg², R5에서 2.011→1.920 deg²다. R4 보정 후에는 평균 분산이 조금 커졌는데도 실제 포함률은 악화했다. 따라서 “P가 작아져서만 실패했다”는 설명은 불충분하다. 각 시점의 평균오차·분산·교차구조가 실제 오차에 맞는지가 중요하다.

R2 B 원본의 평균 Heading prior 오차는 −1.7212°이며 그 제곱은 전체 MSE의 약 63.0%다. R4의 전체 평균은 +0.1946°로 MSE의 2.3%에 불과하다. R4의 undercoverage를 전역 상수 편향 하나로 설명할 수는 없다. 이 분해는 국소 bias·오류 군집을 검증한 것이 아니며 경로 전체 순간 평균에 불과하다.

### 3.2 동작식에서 확인한 경로

원본 상태 x=[px,py,ψ,b_g], 관측 z=[range,s]이며,

`ψ_prior,k = ψ_post,k−1 + Δgyro_k − b_g,post,k−1·Δt`.

따라서 `e_prior = e_previous_post + (Δgyro−Δψ_true) − b_g Δt`다. 현재 RF 이전이라는 의미는 있어도 RF 독립이라는 의미는 없다.

동일 운동 증분을 네 저장 stream에서 역산했을 때 최대 차이는 1.34e−15 rad 이하였다. 이 일치는 원래 예측식의 대수 재현이지 독립 하드웨어 gyro 로그 검증이 아니다.

R2 B 원본의 끝시점 Heading 오차 항등식은 다음과 같다.

- 초기 오차: −2.3588°
- 누적 gyro 증가량−실제 회전량: −0.4400°
- 추정 bias를 뺀 누적 효과: −4.5142°
- 누적 RF Heading 보정: +6.0290°
- 최종 오차: −1.2840°

이 값들은 서로 상쇄하며, bias와 RF 보정이 상호 의존한다. 따라서 bias를 끄면 정확히 4.5142° 좋아진다고 해석하면 안 된다. 현재 궤적의 오류 계수식이지 독립 개입 실험이 아니다.

### 3.3 bias 불확실성은 예측에서 다시 커지지 않는다

원본 online.py에서 과정잡음의 bias 성분은 0이다. F의 bias 행은 identity여서 Pbb가 prediction으로 증가하지 않는다. 저장 trace에서도 전수 일치했다. B0의 일정 bias 설정에서는 이 가정 자체를 버그라고 할 수 없다.

B 원본에서 bias 표준편차는 처음 0.1°/s에서 마지막 R2/R4/R5 각각 0.00353/0.00449/0.00342°/s로 줄었다. 이 상태에 RF 모델 불일치가 누적되면 추정된 bias를 과신할 경로가 생길 수 있다. 하지만 실제 RF 오염 기여와 gyro 잡음 실현, 초기조건, 교차공분산의 기여를 분리한 재귀 대조는 아직 없다. 단순히 Qb를 크게 하면 해결된다는 결론은 내리지 않는다.

## 4. G를 고치면 판별기가 좋아지는가?

### 4.1 같은 자료의 참값으로 반폭만 확대하는 진단

기존 G의 중심은 유지하고 |실제오차|/σ의 95% 분위로 반폭을 확대한 사후 진단을 했다. R2/R4/R5 배율은 약 2.343/2.550/1.164다. 참값으로 맞춘 동일자료 진단이므로 배포용 calibration이 아니다. 기존 K/R/H와 갱신 손익은 변경하지 않았다.

| 선형 규칙 | 배제 수 | 유익 배제 | 해로운 검출 | 배제 시 Heading SSE 변화 |
|---|---:|---:|---:|---:|
| 원래 G, current 폭 | 3 | 3 | 0 | +2.2695 |
| 경험적 G95, current 폭 | 0 | 0 | 0 | 0 |
| 원래 G, width10 | 940 | 555 | 385 | +63.6749 |
| 경험적 G95, width10 | 629 | 353 | 276 | +36.6989 |

넓힌 G는 일부 잘못된 배제를 줄이지만, 10% 폭에서도 전체 순손실은 남는다. 원래 폭에서는 아무 관측도 배제하지 않는다. 이는 집합 확대의 일반적 성질과도 일치한다. **불확실도를 정직하게 표현하는 것과 오류 판별력이 생기는 것은 다르다.** 좁혀서 억지 판별력을 얻는 것은 해결이 아니다.

### 4.2 판단 시점과 action의 기준도 맞춰야 한다

기존 허용집합은 range 적용 전 prior에서 계산하지만, 평가 라벨은 range+s와 range-only의 차이다. 같은 선형화에서 range 후 conditional-s의 잔차·공분산을 사용하도록 진단 기준만 맞췄다.

| 폭 | 기존 Heading SSE 변화 | range-conditioned 검사 SSE 변화 | 판정이 달라진 시점 |
|---|---:|---:|---:|
| current | +2.2695 | +2.2695 | 0 |
| 50% | +14.6623 | +14.1190 | 2 |
| 25% | +39.3780 | +39.0976 | 2 |
| 10% | +63.6749 | +61.5946 | 6 |
| 0% | +68.8168 | +68.8869 | 9 |

action과 판단 기준을 맞추는 것은 필요한 수정이지만, 현재 자료에서 이것만으로 실패가 해결되지는 않았다. 위치·heading의 비선형 허용집합을 새로 계산한 실험은 아니다.

## 5. 왜 관측 양립 가능성과 갱신 이득이 다른가

### 5.1 존재 교차는 목적함수와 다르다

G와 s support의 교차는 “현재 추정이 허용하는 범위 안에 관측을 설명할 상태가 하나라도 있는가?”를 묻는다. 실제 손익은 `2 e_r dψ+dψ²`로 정해진다. 교차가 존재해도 보정 방향이 오차와 같은 쪽일 수 있고, 교차가 없어도 prior의 큰 오차를 고치는 유익한 관측일 수 있다.

특히 기존 판정은 |νs| 중심의 방향 대칭 검사다. 유익/유해 구분에 필요한 e_r와 correction 방향의 관계를 직접 관측하지 못한다. 이는 threshold나 exact nonlinear curve만으로 해결되지 않을 수 있다.

### 5.2 같은 s도 위치·공분산에 따라 다른 Heading 기여를 만든다

현재 조건부 s Heading gain은

`Kψ,s|r = (Pψp|r h_s,pᵀ + Pψψ|r h_s,ψ) / S_s|r`.

현재 수용 3,125시점 중 324시점에서는 위치 교차공분산 항의 절대값이 Heading 직접항보다 컸다. 115시점에서는 Kψ,s|r의 부호가 H_s,ψ의 부호와 반대였다. 그 115개 중 유익 72개, 해로운 43개였다. 이는 교차항이나 gain 부호 반전 자체가 결함이라는 뜻이 아니다. **H_s,ψ 하나로 correction 방향이나 신뢰성을 결정할 수 없다는 데이터 근거**다.

### 5.3 위험의 세 단계를 혼합하면 안 된다

- 물리적 RF 왜곡: 같은 B tap 또는 동일 B 검출기 Full–LoS 대조. 두 정의를 구분.
- 현재 상태에서의 보정 손익: 같은 prior·같은 선형화·같은 action에 대한 오류 변화.
- 이후 재귀 결과: 상태·P·bias·gate가 달라지는 장기 경로.

현재 nonlinear 폭 분석은 첫 번째의 정상 라벨을 참고하면서 두 번째의 교차 분류를 평가한다. 세 번째를 실행하지 않았다. 새로운 state partial update의 실패/성공 판정으로 확대하지 않는다.

## 6. Heading과 gyro bias 평가를 어떻게 나눌 것인가

### 6.1 ‘주요 작용 시점’은 나뉘지만 최종 평가는 결합돼야 한다

- Heading 갱신: 즉시 방향오차와 정상 절대 정렬 회복을 바꾼다. 그 변화가 다음 위치 적분·관측모델·gate에도 전파되므로 현재만 평가하면 안 된다.
- bias 갱신: 현재 Heading 식에 직접 더해지지는 않지만, bias 자체의 정답오차·Pbb를 즉시 평가할 수 있다. 이후 `−T δb_g`로 Heading에 누적되고 XY·관측모델도 바뀐다.
- 두 변화가 상쇄하거나 증폭할 수 있으므로 각각 한 가지 지표로 독립 최적화하지 않는다.

RF가 없는 짧은 고정-bias 전파에서는

`eψ(T) = eψ,r + gyro_noise(T) − b_r T + αψ dψ − T αb db`.

따라서 미래 오차 제곱에는 αψ·αb의 교차항이 있다. 미래 heading 분산에도 `Pψψ−2T Pψb+T²Pbb+과정잡음`이 들어간다. Pψψ와 Pbb만 따로 줄이거나 freeze하는 것으로 전체 신뢰도를 설명하지 못한다.

### 6.2 이번에 수행한 제한적 미래 대조

현재 range-only 결과를 공통 시작으로 놓고, 조건부 s가 더한 Heading/bias 수정만 0/1로 바꾼 뒤 기록된 같은 gyro를 적분했다. 이후 RF는 일체 사용하지 않고 bias는 일정하게 유지했다. 참값은 평가에만 사용했다. 원래 filtered history를 통째로 다시 만든 실험이 아니다.

| 이번 s의 Heading 반영 | 이번 s의 bias 반영 | 즉시 Heading RMSE (N=3,125) | 10초 후 Heading RMSE (N=2,976) |
|---:|---:|---:|---:|
| 1 | 1 | 1.5579° | 1.8576° |
| 1 | 0 | 1.5579° | 1.8588° |
| 0 | 1 | 1.5658° | 1.8651° |
| 0 | 0 | 1.5658° | 1.8666° |

동일 horizon 안에서만 비교한다. 종료구간 때문에 horizon별 표본수가 다르다. 모든 표본에 동일한 차단을 적용해 이득이 나온 것은 아니며, 이번 s→bias 차단만으로 10초 예측이 좋아지지도 않았다. 차이는 작고 시간상관 표본이므로 통계적/운용적 유의성까지 주장하지 않는다.

이것은 **모든 bias 학습을 끄거나 bias를 0으로 되돌린 실험이 아니다.** 이미 만들어진 range-only bias estimate는 그대로 남는다. 실제 B0에서 nonzero 추정 bias가 존재하더라도 현재의 새 s 갱신이 그 잘못된 값을 고치는 중일 수 있으므로, 일률적 freeze는 회복을 막을 수 있다.

### 6.3 필요한 최종 평가축

| 평가축 | Heading partial | bias partial |
|---|---|---|
| 즉시 | Heading·XY 손익, correction 방향, 정상 RF 회복 보호 | bias 오차·분산·교차공분산, 다른 상태 변화 |
| RF 차단 전파 | 시작 yaw 오차가 미래 position/yaw에 미치는 영향 | gyro bias 변화의 누적 yaw/XY 영향 |
| 정상 RF 복귀 | 초기 yaw 오차의 복구시간, 유익한 관측 보존 | 이미 틀린 bias의 회복, 회복 중 공분산 calibration |
| 실제 재귀 | 이후 H/K/P/gate, heading/XY 전체 통계 | drift·bias recovery·추정 신뢰도·전체 궤적 |
| 적대적 조건 | 정상 s + 초기 yaw 오류, 위치 오류, 실제 회전 | nonzero/변화 bias, RF 지속오염, 양쪽 오류 |

## 7. 확인된 병목과 아직 분리하지 못한 원인

| 층위 | 확인된 사실 | 원인 해석의 한계 | 필요한 수정/추가 대조 |
|---|---|---|---|
| 수치·계보 | 원본 SHA·join·joint/conditional 갱신·error identity 일치 | RF모델 정확성·확률적 calibration의 증명 아님 | 기존 재현 유지 |
| RF/기하 | 이전 파형 분석에 연속 왜곡·tap 전환·루트별 차이 | 현재 prior 실패의 물리 경로별 기여율은 미정 | 같은 B Full/LoS 대조와 model mismatch 분리 |
| prior | 참 Heading 포함률 부족, 보정 후 R4는 더 악화 | mean 오류와 P 부정합·모델·R/Q 원인 비중 미정 | prior mean·P·h/μ·RF를 분리 개입 |
| score | G 내부에서도 net loss, widening해도 잔존 손실 | 모든 가능한 score가 실패한다는 증명 아님 | 기대 손익·방향·명목 정보량을 구분 |
| action | harmful 98.9%가 잘못된 방향, 공통 alpha 상한 불리 | adaptive alpha나 새 관측정보의 효과 미검증 | range 후 s-state action과 근거를 일치 |
| bias | H_bg=0, 시간 전파·cross-cov로 갱신; Qb=0 | 모든 bias 갱신이 RF 오염이라는 뜻 아님 | 현재 수정·장기 전파·실제 bias 상황 분리 |
| validation | 노출 복도·B0·단일 seed, frozen prior | 독립 환경·recursive 정책 효과 미검증 | 새로운 조건의 사전고정 평가 |

특정 원인에 대한 “끝까지 규명”은 반증 대조가 완료돼야 가능하다. 현재 산술로 확인한 구조적 경로와 원인 후보를 인과적 기여율처럼 합산하지 않는다.

## 8. 구조 수정 우선순위

### 유지

- B 수신기의 관측 정의와 기존 기준선 재현.
- DR/IMU를 이용한 상대 운동 prior.
- 현재 RF 판단 이전의 입력 계보와 target exclusion.
- 상태별 partial-update/Joseph/Schmidt covariance라는 수학적 선택지.
- range-only 후 conditional s의 공정한 분해.

### 수정 필요

1. **기준 의미:** G를 gyro-only 95% 범위라고 부르지 않는다. 경험적 calibration이 없는 prior 범위에 정답 배제 권한을 부여하지 않는다. 단순 widening은 정합성 수리이지 판별기 완성 아님.
2. **판정 목표:** compatibility와 physical distortion을 realized update utility로 동일시하지 않는다. 개별 helpful/harmful은 평가 라벨이며 정책은 온라인 입력의 조건부 기대 손익/위험을 다뤄야 한다.
3. **판정과 action 정렬:** s 추가 기여를 조절하려면 range posterior 기준으로 conditional s를 다룬다. 원래 prior의 joint RF Heading gain 전체를 줄이는 대조는 별도 arm이다.
4. **Heading/bias 역할:** αψ와 αb를 같은 값으로 묶지 않는다. 현재 보호와 미래 drift를 분리 진단한 후 전체 covariance/궤적에서 공동 평가한다.
5. **평가 범위:** instant loss, RF-off propagation, source-model clean recovery, measured clean CIR, actual recursive run을 서로 구별한다. 사후 유리한 horizon/route만 선택하지 않는다.
6. **조기 채택 금지:** 새 모델 전에 어떤 온라인 정보가 방향·bias 오염을 구별할 수 있는지 입증한다. prior 확대 또는 threshold 재조정만 반복하지 않는다.

### 원인 확정을 위한 최소 개입표

- 같은 실제 RF에서 Heading mean만 / XY mean만 / 둘 다 / 기존 P를 따로 변경하고 h,H를 일관되게 다시 계산하는 oracle 진단. 이는 평가용 원인분해이지 online prior 보정이 아님.
- 같은 prior에서 Full-B vs direct-only-B를 비교하며 clean detector·기존 μ의 불일치까지 보존. native 참조를 섞지 않음.
- bias update, mean recenter, Qb 변화, P calibration을 각각 별도 arm으로 두고, 동일 미래 입력에서 재귀 비교. 한 번에 모두 바꾸지 않음.
- 깨끗한 RF+초기 heading 오류, 오염 RF+정확한 bias, 깨끗한 RF+틀린 bias, 실제 nonzero/변화 bias를 모두 포함.

## 9. 최종 정리

**가능성이 남은 것:** 상태별 부분 갱신을 이용해 좋은 절대 Heading 수정은 보존하고, 불신할 s가 Heading/bias에 과도하게 들어가는 것을 제한하는 구조.

**현재 지지되지 않는 것:** 과거 RF로 만들어진 prior 주변의 s 허용폭 교차만으로 유익·유해 갱신을 판단하고, 그 결과에 공통 alpha 또는 일률 bias freeze를 붙이는 정책.

**이번에 더 분명해진 것:** 주된 realized 손해는 큰 보정의 overshoot보다 작은 잘못된 방향의 반복 보정이다. prior 포함률을 수리하는 것만으로 그 방향 정보가 생기지는 않는다. Heading과 gyro bias는 다른 역할을 갖지만 최종 위치·방향 손실에서는 결합된다.

**상태:** `NUMERIC_RECHECK_PASS / PRIOR_CALIBRATION_INADEQUATE / CURRENT_SELECTOR_UNSUPPORTED / PARTIAL_UPDATE_STRUCTURE_RETAINED / NEW_RECURSIVE_POLICY_NOT_RUN`.

## 입력 계보와 출처

- 고정 GitHub 분석: https://github.com/myoungsunk/sionna-resimulation/tree/a4a0b60af00757f1f02817ea59c0362fb6d4d961/research/B_S_HEADING_FEASIBILITY_20261110
- 원본 core.py, online.py: commit c141839093d1a2e4a76f91eea632cb6467163e28 의 research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources/research/{EKF4_RANGE_S_STAGED_20261014/core.py,MBVAR_PRR_001_20261103/S1/online.py}.
- R2/R4/R5 Actions ZIP source SHA는 AUDIT_SUMMARY.json에 기록. GitHub nonlinear PROVENANCE.json의 기존 입력 계보와 일치.
- 참값·평가용 RF 특성은 이전 PRIMARY_3136.csv, SHA 59f0c0068e76215b8958f3cd62e0fbf8add183035d1d43fb0b3ce5303e4b859b. 이번에 새 evaluator NPZ·원시 IMU를 취득하지 않았다.
- 이번 결과: audit_bottlenecks.py, BOTTLENECK_ROWS_3136.csv, PRIOR_CALIBRATION.csv, POLICY_BY_PRIOR_COVERAGE.csv, S_HARM_MECHANISM_COUNTS.csv, PRE_VS_RANGE_CONDITIONED_DECISION.csv, HEADING_ERROR_ACCOUNTING.csv, S_HEADING_BIAS_OPENLOOP_HORIZONS.csv.

**해석 금지:** 같은 저장 자료의 3,136시점을 독립 실험 3,136개로 부르지 않는다. exact identity의 수치 일치를 독립된 물리·환경 검증으로 확대하지 않는다. 사후 truth로 맞춘 G나 oracle action을 운영 알고리즘이라고 부르지 않는다.