# G1-FLOOR-001 — 편파 sweep 절대 heading floor와 TB3 DR 대비 반해석 판정 (Step 1–2) 계산 사양서

- 작성: 2026-11-13 KST. 상태: **SPEC_READY / SMOKE_ONE_CASE_DONE / FULL_STEP1_NOT_RUN / STEP2_NOT_RUN / scientific_PASS=false**
- 이 문서는 계산 사양이다. 아래 smoke 수치는 단일 case의 파이프라인 확인용이며 결과로 인용하지 않는다.
- 실행자는 이 사양을 수정할 수 있다. 수정 시 §11 변경 기록에 날짜·이유·영향을 남기고, 사전등록 판정 규칙(§7)은 결과를 보기 전에만 바꾼다.

## 0. 질문과 범위

**질문:** 회전이 많은 주행에서 Dual-LP 편파 sweep으로 얻는 절대 heading이 TB3 실측 DR(보정 포함)보다 **명확한 우위**를 보이는가?

- Step 1: 기존 RT(7 case)의 station yaw sweep으로 **편파 sweep heading 오차의 분포, branch 실패율, 공간 상관**을 측정한다. LoS truth나 truth heading은 추정에 쓰지 않는다.
- Step 2: Step 1 오차 모델과 TB3 실측 DR 오차 과정을 결합한 **station 단위 반해석 필터**로 heading 오차-station 곡선, 교차 station 수 N\*, integrity를 계산한다.
- **범위 밖:** 전체 6-state EKF, 새 RT 생성(Step 3), 실측 RF, multipath 완화 모델(Goal 2).
- **주장 경계:** 7 case는 **하나의 복도 형상**이다. 결과는 `GENERALIZATION_NOT_PROVEN`. 같은 H를 seed만 바꿔 반복한 것은 독립 multipath 표본이 아니다.

## 1. 입력 고정

### 1.1 RT 채널 — `codex/post-a23-evidence-20261010` @ `047cce2acb244ec2d7badc563345ccdd1f48613f`

루트 `P = results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449`

| 파일 | 내용 |
|---|---|
| `P/BLOCK_C/CASES.json` | 7 case: poses, anchor_xyz, robot_z=0.45, mount_deg, material, **`H_sha256`=LoS H, `input_H_sha256`=full H** |
| `P/BLOCK_C/FULL_RF/H_<case>.npy` | full multipath H, complex128, (Npose, 257, rx(+45,−45), tx(+45,−45)) |
| `P/BLOCK_C/H_LoS_<case>.npy` | matched LoS-only H, 같은 shape |
| `P/BLOCK_C/<case>/SAMPLES.json` | pose_id, x, y, yaw_body_deg (H의 pose 축 순서와 동일) |
| `P/freqs_hz.npy` | 257 bins, 6.2504–6.7496 GHz. SHA256 `fe0bcfeb…a1169f8` |

Case: `R2_aA_m0, R2_aB_m0, R2_aA_m45, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0`. Anchor A=(4,0,2.65), B=(10,0,2.65) m.
**1차 집합은 mount 0의 6 case**이다(TB3 tag mount 0° 고정). R2_aA_m45는 민감도로만 보고한다.

### 1.2 LUT와 관측 체인 — `codex/a23-results-20261010` @ `f9a7691c14a0c1750790a998de7a91c5d9eb918b`

루트 `Q = results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010`

| 파일 | SHA256 | 비고 |
|---|---|---|
| `Q/INPUTS/hs_lut_2deg.npy` | `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079` | s[θ(0–90°, 2°), φ_tx(−180–178°, 2°), φ_rx]; LoS-only, TX +45 column |
| `Q/INPUTS/hs_lut_meta.json` | 기록 | axis 정의 |
| `Q/retrieved/source/src/qclean_uwb/drivesim/observation.py` | `95079dc0…dbab` | `observe()`: Hann, first path, s=(P1−P2)/(P1+P2) |
| `Q/retrieved/source/src/qclean_uwb/drivesim/hs_lut.py` | `24f1007e…d8a6` | `HsLut`, `s_model(lut, anchor, z, x, y, yaw_rad, mount)` |
| `…/drivesim/pattern_apply.py`, `…/scenarios/corridor.py` | `ab991a70…69e8`, `38c42cb1…354e` | import 의존 |

### 1.3 TB3 DR 오차 과정 — `main`

| 데이터 | 커밋 | 사용처 |
|---|---|---|
| `data/raw/tb3_motion_20261004_20261111/trackA/teach/teach.json` | `3018bb5` | station당 odom yaw 증분 |
| `data/raw/tb3_motion_20261004_20261111/trackA/repeat_20261004_141119/repeat.json` | `14f8a76` | 같은 station의 REPEAT 증분 |
| `data/raw/tb3_imu_allan_20261113T022519Z/` | `1809fa7` | 정지 bias, rate white noise |
| `data/raw/tb3_motion_20261004_20261111/corridor_5p07m/` | `3018bb5` | 직진 drift 시나리오 κ_m |

### 1.4 추출

```sh
git fetch --depth 1 origin codex/post-a23-evidence-20261010 codex/a23-results-20261010
B=origin/codex/post-a23-evidence-20261010; P=results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449
git archive $B $P/BLOCK_C/CASES.json $P/BLOCK_C/FULL_RF $P/BLOCK_C/H_LoS_*.npy $P/freqs_hz.npy \
    $(for c in R2_aA_m0 R2_aB_m0 R2_aA_m45 R4_aA_m0 R4_aB_m0 R5_aA_m0 R5_aB_m0; do echo $P/BLOCK_C/$c/SAMPLES.json; done) | tar -x -C WORK
git archive origin/codex/a23-results-20261010 results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/INPUTS \
    results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source/src | tar -x -C WORK
```

모두 일반 Git 파일이며 LFS가 필요 없다. 추출 후 §1.1–1.2의 SHA를 대조하고, 불일치하면 중단한다.

## 2. 데이터 구조 (R2_aA_m0에서 확인, 나머지는 S1-0에서 확인)

- 1,303 pose, 고유 XY 925개. **같은 XY 그룹(≥3 pose) 21개 = station yaw sweep.**
- 그룹당 19 yaw, 5° 간격, span 90°. pose 순서는 nominal에서 한쪽으로 10개, 반대쪽으로 9개(두 반쪽 sweep).
- Station 간격은 복도 방향 약 2 m, lane 2개(y ≈ +0.4, −0.5 m). **TB3 trackA의 0.45 m 간격과 ±60°(120°) span은 이 데이터에 없다.** → §8 RT_MISSING.
- sweep 사이의 주행 pose는 약 0.04 m 간격이다. §4.4의 공간 상관 계산에 사용한다.

## 3. 관측과 잡음

- `s = observe(H, freqs, noise_var, rng, tx=0)["s"]`. 미검출 샘플은 NaN이며 그대로 둔다.
- 잡음 arm: noise-free(N0), SNR 30 dB(N30), 10 dB(N10). `noise_var = observation.noise_var_from_snr(snr)`.
- 잡음 seed는 {0..19}이다. full H와 LoS H는 같은 seed 흐름에서 각각 독립 잡음을 받는다.
- **1차 보고는 N30**이다. N0는 multipath만의 효과, N10은 하한 민감도로 둔다.

## 4. Step 1 계산

### S1-0 Inventory와 hash gate

case별로 SHA를 대조하고 다음을 기록한다: H shape, 그룹 수, 그룹 크기, span, yaw 간격, 그룹 XY, anchor 수평거리. CASES.json의 `H_sha256`은 **LoS H**, `input_H_sha256`은 **full H**와 비교한다.

### S1-1 Parity (중단 조건)

noise-free LoS H의 s와 `s_model(LUT)`을 전 pose에서 비교한다. **median |Δs| ≤ 0.005이고 p90 ≤ 0.02**이면 통과, 아니면 해당 case를 중단한다.
(smoke R2_aA_m0: 0.0035 / 0.018, 통과)

### S1-2 Sweep 절대 heading 역산 (non-oracle)

그룹마다 첫 pose의 절대 heading ψ0를 추정한다.

- 상대 yaw rel_i: 로봇이 믿는 sweep 상대각이다. 시뮬레이션은 참 상대각을 주므로, 이를 IMU 오차로 교란한다.
  - `rel_bel = rel_true + k·|rel_true|`, k ∈ {0, 0.0085}. 0.0085는 TB3 trackA의 ~2.05°/station ÷ ~240° 회전에서 나온 값이다.
- 비용 함수: J(ψ) = Σ_i (s_obs,i − s_model(x0, y0, ψ + rel_bel,i))². 0.25° 격자로 탐색한다.
- Prior 중심 = ψ_true + e_prior, e_prior ~ N(0, σ_p²), σ_p ∈ {2°, 5°}. 탐색창 W ∈ {±180°(제약 없음), ±30°, ±10°}.
  - ±10° 창에서는 |e_prior|가 크면 참값이 창 밖에 놓일 수 있다. 이 사례는 따로 집계한다.
- 위치 arm: **XY-T**는 참 station XY(1차, 상한), **XY-P**는 XY에 N(0, 0.1²) m 교란(현실적인 위치 prior)이다.
- Span arm: 전체 90°(19점)와 가운데 40°(약 9점). 기존 3점 probe(≈0/10/20°)는 비교 참조로만 둔다.
- 기록: err = wrap(ψ̂0 − ψ0_true), J_min, margin(20° 이상 떨어진 두 번째 최소값과의 상대 차), n_valid, 수평거리, θ_geo.

### S1-3 통계

case × arm(잡음, span, k, σ_p, W, XY)마다 다음을 보고한다.

- median |e|, RMS, P95, 평균 e(bias), bad5, bad10, **branch flip(|e|>45°)**
- 수평거리 구간 [0,5), [5,10), [10,∞) m별
- margin과 |e|의 관계: margin으로 실패를 미리 가를 수 있는지. 단 margin threshold는 train case에서만 정하고 leave-one-route-out으로 평가한다.
- 불확도: **물리 station 단위 cluster bootstrap**(route×XY = 1 cluster, 1000회, seed 20261113)

### S1-4 공간 상관

1. **Sweep 오차의 인접 상관:** 같은 lane에서 인접 station(약 2 m)의 e_k, e_{k+1}의 Pearson·Spearman 상관.
2. **주행 pose의 multipath s 잔차:** δs = s_full − s_LoS(N0)를 복도 방향 lag에 따라 자기상관으로 계산한다(0.04 m 해상도). **lag 0.45 m와 2 m의 값을 보고**하고, 1/e 상관길이 ℓ을 구한다.
3. **heading 등가 변환:** δψ_eq = δs / (∂s/∂ψ). ∂s/∂ψ는 `s_model(with_jac=True)`의 세 번째 성분이며, |∂s/∂ψ|가 작은 pose는 제외한다(기준은 실행 전에 기록). 이 값은 Step 2 AR(1)의 ρ(0.45 m) = exp(−0.45/ℓ) 근거로 쓴다.

## 5. Step 2 반해석 판정

### 5.1 Station 과정 (간격 Δ = 0.45 m, station당 회전 Σ|dθ| ≈ 240°)

- 참 heading ψ_k. DR heading: ψ_DR,k = ψ_k + E_k, E_k = E_{k−1} + β + w_k.
- TB3 실측 값(§1.3에서 재계산해 고정):

| 파라미터 | 값 | 출처 |
|---|---|---|
| β, DR-uncal | 2.05°/station (TEACH 2.28, REPEAT 1.82의 평균) | teach/repeat |
| β, DR-cal | N(0, 0.45²) (한 run으로 보정한 뒤 남는 run 간 차이) | REPEAT−TEACH 평균 차 |
| σ_w | 0.34°/station | 짝 차이 std 0.48 / √2 |
| E_0 | {0°, N(0, 5²)} | 초기 heading을 아는 경우 / 모르는 경우 |
| 정지 drift | 0.0005°/s (station당 정지 시간을 곱해서 더함) | Allan bag |

- 측정: z_k = ψ_k + n_k. n_k는 Step 1의 **경험 오차를 그대로 resampling**한다(1차). 같은 lane에서 연속 station 블록 단위 bootstrap으로 상관을 보존한다. 2차 arm은 Gaussian AR(1)(σ_n, ρ)이다.
- 공간 간격 불일치: RT station 간격은 2 m이고 TB3는 0.45 m이다. ρ(0.45 m)는 S1-4-2/3에서 얻고, 2 m 인접 상관(S1-4-1)과의 일관성을 확인한다.

### 5.2 필터와 비교 arm

- G1: 상태 [E, β, (n의 AR 상태)]의 Kalman filter. 측정 잔차는 z − ψ_DR = −E + n이다.
  - outlier gate: Mahalanobis 기준 χ²₁ 0.99. 1차는 gate 사용, 민감도로 gate 없음.
  - S1에서 margin 기반 기권(abstain) 규칙이 train에서 정해졌다면 그 규칙을 그대로 쓴다.
- 비교 대상: **DR-uncal**, **DR-cal**(β 보정됨), 그리고 **DR-nosweep**(공정성 arm, §6).
- 출력: N = 1…50에서 heading RMSE와 P95, 교차 station 수 N\*(G1 RMSE < DR RMSE가 CI상 성립하는 첫 N), steady-state 오차, **NEES 평균과 95% 포함률**.

### 5.3 반해석 확인

Gaussian white 측정에서는 steady-state 분산 P = (−q + √(q² + 4qr))/2 (q = σ_w², r = σ_n²)과 Monte Carlo가 일치해야 한다. 이 식은 β 보정 후를 가정한다. 불일치하면 구현 오류로 보고 중단한다.

## 6. 공정성 arm

sweep을 **편파 정보를 얻으려고 일부러** 하면, DR만 쓰는 로봇은 그 회전을 할 필요가 없다.

- **DR-nosweep:** 회전이 없는 직진만 하는 DR. E_k는 직진 drift κ_m ∈ {0, 0.1, 0.3}°/m × 0.45 m만큼만 증가한다.
- G1이 DR-cal만 이기고 DR-nosweep은 이기지 못하면, 주장은 **"임무상 회전이 원래 있는 경로"**로 한정한다. 이 경우 Step 3에 지그재그·ㄹ자 경로를 포함해야 한다.
- sweep 1회의 시간 비용(TB3 실측 station 체류 시간)을 함께 보고한다.

## 7. 사전등록 판정 규칙 (결과를 보기 전에만 변경)

1차 조건: N30, mount 0의 6 case, XY-P, σ_p = 5°, W = ±30°, span 90°, k = 0.0085, gate 사용.

| 판정 | 기준 |
|---|---|
| **PROCEED (Step 3로)** | N = 17에서 G1 heading RMSE ≤ 0.8 × DR-cal RMSE이고, station bootstrap 95% CI 상한 < 1.0 × DR-cal. 그리고 G1의 NEES 평균이 [0.5, 2.0] 범위, 95% 포함률 ≥ 0.88 |
| **RESTRICT** | 위를 만족하지만 DR-nosweep(κ_m = 0.1)은 이기지 못함 → 주장을 회전이 원래 있는 경로로 한정 |
| **STOP** | PROCEED 기준 미달. Step 3를 실행하지 않는다. "필요한 floor 역산"(PROCEED에 필요한 σ_n·ρ 조합)만 보고 |

보조 지표(판정에는 쓰지 않음): N\*, steady-state, bad5, branch flip, 거리 구간별 결과.

## 8. 알려진 한계와 RT_MISSING

| 항목 | 현재 | 필요 | 처리 |
|---|---|---|---|
| sweep span | 90° | TB3 ±60°(120°) | 90° 결과는 120°의 근사로 표기 |
| station 간격 | 약 2 m | 0.45 m | S1-4의 주행 pose 상관으로 보간 |
| 형상 | 복도 1개 | TB3 복도, 두 번째 형상 | `GENERALIZATION_NOT_PROVEN` |
| sweep 중 회전 오차 | 시뮬레이션은 정확 | IMU 교란 | k arm으로 근사 |
| 탭 정의 | B tap(현재 observe) | — | K1/K2·FP 재선택 금지(기존 연구 고정 조건) |
| 정지 vs 이동 중 관측 | 정지 sweep | — | 이동 중 s는 재사용하지 않는다 |

## 9. 출력

`research/G1_SWEEP_HEADING_FLOOR_20261113/RUN_<id>/` 아래에 생성한다.

| 파일 | 내용 |
|---|---|
| `S1_INVENTORY.json` | S1-0 |
| `S1_PARITY.json` | S1-1, case별 통과 여부 |
| `S1_SWEEP_ERRORS_<case>.csv` | S1-2 행 단위 기록 |
| `S1_SUMMARY.csv` | S1-3 집계와 bootstrap CI |
| `S1_SPATIAL_CORR.csv` | S1-4: lag별 자기상관, ℓ, ρ(0.45 m) |
| `S2_PARAMS.json` | §5.1 TB3 값의 재계산 결과와 출처 SHA |
| `S2_CURVES.csv` | N별 RMSE/P95/NEES/포함률, arm별 |
| `S2_VERDICT.json` | §7 판정과 근거 수치 |
| `MANIFEST.json` | 입력·코드 SHA, 명령, 시각, 설정 snapshot(AGENTS.md 규칙) |

## 10. 참조 구현과 smoke

- `step1_reference.py`: S1-0(hash gate), S1-1, S1-2의 참조 구현이다. **S1-3, S1-4, Step 2는 구현되어 있지 않다.** XY-P arm과 N10은 추가가 필요하다.
- Smoke(`SMOKE_R2_aA_m0/`): R2_aA_m0, N30, seed {0, 1}, XY-T, 21 station. **파이프라인 확인용이며 결과가 아니다.**

| 채널 | 조건 | median \|e\| | RMS | bad5 | flip |
|---|---|---|---|---|---|
| LoS | span 90, W ±30 | 0.1–0.2° | 0.2–0.3° | 0 | 0 |
| full | span 90, W ±30 | 2.7–2.9° | 8.6–10.2° | 0.33–0.36 | 0 |
| full | span 90, W ±10 | 2.7–3.0° | 4.6–5.3° | 0.33–0.36 | 0 |
| full | span 90, W ±180 | 2.9–3.2° | 54° | 0.36–0.40 | 0.14 |

**해석 경고(smoke 1 case 기준):**
- full multipath의 sweep 오차 RMS는 4.6–10°로, 이전 논의에서 가정한 floor(0.37–1.56°)보다 훨씬 크다. 이전 floor는 주행 중 EKF의 heading RMSE였고, 이 값은 sweep 1회 단독 추정이라 정의가 다르다. Step 2가 이 차이를 판정한다.
- 제약 없는 탐색(±180°)에서는 14%가 branch flip을 보인다. prior 창이 없으면 절대 heading 추정이 성립하지 않는다.

## 11. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-13 | 초판. smoke 1 case 실행 | Claude (proposer 초안) |
