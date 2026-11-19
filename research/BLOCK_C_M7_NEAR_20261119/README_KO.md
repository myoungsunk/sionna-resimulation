# BLOCK_C 중앙선 기준점 주변 4 cm 간격 sweep

질문 ID `BLOCK-C-M7-NEAR-STATION-SWEEP-001`. Snowball 실행 ID `BLOCK_C_M7_NEAR_20261119_2ujQQZVt`.

P016(7.95 m), P010(5.25 m), P003(2.10 m) 각각에서 x를 ±4, ±8, ±12, ±16 cm 이동했다. y=0 m, 수신 높이 0.45 m, mount 0°, 앵커 B=(10, 0, 2.65) m 조건이다. 신규 24위치에서 36개 yaw를 합성해 864 RF pose와 888개 관측 행을 만들었다. +180° 관측은 −180° RF pose를 참조한다. 좌표와 검증 기준은 [실행 계획](PLAN_KO.md)에 있다.

원본 M7 설정으로 추적했다. 투과 ON, 광선 100,000개, 최대 깊이 3, seed 20260924를 유지했다. 24개 위치 모두 기본 17 node와 적응형 추가 추적을 합쳐 21 node를 사용했다. solver 호출 504회에서 H_full, H_LoS, PATHS_NEAR와 전체 raw trace를 저장했다. 실행 기준 코드 `1a0f3c1b15be8e07c1884dbd1e42a1bb6c9b74f4`와 추가 실행 코드의 해시는 계약에 기록했다.

| 검증 | 결과 |
|---|---|
| M7 원본 대조 | R2·R4·R5 합계 9 pose의 H가 원본과 바이트 단위로 일치 |
| G4 | PASS. 888개 관측에서 p90 \|Δs\| = 1.9066851811855303×10⁻⁷, 기준 0.005 |
| G8 | PASS. 864 pose, 복소 계수 888,192개, 최대 상대·절대 재합성 오차 0 |
| 생성 및 저장량 | 본 생성 20.24초, 원본 대조와 검증을 포함한 서버 실행 69.81초, 결과 파일 79,600,154 byte |

비교표의 27위치·972 pose는 이번 864 pose와 기존 중심 3곳의 108 pose로 구성된다. 표에서 `(run_id, pose_id)`로 H 배열을 조회한다. 기존 중심은 [M7 중앙선 원본](../../artifacts/BLOCK_C_CENTERLINE_M7_20261118_dhdj70s5/results/H/BLOCKC_B/)의 행을 참조한다. 신규 H 배열은 `(864, 257, 2, 2)`, `complex128`이다.

| 자료 | 파일 |
|---|---|
| 실행 증거 전체 | [데이터·코드·로그](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/) |
| 신규 H | [H_full.npy](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/results/H/BLOCKC_B/H_full.npy), [H_LoS.npy](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/results/H/BLOCKC_B/H_LoS.npy) |
| 원본 경로 | [PATHS_NEAR.npz](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/results/paths/BLOCKC_B/PATHS_NEAR.npz), [위치별 전체 trace](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/results/traces/BLOCKC_B/) |
| 중심 및 신규 위치 연결 | [비교용 RF pose 표](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/inputs/COMPARISON_RF_POSES.json), [관측 순서 표](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/inputs/COMPARISON_OBSERVATIONS.json) |
| 검증과 재현 | [실행 계약](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/inputs/RUN_CONTRACT.json), [검증 결과와 파일 해시](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/results/completion.json), [실행 코드](../../artifacts/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/code/blockc_m7_near_20261119.py) |
