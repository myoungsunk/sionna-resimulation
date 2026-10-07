# DRIVE_SIM_20261007 — 복도 주행 시뮬레이션 계획 (v1)

상태: **PLAN_ONLY / NOTHING_RUN**. 이 문서는 계획이며 계산·구현 완료나 gate PASS를 뜻하지 않는다.
AGENTS.md 규칙에 따라 각 단계(S0–S6)가 끝나면 상태 보고 후 승인을 기다린다.

## 1. 확정 사항 (사용자 결정)

| 항목 | 확정 |
|---|---|
| Base | `myoungsunk/sionna-resimulation` @ `claude/determined-turing-vxge0c` (`c13797a`). 작업 브랜치 `claude/cool-dijkstra-hnznhm`은 같은 initial commit(`fd2f757`)에서 갈라졌으므로 `c13797a`로 fast-forward 가능 (force 불필요) |
| Producer | `scripts/corridor_sionna_run.py` (LP_DIAG 1 arm, pose당 257 호출, 0.2709 s/call → 약 69.6 s/pose, SCAN2 receipt 기준) |
| Scene | `qclean_uwb/scenarios/corridor.py` (20×2.4×2.7 m, anchor x=4 천장, robot 안테나 z=0.45, x∈[1,19], \|y\|≤0.74). **101-scene CORRIDOR 사용 금지.** 재질(concrete 0.2 / plasterboard 12.5 mm)은 코드상 temporary → config에 `assumption` 태그 |
| `s` | `qclean_uwb/features/fp_power.py` + `port_ratio.py`: LP ±45 first-path(FP) power ratio, `s=(P1−P2)/(P1+P2)`, 이상적 `s=σ·cos 2yaw` |
| CP arm | 불필요 (v1 제외) |
| 환경 | sionna-rt 2.0.1 / mitsuba 3.8.0 (`llvm_ad_mono_polarized`) / drjit 1.3.1, bank SHA256이 `BANK_MANIFEST.json`과 일치 |
| 계산 방식 | B안(trace/pattern 분리) 기본 + parity gate. gate 실패 시 A안(pose별 직접 PathSolver) fallback |
| Probe | v1은 open-loop **P0 / P1**. 적응형 P2는 v2로 이월 |
| Parity reference | `results/CORRIDOR_SWEEP_20261006`, `CORRIDOR_SCAN_20261006`, `CORRIDOR_SCAN2_20261007`의 `*_H.npy` + `*_receipt.json` (`c13797a` 기준 SCAN2 receipt 32개 → 총 12+32=44 position × 19 yaw(0–180°, 10°) × 257 bin) |

## 2. 필수 변경: FP index 규칙 (single-port anchor)

- 현재(`fp_power.first_path_power`): 4개 branch(RX×TX) 중 최강 branch에서 30% leading edge로 FP index 결정.
- 변경: anchor가 **TX +45 한 포트만** 쓰므로, 선택 TX 열(+45)의 **RX 2-branch(+45/−45) 중 최강** branch에서 FP index를 결정하고 `P1,P2=|CIR[index, rx, tx_sel]|²`.
- 구현 원칙: 기존 함수는 재현용으로 보존하고 새 함수(예: `first_path_power_single_tx`)를 추가. `s` 부호 σ=−1 (TX +45)을 문서화.
- 영향: (a) TX −45 열이 없어 `artifact_correction`의 I1(두 TX 포트 불일치) 지표는 v1에서 쓸 수 없다. (b) parity reference의 H는 2×2이므로 **열 0만 취해 새 규칙으로 FP/`s`를 재계산**해서 비교한다. 옛 4-branch 규칙과 FP index가 달라지는 (position, yaw) 비율을 S0/S3에서 보고한다. (c) B안은 TX +45 패턴만 필요하다.
- 테스트: 이상적 LoS H에서 `s=−cos 2yaw`, 열 선택 정확성, 2-branch 선택이 4-branch와 달라지는 합성 케이스, noise-free 재현.

## 3. 비용 (LP_DIAG 1 arm)

| 항목 | pose 수 | A안(직접) |
|---|---:|---:|
| 왕복 18 m, 0.2 m/s, 5 Hz | ≈900 | ≈17.4 core-h |
| Probe 20 s마다 × 19 pose (±45° 5° 간격) | ≈170 | ≈3.3 core-h |
| 합계 / 장착 offset 1개 | ≈1,070 | ≈20.7 core-h (4 core ≈ 5.2 h) |

B안은 trace가 (x,y)에만 의존: 900 위치 × 재질 주파수 node K개 × 0.27 s ≈ 0.07·K core-h (K는 S2에서 결정, 가정). A안 수치는 receipt 기반이고 B안 수치는 **미검증 추정**이다.
RF truth는 truth 궤적에만 의존한다 (truth 궤적과 truth probe yaw를 open-loop로 고정하는 한). drift/seed/noise Monte Carlo는 저장된 noise-free H 위에서 수행.

## 4. 단계

### S0 — 가져오기, 고정, 사전 등록 (무거운 계산 없음)
1. `c13797a`로 fast-forward. 필요한 코드·tests 존재 확인(`corridor_sionna_run.py`, `scenarios/corridor.py`, `features/{fp_power,port_ratio,reflection_attribution}.py`, `tests/test_corridor_*`). 기존 results는 읽기 전용.
2. 환경 재현: 버전 3종 일치, `load_banks()`의 bank SHA256 == `BANK_MANIFEST.json`, `--los-check` 재실행(브랜치 기록: 48케이스 최대 6.1e-7, 기준 1e-4). 이 세션에는 Sionna가 없으므로 실행은 Snowball/KMS 또는 동일 버전 환경에서 한다.
3. **Antenna lever arm 고정**: 기본안은 lever arm = 0 (안테나가 pose 기준점 바로 위, yaw 회전축 위; 현재 `CorridorSetup`의 암묵 가정). 0이 아니면 yaw에 따라 안테나 위치가 `l·(R(θ)−I)`만큼 움직여 (a) probe 19 pose가 trace를 공유하지 못하고, (b) 수 cm의 이동이 파장(≈4.6 cm)과 비슷해져 RF·range 모델에 직접 영향을 준다. 값과 근거를 config에 `assumption`으로 기록하고 **POSES hash 생성 전에** 확정한다.
4. **Parity 임계값 사전 등록** (결과를 보기 전): H 상대 오차, `s` 절대 차이, FP index 일치율, path 수 일치. 값은 S0에서 확정(잠정: H ≤1e-4, FP index 100% 일치).
5. 시간 재측정(pilot 1 pose): thread 수별 s/call. 4 core 스케줄은 `corridor_scan2_run.sh`(단일 core 4개 병렬, receipt 있으면 skip) 방식을 따른다.
6. config 스키마(`assumption` 태그), config hash, manifest 유틸.
- **P0/P1 정의(확인 필요)**: P0 = probe 없음(passive `s`), P1 = 고정 주기(20 s) open-loop probe로 해석했다.

### S1 — Truth 궤적 생성기
- `x:1→19→1`, `y≈0`(\|y\|≤0.74 허용영역), 0.2 m/s, 5 Hz(간격 4 cm), 끝에서 180° 회전, probe(20 s마다, ±45° 19 pose).
- 출력 `POSES.jsonl` + hash. yaw 범위 [−45°, 225°]. 기존 sweep은 0–180°뿐이므로 범위 밖 yaw는 reference가 없다(S2 G4).
- 테스트: 간격, pose 수, 허용영역, yaw 연속성/랩, probe 횟수·타이밍, truth가 drift에 무관함.

### S2 — Pose-batch runner와 parity gate (핵심)
- **A안**: `corridor_sionna_run.py`를 (x,y,yaw) 리스트 입력으로 확장. 위치별 출력, receipt, resume. TX는 +45 한 포트로 줄일 수 있는지 S0에서 확인(출력 `H[...,rx(2),tx(1)]`).
- **B안(기본)**: isotropic V/H 2-port로 trace하여 path별 2×2 전달 행렬과 각도를 export하고, FFD bank(TX +45, RX ±45)를 offline으로 적용. 선결 확인: Sionna 2.0.1에서 행렬 추출 가능 여부, `theta/phi_{t,r}` 좌표계, 재질 주파수 의존성 node 보간.
- **Gate 목록** (모두 통과해야 B안 사용; 실패하면 A안으로 고정 schedule만 계산하고 비용표 갱신):
  - G0: 환경·bank SHA·LoS check.
  - G1: A안 재현 — 기존 position 1곳을 부분 yaw/bin으로 다시 돌려 저장 H와 비교(PathSolver 결정성 확인).
  - G2: B안 vs 저장 H — 44 position × 19 yaw × 257 bin, 사전 등록 임계값(§4 S0-4).
  - G3: **궤적 전체 path 연속성** — 모든 pose에서 `classify_paths(tau, tx, rx, L, half_w, H)`의 미매칭(−1)이 0. 인접 pose 간 매칭된 image-method 시퀀스 집합이 같고(63경로 일정 여부 확인) 변하면 사유를 기록. `tol`(현재 5e-14 s)이 float32 `tau`에서 충분한지 S0에서 점검.
  - G4: 범위 밖 yaw(−45°, −30°, 200°, 225°) — 3개 position에서 A안 직접 실행과 B안 비교(reference 부재 대체).
- Receipt: 버전, SHA, 호출 수, 시간, 명령줄, config hash.

### S3 — H 저장소와 관측 체인
- Noise-free H 저장(`[pose, bin, rx(2)]` + path 메타). 관측 체인: Hann 1028 CIR → 새 FP 규칙(§2) → range, P1, P2, `s`.
- Noise는 post-process: 포트별 thermal noise, SNR은 "10 m LoS co-pol에서 X dB"로 sweep(placeholder). 결정적 range 오차(MP/pattern)는 H에 이미 포함, random 성분만 추가.
- 확인: 옛 규칙 대비 FP index 변경 비율, noise에서의 branch 선택 flip 비율.

### S4 — h_s LUT
- LoS-only `s`를 (θ, φ_tx, φ_rx) 격자(θ 2°, φ 5°)에서 FFD bank + 검증된 Cartesian contraction으로 계산(브랜치 `tx_angle_sweep`/`shift_fit`의 LoS counterfactual 재사용), **같은 새 FP 규칙** 통과.
- Gate: Sionna `max_depth=0` 대비 임의 각도 오차. 모델 불일치 σ는 궤적 위 LUT `s`와 full-sim `s`의 차이로 실측(이전 약 0.09와 비교). 기울기 0인 flat 구간(yaw≈0/90/180°)을 Jacobian 설계에 반영(브랜치 `error_budget`/`flat_axes` 분석 참조).

### S5 — 센서 생성기와 filter
- Gyro/odom/UWB는 독립 생성, 파라미터는 모두 `assumption`: ICM-20648 ARW 0.015 °/√s, SF ±1.5%(0.5/1.5), 잔여 bias 0.01/0.05/0.2 dps, 바퀴 직경비 0.2/0.5/1%, wheelbase 0.5/1%, Thrun형 비체계 오차, 회전 중 slip, UWB σ_r 5/10 cm. 실물 gyro IC(2020년 이후 ICM-20648 vs 구형 MPU9250)와 TB3 기하(r=0.033, b=0.287)는 실물 확인 필요로 표시.
- State `[x, y, θ, b_g, SF_g, ε_d]`, NIS χ²₁(0.99) gating, EKF/IEKF/UKF, 귀환 구간용 Gaussian-sum 초기화. `R_s` = 열잡음(SNR) + 모델 불일치(σ≈0.09).
- 먼저 LUT에서 직접 생성한 합성 데이터로 filter 검증(파라미터 복원, NEES/NIS), 그다음 실제 RF H.

### S6 — 실험 행렬과 보고 (v1)
- 비교군 5: odom+IMU / +range / +range+`s`(P0 passive) / +range+`s`+probe(P1 open-loop) / `s` 대신 역산 heading. **P2(적응형 probe)는 v2.**
- 축: 장착 offset(yaw mount) 2 × drift 3 × SNR 2 × seed 50. RF는 장착 offset당 한 번(B안이면 pattern만 재적용).
- 지표: heading/position RMSE 시계열, NEES/NIS, wrong-branch 비율, gate reject 비율, probe 횟수.
- Manifest: config hash/snapshot, 입력·출력, timestamp, 명령줄, seed, Sionna receipt. 보고서는 링크 점검(`06_build_reports.py --check-links`)까지.

## 5. Claim 경계와 보호 경로

- 시뮬레이션 전용, placeholder 파라미터, hardware 검증 아님. `s`는 q_clean이 아니며 q_clean이 range 오차를 보장한다는 주장과 섞지 않는다.
- 새 산출물은 `results/DRIVE_SIM_20261007/` 아래에만 쓴다. `data/raw/`, `results/frozen/`, `reports/release/`, 기존 corridor/SIONNA results는 덮어쓰지 않는다.
- 브랜치의 `sweep.npz`(경로 단위)는 git에 없으므로 path 단위 parity는 새로 trace한 일부 position에서만 가능하다.

## 6. 열린 항목

1. P0/P1 정의 확인(§4 S0).
2. Lever arm 값(기본 0) 확정.
3. Parity 임계값 사전 등록값.
4. 이 세션에 Sionna가 없으므로 계산 환경(Snowball/KMS 또는 동일 버전 환경) 지정.
