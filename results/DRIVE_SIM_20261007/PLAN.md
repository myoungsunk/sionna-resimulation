# DRIVE_SIM_20261007 — 복도 주행 시뮬레이션 계획 (v1, rev2)

상태: **PLAN_ONLY / NOTHING_RUN**. 이 문서는 계획이며 계산·구현 완료나 gate PASS를 뜻하지 않는다.
AGENTS.md 규칙에 따라 각 단계(S0–S6)가 끝나면 상태 보고 후 승인을 기다린다.

rev2 변경 요약: base 이력 처리(rebase), `s` 정의 위치 정정 및 `src/` 통합, A안 TX 열 유지, S1 설정 추가(lateral, heading 흔들림, 초기 불확실도, probe 시간축, 180° 회전 취급), 가설 사전 등록, probe station snap + 주기 T sweep, LFS bank 확보, S4 대조 규칙, 임계값 확정.

## 1. 확정 사항

| 항목 | 확정 |
|---|---|
| Base | `myoungsunk/sionna-resimulation` @ `claude/determined-turing-vxge0c` (`c13797a`). **작업 브랜치(`f37cf32`)와 c13797a는 갈라진 상태**(fd2f757은 c13797a의 조상이지만 f37cf32는 c13797a 이력에 없음). §4 S0-1 참조 |
| Producer | `scripts/corridor_sionna_run.py` (LP_DIAG 1 arm, pose당 257 호출, 0.2709 s/call → 약 69.6 s/pose, SCAN2 receipt 기준) |
| Scene | `qclean_uwb/scenarios/corridor.py` (20×2.4×2.7 m, anchor x=4 천장, robot 안테나 z=0.45, x∈[1,19], \|y\|≤0.74). **101-scene CORRIDOR 사용 금지.** 재질(concrete 0.2 / plasterboard 12.5 mm)은 코드상 temporary → config에 `assumption` 태그 |
| `s` | signed `s=(P1−P2)/(P1+P2)`, P=first-path(FP) tap power. 이상적 `s=σ·cos 2yaw`, σ=−1(TX +45). **정의 위치 정정**: signed s는 `scripts/corridor_shift_fit.py::signed()`에 있고, `features/port_ratio.py`는 복소 응답의 `\|p1−p2\|/\|p1+p2\|`로 다른 양이다 |
| CP arm | 불필요 (v1 제외) |
| 환경 | sionna-rt 2.0.1 / mitsuba 3.8.0 (`llvm_ad_mono_polarized`) / drjit 1.3.1, bank SHA256이 `BANK_MANIFEST.json`(`results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/`)과 일치 |
| 계산 방식 | B안(trace/pattern 분리) 기본 + parity gate. gate 실패 시 A안(pose별 직접 PathSolver) fallback |
| Probe | v1은 open-loop **P0 / P1**, 적응형 P2는 v2 |
| P0 | 능동 probe 없음. 주행 중 매 UWB 이벤트의 `s` 사용. 끝 지점 180° 회전 구간의 `s`도 쓰되 **별도 flag**로 표시(§4 S1) |
| P1 | 고정 주기 open-loop probe. 기본 T=20 s, T∈{10,20,60,∞} s sweep(§4 S1) |
| 장착 offset | 안테나 **편파가 아니라 물리적 장착 회전**: 로봇 몸체 전방 대비 안테나 local x축의 yaw 차이. 두 포트는 항상 안테나 frame에서 +45°/−45°. 안테나 world yaw = 로봇 heading + offset. v1은 {0°, 45°} (H3) |
| Lever arm | v1은 **0** (안테나가 TB3 base_link 회전 중심=바퀴축 중점 바로 위). 0이 아닌 값은 v2 민감도 분석 |
| Parity reference | `results/CORRIDOR_SWEEP_20261006`, `CORRIDOR_SCAN_20261006`, `CORRIDOR_SCAN2_20261007`의 `*_H.npy` + `*_receipt.json`. c13797a 기준 SCAN2 receipt 32 + 12 = **44 position** × 19 yaw(0–180°, 10°) × 257 bin. `--los-check` 48케이스 최대 6.07e-7 (`CORRIDOR_SWEEP_20261006/LOS_CHECK.json`) |

## 2. 필수 변경: FP index 규칙과 `s` 정의 통합 (single-port anchor)

- 현재(`fp_power.first_path_power`): 4개 branch(RX×TX) 중 최강 branch에서 30% leading edge로 FP index 결정.
- 변경: anchor가 **TX +45 한 포트만** 쓰므로, 선택 TX 열(+45)의 **RX 2-branch(+45/−45) 중 최강** branch에서 FP index를 결정하고 `P1,P2=|CIR[index, rx, tx_sel]|²`.
- **통합**: 새 FP 규칙 함수(예: `first_path_power_single_tx`)와 signed `s`를 함께 `src/qclean_uwb/features/`에 둔다. `corridor_shift_fit.py::signed()`의 정의를 이쪽으로 옮겨 scripts와 filter가 같은 구현을 import한다 (AGENTS.md: 분석 스크립트가 유일한 구현이면 안 됨). 기존 4-branch 함수는 재현용으로 보존.
- **A안은 2×2 H를 그대로 저장**한다. PathSolver 호출 한 번이 2×2 전체를 계산하므로 TX를 한 포트로 줄여도 비용 이득이 없고, 두 열을 저장해 두면 TX −45 비교와 기존 분석(I1 등)과의 연속성이 공짜다. 열 0만 쓰는 것은 관측 체인/filter 쪽이다.
- parity reference의 H도 2×2이므로 **열 0만 취해 새 규칙으로 FP/`s`를 재계산**해 비교한다. 옛 4-branch 규칙과 FP index가 달라지는 (position, yaw) 비율을 S0/S3에서 보고한다.
- 테스트: 이상적 LoS H에서 `s=−cos 2yaw`, 열 선택 정확성, 2-branch 선택이 4-branch와 달라지는 합성 케이스, noise-free 재현, 기존 `signed()`와의 수치 동일성.

## 3. 비용 (LP_DIAG 1 arm)

| 항목 | pose 수 | A안(직접), 궤적 1개 |
|---|---:|---:|
| 왕복 18 m, 0.2 m/s, 5 Hz | ≈900 | ≈17.4 core-h |
| Probe 20 s마다 × 19 pose (±45° 5° 간격) | ≈170 | ≈3.3 core-h |
| 합계 / 장착 offset 1개 | ≈1,070 | ≈20.7 core-h |

- **Lateral y₀∈{0, 0.35} 2개 → 궤적 2개**: A안 ≈41 core-h (4 core ≈ 10.4 h).
- B안: trace는 (x,y)에만 의존. 위치는 궤적당 4 cm 격자 ≈900곳이고 probe station은 이 격자 위에 snap되므로 추가 위치가 없다(§4 S1). 비용 ≈ 위치 수 × 재질 주파수 node K × 0.27 s ≈ 1,800 × K × 0.27 s ≈ 0.14·K core-h (K는 S2에서 결정). 장착 offset·probe 주기 T·heading 흔들림은 pattern만 바꾸므로 추가 RF 계산이 없다. **B안 수치는 미검증 추정**, A안 수치는 receipt 기반.
- RF truth는 truth 궤적(위치와 scripted truth yaw)에만 의존. drift/seed/noise Monte Carlo는 저장된 noise-free H 위에서 수행.

## 4. 단계

### S0 — 가져오기, 고정, 사전 등록 (무거운 계산 없음)
1. **Base 정리**: 작업 브랜치의 내 커밋은 PLAN.md 추가뿐이다. 파일 내용은 어느 방식이든 같다(c13797a 전체 + PLAN.md). 권장: `git merge c13797a`(force push 불필요, 원격 이력 보존). 대안: rebase 후 `--force-with-lease` push(이력이 직선이지만 원격 이력을 덮어씀). PLAN.md는 c13797a에 없는 새 파일이라 충돌 없음. force push는 실행 전에 사용자 승인을 받는다. 필요한 코드·tests 존재 확인(`corridor_sionna_run.py`, `scenarios/corridor.py`, `features/{fp_power,port_ratio,reflection_attribution}.py`, `tests/test_corridor_*`). 기존 results는 읽기 전용.
2. **환경 재현**: 버전 3종, `load_banks()`의 bank SHA256 == `BANK_MANIFEST.json`, `--los-check` 재실행. 이 세션에는 Sionna가 없으므로 Snowball/KMS(또는 동일 버전 환경)에서 실행.
3. **LFS bank 확보**: `git lfs pull --include "LP_plus45_bank.npz,LP_minus45_bank.npz"` (각 약 248 MB). 나머지 4개 bank는 불필요.
4. **Lever arm = 0 고정** (§1). 값과 근거를 config에 `assumption`으로 기록하고 **POSES hash 생성 전에** 확정.
5. **사전 등록** (결과를 보기 전): §6 임계값, §7 가설, §4 S1의 궤적·시간축 파라미터.
6. 시간 재측정: 1-pose pilot으로 thread 수별 s/call → 비용표 갱신. 4 core 스케줄은 `corridor_scan2_run.sh`(단일 core 4개 병렬, receipt 있으면 skip) 방식.
7. config 스키마(`assumption` 태그), config hash, manifest 유틸.

### S1 — Truth 궤적 생성기
- 기본: `x:1→19→1`, 0.2 m/s, 5 Hz(간격 4 cm, pose 체류 0.2 s).
- **Lateral 위치**: 궤적 변형 y₀∈{0, 0.35} m (\|y\|≤0.74 허용영역 안). y=0은 양쪽 옆벽 지연이 같아지는 특수 경우라 일반화가 안 되므로 필수. 비용 2배(§3).
- **Heading 흔들림**: scripted truth yaw에 ±3–5° 섭동(seed 고정, 궤적 일부로 hash에 포함). 이에 따라 yaw 범위는 약 **[−50°, 230°]**이며 G4 범위 밖 yaw 검증도 이에 맞춘다(§5).
- **초기 pose 불확실도**: σ_θ₀=5°, σ_xy=0.1 m (filter의 초기 공분산이자 Monte Carlo 초기 오차 분포; truth RF는 영향 없음).
- **Probe 시간축 (확정)**: 제자리(lever arm 0) 회전. 회전 속도 **25°/s** = 5 Hz 표본당 5°(요구된 5° 각도 분해능, 19 pose ±45°와 일치; TB3 최대 각속도 약 104°/s보다 충분히 낮음). 순서: 현재 heading → −45°(1.8 s) → +45°까지 sweep(3.6 s, 19 표본) → 원 heading 복귀(1.8 s) = **probe 1회 ≈ 7.2 s** (이 시간은 시간 비용으로 집계). 회전은 truth에서 scripted(정확히 25°/s), estimator는 gyro 적분(SF·bias 오차 포함)으로 본다.
  - 모든 probe 표본이 5° 격자에 정렬되면 positioning 구간 표본은 sweep과 같은 yaw라 H를 재사용한다(station당 distinct yaw 19개). heading 흔들림으로 비정렬이면 A안은 probe당 최대 37 pose(약 +3 core-h/궤적)이고 B안은 영향 없음.
- **Probe station snap**: probe 위치는 4 cm 주행 격자 위로 snap한다. 그래야 probe pose가 주행 pose와 trace를 공유하고, **주기 T∈{10, 20, 60, ∞} s sweep을 추가 RF 계산 없이** 수행할 수 있다(H4 판정에 필요).
- **끝 지점 180° 회전**: 회전 자체가 yaw sweep이다. P0에서도 회전 중 `s`를 사용하되 **`turn_phase` flag**를 붙여 별도 집계한다(암묵적 probe 효과를 분리해서 보고). flag를 끈 변형(P0-noturn)을 추가 비교로 둔다.
- 출력 `POSES.jsonl` + hash. 테스트: 간격, pose 수, 허용영역, yaw 연속성/랩, probe 횟수·타이밍·snap, truth가 drift에 무관함, 회전 flag.

### S2 — Pose-batch runner와 parity gate (핵심)
- **A안**: `corridor_sionna_run.py`를 (x,y,yaw) 리스트 입력으로 확장. 위치별 출력, receipt, resume. **2×2 H 전체 저장**(§2).
- **B안(기본)**: isotropic V/H 2-port로 trace하여 path별 2×2 전달 행렬과 각도를 export하고, FFD bank(LP ±45)를 offline으로 적용. 선결 확인: Sionna 2.0.1에서 행렬 추출 가능 여부, `theta/phi_{t,r}` 좌표계, 재질 주파수 의존성 node 보간.
- **보고 분리**: G2 실패 시 원인을 분리하도록 **bin별 trace 결과와 node 보간 결과를 따로 보고**한다.
- Gate (임계값은 §6): G0 환경·SHA·LoS check / G1 A안 재현성 / G2, G2' B안 vs 저장 H / G3 궤적 path 연속성 / G4 범위 밖 yaw. 하나라도 실패하면 A안으로 고정 schedule만 계산하고 비용표를 갱신한다.
- G3 상세: 모든 pose에서 `classify_paths(tau, tx, rx, L, half_w, H)` 미매칭(−1) 0. 인접 pose 간 매칭된 image-method 시퀀스 집합이 같고(63경로 일정 여부 확인) 변하면 사유 기록. `tol`(5e-14 s)이 float32 `tau`에서 충분한지 S0에서 점검.
- Receipt: 버전, SHA, 호출 수, 시간, 명령줄, config hash.

### S3 — H 저장소와 관측 체인
- Noise-free H 저장(`[pose, bin, rx(2), tx(2)]` + path 메타). 관측 체인: Hann 1028 CIR → 새 FP 규칙(§2) → range, P1, P2, `s`.
- Noise는 post-process: 포트별 thermal noise, SNR은 "10 m LoS co-pol에서 X dB"로 sweep(placeholder). 결정적 range 오차(MP/pattern)는 H에 이미 포함, random 성분만 추가.
- 확인: 옛 규칙 대비 FP index 변경 비율, noise에서의 branch 선택 flip 비율.

### S4 — h_s LUT
- LoS-only `s`를 (θ, φ_tx, φ_rx) 격자(θ 2°, φ 5°)에서 FFD bank + 검증된 Cartesian contraction으로 계산(브랜치 `tx_angle_sweep`/`shift_fit`의 LoS counterfactual 재사용), **같은 새 FP 규칙** 통과.
- **대조 규칙**: 브랜치의 `ANGLE_MODEL_COMPARE.json`은 옛 4-branch FP 규칙 결과라 **그대로 비교하지 않는다.** 새 규칙으로 angle model을 다시 계산해 LUT와 비교하고, Sionna `max_depth=0` 대조를 병행한다.
- 모델 불일치 σ는 궤적 위 LUT `s`와 full-sim `s`의 차이로 실측(이전 약 0.09와 비교). 기울기 0인 flat 구간(yaw≈0/90/180°)을 Jacobian 설계에 반영(브랜치 `error_budget`/`flat_axes` 분석 참조).

### S5 — 센서 생성기와 filter
- Gyro/odom/UWB는 독립 생성, 파라미터는 모두 `assumption`: ICM-20648 ARW 0.015 °/√s, SF ±1.5%(0.5/1.5), 잔여 bias 0.01/0.05/0.2 dps, 바퀴 직경비 0.2/0.5/1%, wheelbase 0.5/1%, Thrun형 비체계 오차, 회전 중 slip, UWB σ_r 5/10 cm. 실물 gyro IC(2020년 이후 ICM-20648 vs 구형 MPU9250)와 TB3 기하(r=0.033, b=0.287)는 실물 확인 필요로 표시.
- State `[x, y, θ, b_g, SF_g, ε_d]`, NIS χ²₁(0.99) gating, EKF/IEKF/UKF, 귀환 구간용 Gaussian-sum 초기화. `R_s` = 열잡음(SNR) + 모델 불일치(σ≈0.09).
- 먼저 LUT에서 직접 생성한 합성 데이터로 filter 검증(파라미터 복원, NEES/NIS), 그다음 실제 RF H.

### S6 — 실험 행렬과 보고 (v1)
- 비교군 5: odom+IMU / +range / +range+`s`(P0) / +range+`s`+probe(P1) / `s` 대신 역산 heading. 추가: P0-noturn. **P2는 v2.**
- 축: 장착 offset(yaw mount) 2 × drift 3 × SNR 2 × lateral 2 × seed 50. RF는 궤적×장착 offset당 한 번(B안이면 pattern만 재적용). P1은 T∈{10,20,60,∞} s sweep.
- 장착 offset 2개 = {0°, 45°} (H3 기준; S0에서 확정).
- 지표: heading/position RMSE 시계열, NEES/NIS, wrong-branch 비율, gate reject 비율, probe 횟수.
- Manifest: config hash/snapshot, 입력·출력, timestamp, 명령줄, seed, Sionna receipt. 보고서는 링크 점검(`06_build_reports.py --check-links`)까지.

## 5. Gate 임계값 (S0에서 사전 등록)

효과 크기에서 역산: 모델 불일치 σ_s≈0.09, steep 구간 기울기≈0.03/°이므로 \|Δs\|=1e-3은 heading 약 0.03°에 해당해 무시 가능.

| Gate | 지표 | 임계값 |
|---|---|---|
| G1 (A안 재현성) | H 상대 오차 | ≤ 1e-6 (결정성 확인) |
| G2 (B안, bin별 trace) | H 상대 오차, pose별 | median ≤ 1e-4, max ≤ 1e-3 |
| | FP index 일치 | 100% |
| | \|Δs\| | ≤ 1e-3 |
| | range 차 | ≤ 1 mm |
| G2' (B안, node 보간) | \|Δs\| | ≤ 2e-3 |
| | FP index 일치 | ≥ 99.5% |
| | range 차 | ≤ 2 mm |
| G3 (path 연속성) | 미매칭 path | 0 |
| | 인접 pose 간 path 집합 변화 | 사유를 모두 기록 |
| G4 (범위 밖 **안테나 world yaw**, heading 범위 약 −50°…230° + 장착 offset; 45° 장착이면 약 −5°…275°) | | G2와 같은 기준 (3개 position, A안 직접 실행과 비교) |

## 6. 사전 등록 가설 (S0)

판정은 drift 수준·SNR·lateral·장착 offset별로 분리해 보고한다. 효과 크기·검정 방법은 S0에서 확정.

**검정 방법 (공통, 사전 등록)**
- 단위: seed 쌍. 같은 seed는 같은 drift/noise 실현을 공유하므로 paired 비교. 조건 = drift × SNR × lateral × 장착 offset.
- 지표: run별 heading RMSE (초기 30 s 제외 시간평균). 보조: 귀환 구간 RMSE.
- 검정: paired Wilcoxon signed-rank(양측, α=0.01), Holm 보정(가설별 전체 조건을 한 family로). 효과 크기 = 쌍 차이의 중앙값 + bootstrap 95% CI(10,000회).
- "개선" 판정: Holm 보정 후 유의 **그리고** 중앙값 상대 개선 ≥ 10%. (10%는 제안값; 이의 없으면 확정)
- Wrong-branch 정의: \|θ̂−θ\| > 20°인 시간 step의 비율(초기 30 s 제외). 20°는 제안값, 민감도로 10°/30°도 보고.

- **H1**: range + `s`가 odom+IMU만 쓸 때보다 heading RMSE가 낮다 (drift 수준별).
- **H2**: `s` measurement가 `s`에서 역산한 heading보다 낫다.
- **H3**: 45° 장착이 0° 장착보다 passive(P0) heading RMSE가 낮다.
- **H4**: P1에서 wrong-branch 비율(seed 평균 시간비율)의 bootstrap 95% 상한이 **X=10%** 이하인 최대 probe 주기 T∈{10,20,60,∞} s.

## 7. Claim 경계와 보호 경로

- 시뮬레이션 전용, placeholder 파라미터, hardware 검증 아님. `s`는 q_clean이 아니며 q_clean이 range 오차를 보장한다는 주장과 섞지 않는다.
- 새 산출물은 `results/DRIVE_SIM_20261007/` 아래에만 쓴다. `data/raw/`, `results/frozen/`, `reports/release/`, 기존 corridor/SIONNA results는 덮어쓰지 않는다.
- 브랜치의 `sweep.npz`(경로 단위)는 git에 없으므로 path 단위 parity는 새로 trace한 일부 position에서만 가능하다.

## 8. 열린 항목

1. ~~Probe 회전 속도~~ → 확정(§4 S1: 25°/s).
2. ~~H4의 X, 검정 방법~~ → X=10 확정, 검정 방법은 §6에 기본값으로 기재. 제안값 3개(개선폭 10%, wrong-branch 문턱 20°, α=0.01)는 이의 없으면 확정.
3. 장착 offset {0°, 45°}의 의미(편파가 아니라 장착 회전) 확인 → §1.
4. S0-1 base 정리 방식: merge(force 불필요, 권장) 또는 rebase+force-with-lease.
