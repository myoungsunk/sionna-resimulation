# BLOCK-C-CENTERLINE-SWEEP-001

질문: M7의 R2/R4/R5와 같은 BLOCK_C 원본 형상에서 정확한 복도 중앙선의 360도 station sweep을 새로 생성한다.

## 동결 입력

- BLOCK_C: 길이 20 m, 폭 2.4 m, 높이 2.7 m. 원본 6개 PLY를 SHA-256 일치 확인 후 복사하며 재질과 두께를 유지한다.
- 앵커 B = (10, 0, 2.65) m. 수신 안테나 높이 0.45 m, 장착각 0도.
- station: x = 1.20 + 0.45 i m, i = 0..39, y = 정확히 0 m. 마지막 x = 18.75 m. 시작 위치는 기존 R1 기준이며 마지막 station은 0.45 m 격자 안에서 정한다.
- 절대 world yaw: -180도부터 +180도까지 10도 간격. 관측 순서는 station마다 37행, 합계 1,480행이다.
- -180도와 +180도는 동일한 물리 자세이므로 RF pose는 station마다 36개, 합계 1,440개다. 두 관측은 같은 pose_id를 참조한다. 열잡음을 추가하지 않은 clean H이며 동일 pose를 독립 공간 표본으로 세지 않는다.

## RT 설정과 기존 M7의 차이

확정된 PRODUCTION_F1.json 원본을 해시로 고정한다. 100,000 rays, max_depth=3, 17개 node에서 직접 trace 후 257 bin으로 보간한다. F1의 refraction=false와 전계 계산 전 유한 반사면 검사를 적용한다. M7 원본은 refraction=true였으므로 원본과 완전히 동일한 RT 설정이라는 주장을 하지 않는다. 공간·재질·FFD는 원본을 사용한다.

위치마다 하나의 기하 trace를 yaw별 FFD에 적용한다. H_full과 PATHS_NEAR는 같은 trace에서 생성하며 별도 경로 재추적을 하지 않는다. H_LoS는 기존 채택 방식대로 native 포트 계수와 배정밀도 위상으로 저장한다.

## 실행·검증·중단 범위

1. 입력 해시, station 격자, pose 중복, 관측 참조 및 몸체 벽 여유를 검사한다.
2. station 0, 20, 39에서 파일럿을 실행하고 경로 node coverage와 PATHS_NEAR → H_LoS 직렬화를 검사한다. 실패하면 전체 실행을 중단하고 결과를 보존한다.
3. 파일럿 통과 후 4개 worker(각 CPU 1개, 메모리 상한 12 GiB)로 전체 40개 station을 계산한다. 컨테이너는 기존 동결 image를 사용하며 네트워크를 끈다.
4. 1,440 pose 병합 시 shard 해시·coverage·같은 trace 사용을 확인하고 기존 G8 직렬화 기준 및 독립 LoS 모델의 G4 기준(p90 |delta s| <= 0.005)을 적용한다. 이 G4는 새 BLOCK_C 데이터에 한정한 재사용 검사다. 기존 001/002 전체 gate 통과를 의미하지 않는다.
5. heading 오차를 계산하지 않는다. G-T2/G-V 봉인 데이터는 읽지 않는다. 기존 데이터와 FAIL 기록을 변경하지 않는다.

실행 계약, 코드 revision, 원본 및 입력 SHA-256, 컨테이너 명령, 시간, 자원 전후 기록, 데이터 SHA-256과 저장량을 새 run root에 보존한다. 원래 결과와 구분된 별도 디렉터리에만 쓴다.
