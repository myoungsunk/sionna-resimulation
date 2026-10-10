# 1단계: NEES·coverage·RMSE 계산 독립 확인

## 판정과 실행 범위

**산술 검증 완료: ARITHMETIC_CONFIRMED. 기존 NEES≈321, coverage=0은 계산 오류로 설명되지 않는다.** 이는 측정모델 또는 필터의 과학적 PASS가 아니다. F01/F02는 유지한다. 사용자가 승인한 새 순서의 1단계만 수행했으며, 2단계 센서·필터 대조군 및 3–10단계는 실행하지 않았다.

작업 checkout은 `D:/SLAM_bot/artifacts/DRIVE_SIM_VALIDATION_REPAIR_20261008_01a11a0b/checkout`, HEAD는 `991da089e0723644b244fb663b37c519b6e941e2`, 작업 브랜치는 `codex/drive-validation-20261008`이다. HEAD만으로 미커밋 수정 코드를 특정할 수 없으므로, 실제 소스·입력·기존 결과의 SHA-256을 [PLAN.json](PLAN.json)에 기록하고 이전 `FINAL_OUTPUT_MANIFEST.json`의 코드 해시와도 대조했다. 기존 코드·결과를 수정하거나 commit/push/merge하지 않았다.

## 기존 검증 방식 → 문제 → 수정 이유

기존 `scripts/drive_sim/validation_repair.py`의 `metric()`은 wrapped heading 오차와 pose 공분산으로 NEES를 계산하고, `stage6()`에서 seed별 값을 요약했다. `STEP6_JOINT_EVALUATION.json`에는 24개 seed × 3개 모델의 요약이 있지만, 해당 실행의 추정 궤적·공분산 배열은 남아 있지 않았다. 따라서 **당시 저장 배열을 직접 재계산했다는 주장은 할 수 없다.**

필요한 보완은 필터 또는 R의 변경이 아니라, 동일 조건 재생에서 배열을 보존하고 원 분석 함수와 독립인 계산으로 수치가 재현되는지 확인하는 것이다. 원 `metric()`, `aggregate()`, `stage6()`을 호출하지 않았다. 입력·센서 생성·보정 table 생성·필터 구현은 재현을 위해 재사용했다. 따라서 계산 함수의 독립 검증이며, 필터나 RF 구현의 독립 검증은 아니다.

## 실제 수행 방법

새 `scripts/drive_sim/independent_metrics_check.py`에서 다음을 수행했다.

1. 실행 전 `PLAN.json`에 기준 revision, 실행 명령, 입력·수정 코드·기존 산출물 해시, seed, 비교 조건, 오차 허용범위를 고정했다. 원본 확보를 포함한 전체 0단계를 새로 수행한 것은 아니다.
2. 기존과 같은 R2 / anchor-A / mount-0, seed 5000–5023, constant/distance/joint 모델을 재생했다. RF는 저장 H를 재사용했으며 새 RF 계산, noise tuning 또는 filter 변경은 없었다. 센서와 초기 prior 생성도 기존과 동일하다.
3. 전체 재생의 estimate `[n,6]`, covariance `[n,6,6]`, truth `[n,3]`, 시간·pose ID·평가 마스크, wrapped error, NEES, gate 이벤트를 72개 NPZ에 저장했다. covariance는 관측 갱신이 끝난 posterior이고, truth와 동일 시점에 대응한다.
4. 평가 마스크는 저장된 `STEP5_CALIBRATION.json`의 evaluation_indices를 사용했다. 별도 인덱스 수식으로 마지막 40%, `t>=30s`, 보정 pose ID 제외 조건을 다시 구성해 일치를 확인했다. 보정 241개, 평가 392개이다. 독립 초기화가 아닌 앞 구간을 거쳐 온 동일 replay이며, 이를 일반화 검증으로 해석하지 않는다.
5. heading 오차는 radian으로 유지하고 `atan2(sin(error),cos(error))`로 감쌌다. 전체 공분산에서 인덱스 `[0,1,2]`를 양 축에 적용했다. 비대각 원소를 포함하는 3×3 공분산의 Cholesky factor로 오차를 whitening하고 제곱합을 NEES로 계산했다. 원 함수의 `solve(P,error)` 수식을 호출하지 않았다.
6. 위치 RMSE는 x/y 오차 제곱합의 시간 평균 제곱근이며 단위는 m이다. heading RMSE는 radian 오차에서 계산한 뒤 degree로 변환했다. seed별 지표를 먼저 계산하고 24개 seed를 같은 가중치로 평균했다. 9,408개 시간 표본을 독립 반복으로 간주하는 검정은 하지 않았다.
7. pose coverage는 자유도 3의 **95% 타원체 포함률**이며 임계값은 7.814727903이다. heading coverage는 heading marginal 표준편차의 ±1.95996398454 구간 포함률이다. NEES 양측 tail은 자유도 3의 2.5%/97.5% 경계 0.215795283 / 9.348403604를 사용한다. `scipy.stats`의 경계는 별도 incomplete-gamma CDF의 수치 역산과 대조했다. 이 기존 지표 정의를 새 승인 기준으로 승격하지 않았다.
8. 비대각 공분산이 있는 해석 가능한 예제, 2π를 넘는 heading, 단위 변환, 빈 마스크 거부, 비양정 공분산 거부를 확인했다. 저장 NPZ 72개를 다시 읽어 재계산했고, timeline CSV는 기존 reader와 별개로 읽어 truth와 시간을 대조했다.

명령: `py -3.10 -X utf8 scripts/drive_sim/independent_metrics_check.py --prepare`, 이후 `py -3.10 -X utf8 scripts/drive_sim/independent_metrics_check.py`. 정상 재실행 exit code는 0이다. 실행 출력은 [RUN.log](RUN.log), 세부 수치는 [RESULT.json](RESULT.json), 저장 배열 및 원본 보존 확인은 [SAVED_ARRAY_CHECKS.json](SAVED_ARRAY_CHECKS.json)에 있다. 소스·입력·출력 해시와 실제 실행 시각은 JSON 및 [OUTPUT_MANIFEST.json](OUTPUT_MANIFEST.json)에서 추적할 수 있다.

## 실제 결과

| 모델 | 위치 RMSE, seed 평균 m | heading RMSE, seed 평균 ° | pose NEES, seed 평균 | pose coverage95 | heading coverage95 |
|---|---:|---:|---:|---:|---:|
| constant | 0.658104564 | 15.844272748 | 532.788679396 | 0 | 0 |
| distance | 0.469602464 | 7.397791539 | 320.776144404 | 0 | 0 |
| joint | 0.469602464 | 7.397791539 | 320.776144404 | 0 | 0 |

72개 run의 개별 RMSE·NEES·coverage·tail·worst-case·covariance 지표가 모두 기존 값과 일치했다. 가장 큰 개별 절대 차이는 약 1.65×10⁻¹²이고, seed 평균 NEES의 최대 차이는 약 1.19×10⁻¹²이다. 저장 NPZ를 다시 읽은 계산과 최초 독립 계산의 차이는 0이다.

모델별 전체 9,408개 평가 표본에서 constant NEES 최소/최대는 67.780509 / 928.127354, distance 및 joint는 92.655396 / 725.507478이었다. 최소값도 95% coverage 경계와 97.5% 상측 tail 경계보다 크므로 coverage=0, lower-tail=0, upper-tail=1이 설명된다. 공분산의 자유도를 6으로 사용하거나 heading을 degree로 넣어서 발생한 수치가 아니다.

distance와 joint 결과의 동일성은 기존대로 유지된다. 이 검산은 편파 관련 변수의 효과를 추가로 입증하지 않는다.

## NIS와 rejection의 계산 범위

각 측정의 gate 판단 전 scalar NIS와 실제 수용/거절을 기록했다. range 갱신 뒤의 상태로 s NIS를 계산하므로 두 innovation은 같은 prior에서 병렬 계산한 값이 아니다. 원 보고서의 NIS 평균은 **held-out 구간에서 시도한 전체 측정, rejection 포함**의 gate 전 값과 일치했다. NIS 수치의 최대 차이는 2.22×10⁻¹⁶이었다.

| 모델 | range NIS: gate 전 / 수용만, seed 평균 | s NIS: gate 전 / 수용만, seed 평균 | held-out range 거절 / 전체 시도 | held-out s 거절 / 전체 시도 |
|---|---:|---:|---:|---:|
| constant | 1.330281 / 1.125768 | 7.729907 / 1.512627 | 231 / 9408 | 866 / 9408 |
| distance | 1.029405 / 0.897764 | 17.760724 / 1.211493 | 143 / 9408 | 3500 / 9408 |
| joint | 1.029405 / 0.897764 | 17.760724 / 1.211493 | 143 / 9408 | 3500 / 9408 |

수용만의 NIS도 seed별 평균 후 24개 seed를 같은 가중치로 평균한 값이다. 거절 측정만의 값은 RESULT.json에 있다. 수용만의 NIS는 gate가 분포를 잘라낸 조건부 통계이므로, 값이 1 근처라는 이유로 전체 불확실성 모델이 정상이라고 판단할 수 없다.

기존 rejection 총계는 **전체 979개 시점 replay**의 값이었다. constant range/s는 581/2134, distance 및 joint는 499/5145로 기존과 일치했다. 위 표의 held-out 총계와 혼용하면 안 된다. 이 단계는 gating 효과의 인과 분해를 수행하지 않았다. 정확도 개선이 가중치 또는 rejection 중 어디에서 비롯되는지는 새 순서의 7단계 질문으로 남는다.

## 실패 run 처리와 기록기 수정

기존 72개 요약에 seed/model 중복·누락이 없음을 확인했고, 정상 재실행에서는 기대한 72개를 모두 완료했다. 실패 run을 제외해 평균을 만들지 않았다. 새 기록기는 exception을 seed/model과 함께 기록하고, 누락·실패·수치 불일치가 하나라도 있으면 완료 판정을 거부한다. 기존 역사 실행의 모든 실패 시도를 포괄하는 별도 run receipt는 없으므로, 과거에 보고되지 않은 실패 시도가 전혀 없었다고 증명하지 않는다.

첫 실행은 range 갱신이 `_gate_ok()`를 호출하지 않고 inline 비교를 한다는 점을 기록기가 놓쳤다. rejection count 대조가 72개 모두를 거부했고, 빈 집계 NaN의 JSON 직렬화도 실패하여 exit 1로 끝났다. 그 시도의 결과를 채택하지 않았다. range의 gate 전 NIS를 기록하고 실제 거절 counter 변화로 수용 여부를 판독하도록 수정했다. 필터, 입력, seed, 모델, 지표 정의는 바꾸지 않았다. 수정 전·후 소스 SHA와 사유는 [INSTRUMENTATION_AMENDMENT.json](INSTRUMENTATION_AMENDMENT.json)에 보존했다. 정상 재실행에서는 실패 0, 완료 72, exit 0이다.

## 기대효과 달성 여부와 남은 한계

실패 수치의 산술·단위·wrapping·subspace·시간 마스크·seed 집계·coverage 경계·NIS 범위를 확인하는 1단계 목적은 달성했다. 후속 센서/필터 진단의 출발점인 NEES≈321과 coverage=0을 유지할 근거가 생겼다.

당시 저장 배열이 없어 결정적 재생으로 대체했으므로, 과거 배열 자체의 무결성은 미검증이다. 같은 필터와 RF 입력을 사용하므로 이 결과는 필터 모델의 정확성, 공유 gyro/wheel 처리, RF 물리 타당성, 독립 route·anchor·mount 일반화를 검증하지 않는다. 기존 공분산이나 R을 조정하지 않았으며, 이미 통과한 Jacobian/Joseph/PSD 회귀 시험을 반복하지 않았다. 원본 보고서·실행 계획·결과·raw 및 기존 수정 소스의 해시는 유지됐다. 새 산출물과 검산 스크립트만 추가했고 파일 이동·삭제는 없었다.

**여기서 종료한다. 2단계는 이번 실행에 포함하지 않는다.**
