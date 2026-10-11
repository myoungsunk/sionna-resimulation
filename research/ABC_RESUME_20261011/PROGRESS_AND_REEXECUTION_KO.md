# A–B–C 진행 보고 및 미완료 A 재실행 결과

작성: 2026-10-11. 기준 소스: `3bfcae6715bac5a933cc3b8336b6e6fad846c58a` (`codex/p0-close-p1-factorial-20261011`). 이번 작업 브랜치: `codex/abc-gated-resume-20261011`.

**현재 판정: Stage A는 아직 전체 통과하지 않았다. Stage B와 Stage C의 Native 성능 실험은 이번 작업에서 실행하지 않았다.** 기존 실패 항목을 제외하거나 기존 7케이스만으로 축소하여 A를 완료 처리하지 않았다. Stage B 선행 실행 38124202873/38124280840은 계속 격리하며 결과를 재해석하지 않았다.

## 1. 항목별 상태

| 항목 | 이번 확인·실행 | 판정 |
|---|---|---|
| V00 RF 시간–pose | 원 19,038개 요청의 모든 필수 identity 및 올바른 pose_id/H행 대응 재검산; 수정된 첫 입력부터 전체 이력을 거친 128seed 저장 P6를 독립 재계산 | PASS, 원 7케이스 등록범위 |
| V01 동일 입력 관측기 | 42개 조건, 4,032 sample 비교, branch간 s 차이 0 및 공통 firstpath tap 일치 | PASS |
| V01 생성계통 동등성 | 신규 Native 5개는 확보; 비교할 과거 legacy Method-B 5개 원본 bytes를 추가 찾았으나 복원하지 못함 | BLOCKED |
| V02 센서–필터 정합 | 새 독립 seed 640–767, 14개 조건 × 2개 추정기 × 128 = 3,584개 필터 실행 완료 | FAIL |
| V03 극점 모델값 | 기존 9,519 native LoS 및 독립 직접 FFD 1,120점 회귀, 새 Native 6개 raw H 재계산 | PASS, 해당 검증범위 |
| V03 XY/Heading Jacobian | 원본 SHA 검증 FFD 직접 계산의 유한차분과 수정 모델 analytic Jacobian을 추가 비교, 24조건 | PASS, 해당 검증범위 |
| B / V04–V10 | A 전체 미통과 | NOT_RUN_AFTER_A |
| C / V11–V13 | A/B 미통과, 검증된 최선 passive 기준선 미확정 | NATIVE_RUN_NOT_STARTED |

성능 수치와 공분산 일관성 판정은 'workflow success', '파일 생성', 'PSD'와 구분한다.

## 2. V00 및 동일 입력 관측기 재검산

원본 V00 실행 38120812381과 완전 identity 영수증 실행 38126674932를 확보했다. `case, timeline_k, time_s, requested_pose_id, H_row, H_pose_id, actual/requested XY/yaw, mount, anchor, antenna frame, source SHA`가 있는 19,038행을 검사했다. request_id 중복 0, requested pose와 H pose 불일치 0. 좌표 차이 최대 4.9995e-7m, yaw 차이 최대 4.8228e-7deg는 원 SAMPLES 소수점 반올림 범위다.

수정된 128seed P6/정답오차에서 Cholesky 기반 별도 NEES 재계산과 이전 기록의 최대차이는 3.55e-15다. 처음부터 pose_id에 맞춰 재실행한 기존 영수증을 확인한 것이며, 이번에 V00 필터를 128번 새로 실행했다고 주장하지 않는다. 잘못된 H[:last+1] 결과는 사용하지 않았다.

42개 branch/채널/잡음 관측기 조건은 총 4,032 sample 비교에서 s 차이 0, FP tap 동일이었다. **이 결과는 legacy/native 전파 생성계통의 full-channel 동등성을 뜻하지 않는다.**

## 3. V01: 신규 시뮬레이션 파일과 비교 원본을 혼동하지 않음

새 Native mount45 H 다섯 개는 archive에서 이미 SHA 검증됐다. 미확보한 것은 다음 과거 Method-B 비교 원본이다.

| 과거 원본 | 필요한 SHA256 |
|---|---|
| H_R2_aB_m45.npy | fb229e187f9498025847ca550e061d3ab2cd82624f1c6e20ed9b78a5e7a60f75 |
| H_R4_aA_m45.npy | 5eabb1e44677bdf82630cdf9eea43cad729af2459b9b790d246310d62b725724 |
| H_R4_aB_m45.npy | 3f76d713edccf90ed1d20c8e0f65064add3ca5c5340b56d11c1f391ca81c791d |
| H_R5_aA_m45.npy | 1e2c2f36c8d4945e3868c418875b6f08e459c669bcdad981318daf4521ecfbc2 |
| H_R5_aB_m45.npy | 8f0d87f213a04d6861d6de12f557ce5ce4ae2ba369b9c94e49496bc4f3e154e9 |

이번 추가 작업:
- Actions 38130108660에서 위 **정확한 SHA 객체**만 Git LFS로 복구 시도했다. 5개 모두 `404 Object does not exist on the server`; 복구 0/5. 작업 성공 종료는 조회가 끝났다는 뜻이지 V01 PASS가 아니다.
- 연결된 Drive에서 위 정확한 파일명/RAW_ARCHIVE.tar와 DRIVE_SIM을 검색했으나 관련 결과가 없었다.
- Actions 38131058250에서 branch HEAD뿐 아니라 도달 가능한 과거 Git 이력도 조회했다. 과거 commit fetch는 완료했으나 object 열거가 120초 제한에 걸려 **전체 이력 검사는 INCOMPLETE**다. 따라서 'Git 전체 과거에 파일이 없다'고 단정하지 않는다.

V01을 닫는 두 경로는 (a) 실제 과거 원본을 회수해 동일 pose·frequency·port 기준으로 비교하거나, (b) 전체 12조건을 하나의 동일 Native source로 새로 생성하고 새 provenance로 승인하는 것이다. 현재 7 legacy+5 native의 혼합을 동등하다고 선언하지 않는다. 이 둘 중 어느 경로도 이번에 완료하지 못했다.

## 4. V02: 미완료 조건을 새 독립 seed로 실제 재실행

`V02_NONLINEAR_REPAIR_PREREG.json`을 먼저 커밋했다. 원 14조건/초기분포/Q/R/게이트/trajectory는 보존하고 아래 두 추정기를 비교했다.

- ORIGINAL_FIXED_SENSOR_V2: 기존 소스 그대로.
- JOINT_STATE_INPUT_CUBATURE_GH9_CANDIDATE: 상태6와 공유 IMU/wheel 입력잡음3을 함께 cubature로 적분하고, range 비선형 관측은 9×9 Gauss-Hermite로 적분하는 후보. 사후 Q/R 확대 없음. 학습된 신뢰도나 다중경로가 등장하는 Stage B 실험이 아니라 **이상적 관측/센서 정합을 위한 Stage A 수치근사 대조**다.

새 seed는 **640–767**, 각 128개, 평가 시각 0/12/24/48초. 총 3,584회 필터 실행이 완료됐고 원 오차 및 full-P6 텐서를 보존했다. 실행 환경은 Python3.13.5/numpy2.3.5/scipy1.17.0/pandas2.2.3. 원 추정기와 후보 모두 같은 환경/입력에서 실행했다. GitHub에 올린 실행 소스는 실행 당시 byte와 동일함을 Git blob 및 SHA256으로 확인했다.

### 48초 대표 결과

| 조건 | 기존 NEES | 후보 NEES | 기존 pose95포함률 | 후보 pose95포함률 |
|---|---:|---:|---:|---:|
| SMALL_IDEAL_RANGE | 3.14863 | 3.03998 | 90.625% | 90.625% |
| LARGE_IDEAL_RANGE | 6.66159 | **5.06517** | 78.125% | **89.063%** |
| HIGH_LEGACY_OFF | 4.61966 | 4.40765 | 85.156% | 86.719% |
| HIGH_GAUSSIAN_MODELED_RANGE | 8.04677 | **5.97468** | 71.094% | **84.375%** |

`LARGE`는 이름상 stress 조건이지만 공간 prior는 기존 설정 x/y 표준편차 0.10m, yaw5° 수준이고, SMALL은 0.03m/2°다. 이를 극단적인 거대 초기오차로 묘사하면 안 된다.

동결 판정에서 NEES의 112개 비교군 상한은 3.81968, 하한 2.29820이다. 포함률 검정 구간은 [86.719%,100%]. NEES와 포함률 각각에 Bonferroni family를 적용했으며, 두 지표를 합친 전체 family 95%라고 확대 해석하지 않는다. 원래 56-checkpoint 기준 결과도 파일에 별도로 보존했다.

기존 추정기 45/56 checkpoint 통과, 후보 46/56 통과. 후보의 **10개 필수 checkpoint는 여전히 실패**한다. 기존 56-checkpoint 기준으로도 통과 개수는 동일하다. 성공한 SMALL/일부 matched-prior만 골라 V02를 닫지 않았다.

독립 재계산은 저장 P6의 Cholesky whitening으로 수행했고 원 계산과 평균 NEES 최대차이 2.18e-13, coverage는 동일했다. PSD 수식 검증은 통계적 일관성 승인과 별개다.

해석: 비선형 moment 근사는 일부 오차를 줄였으나 전체 실패를 제거하지 못했다. 큰 prior/센서 보정 파라미터 및 공유 입력잡음의 추정 정합 문제를 추가 분리해야 한다. RF 다중경로가 없는 이상적 range에서도 실패하므로 이를 Stage B의 multipath 모델로만 설명해서는 안 된다. 비정규 signed legacy prior에 대한 chi-square 가정 적합성도 별도 유지 과제다.

## 5. V03: 원본 FFD와의 독립 미분 비교까지 보강

기존 수정 모델 `CARTESIAN_FIELD_DEG4_CORE2_BLEND2_3_FP_V2`, coefficient SHA `87a38e9cc221244cb8b6ca08ba59afd2090bb64594d486b020c694d06dc76a5e`를 변경하지 않았다.

- 기존 9,519 native LoS 및 1,120개 직접 FFD 신규점 검증 영수증 확보.
- 9개 극점 pose의 RMS: 원 LUT .339094 → 수정 모델 .0006082.
- 새 Native6점 실행 38126804417 raw H에서 직접 IFFT·공통 FP s를 다시 계산; CSV 대비 최대차이 1.53e-16.
- 새 Native 중심값과 수정 모델의 최대 |Δs|=.00098365.
- 추가 실행 **38130986616**: 원본 두 FFD bank를 실제 SHA 검증 후, Native6점 중심에서 XY·yaw를 각 축 ±1e-5 및 ±5e-6으로 움직여 직접 FFD contraction의 미분을 계산했다. 모델 자체를 미분한 값만 비교한 것이 아니다.
- 고정10m 기준 원 관측정의에서 최대차이: Jx .0018303/m, Jy .0086953/m, Jpsi .0016168/rad. 사전고정 각 축 .01 기준을 모두 통과했다.
- 실제 링크거리 관측정의도 별도 기록: 최대 Jx .0059911/m, Jy .0073604/m, Jpsi .0035605/rad; 모든 작은 perturbation에서 FP tap이 유지됐다.

총24조건이 통과했다. 고정10m 모델과 실제 링크거리 모델은 동일 관측정의로 혼동하지 않는다. 검증은 위 위치/범위의 모델값·미분이며, 이 결과만으로 full-route 추정기나 전체환경의 통계적 PASS를 주장하지 않는다.

## 6. B·C 착수 판정과 재개 경로

**A 전체 PASS=false; B 실행허용=false; C 실행허용=false.** 기존 조기 B 결과는 격리 유지. 현재 검증된 최선 passive RF 모델도 확정되지 않았으므로 C의 비교 기준을 임의로 선택하지 않았다.

A의 남은 실제 업무:
1. V01 원본 counterpart5 복원 또는 동일 source12 전체 재생성 후 full H/관측 parity 승인.
2. V02 Gaussian/mixed prior와 실제 센서 생성분포, noisy 입력을 조건화하는 전이/odom 공분산 모델을 분해한다. 원 Q/R 임의 확대 또는 실패 조건 제거 대신 single-Gaussian 근사/공유 calibration nuisance를 구분하는 새 사전등록 대조가 필요하다.
3. 변경한 소스/모델은 독립 seed로 모든 필수 checkpoint 재검증하고, 통과한 모델에 대해 고정 source·observer·coeff SHA를 확정한다.

A가 실제 통과하면 B의 V04–V10을 그 기준에서 실행한다. 과거 탐색 결과를 그대로 새 baseline 결과로 재라벨링하지 않는다. B에서 Range/편파/공분산 모델과 최선 passive 기준선이 검증된 다음 C를 실행한다.

C의 강제 조건은 사용자 요구 그대로다: 관측 기반 위험 trigger; s 갱신 전 보류; 실제 제동 후 새 s0; 같은 실제 정지 위치의 2–3yaw; slip/lever arm 위치 변화 반영; 공동 posterior/P6가 다음 주행 predict로 전파; source-consistent 12조건; 동일 실제 회전·대기·range의 SHAM; checkpoint와 전체 소요시간 평가를 분리. **이 문서 작성/단계 gate 단위테스트를 Native C 실행으로 계산하지 않는다.**

## 7. 산출물과 실행 여부

GitHub: 이번 독립 FFD 미분 코드/실행, 정확한 legacy SHA recovery workflow, V02 실제 실행 소스·사전등록·보고서 보존. 다운로드 패키지에는 3,584회 원 오차/P6, checkpoint CSV, 독립 재계산, 원 V00/V03 receipts, source snapshot, 실패 영수증, A/B/C gate 상태 및 해시 manifest가 포함된다. 후보를 기존 production Sensor-v2 소스에 덮어쓰지 않았다.

현재 진행 결과를 'A/B 완료 후 C 시작'이라고 보고하지 않는다. **A의 V00/V03는 검증을 닫았고, V01/V02는 재시도 결과와 잔여 실패가 명확해진 상태**다.
