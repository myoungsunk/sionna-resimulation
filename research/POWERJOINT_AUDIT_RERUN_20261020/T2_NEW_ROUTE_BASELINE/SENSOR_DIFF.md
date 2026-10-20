# T2 신규 주로 센서 설정 감사

| 항목 | Chain F 보존 lock·evidence | Crosscase §D | 이번 정본 설정 |
|---|---|---|---|
| motion clock | 원본 전체 .25s pose/time로 synthetic control | .25s motion 및 radio 원래 1Hz 이동+subsecond yaw 서술; 실행 소스 미확보 | 원본 ROUTE_POSE 전체 .25s |
| RF clock | 제공 RF pose_id에만 update | radio pose 서술 외 control alignment 세부 미확인 | RADIO_POSE pose_id 정확 매칭, turn/scan/vertex 추가 radio 유지 |
| gyro/wheel 잡음 | 기존 SourceFFD/Sensor-v2 source 사용 서술; 실제 builder 원본 실행 소스 미확보 | 정확한 generate cfg/RNG 소스 미확보 | pinned build_positive_bias_controls code, 원본 Sensor-v2 namespace/streams 그대로 |
| yaw 과정 | 원본 full motion synthetic | 이동 radio 1Hz + yaw subsecond 기술 | 원본 body yaw CSV 그대로, wrapped increments |
| bias | B0/L0/L1/L2 | B0 결과 제공, 나머지 세부 미확인 | 0/.01/.05/.20deg/s 양의 고정 bias; 다른 drift=0 |
| 초기 P | 보존 lock에는 값 없음 | 보고서만으로 미확인 | diag(.1m²,.1m²,5deg²,.1deg/s²) |
| 초기 상태 | exact rng(initial) 여부 source 미확인 | 미확인 | exact Sensor-v2 initial stream, std [.1m,.1m,5deg] |
| POWER train | R2-heldout R4/R5, 5608 rows, R2 site exclusion | 세부 source 미확인 | 기존 R2/R4/R5 전체; 신규 주로 미사용 |
| 조건 | 8 case, O03 없음 | 9 case, O03 포함 | 9 case, O03 los_exists=false 보존 |

근거: `CHAIN_VALIDATED_RESULTS_20261019/external_evidence/EXTERNAL_TEST_LOCK.json`, `EXTERNAL_INPUT_QA.csv`, `EXTERNAL_SUMMARY.json`; `POWERJOINT_CROSSCASE_20261020/00_ANALYSIS_RESULTS_KO.md` §D; `POWERJOINT_M45_COMPACT_20261019/01_ROUTE_REQUEST.json`, `02_prepare_routes.py`; `EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py`; Sensor-v2 source. 보고서만으로 기존 두 실행의 정확한 잡음·초기화 차이를 확정하지 않는다. 주어진 결과 차이는 센서 외 POWER train 차이도 포함할 수 있다.

## CSV 양자화 처리

route generator는 x/y/yaw를 소수 6자리로 저장한다. 반면 exact builder는 legacy-euler nonholonomic lateral tolerance=1e-9m를 기본으로 사용한다. 1um 단위 좌표의 두 endpoint 반올림만으로 1e-9m보다 큰 lateral residual이 생길 수 있다. 이를 잡음이나 다른 주로로 바꿔 숨기지 않는다.

정본은 저장 CSV truth를 수정하지 않는다. 원래 `motion_increments`의 tolerance만 사전등록한 2e-6m로 허용하고, 원래 알고리즘의 body-direction projection을 그대로 쓴다. 6자리 좌표 두 endpoint의 성분 오차로 인한 상한은 약 sqrt(2)um이며, .05m step의 yaw 반올림 효과는 이보다 훨씬 작다. 2um를 넘으면 자동 수리 없이 BLOCKED_INPUT이다. 모든 interval의 lateral residual을 출력한다. exact builder 함수의 globals 사본에서 해당 호출의 tolerance만 바꾸며 원본 module이나 잡음·RNG·cfg는 수정하지 않는다.

## 입력 계약

`prepare_new_route(route_root, route_id)`는 release subset 디렉터리 안의 ROUTE_POSE/RADIO_POSE와 SHA receipt를 읽어 `{motion_t, motion_truth, rf_motion_indices, rf_pose_ids, metadata, cases}`를 반환한다. 각 case에 Full/LoS H 경로, 실제 los_exists 배열과 RF pose 행을 보존한다. 중복 motion/radio 파일은 bytes가 같아야 한다. `ARCHIVE_CONTENTS_AND_SHA.json`의 extracted 또는 `SOURCE_RELEASE_SUBSET_RECEIPT.json`의 kept 기록과 실제 파일 hash를 맞춘다. source subset extractor가 LOS_EXISTS.npy를 누락했다면 추가 복원이 필요하며 O03 LoS를 합성하지 않는다.

`prepare_inputs.py --route-root RELEASE_SUBSET --route-id C01 --source-root SOURCE --out OUTPUT`는 seeds0–4×4bias의 motion controls NPZ와 alignment/lateral CSV를 준비한다. RF의 수치 변환, POWER fit, EKF baseline은 Mother 공통 runtime이 담당한다. 그 runtime은 0.25s 전체를 predict하고 `rf_motion_indices`에서만 update해야 한다. `motion_truth`는 generator·scorer에만 전달한다.

## 주장하지 않는 것

motion-noise 반복으로 RF·독립 장면 반복, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 이전 두 실행의 미확보 코드 차이를 수치로 재구성하지 않는다.
