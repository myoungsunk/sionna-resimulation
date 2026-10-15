# 물리 피처 기반 R_s — A/B/C 실제 실행 및 감사 결과

2026-10-15 | myoungsunk/sionna-resimulation | research/physics-rs-staged-audit-20261015

## 결론
물리 피처는 관측오차 예측에 추가 정보를 제공했다. Full RF/R2 Mount 0°에서는 B0/L0/L1/L2 모두 Heading RMSE가 약 42% 개선됐다. 그러나 Mount 45°에서는 악화했고, 전체 Pose 공분산의 일관성도 해결하지 못했다. **피처의 유용성은 지지하지만, 이번 R_s-only 정책의 일괄 운용 채택은 보류한다.** 결과를 좋게 만들기 위한 사후 모델 튜닝은 하지 않았다.

## 실행 위치·보존
입력 확보·원 SHA 감사는 [Actions 38681443033](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38681443033), [artifact 11948391783](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38681443033/artifacts/11948391783)이다. 입력 snapshot commit은 5fd96b5da004a9b92007574f6b17decb31febf9a이다. **A/B/C 및 추가 진단은 현재 대화의 실행 컨테이너에서 실제 실행했다. GitHub Actions가 모든 과학 계산을 수행한 것은 아니다.**

원 RF one-step artifact 11782748118, 원 R2 baseline artifact 11940333419를 재사용했다. 원 RF H/LUT/Q/Range R_r/core.py는 변경하지 않았다. 120개 파일 SHA256, 원 manifest 31개 경로, 핵심 7개 Git blob을 대조했다. 이 폴더에는 실행·진단 코드와 결과 요약을 게시하며 전체 raw x/P, 학습 모델, OOF 예측, 실패/재감사 로그는 대화에 첨부한 physics_rs_full_results.zip에 보존한다. 결과 ZIP에 원 250MB H 입력을 중복 포함하지 않았다.

## 완료 범위
| 단계 | 실행 범위 | 결과 |
|---|---|---|
| 사전 감사 | 실행/진단 코드 검토, 수학·음성 대조, 입력/코드 해시 | 최종 22개 시험 PASS |
| A | 7 case × LoS/Full, 각 채널 9519 pose | 19038행, 17개 피처 |
| 관측 재현 | 원 14502시점 | s/r 최대 차이 정확히 0 |
| B | R2/R4/R5 holdout × 6피처군 | 18모델, 기준선 포함 152304 OOF 예측 |
| C1 | 14 trace × 7방법, 동일 prior/공통 gate | 98개 평가행 |
| C2 | R2 2 mount × 2 channel × 4 bias × 7방법 | 112개 평가행 |
| 사후 검산 | 원시 P와 평가표 별도 수식 재계산 | 211162 P행렬, 210평가행 |
| 추가 진단 | L2/Full 두 mount | 원 scalar 구현 재현 및 고정 gate 비교 |

감사는 동일 assistant의 소스 검토와 독립 수식·음성 대조이며 제3자 감사라고 주장하지 않는다. PSD 검산과 실제 통계적 calibration은 구분한다.

## 감사 결함과 수정
1. 첫 tap과 전체창에 동일 절대 epsilon을 더한 로그비 regularizer가 이상적 LoS에서도 가짜 괴리도를 만들었다. 각 지지영역의 전력에 상대적인 epsilon으로 수정하고 기존 1e-12 시험 기준을 유지했다.
2. RandomForest 병렬 prediction 합산 순서 때문에 heldout label 불변성 대조에서 1.11e-16 차이가 발생했다. 학습 2 thread는 유지하고 예측은 1 thread로 고정하여 정확 비교를 통과했다.
3. RF SAMPLES 좌표/yaw는 6자리 직렬화이고 주행 truth는 더 정밀했다. 직렬화된 좌표를 정확 비교하도록 수정했다. 원 추정 결과의 허용기준을 늘린 것이 아니다.
4. 첫 입력 bundle에 불필요한 과거 대형 trace가 포함됐다. 해당 3.5GB 패키지는 분석에 사용하지 않았고 필요한 파일만 포함한 250MB 패키지를 재감사했다.
5. 중단된 긴 계산을 숨기지 않고 checkpoint를 추가했다. 기존 모델 재사용 때 데이터 hash·split·피처·모델 파라미터를 확인했고 결과를 보고 학습설정을 바꾸지 않았다.
6. C1 batch Joseph와 C2 최적화 scalar는 독립 수학 대조 후 사용했다. 저장된 이전 scalar C1 결과와 일치했고, 추가 진단의 실제 G5 두 궤적은 원 scalar x/P와 정확히 일치했다.
7. 단계별 GO에 실제 코드 hash를 저장했다. 수정한 실행/진단 코드는 다시 감사했다. 실패·부분 결과는 결과 ZIP의 audit/에 남겼다.

## A. 물리 피처
| 그룹 | 구성 |
|---|---|
| G0 | 측정 거리, FP 총전력 로그, abs(s_FP) |
| G1 | G0 + 초기 4/8/16tap 에너지, 합산 delay spread, 포트 peak 지연차 |
| G2 | G0 + FP/80tap 로그 편파비 괴리, 초기 4/8/16tap 편파차, 가중 tap 편파 분산 |
| G3 | G0 + 주파수 Jones 고유값 비, 전력가중 주파수 편파 분산 |
| G4 | G0 + 20/30/40% 검출 임계값에 대한 s·delay 민감도 |
| G5 | G0~G4 결합 |

원 30% detector와 EKF 입력 관측은 바꾸지 않았다. 지연창은 FP부터 80tap, 초기창은 4/8/16tap이다. Jones 지표는 주파수 2차 모멘트의 작은 고유값/trace이지 물리적 탈편파율 또는 완전한 yaw 불변량이 아니다. zero/missing packet은 clean 0이 아닌 invalid로 처리했다.

Full의 abs(s_full-s_los)에 대한 Spearman 상관:
| 피처 | R2 | R4 | R5 |
|---|---:|---:|---:|
| measured range | .6257 | .6443 | .6547 |
| delay spread | .4387 | .5498 | .4585 |
| FP/80tap 로그비 괴리 | -.0302 | .1596 | -.0190 |
| 초기4tap 편파차 | .4713 | .4943 | .5093 |
| Jones diversity | .4076 | .5583 | .4424 |
| 주파수 편파 분산 | .5643 | .5722 | .5911 |
| 검출 s 민감도 | .5067 | .5643 | .5983 |

LoS/Full 중앙값은 Jones 지표 .004067/.103055, 주파수 s 분산 .001164/.087002였다. 실제 LoS에서도 값이 0이 아니고 yaw에 따라 변했다. FP-전체 로그비 괴리도를 가장 직접적이고 보편적인 오염 지표로 선정할 근거는 없었다. 주파수 편파 변화와 검출 민감도는 세 route에서 양의 연관을 보였다. 상관계수는 공분산 calibration이나 인과 기여율이 아니다.

## B. 경로를 분리한 오차 예측
Target은 e_total=s_channel-h_LUT(true_pose)의 제곱이다. 이는 중심분산이 아닌 조건부 평균제곱오차이다. e_MP=s_full-s_los 및 e_LUT=s_los-h_LUT는 평가용으로 분리했다. 채널/true pose/oracle 오류를 predictor로 넣지 않았다.

동일 route의 yaw/mount/anchor/channel을 같은 fold에 묶었다. 다른 route의 coincident XY<=1e-4m 학습행을 제거했다. train/test 행은 R2 11216/7818, R4 15344/3688, R5 11506/7532이다. **매우 인접한 다른 위치는 여전히 남으므로 독립 환경 검증은 아니다.** 같은 위치의 반복 수에 역비례하는 가중치를 사용했다.

고정 모델: RandomForest 160 trees, depth6, min-leaf40, seed20261015. Holdout 결과로 파라미터를 바꾸지 않았다. Full 관측오차 제곱 예측의 R²:
| 모델 | R2 | R4 | R5 |
|---|---:|---:|---:|
| G0 | .0202 | -.3058 | .0542 |
| G2 | .0597 | -.3158 | .1478 |
| G3 | .1748 | -.4419 | .2836 |
| G4 | .2879 | .0306 | .4072 |
| G5 | .3868 | .0824 | .4282 |

EKF용 실험은 R_eff=clip(R_pred,.0081,.81)로 동결했다. 기존 R0보다 작게 만들지 않는 inflation-only 비교이며 별도 LoS 분산을 다시 더하지 않았다. Full 관측오차의 명목95% 구간 실제 포함률(%), site 가중:
| 모델 | R2 | R4 | R5 |
|---|---:|---:|---:|
| R0 | 86.24 | 82.08 | 94.28 |
| G0 | 95.57 | 93.46 | 96.57 |
| G3 | 95.01 | 95.92 | 98.33 |
| G4 | 95.54 | 93.04 | 99.31 |
| G5 | 96.30 | 95.53 | 99.54 |

R5의 높은 포함률은 과대분산 가능성도 의미한다. floor 없는 raw R_pred는 일부 경로에서 과소분산·NLL 악화를 보였다. **관측오차의 포함률 개선을 EKF Heading/Pose calibration 성공으로 해석하지 않는다.**

## C1. 동일 prior·동일 gate one-step
각 채널 6201개 t>=30 시점의 pooled Heading RMSE(deg):
| 모델 | LoS | Full |
|---|---:|---:|
| R0 | .75111 | 2.34543 |
| G0 | .77565 | 1.63319 |
| G1 | .75114 | 1.51319 |
| G2 | .75316 | 1.57429 |
| G3 | .75140 | 1.52710 |
| G4 | .75150 | 1.66805 |
| G5 | .75187 | 1.58063 |

원 기준선을 모든 시점에서 1e-9 이내로 재현했다. 이 단계는 P4와 같은 zero-cross bias augmentation이다. 단일 시점 결과를 누적 gyro-bias 보정 성능으로 주장하지 않는다.

## C2. R2 재귀 Heading RMSE
B0=0, L0=.01, L1=.05, L2=.20 deg/s의 양의 고정 gyro bias, seed0, 각 조건 829평가시점이다. R2를 학습하지 않은 R4/R5 모델만 적용했다. **Bias Freeze 없이 R_s만 바꿨다.** 수치 gate threshold는 그대로이지만 각 방법의 predictive NIS로 gate를 판단했다.

Full/Mount0 Heading RMSE(deg):
| 방법 | B0 | L0 | L1 | L2 |
|---|---:|---:|---:|---:|
| R0 | 7.4900 | 7.4991 | 7.5399 | 7.5209 |
| G0 | 5.8443 | 5.8483 | 5.8543 | 5.7797 |
| G1 | 4.5015 | 4.5100 | 4.5317 | 4.5477 |
| G2 | 4.2708 | 4.2835 | 4.2978 | 4.2986 |
| G3 | 4.6866 | 4.6899 | 4.7098 | 4.6855 |
| G4 | 4.6812 | 4.6705 | 4.6945 | 4.7580 |
| G5 | 4.3038 | 4.3047 | 4.3257 | 4.3776 |

Full/Mount45 Heading RMSE(deg):
| 방법 | B0 | L0 | L1 | L2 |
|---|---:|---:|---:|---:|
| R0 | .8450 | .8444 | .8436 | .8481 |
| G0 | 1.0943 | 1.0936 | 1.0881 | 1.0593 |
| G1 | 1.7555 | 1.7551 | 1.7612 | 1.7909 |
| G2 | 1.3990 | 1.3991 | 1.3968 | 1.4067 |
| G3 | 1.3833 | 1.3832 | 1.3832 | 1.3625 |
| G4 | 1.5590 | 1.5592 | 1.5625 | 1.5798 |
| G5 | 1.3488 | 1.3487 | 1.3511 | 1.3610 |

Mount0 G5는 네 bias 모두 약42% 개선했다. L2에서는 G0 5.7797deg보다 G5 4.3776deg가 약24% 낮았다. 그러나 Mount45에서는 모든 새 모델이 악화했다. LoS/L2는 G5에서 Mount0 .2435→.2375deg, Mount45 .1583→.1581deg로 거의 유지됐다.

### L2 Full 불확실성
| Mount | 방법 | Heading RMSE deg | Bias RMSE deg/s | Heading NEES | Heading95 % | Pose NEES | Pose95 % |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | R0 | 7.52091 | .09608 | 86.3733 | 16.285 | 297.853 | 16.767 |
| 0 | G5 | 4.37759 | .07102 | 19.2868 | 39.083 | 2787.35 | 16.767 |
| 45 | R0 | .84809 | .01480 | 3.8606 | 59.952 | 86.8445 | 0 |
| 45 | G5 | 1.36103 | .01746 | 6.19684 | 48.010 | 135.046 | 0 |

**Heading 개선과 전체 공분산의 성공은 별개다.** Mount0에서 G5는 Heading NEES를 낮추지만 Pose NEES를 약9.36배 악화시켰다. 위치 RMSE는 .8710→.6598m로 개선되었으므로 점추정 오차 감소만으로 공분산 정합을 주장할 수 없다.

## D. 예상 밖 Pose NEES 추가 진단
진단 코드도 감사하고 수학 대조를 추가한 후 실행했다.

1. 원 scalar predict/update로 Full/L2 두 G5 궤적을 다시 계산했다. 최적화 코드와 상태·공분산 최대 차이는 두 경우 모두 **정확히0**이었다. 이 두 사례의 악화를 계산 최적화 버그로 설명할 근거는 없었다.
2. Cholesky를 [psi,x,y] 순으로 분해했다. Mount0/R0는 Heading 항86.373+조건부XY211.480=Pose297.853, G5는 Heading19.287+조건부XY2768.063=Pose2787.350이었다. **G5 Pose NEES의99.31%가 조건부XY 항**이었다. 이것은 통계적 분해이지 특정 물리 원인의 인과 기여율이 아니다.
3. 수용 관측 수는 Mount0 766→808, Mount45 649→791(각829)이었다. 오프라인 진단으로만 R0의 수용 일정을 G5에 강제했다. Mount0 Heading4.902deg/Pose NEES9337.95, Mount45 Heading1.558deg/Pose91.00으로 나왔다. Gate를 같게 만들어도 문제가 사라지지 않았으므로 수용 증가만으로 악화 전체를 설명할 수 없다. 이 사후 진단은 배포 정책이나 본 비교의 대체 결과가 아니다.

## 사후 수치 검산 및 역사적 재현
원시 P 211162개, 표210행을 독립 atan2 angle wrapping·Cholesky NEES·별도 평균 계산으로 확인했다. 기존 보고값과 최대 절대 차이는 1.6370904631912708e-11이었다. 원시 x/P의 finite/PSD, Rs의 OOF key·floor·cap 일치도 확인했다.

기존 R2 artifact와 strict1e-9 비교는 **15/16 통과, B0/Full/Mount0 한 조건 미통과**였다. 최대 state 차이4.3857881465436677e-8, covariance3.5062934516548114e-10, gate차이0이다. 임계값을1e-6으로 바꿔 PASS하지 않았다. 현재 환경의 원 전체 run_filters와 새 R0 비교는 Full/Mount0 네 bias에서 정확히0이었다. 이전 상태를 고정한 원 operator 한-step 대조는 최대 state8.88e-16/gate0이었다. 미세 수치 차이 누적과 양립하지만 정확한 환경별 원인은 확정하지 않았다. 과거 재현 한계와 새 paired 실험 내부 일치를 별도 보고한다.

## 최종 판단과 한계
- 물리 피처의 추가 정보와 Full/Mount0의 안정적인 Heading 개선은 후속 연구의 유효한 근거다.
- 반면 현재 R_s-only 모델은 Mount45와 전체 Pose 공분산 정합을 개선하지 못하므로 일괄 채택하지 않는다.
- 한 복도/noise-free RF/재귀 sensor seed0/양의 일정 bias에 한정된다. 독립 새 환경·실물 포트 위상 교정은 미검증이다.
- H만으로 진짜 ray별 지연 label을 복원하지 않았다. 따라서 미분리 반사만의 검출 성능은 미검증이다. equal-delay blind spot은 합성 수학 대조로만 확인했다.
- signed mean, R_rs, R_r, 시간상관을 수정하지 않았다. 이 항들의 인과 기여율은 이번 결과만으로 확정하지 않는다.
- scientific_PASS=false는 피처 연구가 무의미하다는 뜻이 아니라 범용 교정/운용 검증을 완료하지 않았다는 뜻이다.

## 전달 파일 SHA256
- physics_rs_source.zip: dc7c582705675dbc49f28411bc725587788f300fb2e37467bfb653d41cc099f1
- physics_rs_full_results.zip: beb1318c98714bb9a646a822fced949a2b0583ee4637fe40654c836dd1e3e66d
- physics_rs_audited_inputs.zip: 8d905d61fe850b21fabe031f1bf77fa4762c60f86ed890bd05a74cb87236cb65

대화 첨부 ZIP에는 전체 실패/감사 로그 및 raw 결과가 있다. GitHub code/에는 11개 실행·진단·테스트 파일을 게시한다. 결과보고서 생성·압축용 release.py는 source ZIP에 추가로 포함되어 있다.
