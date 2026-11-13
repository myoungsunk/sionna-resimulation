# G1-RT-TB3-001 — TB3 trackA형 복도 ray-tracing 데이터 재생성 사양서

- 작성: 2026-11-13 KST. 상태: **SPEC_DRAFT / INPUTS_PARTIALLY_MISSING / NOT_RUN**
- 목적: G1-FLOOR-001/G1-MODEL-001의 RT 한계(station 2 m 간격, sweep 90°, 형상 1개, passive 회전 경로 없음)를 없앤 RT 채널을 새로 만든다. TB3 TEACH/REPEAT와 **같은 경로·station·sweep 프로토콜**을 TB3 복도와 비슷한 형상에서 재현한다.
- 이 문서는 데이터 생성 사양이다. 분석 판정은 G1-MODEL-001 §7 규칙을 이 데이터에 다시 적용하는 별도 사양(G1-MODEL-002)에서 한다.
- `MISSING`으로 표시한 항목은 실행 전에 실측값이나 결정을 채워야 한다. 기본값으로 실행하면 해당 항목을 결과에 `ASSUMED`로 표기한다.

## 0. 이 데이터가 답해야 하는 질문

| Q | 질문 | 필요한 데이터 특성 |
|---|---|---|
| Q1 | TB3 sweep 프로토콜(5점, ±60°)과 연속 sweep(조밀 격자)에서 sweep heading 오차 분포는? | station별 yaw 격자 −60…+60° |
| Q2 | 0.45 m station 간격에서 sweep 오차의 실제 공간 상관은? | 0.45 m station 18개를 직접 계산(근사 불필요) |
| Q3 | sweep 없이 주행 중 s를 쓰는 passive 경로가 회전 없는 DR을 이길 수 있는가? (G1-MODEL-001 A2′) | 자연 회전이 있는 경로의 조밀 주행 pose |
| Q4 | 결과가 형상에 얼마나 의존하는가? | 형상 2개 이상, 같은 pose 집합 |
| Q5 | 거리 인지 관측 모델(M1)이 새 형상에서도 parity를 통과하는가? | 모든 pose의 LoS H |

## 1. 형상

### 1.1 TB3 복도에서 확인된 치수 (LiDAR, `trackA/teach/teach.json` @ `3018bb5`, `corridor_5p07m/replay.json`)

로봇 lane 기준(+y = 왼쪽) 벽까지 거리(station base, LiDAR 기준점, laser x 오프셋 −0.064 m):

| 구간(trackA along, m) | 왼쪽 벽 | 오른쪽 벽 | 해석 |
|---|---|---|---|
| 0.00–0.45 (P001–P002) | +0.69 | −1.44 | 왼쪽 오목부(깊이 약 0.19 m) |
| 0.90–2.25 (P003–P006) | +0.50 | −1.44 | 기본 단면, **폭 1.94 m** |
| 2.70–4.05 (P007–P010) | +0.49 | −1.03…−1.07 | **오른쪽 돌출물**(약 0.37–0.41 m, 길이 ≤ 1.4 m), 실체 `MISSING` |
| 4.50–6.30 (P011–P015) | +0.49 | −1.44 | 기본 단면 |
| 6.75–7.65 (P016–P018) | +0.68 | −1.44 | 왼쪽 오목부 |

- corridor_5p07m(11/11): 왼쪽 +0.50, 오른쪽 −1.44 m로 기본 단면과 일치한다.
- 로봇 lane은 복도 중심에서 왼쪽으로 약 0.47 m 치우쳐 있다(왼쪽 벽 0.50 m).

### 1.2 형상 정의

| ID | 정의 | 용도 |
|---|---|---|
| **G-T1** | 직육면체 복도. 폭 1.94 m, 길이 L, 높이 H. 로봇 lane y = +0.47 m(중심 기준) | 1차. 기존 BLOCK_C(폭 2.4 m)와 같은 단순 구조 |
| **G-T2** | G-T1 + §1.1의 왼쪽 오목부 2곳(깊이 0.19 m) + 오른쪽 돌출물 1개(0.39 × 1.4 m, 높이 `MISSING`) | TB3 trackA 재현도 |
| **G-V** | 폭 2.40 m(BLOCK_C와 동일), 벽 재질 교체(plasterboard ↔ concrete) | 형상 일반화 대조. BLOCK_C와의 연결 고리 |

| 파라미터 | 값 | 상태 |
|---|---|---|
| 길이 L | trackA 7.65 m + 양끝 여유. 기본 20 m(trackA는 x ∈ [6.0, 13.65]) | `MISSING`(실제 복도 길이, 끝벽 위치) |
| 높이 H | 기본 2.70 m(BLOCK_C) | `MISSING`(실측) |
| 벽 재질 | 기본 plasterboard 12.5 mm(BLOCK_C) | `MISSING`(실제 벽: 석고보드/콘크리트/유리) |
| 바닥·천장 | concrete 0.2 m | `MISSING`(천장재: 텍스 타일이면 별도 slab 모델 필요) |
| 오목부 실체 | 문 recess로 가정 | `MISSING`(문 재질: 목재/금속) |
| 돌출물 실체 | 콘크리트 기둥으로 가정 | `MISSING` |

Mesh는 기존 `scene/*.ply` 형식(BLOCK_C)을 따른다. 재질은 Sionna ITU 재질명과 두께로 바인딩하고, 각 ply의 SHA256을 manifest에 기록한다.

## 2. Anchor와 안테나

| 항목 | 값 | 상태 |
|---|---|---|
| Anchor | 천장 설치, boresight 아래, rotation diag(1, −1, −1), standoff 0.05 m, 단일 포트 TX +45(TX column 0) | 기존과 동일 |
| Anchor 위치 | **A**: trackA 시작점 x+1.0 m(trackA 위쪽 끝 근처), **B**: trackA 중앙(x+3.8 m), **C**: trackA 밖 x−3.0 m. 모두 복도 중심 y=0 | `MISSING`(실제 설치 계획). A/B/C는 수평거리 0–8 m를 덮도록 정한 기본값 |
| 로봇 RX | dual-port ±45° LP, rotation Rz(body yaw + mount), **mount 0°** | 기존과 동일, mount 0 고정 결정 |
| RX 높이 | 기본 0.45 m(BLOCK_C) | `MISSING`(TB3 탑재 안테나 실측 높이) |
| RX 기울기 | 기본 수평. 민감도: roll −1.6°, pitch +1.5°(TB3 정지 IMU) | 민감도 arm에서만 |
| FFD bank | `LP_plus45_bank.npz`, `LP_minus45_bank.npz`(Git LFS), A23 `FFD_RESTORE_MANIFEST` SHA와 대조 | 기존과 동일 |

한 run은 anchor 하나만 쓴다. Anchor마다 같은 pose 집합으로 별도 H를 만든다.

## 3. Pose 집합

모든 pose는 (x, y, yaw_body_deg)와 pose 유형, station_id, 순서 index를 가진다. 좌표는 trackA line 좌표(along, lateral)를 형상 좌표로 옮긴 것이다(x = x0 + along, y = y_lane + lateral).

### P-A: trackA station sweep (Q1, Q2)

- Station 18개, 간격 0.45 m. **TEACH 실측 line_pose(along, lateral, yaw)를 그대로 사용**한다(`teach.json` station.base.line_pose). REPEAT용 집합은 `repeat.json`의 정렬 후 자세로 별도 생성한다.
- Station마다:
  - **TB3 프로토콜 5점**: TEACH의 achieved_rel_deg(약 −60, −30, 0, +30, +60)와 base, base_after
  - **조밀 격자**: −60…+60°, 2.5° 간격, 49점(연속 회전 중 측정용)
- 같은 station의 sweep pose는 회전 중심을 base XY로 둔다. 회전 중심과 안테나 위치의 오프셋은 `MISSING`(TB3 안테나 장착 위치)이며 기본은 0이다.

### P-A′: trackA 이동 구간 (Q2, Q3)

- Station 사이 직진 구간을 0.02 m 간격으로 채운다(station당 약 22점). heading은 TEACH drive 기록의 선형 보간이다.
- 근거: 기존 δs 상관길이 0.08–0.40 m를 해상하려면 0.02 m 간격이 필요하다.

### P-B: corridor 5.07 m 직진 (Q3 대조)

- `corridor_5p07m` odom 궤적(scale 0.96756 보정)을 0.02 m로 다시 샘플링한다. 벽 기준 lateral 보정(replay.json checkpoints)을 적용한다.

### P-C: 자연 회전 경로 (Q3)

TB3 새 패키지의 경로 4종을 쓴다.

| 경로 | 정의 | 상태 |
|---|---|---|
| C1 네모 루트(map 생성) | 복도 폭 안에서 가능한지 확인 필요 | `MISSING`: waypoint 파일 |
| C2 직선 | P-B와 동일 계열 | 사용 가능 |
| C3 지그재그(자유 루트) | 폭 1.94 m 안의 진폭 | `MISSING`: waypoint 파일 |
| C4 ㄹ자 | 폭 1.94 m 안의 반환 반경 | `MISSING`: waypoint 파일 |

- 주행 pose는 0.02 m 간격, 회전 구간은 2.5° 간격이다. 제자리 회전과 호 회전을 구분해 기록한다.
- 각 pose에 누적 \|dθ\|를 기록한다. DR 회전 오차 모델(Σ\|dθ\| 비례)의 입력이 된다.
- 경로가 복도 안에 들어가는지(TB3 waffle_pi 몸체 약 0.28 × 0.31 m 기준 벽 여유 ≥ 0.05 m)를 G0에서 검사한다.

### 규모 추정 (형상 1개, anchor 1개)

| 집합 | pose 수 |
|---|---|
| P-A(조밀 + 5점 + base) | 18 × (49 + 5 + 2) ≈ 1,010 |
| P-A′ | ≈ 390 |
| P-B | ≈ 260 |
| P-C(경로당 20–40 m 가정) | 4 × (1,000–2,000 + 회전) ≈ 5,000–8,500 |
| 합계 | ≈ 6,700–10,200 |

형상 3개 × anchor 3개 × (full + LoS) = 18 H store. 기존 BLOCK_C는 1,303 pose의 apply가 27 s였다. trace 시간은 pilot(§6 G1)에서 측정한다.

## 4. RT 실행

기존 Method B 파이프라인(`codex/post-a23-evidence-20261010` @ `047cce2`)을 그대로 쓴다.

| 단계 | 스크립트 | 설정 |
|---|---|---|
| 형상 | 신규 `scripts/drive_sim/build_tb3_scene.py` | §1.2, `CorridorSetup` 확장(오목부·돌출물 mesh) |
| Pose | 신규 `scripts/drive_sim/build_tb3_poses.py` | §3. 출력은 `rf_poses_<set>.json`, `rf_tasks_<set>.json`, `SAMPLES.json` 형식(BLOCK_C와 동일 필드) |
| Trace | `scripts/drive_sim/rf_b_trace.py` | Sionna RT 2.0.1, mitsuba 3.8.0, drjit 1.3.1. 17 node 생산 + bin-by-bin parity |
| Apply | `scripts/drive_sim/rf_b_apply.py` | mount 0. FFD bank 적용. 257 bins, 6.2504–6.7496 GHz |
| LoS | 같은 trace에서 max_depth 0 | BLOCK_C `H_LoS_*` 생성 방식과 동일 |
| Full max_depth | BLOCK_C full H 생산 설정과 동일 | `TO_READ`: BLOCK_C trace 설정에서 읽어 고정 |
| 연속성 | `scripts/drive_sim/path_continuity.py` | 경로별 |

모든 단계는 manifest(config hash, 입력·출력 SHA, 명령, 시각, 패키지 버전)를 쓴다. 실행 위치는 Snowball/KMS이며 `run_rf_snowball.sh`의 단계 구조를 따른다.

## 5. 출력

`results/G1_RT_TB3_CORRIDOR_<date>/` 아래:

```text
scene/<geom>/*.ply, SCENE_MANIFEST.json
poses/<set>/rf_poses.json, SAMPLES.json, TIMELINE.csv (along, cum_abs_dtheta, pose 유형, station_id)
H/<geom>_<anchor>_<set>/H_full.npy, H_LoS.npy (pose, 257, rx(+45,-45), tx(+45,-45)), MANIFEST.json
paths/<geom>_<anchor>_<set>/PATHS_LoS.npz, path 요약
gates/G0…G5.json
CASES.json   (BLOCK_C 형식: case, poses, anchor_xyz, robot_z, mount, H_sha256(=LoS), input_H_sha256(=full) — 혼동 방지를 위해 los_H_sha256, full_H_sha256 필드를 추가)
RUN_MANIFEST.json
```

## 6. Gate

| Gate | 내용 | 기준 |
|---|---|---|
| G0 | 형상·pose 검사: 로봇 벽 여유, anchor 여유, pose 중복, yaw 단위 | 위반 0건 |
| G1 | Pilot: G-T1 × A × P-A 앞 3 station. 시간·저장량 측정, 전체 계획 확정 | 기록 |
| G2 | **회귀**: BLOCK_C R2_aA_m0의 pose 50개를 기존 형상에서 새 파이프라인으로 재계산 → 기존 H와 비교 | 최대 상대 오차 < 1e-6 |
| G3 | bin-by-bin vs 17 node parity(기존 `parity_gate.py` 기준) | 기존 임계값 |
| G4 | 거리 인지 관측 모델 parity(G1-MODEL-001 M1-T): noise-free LoS H vs 직접 계산 | p90 \|Δs\| ≤ 0.005, 모든 case |
| G5 | **TB3 형상 정합**: G-T2에서 station base의 벽 거리(시뮬레이션 기하)와 trackA LiDAR 벽 거리 비교 | \|차이\| ≤ 0.03 m |
| G6 | 경로 연속성(path_continuity) | 기존 기준 |

G2 실패 시 전체를 중단한다(파이프라인이 기존과 다름).

## 7. 이 데이터의 사용 계획 (G1-MODEL-002에서 정의)

1. G1-MODEL-001 §7 규칙으로 sweep 경로를 재판정한다. 2 m → 0.45 m 근사(셀/독립/Markov) 대신 실제 0.45 m station을 쓴다.
2. 5점 TB3 프로토콜과 49점 조밀 sweep을 비교한다.
3. passive 경로 arm: P-C에서 sweep 없이 주행 중 s를 쓰는 G1과, 같은 경로의 DR(회전 오차 Σ\|dθ\| 비례 + 정지 drift + κ_m)을 비교한다. A2′(DR-nosweep 대비) 판정은 이 arm에서만 한다.
4. 형상 G-T1/G-T2/G-V로 결과의 형상 의존성을 보고한다. G-V와 BLOCK_C의 비교로 기존 결과와의 연결을 확인한다.
5. 같은 pose와 경로로 TB3 실측 RF를 수행하면 시뮬레이션–실측 대조가 가능하다(형상이 TB3 복도를 근사하므로).

## 8. 한계

- 형상은 TB3 복도의 근사다. 천장재, 벽 재질, 가구, 문은 `MISSING` 항목에 따라 크게 달라질 수 있다. G-T1/G-T2/G-V 비교로 민감도를 보고하지만, 실측 환경과 동일하다고 주장하지 않는다.
- trackA pose는 TEACH 실측 자세를 쓰지만, RF는 시뮬레이션이다. RF 실측은 별도 단계다.
- 안테나 기울기, 로봇 몸체 반사(차체 금속)는 1차 모델에 없다. 로봇 몸체 반사는 Goal 1 이후의 별도 민감도 후보다.

## 9. 실행 전 채워야 할 항목

| 항목 | 필요한 이유 | 측정·결정 방법 |
|---|---|---|
| 복도 길이, 끝벽 위치 | 끝벽 반사 지연 | 줄자 또는 corridor map |
| 천장 높이, 천장재 | anchor 기하와 천장 반사 | 레이저 거리계 |
| 벽·문·돌출물 재질과 치수 | 반사 계수 | 육안·줄자, P007–P010 구간 사진 |
| TB3 RX 안테나 높이와 장착 위치(회전 중심 오프셋) | 기하, sweep 중 안테나 이동 | 줄자 |
| 실제 anchor 설치 계획(위치 수, 좌표) | anchor 집합 | 설치 계획 |
| 경로 C1/C3/C4 waypoint 파일 | P-C | TB3 새 패키지 |

## 10. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-13 | 초판 | Claude (proposer 초안) |
