# 생성 코드·입력 데이터 및 마운트 45° 범위 확인

2026-10-28, 기준 커밋 `16eb9521e19f04fd75bdeb02abd4cc687debb944`.
기존 코드·입력·결과를 변경하지 않고 누락된 준비 입력 두 개와 출처 확인 기록을 추가했다. 시뮬레이션, 학습, EKF 재실행은 수행하지 않았다.

## 요청 파일의 브랜치 위치

| 요청 항목 | 저장소 위치 | 상태 |
|---|---|---|
| `DS_MASK_CAUSAL_X0A_X1_20261026_01a1775b/run_stage.py` | [기존 run_stage.py](../DS_MASK_CAUSAL_X1_X2_20261026/x1/run_stage.py) | 이미 커밋됨; 원본 생성본과 SHA-256 동일. `load_case`는 86행부터 |
| `DS_NONLINEAR_E1_E4_20261027_01a1775b/run_experiments.py` | [기존 run_experiments.py](../DS_MASK_CAUSAL_X1_X2_20261026/e1_e4/run_experiments.py) | 이미 커밋됨; 원본 생성본과 SHA-256 동일 |
| `OBSERVATION_FEATURES_LABELS.csv.gz` | [prepared/OBSERVATION_FEATURES_LABELS.csv.gz](prepared/OBSERVATION_FEATURES_LABELS.csv.gz) | 이번에 추가; 원본 아티팩트 SHA-256 manifest와 동일 |
| `OOF_PARAMETERS.csv.gz` | [prepared/OOF_PARAMETERS.csv.gz](prepared/OOF_PARAMETERS.csv.gz) | 이번에 추가; 원본 아티팩트 SHA-256 manifest와 동일 |
| `results_murec/MR_SERIES.csv.gz` | [기존 MR_SERIES](../PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz) | 이미 커밋됨; 동결 입력과 Git blob 바이트 동일 |
| `results_hgate/HG_SERIES.csv.gz` | [기존 HG_SERIES](../PJ_DS_GATED_20261021/results_hgate/HG_SERIES.csv.gz) | 이미 커밋됨; 동결 입력과 Git blob 바이트 동일. 로컬 sparse checkout에서 생략됐던 파일 |

이 패키지는 입력 보완이며 완전한 독립 실행 배포본은 아니다. 과거 실행 스크립트의 절대 경로와 원본 RF·FFD bank·trace 의존성은 그대로 보존했다. 실제 재실행 시 기존 결과 폴더를 출력 경로로 사용하면 안 된다.

## μ와 R의 원천 및 정합 확인

`load_case`는 case/channel/pose_id로 표를 정렬한다. BASE의 `mu_r, mu_s, Vr, Vs, Crs`는 `OOF_PARAMETERS`의 `POWER_DIAG` 행에서 가져오며, μ_M은 특징 표의 `e_r - MR.MU_R_EXDS__meas_r_cm/100`으로 복원한다. HG의 `e_r`도 같은 특징 표와 일치해야 한다.

원본 RF 특징 표의 전체 행과 replay 시계열의 행 수는 다르다. replay에 사용된 pose_id 부분집합으로 정렬하는 원래 loader 동작을 유지해야 한다. 검증은 7 case × B0/L2의 MR/HG 시간·ID 정합, BASE 평균 복원, HG 잔차 및 유한 μ_M을 확인했다. BASE 평균 복원 최대 오차는 약 6.53e-16이다.

- [INPUT_SOURCE_MAP.json](INPUT_SOURCE_MAP.json): 원본 위치, 브랜치 위치, 바이트 수와 SHA-256
- [VALIDATION.json](VALIDATION.json): 해시·14조건 입력 조인 검증
- [verify_inputs.py](verify_inputs.py): 입력 정합 재검산; pandas/numpy 필요. sparse checkout에서 기존 파일은 Git blob으로 읽는다.

## 요청한 마운트 45° Full RF 채널

확인 범위는 `execution_33e9849/p2`의 원본 채널 디렉터리와 입력 manifest, 준비된 아티팩트다. 다른 서버·미복원 외부 아카이브 전체를 검색했다는 의미는 아니다.

| 조건 | 동결 Full H | 준비 특징/OOF 예측 |
|---|---|---|
| R2_aA_m45 | 존재 | 존재 |
| R2_aB_m45 | 없음 | 없음 |
| R4_aA_m45 | 없음 | 없음 |
| R4_aB_m45 | 없음 | 없음 |
| R5_aA_m45 | 없음 | 없음 |
| R5_aB_m45 | 없음 | 없음 |

현재 Full H는 `p2/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/FULL_RF/`의 7개 파일뿐이다. 파일명·배열 shape·dtype·해시는 [MOUNT45_AUDIT.json](MOUNT45_AUDIT.json)에 기록했다. 편파의 관측 Jacobian H와 복소 RF 채널 H를 혼동하지 않는다. mount0 채널이나 LoS-only 채널을 mount45 Full 채널로 대신 사용할 수 없다.

요청한 다섯 조건은 동일 시나리오·안테나 mount 정의의 검증된 외부 아카이브가 없다면 원래 Sionna 시나리오에서 **새 Full RF H를 생성**해야 한다. 이후 특징·OOF/MR/HG 예측과 trace를 새 입력 lock 아래 생성해야 하며, 기존 표의 case 이름만 바꾸어 사용할 수 없다.

## OOF 학습 마운트 범위와 재학습 판단

BASE POWER_DIAG의 실제 생성 코드는 [power_oof_experiment.py 123–151행](evidence/power_oof_experiment.py#L123-L151)이다. 평가 경로를 제외한 Full 데이터만 학습하고, 평가 XY와 1e-4 이내 중복 위치를 추가로 제거한다. EX/EXDS 평균 보정의 실제 코드는 [mu_recursive.py 29–53행](evidence/mu_recursive.py#L29-L53)이며 평가 경로를 제외한 Full 특징으로 HGB를 fit한다. 둘 다 **경로 홀드아웃이며 마운트 홀드아웃은 아니다**.

| 평가(held) 경로 | 학습 경로 | POWER의 45° 학습 행 | EXDS의 45° 학습 행 |
|---|---|---:|---:|
| R2 | R4, R5 | 0 | 0 |
| R4 | R2, R5 | 1,302 | 1,303 |
| R5 | R2, R4 | 1,303 | 1,303 |

45° 학습 행은 모두 `R2_aA_m45`다. 마운트 0°만으로 모든 모델이 학습됐다는 결론은 틀리며, 모든 경로의 45°를 학습했다는 결론도 틀리다. POWER 행 수와 route 선택은 원본 [TRAIN_FOLD_RECEIPTS.json](evidence/TRAIN_FOLD_RECEIPTS.json)에 부합한다. 다만 CSV에서 다시 직렬화한 학습 데이터 해시는 영수증의 원래 메모리 직렬화 해시와 일치하지 않았다. 원인을 확정하지 않았으며, 수치 학습 재현을 완료했다고 주장하지 않는다. 원본 압축 입력 파일 자체의 SHA-256 검증과 이 내부 학습 해시 검증은 구분한다.

권장 후속 비교는 **기존 학습 집합·분할·하이퍼파라미터를 동결하고 새 45° 조건에 예측을 생성하는 것**이다. 현재 확인한 prepared 아티팩트에는 fitted estimator 파일이 없으므로 기존 학습 fold를 같은 규칙으로 다시 fit해 예측해야 할 수 있다. 이는 새 평가 데이터로 모델을 재학습하는 것과 다르다. 새 target 경로를 해당 fold의 학습에 넣으면 안 된다.

여러 경로의 45°를 학습에 추가하는 비교는 별도 실험으로 버전 관리한다. 그 경우에도 각 target 경로는 제외하고, 기존 모델과 확장 학습 모델의 결과를 분리한다. 기존 POWER의 XY 제외 규칙이 새로운 평가 집합 때문에 달라지는 경우에도 학습 집합 변경을 명시해야 한다. 이번 커밋에서는 RF 생성·재학습·새 trace 실행을 하지 않았다.
