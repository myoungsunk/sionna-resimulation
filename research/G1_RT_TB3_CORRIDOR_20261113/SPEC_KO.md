# G1-RT-TB3-001 — TB3 trackA형 복도 ray-tracing 데이터 재생성 사양서

- 작성: 2026-11-13 KST. 상태: **SPEC_FINAL / ALL_INPUTS_ASSUMED_AND_FIXED / NOT_RUN**
- 목적: **TB3 실측 센서 파라미터를 넣은 조건에서 편파 정보의 유효성을 평가**하기 위한 RT 채널을 새로 만든다. 경로·station·sweep 프로토콜은 TB3 TEACH/REPEAT와 같게 하고, 복도 형상은 TB3 복도와 비슷한 수준으로 둔다.
- **범위 결정:** 복도 형상, anchor·tag 위치, 재질은 실측 환경과 같을 필요가 없다. 이 데이터는 실측 multipath를 재현하지 않는다. 모든 환경 값은 아래 `ASSUMED` 값으로 **고정**하며, 실행 중 바꾸지 않는다. 결과는 "대표 복도 환경에서의 편파 정보 유효성"으로만 해석하고, 실측 환경과의 동일성이나 실측 multipath의 재현을 주장하지 않는다.
- 해제한 G1-FLOOR-001의 RT 한계: station 2 m 간격 → 0.45 m, sweep 90° → ±60°(TB3 5점 + 조밀 49점), 형상 1개 → 3개, passive 회전 경로 없음 → 4종 추가.
- 분석 판정은 G1-MODEL-001 §7 규칙을 이 데이터에 다시 적용하는 G1-MODEL-002에서 한다.

## 0. 이 데이터가 답해야 하는 질문

| Q | 질문 | 데이터 특성 |
|---|---|---|
| Q1 | TB3 sweep 프로토콜(5점, ±60°)과 연속 sweep(49점)에서 sweep heading 오차 분포는? | station별 yaw 격자 −60…+60° |
| Q2 | 0.45 m station 간격에서 sweep 오차의 공간 상관은? | 0.45 m station 18개를 직접 계산 |
| Q3 | sweep 없이 주행 중 s를 쓰는 passive 경로가 회전 없는 DR을 이길 수 있는가? | 자연 회전 경로의 조밀 주행 pose |
| Q4 | 결과가 형상에 얼마나 의존하는가? | 형상 3개, 같은 pose 집합 |
| Q5 | 거리 인지 관측 모델(M1)이 새 형상에서도 parity를 통과하는가? | 모든 pose의 LoS H |

## 1. 형상 (ASSUMED, 고정)

좌표: x는 복도 방향, y는 폭 방향(+y = 로봇 진행 방향의 왼쪽), z는 위. 바닥 z = 0, 복도 중심 y = 0.

### 1.1 공통 값

| 파라미터 | 값 | 근거 |
|---|---|---|
| 길이 L | 20.0 m (x ∈ [0, 20]) | BLOCK_C와 동일 |
| 높이 H | 2.70 m | BLOCK_C와 동일 |
| 바닥·천장 | ITU concrete, 0.20 m | BLOCK_C와 동일 |
| 끝벽(x = 0, 20) | ITU concrete, 0.20 m | BLOCK_C와 동일 |
| 측벽 | ITU plasterboard, 12.5 mm | BLOCK_C와 동일 |

### 1.2 형상 3종

| ID | 단면 | 추가 구조 | 근거·용도 |
|---|---|---|---|
| **G-T1** (1차) | 폭 **1.94 m** (y ∈ [−0.97, +0.97]) | 없음 | trackA·corridor_5p07m LiDAR 기본 단면(왼쪽 벽 +0.50, 오른쪽 −1.44 m, lane 기준) |
| **G-T2** | G-T1과 동일 | 왼쪽 벽 오목부 2곳: x ∈ [6.0, 6.7], [12.65, 13.65], 깊이 0.19 m, 높이 2.10 m, 오목부 안쪽 벽은 ITU wood 40 mm. 오른쪽 돌출물 1개: x ∈ [8.6, 10.0], 폭 방향 0.39 m, 전 높이, ITU concrete | trackA P001–P002, P016–P018의 왼쪽 +0.69 m, P007–P010의 오른쪽 −1.05 m 구간을 블록으로 근사 |
| **G-V** | 폭 **2.40 m** (y ∈ [−1.2, +1.2]) | 측벽을 ITU concrete 0.20 m로 교체 | 형상·재질 대조, BLOCK_C(폭 2.4 m)와의 연결 |

Mesh는 BLOCK_C `scene/*.ply` 형식을 따른다. G-T2의 오목부와 돌출물은 별도 ply 객체로 만들고 재질을 바인딩한다. 모든 ply의 SHA256을 `SCENE_MANIFEST.json`에 기록한다.

## 2. Anchor와 안테나 (ASSUMED, 고정)

| 항목 | 값 |
|---|---|
| Anchor 위치 | **A** (7.0, 0.0, 2.65), **B** (9.8, 0.0, 2.65), **C** (3.0, 0.0, 2.65) m. 천장 2.70 − standoff 0.05 |
| Anchor 방향·포트 | rotation diag(1, −1, −1)(boresight 아래), 단일 포트 TX +45 (TX column 0) |
| 로봇 RX | dual-port ±45° LP, rotation Rz(body yaw + mount), **mount 0°** |
| RX 높이 | 0.45 m |
| RX 위치 | 로봇 회전 중심과 일치(오프셋 0) |
| RX 기울기 | 수평(1차). 민감도 arm: roll −1.6°, pitch +1.5° (TB3 정지 IMU 실측) |
| FFD bank | `LP_plus45_bank.npz`, `LP_minus45_bank.npz`(저장소 루트, Git LFS). A23 `FFD_RESTORE_MANIFEST` SHA와 대조 |

- trackA 구간 x ∈ [6.0, 13.65]에 대해 A는 시작점 근처, B는 중앙, C는 구간 밖이다. 수평거리 약 0–10.7 m를 덮는다.
- 한 run은 anchor 하나만 쓴다. Anchor마다 같은 pose 집합으로 별도 H를 만든다.

## 3. Pose 집합 (고정)

공통:
- 로봇 lane: **y_lane = +0.47 m**(G-T1/G-T2, 왼쪽 벽에서 0.50 m). G-V는 같은 왼쪽 벽 거리를 유지해 y_lane = +0.70 m.
- 진행 방향 +x, nominal heading 0°. trackA 시작 x0 = 6.0 m.
- 각 pose는 (x, y, yaw_body_deg), pose 유형, station_id, 순서 index, 누적 |dθ|를 가진다.
- TB3 운동 값: 직진 속도 0.08 m/s(실측 평균 0.0805), 회전 각속도 0.3 rad/s(TEACH `w_max`), RF 샘플 주기 0.2 s.

### P-A: trackA station sweep (Q1, Q2)

- Station 18개, 간격 0.45 m. 위치·heading은 **TEACH 실측 `line_pose`(along, lateral, yaw)**를 x = x0 + along, y = y_lane + lateral로 옮긴다. REPEAT용 집합은 `repeat.json` 정렬 후 자세로 같은 방식으로 만든다.
- Station마다:
  - **TB3 프로토콜 5점**: TEACH `achieved_rel_deg`(약 −60, −30, 0, +30, +60)와 base, base_after
  - **조밀 격자**: −60…+60°, 2.5° 간격, 49점
- sweep 회전 중심은 base XY다.

### P-A′: trackA 이동 구간 (Q2, Q3)

- Station 사이 직진 구간을 0.02 m 간격으로 채운다(station당 약 22점). heading은 이웃 station base heading의 선형 보간이다.

### P-B: 직진 5.07 m (Q3 대조)

- `corridor_5p07m` odom 궤적(scale 0.96756 보정, replay.json의 벽 기준 lateral 보정 적용)을 x0 = 6.0에서 시작해 along 방향 0.02 m 간격으로 양 끝점을 포함해 다시 샘플링한다. replay의 벽 기준 측방 관측값을 각 체크포인트와 종점에서 적용하고, 체크포인트 사이에서는 odom 대비 측방 보정량을 선형 보간한다.

### P-C: 자연 회전 경로 (Q3, ASSUMED 파라미터)

| 경로 | 정의 (lane y_lane 기준) | 회전 |
|---|---|---|
| **C1 네모** | x ∈ [6.0, 12.0], y ∈ [y_lane − 0.80, y_lane]의 직사각형 1바퀴(반시계) | 모서리마다 제자리 90°, 4회 |
| **C2 직선** | x ∈ [3.0, 17.0] 왕복(14 m × 2) | 끝에서 제자리 180°, 1회 |
| **C3 지그재그** | x ∈ [4.0, 16.0], 중심선 y = y_lane − 0.40, 진폭 0.30 m, 반주기 1.0 m. 꼭짓점 x = 4.5, 5.5, …, 15.5 m | 꼭짓점 12개를 반경 0.40 m 원호로 연결 |
| **C4 ㄹ자** | x ∈ [6.0, 12.0] 직진 3줄, 줄 간격 0.40 m(y = y_lane, y_lane − 0.40, y_lane − 0.80) | 줄 끝마다 제자리 90° → 0.40 m 횡이동 → 제자리 90°, 2회 반복 |

- C3는 중심선에서 출발·도착한다. 출발 전 0° → +30.96°, 도착 후 +atan(0.6) → 0°로 제자리 회전한다. 각 꼭짓점의 원호 회전량은 약 61.93°이고 0.08 m/s에서 각속도는 0.20 rad/s이다. 원호 접점까지의 직선 길이는 0.24 m이며, 원호 사이에 직선 구간을 유지한다.
- 주행과 제자리 회전은 각각 0.02 m, 2.5° 이하의 간격으로 양 끝점을 포함한다. C3 원호는 두 간격을 모두 충족한다. 제자리 회전과 호 회전을 구분해 기록한다.
- G0에서 회전한 TB3 몸체 직사각형(길이 0.281 m × 폭 0.306 m)과 벽·돌출물의 최소 여유가 0.05 m 이상인지 검사한다. G-V는 동일한 경로 정의를 해당 형상의 lane에 적용한다.

### RF pose와 관측 순서

- 형상 × anchor별 RF pose 표에 모든 pose 집합을 합친다. XY 유클리드 거리 ≤ 1e-6 m, 원형 yaw 차이 ≤ 1e-6°를 동시에 만족할 때 같은 물리적 pose로 본다. 최초 좌표를 반올림 없이 보존하고 RF는 pose_id당 한 번 계산한다. TEACH의 achieved_rel_deg를 격자각에 맞추지 않는다.
- 관측 순서 표는 관측마다 한 행을 유지한다. 열은 set, station_id, sequence_index, protocol (tb3_5pt, dense49, base, base_after, transit, route), planned_rel_deg, achieved_rel_deg, pose_id를 포함한다. TEACH는 기록 순서를 유지한다. REPEAT base는 마지막 정렬의 `observed_correction`을 TEACH `line_pose`에 합성한다. 각 sweep 관측 yaw는 해당 TEACH 목표 자세에 REPEAT ICP yaw 잔차를 더한다. 회전 중심은 station base XY로 고정한다. REPEAT 재시도 순서를 유지하고 목표각별 최종 관측을 표시한다. 조밀 격자는 별도 모의 sweep 순서를 갖는다.
- 같은 pose_id를 참조하는 관측은 clean H를 공유한다. G1-MODEL-002에서 관측 행의 sequence_index를 포함한 seed로 열잡음을 따로 샘플링한다. 같은 pose의 반복 관측은 독립 공간 표본 수를 늘리지 않는다.
- G0는 RF pose 표의 중복 0건, 관측 행의 pose_id 참조 무결성, set·station 내 sequence_index의 엄격 증가를 확인한다.

### 규모 (형상 1개, anchor 1개)

| 집합 | pose 수(약) |
|---|---|
| P-A (TEACH, 49 + 5 + 2) | 1,010 |
| P-A (REPEAT) | 1,010 |
| P-A′ | 390 |
| P-B | 260 |
| P-C (C1 15 m, C2 28 m, C3 13 m, C4 20 m) | 3,800 + 회전 약 600 |
| 합계 | 약 7,100 |

형상 3 × anchor 3 × (full + LoS) = 18 H store, 약 64,000 pose-채널. BLOCK_C apply는 1,303 pose에 27 s였다. trace 시간은 G1 pilot에서 측정한다.

## 4. RT 실행

기존 Method B 파이프라인(`codex/post-a23-evidence-20261010` @ `047cce2`)을 그대로 쓴다.

| 단계 | 스크립트 | 설정 |
|---|---|---|
| 형상 | 신규 `scripts/drive_sim/build_tb3_scene.py` | §1. `CorridorSetup`의 좌표와 PLY 형식을 따르는 mesh 및 재질 manifest 생성. Sionna 연결은 G1 pilot에서 확인 |
| Pose | 신규 `scripts/drive_sim/build_tb3_poses.py` | §3. 형상 × anchor별로 BLOCK_C 필드의 `rf_poses.json`, `rf_tasks.json`, 관측 `SAMPLES.json` + `TIMELINE.csv` |
| Trace | `scripts/drive_sim/rf_b_trace.py` | Sionna RT 2.0.1, mitsuba 3.8.0, drjit 1.3.1. 생산은 17 node, parity는 bin-by-bin |
| Apply | `scripts/drive_sim/rf_b_apply.py` | mount 0. 257 bins, 6.2504–6.7496 GHz |
| LoS | 같은 trace, max_depth 0 | BLOCK_C `H_LoS_*`와 동일 방식 |
| Full max_depth | BLOCK_C full H 생산 설정과 동일 | 실행 전에 BLOCK_C trace 설정에서 읽어 manifest에 고정 |
| 연속성 | `scripts/drive_sim/path_continuity.py` | 경로별 |

모든 단계는 manifest(config hash, 입력·출력 SHA, 명령, 시각, 패키지 버전)를 쓴다. 실행 위치는 Snowball/KMS이며 `run_rf_snowball.sh`의 단계 구조를 따른다.

## 5. 출력

`results/G1_RT_TB3_CORRIDOR_<date>/` 아래:

```text
scene/<geom>/*.ply, SCENE_MANIFEST.json
poses/<geom>_<anchor>/rf_poses.json, rf_tasks.json, SAMPLES.json, TIMELINE.csv
H/<geom>_<anchor>/H_full.npy, H_LoS.npy  (pose, 257, rx(+45,-45), tx(+45,-45)), MANIFEST.json
paths/<geom>_<anchor>/PATHS_LoS.npz, 집합별 path 요약
gates/G0…G6.json
CASES.json   (BLOCK_C 형식 + 혼동 방지용 los_H_sha256, full_H_sha256 필드)
RUN_MANIFEST.json
```

## 6. Gate

| Gate | 내용 | 기준 |
|---|---|---|
| G0 | 형상·pose 검사: 회전한 몸체와 벽·돌출물의 여유, anchor 여유, RF pose 중복, 관측 참조·순서, yaw 단위 | 위반 0건 |
| G1 | Pilot: G-T1 × A × P-A 앞 3 station. 시간·저장량 측정, 전체 일정 확정 | 기록 |
| G2 | **회귀**: BLOCK_C R2_aA_m0의 pose 50개를 BLOCK_C 형상에서 새 파이프라인으로 재계산해 기존 H와 비교 | 최대 상대 오차 < 1e-6. 실패 시 전체 중단 |
| G3 | bin-by-bin vs 17 node parity(기존 `parity_gate.py`) | 기존 임계값 |
| G4 | 거리 인지 관측 모델 parity(G1-MODEL-001 M1-T): noise-free LoS H vs 직접 계산 | p90 \|Δs\| ≤ 0.005, 모든 case |
| G5 | 형상 구성 검사: G-T2 station base에서 기하 벽 거리를 §1.2 정의값과 비교 | \|차이\| ≤ 0.01 m |
| G6 | 경로 연속성(path_continuity) | 기존 기준 |

## 7. 이 데이터의 사용 (G1-MODEL-002에서 정의)

1. G1-MODEL-001 §7 규칙으로 sweep 경로를 재판정한다. 실제 0.45 m station을 쓰므로 셀/독립/Markov 근사가 필요 없다.
2. TB3 5점 프로토콜과 49점 조밀 sweep을 비교한다.
3. passive 경로 arm: P-C에서 sweep 없이 주행 중 s를 쓰는 G1과, 같은 경로의 TB3 DR(회전 오차 Σ|dθ| 비례 + 정지 drift + κ_m)을 비교한다. DR-nosweep 대비 판정은 이 arm에서만 한다.
4. G-T1/G-T2/G-V로 형상 의존성을 보고한다. G-V와 BLOCK_C 비교로 기존 결과와 연결한다.
5. TB3 DR 파라미터는 G1-MODEL-001 §4(σ_w 0.486°, β 2.046°/station, σ_β {0, 0.32, 0.45}, 정지 bias 0.0005°/s 등)를 쓴다.

## 8. 해석 경계

- 환경 값은 모두 `ASSUMED`이며 실측 환경과의 동일성을 주장하지 않는다. 결과는 대표 복도 형상 3종에서의 편파 정보 유효성이다.
- 실측 multipath 재현을 주장하지 않는다. 형상 3종의 차이는 형상 민감도로만 보고한다.
- 로봇 몸체 반사, 안테나 장착 오프셋은 1차 모델에 없다.
- 결과 표기: `ENV_ASSUMED`, `GENERALIZATION_NOT_PROVEN`(형상 3종은 같은 복도 계열).

## 9. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-13 | 초판(SPEC_DRAFT, MISSING 항목 포함) | Claude |
| 2026-11-13 | 사용자 결정 반영: 환경·anchor·tag 위치는 실측과 같을 필요 없음 → 모든 MISSING을 ASSUMED 고정값으로 확정, P-C 경로 파라미터 정의, anchor 좌표 확정, G5를 형상 구성 검사로 변경, 상태 SPEC_FINAL | Claude |
| 2026-11-13 | 사용자 결정 반영: C3 꼭짓점 12개와 반경 0.40 m 고정, RF pose 표와 관측 순서 표 분리 및 G0 검사 명시 | Codex |
| 2026-11-14 | 부속 사양 `SPEC_DIAG_KO.md`(G1-RT-TB3-002) 추가: P-D/P-E/P-F pose, near-delay 경로 export, G7–G9, 특성화(G-T1)·확인(G-T2, G-V) 분리. 이 문서의 기존 항목은 변경 없음 | Claude |
