# DRIVE_SIM 2단계: RF 없는 sensor-v2 센서·필터 대조군

## 결론과 적용 범위

**2A–2E의 제한된 CPU 검증을 완료했다. 전체 판정은 부분 확인이며 RF·production PASS가 아니다.** 기존 센서 기하식과 공유 입력 상관의 부호·시점은 독립 수식과 일치했고, 사전 분산을 사용하는 기본 잡음 및 prior 정합 대조군은 유용한 기준을 만들었다. 그러나 one-step 교차공분산의 사전 15% 표본 허용오차는 실패했다. 무잡음 calibration 불일치 3개 조건에서는 공분산이 수치적으로 부정정해지는 것도 확인했다. 기존 절대 PSD 검사만으로 이를 허용하던 결함을 최소 수정해 명시적으로 거부하도록 했다. 분산·prior·gain·gate를 조정하지 않았다.

**F01/F02는 OPEN, scientific_PASS=false를 유지한다.** 이번 시험으로 RF 조건의 F02를 설명하는 비율은 계산하지 않았다. UWB range와 s를 모두 끄고 LUT/FFD/RF를 사용하지 않았다. 새 RF 실행, Snowball, 로봇/ROS/firmware 변경, commit/push/merge 및 3단계 이후 실행은 없다.

## 2A — 어떤 구현과 독립 기준을 검증했는가

**질문:** 미커밋 sensor-v2의 실제 기준이 무엇이며, 모델 정합과 현실적 근사를 어떻게 구분하는가?

**기대값:** 원 작업을 보존하면서 실제 소스 SHA를 고정해야 한다. 생성기와 필터를 같은 함수로 비교한 것만으로 공통 오류를 배제할 수는 없다.

**방법:** 작업 checkout은 `D:/SLAM_bot/artifacts/DRIVE_SIM_SENSOR_V2_REVIEW_20261008_01a11a7b/checkout`, branch는 `codex/sensor-model-v2-review-20261008`, HEAD는 `2337c33fe25917029c2aa95973e6ae7672386a5e`였다. dirty 상태를 [PLAN.json](PLAN.json)에 보존했다. 원 작업 `DRIVE_SIM_SENSOR_V2_20261008_01a11a01/checkout`의 복사 출처 15파일을 `../COPIED_SOURCE_MANIFEST.json`과 대조했고 모두 일치했다. 보완 checkout의 입력 검사 변경은 이전 보완 기록에 해당하며 이번에 새로 작성한 것으로 표시하지 않는다. 원 작업 결과 2,711파일을 포함해 총 2,749개 보호 파일을 실행 전후 해시로 대조했다.

실행 전에 PLAN.json을 작성했다. seed 81000–81063, 각 arm 64개, 32개 arm, 총 2,048개 run으로 고정했다. 각 경로의 길이는 12초이다. 기본 dt=0.2초, dt 비교는 0.1/0.2/0.4초이다. mixed 경로는 2초씩 직진 0.2m/s, 직진 0.35m/s, 제자리 좌회전 +0.4rad/s, 우회전 −0.4rad/s, 원호 0.2m/s·+0.2rad/s, 후진 원호 −0.1m/s·−0.2rad/s이다. 직선 일정속도 경로와 속도 변화 경로도 별도로 사용했다. B4/C_full 및 B3/E_dt_0.2는 같은 기준 설정을 공유하며 새로운 독립 반복으로 세지 않는다.

독립 기준은 원호의 sin/cos 끝점 차분, 좌우 wheel 기하식의 별도 전개, block joint Gaussian covariance의 조건부 갱신, 실제 수치의 seed 단위 평가로 구성했다. 읽기 전용 독립 reviewer도 sensor/filter 함수를 실행하지 않고 wheel 기하·C 부호·pre-step H·bias RW 순서를 유도했다. 이 검토는 수식 판단이며 MC 실행을 독립 재현한 것은 아니다.

**실제 결과:** 출처와 기준을 확인하고 실행 계획을 고정했다. 원 작업·원본 결과는 보존됐다. 변경은 보완 checkout의 최소 공분산 검사와 새 검증 코드/산출물에 한정된다. 세부 해시와 수정 전 파일은 [CORRECTION_RECEIPT.json](CORRECTION_RECEIPT.json), [FILTER_V2_BEFORE.py.txt](FILTER_V2_BEFORE.py.txt), [OUTPUT_MANIFEST.json](OUTPUT_MANIFEST.json)에 있다.

**판정:** 기준 확보 완료. HEAD만으로 현재 구현을 특정하지 않고 소스 해시를 함께 사용했다.

**다음 RF 검증에 주는 의미:** 이후 비교는 이번 수정 코드의 SHA와 활성 센서·초기화 설정을 같이 기록해야 한다. 이번 HEAD나 historical PASS를 RF 준비 완료로 해석하지 않는다.

## 2B — RF 없이 정합 잡음을 넣었을 때 공분산이 맞는가

**질문:** 무오차, gyro만, wheel만, 두 잡음에서 생성 오차와 필터 예측이 설명 가능한가?

**기대값:** wheel의 거리/yaw 독립 잡음을 좌우 wheel로 바꾸면 일반적으로 좌우가 상관된다. 명령 경로에 따라 사전에 정의한 Q를 사용하는 정합 arm과 measured-increment Q를 사용하는 production 근사 arm은 구분해야 한다.

**방법:** sensor-v2 생성기를 사용하고 UWB 갱신을 모두 끈 상태에서 다음 순서로 실행했다. 무오차 → gyro 전파만 → gyro 전파+wheel 관측 → wheel 잡음 → 두 잡음. known calibration과 0 prior를 사용하는 전체 정확 초기화에서는 6상태 전체를 정확히 초기화했다. prior 정합 arm은 기본 prior 표준편차와 같은 Gaussian으로 실제 bias/SF/asymmetry와 독립 pose 초기오차를 생성했다.

Q의 정합 arm은 사전 명령 schedule에서 `q_d=k_s|v_command dt|`, `q_g=N²dt`, `q_o=k_theta|omega_command dt|+k_stheta|v_command dt|`를 정했다. 필터에 생성된 잡음·evaluation true variance를 넘기지 않았다. 이는 정확히 명령을 따르는 제한된 합성 세계에서 공개된 분산 schedule을 안다는 가정이다. 실제 로봇에 같은 Q가 정확하다는 의미는 아니다. measured arm은 현재 sensor-v2의 measured ds/odom-yaw 기반 Q를 그대로 사용했다.

이 시험에서 잡음 law와 초기 prior는 맞출 수 있지만, nonlinear EKF는 여전히 1차 근사이며 gate도 유지된다. 따라서 “비선형 posterior까지 완전한 Gaussian 정합”이라고 부르지 않는다. 이전에 통과한 국소 Jacobian/Joseph 시험은 반복하지 않았다.

**실제 결과:** 새 독립 deterministic 센서 식은 최대 차이 0, 원호 끝점은 약 1.01×10⁻¹⁶, wheel covariance 역변환은 약 2.96×10⁻²¹로 일치했다. 대표 결과는 다음과 같다. RMSE는 t≥2초의 궤적 지표를 seed별 계산한 뒤 평균했다. NEES/coverage는 시간 평균이 아니라 **12초 endpoint의 독립 seed 64개** 결과이다.

| 조건 | 위치 RMSE m | heading RMSE ° | endpoint pose NEES / 실제 df | pose coverage95 |
|---|---:|---:|---:|---:|
| 무오차·전체 정확 초기화 | 수치 roundoff 수준 | 0 | 미정의 / 0 | 미정의 |
| gyro 전파만 | 0.000355 | 0.035897 | 3.265447 / 3 | 0.9375 |
| wheel 잡음 | 0.004863 | 0 | 2.456868 / 2 | 0.921875 |
| 두 잡음·사전 Q | 0.004890 | 0.035737 | 3.507967 / 3 | 0.921875 |
| 두 잡음·measured Q | 0.004890 | 0.035761 | 3.503850 / 3 | 0.9375 |
| prior 정합·사전 Q | 0.154672 | 4.130142 | 2.779590 / 3 | 0.984375 |

사전 Q와 measured Q의 상대 norm 차이는 평균 3.9562%였다. 이 조건에서는 정확도·NEES 차이가 작았으나 두 확률모델이 같다는 증거는 아니다. production 함수와 measured diagnostic의 상태·전체 공분산은 seed 81000에서 exact 일치했다. prior 정합의 full-state NEES는 df=6에서 5.439767이었다. 실제 endpoint pose error second moment/filter covariance trace 비는 약 0.99918이며, 기본 두 잡음에서는 약 1.21658이었다. centered empirical covariance와 bias를 제거하지 않은 second moment를 별도로 저장했다.

gyro 잡음만인데 wheel 관측은 정확한 경우 공유 입력 갱신은 gyro 잡음을 1차에서 제거한다. 대부분 공분산 rank가 0으로 수축한다. 그래도 비선형 2차 잔차와 gate의 드문 거절이 남았고 nullspace 오차 최대 약 2.10×10⁻⁸이다. 이 경우 양의 고유값 방향만의 NEES나 전체 상태 coverage를 강제로 만들지 않았다. rank가 seed마다 0/1인 결과는 단일 df 검정으로 집계하지 않는다.

**판정:** 제한된 정합/근사 대조군과 정확 초기화의 차이를 분리했다. 유한 seed·gate·비선형 근사가 있으므로 보편적인 EKF 일관성 PASS는 아니다.

**다음 RF 검증에 주는 의미:** RF 없이도 검증 가능한 공분산 기준이 생겼다. 이후 R 조정 전에 measured Q와 초기 calibration prior가 어떤 arm인지 명시해야 한다.

## 2C — 공유 gyro·wheel-distance 상관의 부호와 적용이 맞는가

**질문:** 같은 입력의 재사용이 C/R/S/gain/posterior에 올바르게 반영되는가?

**기대값:** 상태 오차 `e=true−estimate`에서 `e_minus=F e_prev−G n`, 관측 잡음 `v=B n`이므로 `C=−G Q Bᵀ`이다. `S=H P_minus Hᵀ+R+2HC`, gain은 `(P_minus Hᵀ+C)/S`이다. gyro variance를 R에 더하는 것만으로 공유 상관을 처리할 수 없다.

**방법:** 동일 prior/입력/seed로 full correlation, wheel-distance 항만, gyro 항만, C=0을 비교했다. 이 옵션은 새 검증 스크립트의 diagnostic subclass에만 있으며 production 설정에 노출하지 않았다. 기록된 joint block `[[P,C],[Cᵀ,R]]`에 innovation vector `[H,1]`을 곱하는 별도 계산으로 S와 gain을 검산했고, 조건부 covariance의 Schur complement를 correlated Joseph 결과와 대조했다. C=0 arm은 표준 상관 없는 갱신의 실제 제한 사례이다.

독립 wheel 전개에서 common scale c=0이면 `d_o=s+eps*b_true*a/4`, `o=(a+eps*s/b_true)/(1+e_b)`이며, 이를 소거한 현재 h식과 일치했다. h는 pose에 의존하지 않고 calibration은 endpoint RW 전에 고정이므로 pre-step H와 예측 P를 쓰는 시점도 맞다. 공유 잡음의 gyro와 distance 두 항을 각각 기록했다.

**실제 결과:** 유효 joint block에서 별도 gain 계산 최대 차이는 약 2.11×10⁻¹⁵, S 차이는 0, posterior 차이는 약 2.39×10⁻¹⁵였다. covariance 대칭성 최대 차이는 약 3.47×10⁻¹⁸이다. 부분/무상관 arm에서도 이번 noisy prior 정합 조건의 joint covariance는 유효했다. 이것이 생략 모델의 물리적 정확성을 뜻하지는 않는다.

full과 C=0의 pose NEES는 2.779590 / 2.779556, 위치 RMSE는 0.154672 / 0.154679m였다. 작은 gyro noise와 큰 초기 pose prior가 있는 이 조건에서는 차이가 작았다. 상관 처리가 불필요하다거나 F02를 설명하는 비율이 작다는 결론으로 확대하지 않는다.

calibration이 정확하고 pure gyro인 독립 식에서는 H=0, `C_heading=q_g`, gain은 `q_g/(q_g+q_o)`, posterior yaw variance는 `q_g*q_o/(q_g+q_o)`이다. C를 없애면 pose gain은 0이 되어 같은 설명을 복구하지 못한다.

**중요한 유지 실패:** 0이 아닌 SF/asymmetry를 알고 있는 one-step nonlinear 조건에서 사전에 정한 4,096개 독립 noise draw를 사용했다. population C 대비 empirical C 상대 오차는 **31.7685%**로 15% 허용오차를 넘었다. R 표본분산은 3.39025×10⁻⁶, 해석값은 3.47529×10⁻⁶이었다. 표본을 늘리거나 seed를 바꿔 PASS시키지 않았다.

저장 draw의 sample Q에는 유한 표본의 비영 교차항이 있었고, `−G sample_Q Bᵀ`는 nonlinear empirical C와 상대 오차 약 8.08×10⁻⁷로 일치했다. population C와의 차이는 x/y 성분에서 약 −2.69/−2.70 표준오차였다. 이는 실패 수치가 표본 상관으로 설명되는 근거이나, 사전 15% 기준을 소급해 통과시킨 것이 아니다. 생성기에서 뽑은 localization stream과 별개의 독립 Gaussian draw를 사용했으며, 이 one-step 검산과 sensor-v2 nonlinear run을 구분한다. [ONE_STEP_INTERPRETATION.json](ONE_STEP_INTERPRETATION.json)에 원래 실패와 후속 해석을 함께 남겼다.

**판정:** 공유 입력 공식·부호·시점·조건부 갱신을 확인했다. 경험적 C의 사전 수치 기준은 미충족이므로 제한된 부분 확인이다.

**다음 RF 검증에 주는 의미:** full correlation 규약은 유지한다. 후속 검증에서 이 미충족 항목을 숨기거나, R만 증가시켜 대체해서는 안 된다.

## 2D — 체계 오차와 초기화는 무엇을 만드는가

**질문:** bias/SF/asymmetry, wheelbase, common scale, 초기 prior를 혼동 없이 설명할 수 있는가?

**기대값:** 알려진 고정 calibration은 생성기 수식을 역으로 풀어 경로를 복원한다. 모르는 wheelbase와 common scale은 6상태에 없는 mismatch이다. pose만 정확해도 nuisance 초기오차와 prior가 있으면 전체 상태의 정확 초기화가 아니다.

**방법:** 고정 bias 0.12°/s, SF 0.0104, asymmetry 0.0064를 단독으로 추가하고 known calibration/pose-exact unknown calibration을 비교했다. 주요 조합은 bias+asymmetry 한 개이다. wheelbase는 기본 0, 실제 e_b=0.0075를 알고 보정, 같은 실제 값이 있으나 estimator가 모르는 조건이다. common scale=0.01은 별도 mismatch arm이다. 초기화는 full6 exact/P0=0, Gaussian prior 정합, pose exact+nuisance default prior, 기존 production pose-only RNG+nuisance estimate0/부호 sensitivity 분포로 구분했다. 값과 실제 분포는 PLAN.json 및 [DT_AND_INITIALIZATION.json](DT_AND_INITIALIZATION.json)에 있다.

**실제 결과:** 알려진 bias/SF/asymmetry 각각은 deterministic 경로를 roundoff 수준으로 복원했다. unknown wheelbase의 영향은 이번 gyro 우세 조건에서 작았다. known/unknown heading RMSE는 약 0.035740/0.035742°였다. 그럼에도 noiseless 관측 기하식에서는 odom yaw가 `1/(1+e_b)`로 변하는 약 0.744%의 차이가 존재한다. 작은 RMSE 차이를 wheelbase 효과가 없다는 증거로 해석하지 않는다.

common scale=0.01에서는 위치 RMSE가 0.011841m, pose NEES가 8.954979, coverage가 0.5가 됐다. 기준 두 잡음 arm은 0.004890m, 3.507967, 0.921875였다. 공통 scale은 현재 상태에 없고 source를 고쳐 추정한다고 주장하지 않는다.

production 초기화에서는 pose RMSE 0.155035m, heading 4.103881°, pose NEES 2.920442, full6 NEES 6.254218이었다. 이는 동일 초기 분포와 경로에 한정된 결과이다. Gaussian calibration prior 정합 arm과 부호를 선택한 sensitivity 분포는 분포 자체가 다르며, 값이 비슷해도 동일 모델로 취급하지 않는다. RF 없는 odometry는 전역 pose gauge를 고정하지 않으므로 초기 위치/heading 오차가 남는 것 자체가 구현 오류는 아니다.

### 확인한 실제 수치 결함과 최소 수정

무잡음 unknown bias, unknown asymmetry, bias+asymmetry의 세 arm에서 각 64개, **총 192개 run**에 유의한 음의 posterior 또는 joint covariance가 생겼다. 예를 들어 bias+asymmetry의 최종 최소 eigenvalue는 −3.44720×10⁻¹¹이다. 기존 `run_filter_v2`는 고정 −1e−10 기준 때문에 실제 같은 saved-input 실행을 성공으로 반환했다. 자체 diagnostic loop에도 같은 느슨한 검사가 있었다.

그런 공분산에서 음의 방향을 버린 NEES를 정상 chi-square로 해석하면 안 된다. 수정 전 원자료/집계는 보존하고, [SUMMARY_VALIDATED.json](SUMMARY_VALIDATED.json)에서는 세 arm을 `INVALID_COVARIANCE`로 재분류하여 NEES·coverage를 미정의로 만들었다. 실패 sample과 invalid mask를 [VALIDITY.json](VALIDITY.json) 및 raw `VALIDITY_*.npz`에 보존했다. 실패 seed를 제외해 성공 arm의 평균을 만드는 방식은 사용하지 않았다.

최소 수정은 `filter_v2.py`의 사후 검사이다. float64의 `512*eps*scale` 기준으로 대칭성/PSD를 확인한다. scale은 initial covariance, 현재 covariance, 갱신 전 predicted covariance의 spectral norm 규모이다. 거의 0으로 취소된 posterior의 roundoff를 그 작은 posterior 자체로만 판단하지 않도록 prediction 규모를 포함했다. 이 규약을 saved diagnostic 결과의 재판정에도 적용했다. projection, eigenvalue clipping, regularization, process noise/prior/R 증가 또는 gain 변경은 없다.

수정 후 actual `run_filter_v2`는 bias+asymmetry seed 81000을 sample 2, t=0.4초에서 최소 eigenvalue −5.50708×10⁻¹⁵, 허용오차 1.22964×10⁻¹⁷로 명시적으로 거부했다. 정상 measured-noise와 완전 취소 gyro 조건은 **추정·전체 공분산 배열이 수정 전과 exact 일치**하며, 정상 prior+noise 실행도 유지됐다. 새 targeted regression 4개를 통과했다. [COVARIANCE_GUARD_BEFORE.json](COVARIANCE_GUARD_BEFORE.json), [COVARIANCE_GUARD_AFTER.json](COVARIANCE_GUARD_AFTER.json), [GUARD_TESTS.log](GUARD_TESTS.log)에 전후 증거가 있다.

원인은 exact zero-noise 관측과 nonlinear calibration 오차에서 ill-conditioned 공분산 수축이 나타나는 경계이다. 어떤 연산이 처음 numerical indefiniteness를 만드는지의 세부 안정화는 미해결이다. guard는 이를 안전하게 거부하는 수정이며, covariance를 올바르게 복원하는 알고리즘 수정은 아니다. SF 단독처럼 PSD이나 거의 0인 공분산에 작은 잔차가 남는 경우도 있다. nullspace 오차를 별도 표시하며 전체 coverage를 주장하지 않는다.

**판정:** 체계 오차와 prior 영향 분리 완료. 작은 covariance의 실패를 놓치는 validation 결함은 수정했다. 무잡음 nonlinear calibration의 추정·수치 안정성 자체는 미해결이며 해당 적용 범위는 채택하지 않는다.

**다음 RF 검증에 주는 의미:** RF 잔차에 앞서 invalid covariance를 차단해야 한다. common scale/unknown wheelbase 및 calibration prior 불일치는 별도 조건으로 보존하고 RF R로 감추지 않는다.

## 2E — dt·운동 조건·RW·slip의 평가와 원인 판정

**질문:** sample rate나 운동 조건이 분산 law, 이산 bias 규약, 식별성에 어떤 차이를 만드는가?

**기대값:** 같은 12초 경로에서 white gyro 누적분산은 N²T, wheel-distance/yaw 누적분산은 k계수와 총 이동/회전량으로 결정된다. bias RW는 interval 시작값을 사용하므로 연속 Brownian 적분과 다르다. 직선 일정속도에서는 bias–asymmetry가 혼동되며 SF의 직접 정보가 없다.

**방법:** dt 0.1/0.2/0.4초에서 기본 Gaussian 및 bias RW sigma=1e−4 rad/s/√s를 분리했다. sensor 생성 잡음은 true geometry와 interval 시작 bias를 별도 식으로 제거해 누적 오차를 계산했다. 64개 독립 seed의 분산과 confidence interval을 사용했으며 시간 샘플을 독립 반복으로 세지 않았다. slip은 마지막 별도 arm에서만 활성화했다. 식별성은 calibration 행 `[-dt, -a, ds/b]`의 rank 및 실제 오차/공분산 변화를 함께 봤다.

**실제 결과:** 기본 Gaussian endpoint pose NEES는 dt=0.1/0.2/0.4에서 3.404848/3.507967/3.125757, heading RMSE는 0.036208/0.035737/0.033689°였다. 64 seed의 df=3 평균 NEES 참조 구간은 [2.430010,3.629143]이며 세 값은 내부이다. 실제 endpoint error covariance와 filter covariance가 완전히 같다는 주장이나, 다중 비교를 통제한 승인 기준은 아니다. endpoint coverage 및 양측 tail과 Wilson interval은 SUMMARY_VALIDATED.json에 있다.

누적 센서 분산의 해석값은 distance 3.4×10⁻⁵m², gyro 8.22467×10⁻⁷rad², odom yaw 2.57×10⁻⁴rad²였다. gyro의 표본분산은 8.00955×10⁻⁷ / 8.81897×10⁻⁷ / 7.73704×10⁻⁷이었다. distance의 표본분산은 4.73991×10⁻⁵ / 4.20857×10⁻⁵ / 3.65774×10⁻⁵였다. **dt=0.1 distance 항에서는 탐색적 95% 분산 interval [3.43908×10⁻⁵,6.95256×10⁻⁵]가 기대값을 포함하지 않았다.** 기본/RW arm은 동일 wheel stream을 공유하므로 이것을 두 독립 실패로 세지 않는다. 이 변동을 숨기거나 추가 seed로 지우지 않았다.

bias RW의 endpoint variance 기대값은 모든 dt에서 1.2×10⁻⁷이다. gyro에 들어가는 누적 시작-bias 적분분산은 `sigma_b² dt³ (n−1)n(2n−1)/6`이다. dt 0.1/0.2/0.4의 해석값은 5.6882/5.6168/5.4752×10⁻⁶rad², 실제 표본값은 4.96382/5.56865/5.42240×10⁻⁶이었다. 연속 Brownian 참조는 5.76×10⁻⁶으로 같지 않다. filter의 endpoint bias RW 추가 시점은 생성기의 이산 규약과 일치하며, 연속시간 exact interval 적분을 구현했다고 표현하지 않는다.

직선 일정속도/속도 변화/mixed의 국소 calibration rank는 1/2/3이었다. 실제 단독 경로 시험의 heading RMSE는 1.093467/0.409505/0.630770°였다. 더 풍부한 운동이 항상 해당 finite-seed RMSE를 단조 감소시키는 것은 아니다. 일정속도에서 pose NEES 4.027901, error/filter pose trace 비 1.75832로 불일치가 남았다. bias/SF/asymmetry의 endpoint 오차와 공분산은 원자료에 있다. 이는 고정 nuisance 값이 prior 분포와 다른 조건의 탐색적 진단이다. global x/y/heading을 odometry만으로 관측 가능하게 만든 결과는 아니다.

slip은 1,280개 eligible interval에서 10회 발생했고 시간 확률 law의 기대값은 12.8회였다. Student-t(df=3) heavy tail로 생성했고 gate 거절 총계는 기본 4회에서 slip arm 7회로 달라졌다. 이번 작은 표본과 gyro 우세 조건에서는 RMSE 차이가 작았다. 꼬리의 강건성이나 Gaussian 모델 정합을 입증했다고 하지 않는다.

**판정:** dt와 이산 적분 규약을 확인하고 motion-dependent 식별성 및 heavy-tail의 적용 한계를 분리했다. 일부 표본 분산 참조가 벗어난 상태를 유지했다.

**다음 RF 검증에 주는 의미:** 센서 파라미터뿐 아니라 dt, command/measurement Q, 초기 분포, 운동 excitation을 고정해야 한다. 센서 시험의 작은 RMSE나 높은 coverage를 RF 조건의 F02 해결로 옮기지 않는다.

## 실행·검증·채택의 분리와 남은 항목

| 항목 | 구현/실행 상태 | 검증 판정 | 채택 범위 |
|---|---|---|---|
| 기존 sensor-v2 재사용·출처 | 완료 | source15 및 원본 보호 해시 확인 | 기존 source 출처 보존 |
| 센서 기하·기본 Gaussian | 완료 | 제한 정합 대조군 확인 | 해당 합성 조건의 기준 |
| 공유 입력 공식/시점/conditional update | 완료 | 수식/블록 검산 확인, empirical15% 미충족 | full correlation 규약 유지; 전체 PASS 아님 |
| PSD guard correction | 최소 수정+targeted4개 완료 | invalid case 거부, 정상 배열 불변 | validation guard만 채택 |
| 무잡음 nonlinear calibration 안정화 | 원자료 실행 완료 | 192개 invalid, 별도 거부/집계 미정의 | 미채택·미해결 |
| common scale/unknown wheelbase | mismatch 실행 완료 | 적용 한계 확인 | 상태에 포함됐다고 주장하지 않음 |
| dt/RW/slip | 제한 실행 완료 | 이산 규약 확인, 분산 일부 벗어남·tail 표본 부족 | 실물/RF 검증으로 확대하지 않음 |
| F01/F02 | 이번 해결 범위 밖 | OPEN, scientific_PASS=false | 그대로 유지 |

전체 2,048개 baseline run의 실행 오류는 0이고, 후속 수치 판정에서 192개 covariance-invalid를 확인했다. 두 숫자는 다른 상태이다. 무잡음 고정 파라미터 arm의 64개 seed는 실제로 동일한 deterministic 입력을 만드는 복제이며, 독립 확률 표본 64개로 취급하지 않는다. 192개 실패는 세 deterministic 조건의 재현을 뜻한다. 이들에 표준 chi-square 신뢰도를 부여하지 않았다. 원 baseline `SUMMARY.json`은 당시 느슨한 검사 결과로 보존하며 최종 판단에는 `SUMMARY_VALIDATED.json`을 사용한다. source correction 후 전체 MC를 재실행하지 않았다. gain/model 변경이 없는 guard 수정이므로 저장 입력의 4개 targeted regression과 모든 baseline raw의 재분류로 확인했다. 알고리즘 안정화 전후 RMSE 개선으로 보고하지 않는다.

미수행 항목은 큰 표본으로 empirical C를 다시 통과시키는 일, continuous Brownian exact interval 모델, slip tail의 광범위 강건성, calibration 수치 안정화의 완전한 수정, RF·production·실물 일반화이다. 추가 실행 없이 과학적 결과를 승격하지 않는다.

다음에 필요한 검증은 **별도 승인된 L1/LoS 단계에 앞서 이 센서 기준과 제외 조건을 인계하는 것**이다. 무잡음 calibration을 사용하려면 먼저 수치 안정화와 nullspace 잔차를 별도 과제로 해결해야 한다. 이번 세션은 2단계에서 종료하며 L1/L2나 이후 RF 단계는 시작하지 않는다.

## 재현 경로와 명령

- 입력/코드 기준: [PLAN.json](PLAN.json), 복사 출처 `D:/SLAM_bot/artifacts/DRIVE_SIM_SENSOR_V2_REVIEW_20261008_01a11a7b/COPIED_SOURCE_MANIFEST.json`.
- 과거 evidence: 원 checkout의 `results/SENSOR_V2_20261008/{MODEL_CONTRACT.md,PREREG_V2.md,SENSOR_V2_REAUDIT_KO.md,CHANGE_MANIFEST.json,CORRELATION_ABLATION,validation_verified.json}`. 과거 실행을 이번 성과로 다시 세지 않았다.
- 이번 전체 raw: `raw/{arm}_{seed}.npz`. truth6/estimate6/full covariance/input/generated parameters/Q/innovation/R/S/H/C/gain/prediction/status/time/evaluation mask를 보존한다. `raw/VALIDITY_{arm}_{seed}.npz`는 원 raw SHA와 invalid mask이다.
- run 상태: [STATUS.json](STATUS.json), [RUNS.json](RUNS.json), [VALIDITY.json](VALIDITY.json), [POST_ANALYSIS_STATUS.json](POST_ANALYSIS_STATUS.json).
- 수식·표본 분석: [INDEPENDENT_CHECKS.json](INDEPENDENT_CHECKS.json), [INDEPENDENT_ONE_STEP.npz](INDEPENDENT_ONE_STEP.npz), [ONE_STEP_INTERPRETATION.json](ONE_STEP_INTERPRETATION.json), [DT_AND_INITIALIZATION.json](DT_AND_INITIALIZATION.json), [INDEPENDENT_REVIEW.json](INDEPENDENT_REVIEW.json).
- 실행: `py -3.10 -X utf8 scripts/drive_sim/validate_sensor_v2_stage2.py --prepare`, 다음 `--run` — exit 0. [RUN.log](RUN.log).
- saved raw 분석: `py -3.10 -X utf8 scripts/drive_sim/analyze_sensor_v2_stage2.py` — exit 0. [ANALYSIS.log](ANALYSIS.log). 새 Monte Carlo를 실행하지 않는다.
- correction regression: `py -3.10 -X utf8 -m pytest tests/test_sensor_v2_covariance_guard_stage2.py -q` — exit 0, 4 passed. [GUARD_TESTS.log](GUARD_TESTS.log).
- 변경 위치: `src/qclean_uwb/drivesim/filter_v2.py`의 `covariance_diagnostic()` 및 `run_filter_v2()` 사후 검사, 새 `scripts/drive_sim/{validate_sensor_v2_stage2.py,analyze_sensor_v2_stage2.py}`, 새 `tests/test_sensor_v2_covariance_guard_stage2.py`.
- 최종 해시/보존/명령 receipt: [OUTPUT_MANIFEST.json](OUTPUT_MANIFEST.json), [FINAL_CHECKS.json](FINAL_CHECKS.json). 파일 이동·삭제는 없다.
