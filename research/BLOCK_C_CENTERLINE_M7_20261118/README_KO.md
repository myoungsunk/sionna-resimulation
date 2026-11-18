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

실행 결과는 완료 후 이 문서와 별도 증거 디렉터리에 추가한다.
