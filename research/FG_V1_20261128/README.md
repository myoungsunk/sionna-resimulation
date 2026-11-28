# FG-V1 — single-anchor 편파 heading factor graph 1차 테스트 (2026-11-28)

M7 H2 EKF와 같은 모델로 factor graph(FG)를 구성하고, b_g를 제외한 3-state 구조에서 lag=∞ causal FG를 처음 실행한 결과다. R5 초반 이탈의 원인 진단(s 관측 오차의 시간 상관)까지 포함한다.

- 기준 브랜치: `research/g1-sweep-heading-floor-spec-20261113` @ `ceff863f`
- 입력: `research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1/attempt_02` (M7 online packets), `gm_theta_m6/inputs/*_evaluator.npz` (truth)
- 관측 모델: FFD (`continuation_ks/replay_inputs/R45_sources` + `LP_plus45/minus45_bank.npz`)
- 실행 기록: `results/MANIFEST.json` (입력·출력 sha256, 명령, 소요 시간, 환경)

## 1. 기본 구조 (v1a, e_s 없음)

| 요소 | 정의 |
|---|---|
| 변수 | X_k = (x, y, ψ), world-frame Vector3, UWB packet마다 1개. gyro bias 상태 없음 |
| prior | X_0 ~ N(x0[:3], P0[:3,:3]) (M7 packet의 x0, P0) |
| odom factor | X_k − f(X_k−1; ds, gy, dt), f = M7 `core.transition` (sinc_half 원호 적분). Q = G·diag(2e-5·\|ds\|, (N°)²·dt)·Gᵀ + 1e-10·I (횡방향 잡음 0이라 rank 2 → 정규화) |
| 관측 factor | [r, s] 2D 하나: h(X_k) + μ_MB − z, R = EKF Reff (packet R + diag(0, σ_b²), σ_b = 0.005). EKF의 2D NIS gate(9.21) accept mask를 그대로 사용 |
| h | FFD 원본 또는 surrogate (아래) |
| solver | iSAM2, QR factorization (Cholesky는 ill-posed 예외), relinearizeThreshold 1e-3, relinearizeSkip 1. causal 출력 = 매 step 최신 node 추정값과 marginal covariance |

b_g 제외 근거: 평가 조건 N0/N2(L0)는 실제 bias 0이고 heading 오차의 주원인은 gyro ARW. M7의 b_g prior(σ = 0.1°/s)는 R2 길이(196 s)에서 heading 1σ ≈ 19.6°에 해당해, ARW(N0 0.21°, N2 0.84°)보다 heading 불확도를 지배하고 e_s를 흡수하는 통로가 된다. 비교 기준 EKF도 3-state로 맞췄다.

조건: B0 (gyro ARW 0.015°/√s), L2_GYRO_ARW (0.060°/√s). seed 10. 경로 R2 (979 packet), R4 (742), R5 (1415). anchor (10.0, 0.0, 2.65).

## 2. 등가성·모델 확인

| 항목 | 결과 |
|---|---|
| EKF 재구현 (`code/ekf3.py`, nstate=4) vs 저장소 M7 H2 trace | max\|dx\| 1.4e-14, max\|dP\| 3.1e-17, gate mask 동일 (B0, L2) |
| surrogate (x 0.025 m × y 0.05 m × ψ 4°, h·H trilinear, 280만 점, FFD 2코어 약 31분) | s 오차 p95 0.004–0.009 (σ_s 중앙값 0.108의 0.08배 이하), 최대 0.059 (고립점). range 오차 ≤ 0.2 mm. 호출 0.09 ms (FFD 1.67 ms) |
| EKF3: surrogate vs FFD (B0/R2) | 위치 1.8 cm, yaw 0.21° 이내, gate mask 동일 |
| G0 gate: FG(lag=1, GN 1회) vs EKF3 (B0/R2, surrogate) | 위치 4.4e-5 m, yaw 1.1e-5 rad, P 1.5e-6 |
| R 비대각 | 125,440 packet 전부 0. joint [r, s] factor와 1D 두 개로 분리한 FG가 완전히 동일 (차이 0.0). 분리 시 1.6배 느림, gate 규칙은 별도 필요 |

## 3. lag=∞ causal FG vs EKF3 (surrogate, seed 10)

| cell | 시간 | 위치 RMSE EKF / FG (m) | yaw RMSE EKF / FG (°) | ANEES(3-dof) EKF / FG |
|---|---|---|---|---|
| B0 R2 | 57 s | 0.082 / 0.084 | 0.69 / 0.71 | 4.44 / 4.36 |
| B0 R4 | 27 s | 0.032 / 0.032 | 0.75 / 0.76 | 7.91 / 8.14 |
| B0 R5 | 96 s | 0.039 / 0.112 | 0.62 / 1.08 | 3.57 / 4.49 |
| L2 R2 | 60 s | 0.091 / 0.093 | 1.09 / 1.10 | 6.76 / 6.81 |
| L2 R4 | 24 s | 0.049 / 0.047 | 0.92 / 0.92 | 10.11 / 10.23 |
| L2 R5 | 89 s | 0.065 / 0.129 | 0.88 / 1.28 | 5.14 / 6.12 |

시간은 `run_all.py` 재실행 기준(2코어 중 1코어). 이전 구성(b_g 포함 4-state, FFD)에서는 R2 1회 약 13분으로 추정됐다(legacy, 미재실행).

## 4. R5 초반 이탈 진단 (B0/seed10/R5, graph k = 0–156)

R5의 FG 오차 증가는 k ≈ 120–200 (x ≈ 5–7 m) 구간에만 있고(최대 0.78 m), k > 200에서는 EKF와 같다.

| 진단 | k=156 위치 오차 | 해석 |
|---|---|---|
| batch LM을 참값 / EKF / iSAM2 해에서 시작 | 0.78 / 0.78 / 0.78 m (cost 26.78) | solver·국소해 문제 아님 |
| odom 잡음을 참값 잔차 수준으로 | 0.78 m | odom 아님 (참값 odom 잔차 / 모델 σ = 1.01 along, 0.98 yaw) |
| s만 white synthetic | 0.013 m | s 관측이 원인 |
| range만 white synthetic | 0.379 m | |
| range·s 모두 white synthetic | 0.081 m | 모델 일치 시 정상 |
| R_ss ×5 / ×20 | 0.080 / 0.026 m | s 과신 |
| FFD 원본 (surrogate 대신) | 0.248 m | surrogate가 증폭 |

- 참값에서 계산한 s 잔차의 lag-1 자기상관: 0.68 (k 0–100), 0.90 (100–160), 0.96 (160–260), 0.74 (260–500). 구간 whitened 평균 +0.20, −0.26, −0.07, +0.16.
- 이탈 형태: 구간 전체의 거의 일정한 heading offset (surrogate −6.9°, FFD −1.6°). anchor 축 rigid 회전으로 설명되는 몫은 일부 (위치 RMSE 0.46 → 0.33 m).
- range와 odom은 anchor 축 rigid 회전에 불변 (range 민감도 1.8e-11). 이 방향은 s만 결정. white 가정 정보량: rigid 회전 σ 1.6°, heading σ 1.3°.
- surrogate − FFD의 s 차이는 참값 궤적에서 whitened 평균 0.008–0.024이지만 MAP는 0.25 → 0.78 m로 이동 → MAP가 h의 작은 계통 차이에 민감.
- FFD 원본 lag=∞ causal (k 0–260): FG 최대 0.241 m (k=161), 같은 시점 EKF 0.117 m.
- 미해결: 같은 white 가정의 EKF가 이 구간에서 덜 벗어나는 이유.

## 5. 재현

```bash
cd research/FG_V1_20261128/code
./setup.sh                      # native bundle + LFS 입력(125 파일)을 media.githubusercontent.com에서 받음
python3 gen_grid.py 0 200       # FFD grid, x-index 구간별 (0-200, 200-400, 400-600, 600-761), 약 31분 / 2코어
python3 run_all.py              # 전 단계 재실행 + results/MANIFEST.json
```

setup.sh가 받은 LFS 파일은 git에서 수정됨으로 보인다(LFS filter 미설정 시). 커밋하지 말 것.

| 파일 | 내용 |
|---|---|
| `code/common.py` | 경로(저장소 상대), packet·truth 로더, FFD h |
| `code/ekf3.py` | M7 H2 EKF 재구현 (nstate 3/4) |
| `code/fg3.py` | 3-state FG: `g0()` 등가성 gate, `run_isam()` lag=∞ causal, `split=True` |
| `code/surrogate.py`, `code/gen_grid.py` | FFD 격자와 trilinear surrogate |
| `code/run_lag_inf.py` | cell 하나: EKF3 vs FG lag=∞ |
| `code/diag_r5*.py` | R5 이탈 진단 6종 |
| `code/surrogate_check.py`, `code/r_offdiag_check.py`, `code/parity_ekf3.py`, `code/equivalence_check.py` | 검증 |
| `code/cir_es_rank_check.py` | station sweep에서 CIR 특징의 \|e_s\| 순위 예측력 (RT 라벨) |
| `code/run_all.py` | 전 단계 재실행과 MANIFEST 기록 |
| `code/legacy/` | 4-state(b_g 포함)·FFD 시기의 스크립트. 작성 당시 절대 경로 그대로 (fixed-lag W=10: 132 ms/step, W=50: 568 ms/step) |
| `results/` | 위 표의 JSON 원본과 MANIFEST |
| `FABLE_DISCUSSION_PROMPT.md` | 시간 상관 적용 방식·검증 arm 논의용 프롬프트 |
