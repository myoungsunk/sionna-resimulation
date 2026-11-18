# BLOCK_C 중앙선 sweep — M7 원본 RT 설정

질문 ID: `BLOCK-C-CENTERLINE-SWEEP-M7-001`

## 목적과 고정 조건

station 위치를 새로 정해도 M7 원본 R2/R4/R5의 RT 기본 설정과 원본 계산 동작을 유지한다. 이전 F1 sweep은 보존하고, 이번 결과와 구별한다.

- 원본 BLOCK_C 형상·재질·6개 PLY, 앵커 B=(10, 0, 2.65) m, 수신기 높이 0.45 m, mount 0°.
- x=1.20–18.75 m, 정확히 y=0, 0.45 m 간격 40 station.
- 물리 yaw는 −180°부터 +170°까지 10° 간격: 1,440 RF pose.
- 관측 표는 +180°를 포함하여 1,480행이며, −180°와 +180°는 같은 pose_id를 참조한다.
- 기존 F1 실행의 pose/관측 표를 바이트 그대로 복사하고 SHA-256으로 확인한다.

## RT 계약

원본 Method B commit `047cce2acb244ec2d7badc563345ccdd1f48613f`의 동결 소스와 FFD SHA-256을 확인한다. 원본 solver JSON 전체가 같아야 하며 다음 주요 값을 포함한다.

| 항목 | M7 원본 및 이번 실행 |
|---|---|
| refraction | true |
| samples_per_src | 100,000 |
| max_depth | 3 |
| max_num_paths_per_src | 1,000,000 |
| seed | 20260924 |
| 주파수 추적 | 기본 17 node + 원본 경계 구간 적응형 추가 추적 |
| 유한 반사면 검사 | 적용하지 않음 |
| 직접파 계수 대체·경로 후처리 필터 | 적용하지 않음 |
| H_full 합성 | 원본 `rf_store.h_for_antenna_yaws`와 배열 비트 일치 강제 |

Jones 계수의 보간과 각 bin에서의 지연 위상 합성을 포함해 원본 동작을 유지한다. RT 엔진·소스·solver·입출력 해시와 실제 node 목록은 실행 증거에 기록한다. 기존 M7의 알려진 수치적 현상도 호환성을 위해 그대로 유지하며, 이를 수정한 F1과 동일하다고 주장하지 않는다.

H_full, H_LoS와 PATHS_NEAR는 같은 trace에서 저장한다. 여기서 H_LoS는 full trace 안의 직접파 기여를 추출한 진단용 분해이며, 별도 native LoS solver 결과로 대체하지 않는다. 지연이 긴 경로까지 포함한 전체 raw trace도 station마다 저장한다.

## 실행 전 대조와 검증 범위

원본 R2/R4/R5 각각 첫·중간·마지막 pose를 다시 추적하여 원본 H와 `array_equal`이 모두 참이고 최대 복소 계수 차이가 0이어야 한다. 한 건이라도 다르면 새 station의 본 생성을 시작하지 않는다. 이는 9 pose의 표본 대조이며 원본 전체 배열 재검증이라는 주장은 하지 않는다.

본 생성 후 40 station·1,440 pose의 완전성, 원본 H 합성 일치, 저장 해시, G4(직접파 모델), G8(동일 trace 직렬화)를 확인한다. G4와 G8은 원본 다중경로 동등성 전체 검증을 대신하지 않는다. G-T2·G-V를 읽지 않고 heading 오차를 계산하지 않는다. 기존 데이터와 FAIL 기록은 보존한다.

## 완료된 실행

Snowball 실행 ID: `BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5`.
실행 코드 commit: `e9b4a76a8ce85d15de0f2be94900487c9b7b52bf`.
실행 시각: 2026-11-18 02:15:42–02:17:44 UTC.

- 원본 대조 PASS: R2 pose 0/651/1302, R4 pose 0/461/921, R5 pose 0/941/1882의 복소 H 계수 9,252개가 원본과 정확히 일치했다. 별도 바이트 비교에서도 각 route의 SHA-256이 같았다. 이 9 pose 표본에 한정한 원본 대조다.
- 전체 생성 PASS: 40 station, 1,440 RF pose, 1,480 관측 행. 모든 station에서 원본 적응형 추적으로 실제 21 node를 사용했다. 본 생성 solver 호출은 840회이며 export를 위한 추가 RT 호출은 0회다.
- 전체 1,440 pose의 H_full은 같은 trace를 원본 합성 함수에 넣은 결과와 배열 값이 정확히 같았다. 유한 반사면 검사·직접파 계수 대체·경로 후처리 필터는 적용하지 않았다.
- G4 PASS: 관측 1,480행 기준 p90 |Δs|=2.233846791932504e-7, 최대=5.810667242367451e-7. 기존 p90 기준 0.005를 유지했다.
- G8 직렬화 PASS: 1,440 pose, 복소 계수 1,480,320개, 최대 상대·절대 재합성 오차 0. PATHS_NEAR는 3,168개 경로 행이며, 전체 경로 raw trace도 40개 저장했다.
- 소요 시간: 원본 대조 43.48초, 본 생성 69.47초, 병합·검증 8.34초, 합계 121.29초. 코드 준비·복사·업로드 시간은 제외한다.
- 최종 results 폴더 용량: 128,201,448 byte(128.20 MB). 입력·대조 출력·로그·자원 기록을 포함한 전송 대상은 131,801,291 byte다.
- G-T2·G-V 봉인을 유지했고 heading 오차는 계산하지 않았다. 기존 F1 데이터와 FAIL 기록은 보존했다.

[전체 실행 증거](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/)에 입력, 계약, 원본 대조, 로그, 자원 기록과 결과를 보관한다.

| 파일 | 내용 |
|---|---|
| [H_full.npy](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/results/H/BLOCKC_B/H_full.npy) | M7 원본 RT 동작의 다중경로 H, shape (1440,257,2,2), complex128 |
| [H_LoS.npy](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/results/H/BLOCKC_B/H_LoS.npy) | 동일 full trace의 직접파 기여 |
| [M7_RT_CONFIG.json](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/inputs/M7_RT_CONFIG.json) | 원본 solver 전체 설정과 node 정책 |
| [BASELINE_BYTE_CHECK.json](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/BASELINE_BYTE_CHECK.json) | 원본 9 pose의 바이트 SHA-256 비교 |
| [completion.json](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/results/completion.json) | 전체 결과·검증·파일 SHA-256 |
| [raw traces](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/results/traces/BLOCKC_B/) | station별 전체 경로 Jones·지연·방향·node 존재 여부 |
