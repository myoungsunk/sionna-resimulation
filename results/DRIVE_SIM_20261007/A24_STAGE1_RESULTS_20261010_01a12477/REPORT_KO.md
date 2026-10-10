# A24 Stage 1 실행 자료

지정한 source commit `723711cdb032ea6d844f3a4c21a5496febe7b440`과 사양서 순서로 실행했다. F0aug의 A0/S6 재현 게이트 이후 F2→F1→F3→F2acf→F1acf를 실행했다. 이 보고서는 실행·자료 완전성을 확인한다. no-harm, 인과 설명, scientific adoption의 PASS/FAIL은 판정하지 않았다.

## 먼저 확인한 필수 게이트

[OUTPUT_GATE/A0_CHECK.json](OUTPUT_GATE/A0_CHECK.json)은 `filter_variant=F0aug`, `inference_valid=true`이다. 요청 키 150개와 S6 대응 150개를 확인했고 누락·중복·문제가 없었다. 최대 차이는 heading RMSE 1.7763568394e-15, 위치 RMSE 2.22044604925e-16, NEES 2.84217094304e-14로 사양서 허용오차 1e−9 이내였다. [gate 로그](check-a0.log)와 [원 manifest](OUTPUT_GATE/RUN_MANIFEST_check-a0.json)를 보존했다.

## 실제 실행 범위와 산출물

R2-A, mount 0°, SNR 30, drift 0–2, seed 0–49, 22 arms 전부를 사용했다. 변형마다 3,300 run, 총 16,500 본 실행이다. gate 150 run은 별도이며 이를 본 실행 표본 수에 합하지 않았다. nproc=4, CPU 4, memory 16 GiB, BLAS thread 1, 기존 pinned image `rt-dual-engine:s2-deps-r2-20260928`를 사용했다. [명령·UTC 시각·exit code](EXECUTION.json), [Docker 실행 정보](RUNTIME_INSPECT.json), [고정 실행 계획](PLAN.json)을 보존했다.

| 라벨 | 결과 행 | 실패 run | trace 파일 |
|---|---:|---:|---:|
| F2 | 3300 | 0 | 330 |
| F1 | 3300 | 0 | 330 |
| F3 | 3300 | 0 | 330 |
| F2acf | 3300 | 0 | 330 |
| F1acf | 3300 | 0 | 330 |

각 `OUTPUT_<label>/`에 `ARMS_<label>.csv`, `ARM_UNIT_STATS_<label>.csv`, `RUN_MANIFEST_<label>.json`, `A0_CHECK.json`, `TRACES/`가 있다. 모든 변형은 통과한 F0aug 체크 파일과 manifest를 정확히 복사한 뒤 실행했고 `a0_gate=passed`를 기록했다. 키 집합 22 arms × 3 drifts × 50 seeds를 검산했다. 라벨별 출력 디렉터리가 달라 trace 파일명의 충돌과 덮어쓰기가 없다. [자료 완전성 검산](VERIFICATION.json)에 label별 실패 원문과 trace shape, 적용 fit params가 있다.

trace는 라벨당 seed 0–4 × 3 drift × 22 arms = 330개, 전체 1,650개다. gate trace 15개는 `OUTPUT_GATE/TRACES/`에 별도 보존했다. 상태·6×6 공분산·센서 입력·관측·갱신별 로그·평가 keep mask에 `beta_hat`, `beta_var`, `beta_cross`를 함께 저장했다. F1/F1acf의 beta는 1개, F2/F3/F2acf는 2개다. `beta_cross`는 구현이 저장하는 beta–pose `[n,n_aug,3]` 블록이다. 이를 전체 확장 상태 공분산이라고 부르지 않는다. 원 trace 규약과 관측 처리, 필터 설정을 변경하지 않았다.

## S6 기준선과 재현 입력

[원 S6 CSV](INPUTS/results_R2_aA_m0.csv)와 [원 S6 manifest](INPUTS/manifest_R2_aA_m0.json)를 전체 바이트로 보존했다. [요청 키 기준선 행](INPUTS/S6_REQUESTED_BASELINES.csv)은 odom_imu 150행, range-only(`baseline=range`) 150행, range_s_P0 150행을 포함한다. 이는 원 S6에서 추출한 자료이며 기준선 필터를 새로 실행하지 않았다.

source는 지정 commit의 Git archive를 사용했다. [SOURCE_REVISION.json](SOURCE_REVISION.json)에 commit·archive SHA256·출처를 기록했고, 실행 대상 source 내용 해시는 각 RUN_MANIFEST의 `source_sha256`에 있다. [동결 source·fit·사양서](FROZEN_SOURCE/)도 제공한다. 새 checkout을 만들 때 불필요한 bank LFS 다운로드가 시작돼 해당 준비 프로세스만 중단하고 `GIT_LFS_SKIP_SMUDGE=1`로 source를 동결했다. 새 checkout의 index를 복구하고 source 준비 후 dirty 상태 0을 확인했다. A24 실행은 실제 bank pointer를 사용하지 않고 검증된 A23 H/LUT/frequency/timeline/S6를 읽기 전용 mount로 재사용했다. 원 checkout과 원 RF 자료는 수정하지 않았다. container에 Git이 없어 wrapper는 source 출처 metadata만 주입했다. 필터 함수·난수·평가 계산은 수정하지 않았다.

파라미터는 사양서의 `A24_FIT_PARAMS.json` 그대로다. primary/ACF 선택, F3 거리 profile 및 실제 적용 설정과 fit SHA는 manifest에 있다. 실행 결과에 맞춘 refit, noise/prior/gate tuning, 임계값 변경은 없었다. A24는 동일 R2-A 보정 조건의 stage 1이며 독립 held-out 평가가 아니다.

## 보존 및 중단 상태

기존 full RF interaction 재실행 container `drive-full-rf-interactions-01a1246d`는 사용자 지시에 따라 pause 상태로 보존했다. A24 종료 후 자동으로 재개하지 않았다. 이번에는 새 RF 계산, held-out stage 2, sensor-v2 stage 3, 후속 모델 수정·결과 해석을 실행하지 않았다.

모든 반환 파일의 SHA256은 [TRANSFER_MANIFEST.json](TRANSFER_MANIFEST.json)과 [게시 manifest](PACKAGE_MANIFEST.json)에 기록했다. 각 파일은 40 MiB 미만이며 NPZ/NPY를 LFS pointer로 대체하지 않는다. 기존 감사 결과와 사전등록은 보존했다. **게이트 재현 및 실행 완료는 측정모델 해결의 증거가 아니다. F01/F02 미해결과 scientific_PASS=false를 유지한다.**
