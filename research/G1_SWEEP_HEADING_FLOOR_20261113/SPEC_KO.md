# G1-FLOOR-001 — 편파 sweep 절대 heading floor와 TB3 DR 대비 반해석 판정 (Step 1–2) 계산 사양서

- 작성 및 설계 변경일은 2026-11-13 KST다. 이 문서에는 사전 확정한 계산 규칙과 초판의 단일 case smoke를 기록한다.
- 이 문서는 계산 사양이다. 아래 smoke 수치는 단일 case의 파이프라인 확인용이며 결과로 인용하지 않는다.
- 실행자는 이 사양을 수정할 수 있다. 수정 시 §11 변경 기록에 날짜·이유·영향을 남기고, 사전등록 판정 규칙(§7)은 결과를 보기 전에만 바꾼다.

## 0. 질문과 범위

**질문:** 회전이 많은 주행에서 Dual-LP 편파 sweep으로 얻는 절대 heading이 TB3 실측 DR(보정 포함)보다 **명확한 우위**를 보이는가?

- Step 1: 기존 RT(7 case)의 station yaw sweep으로 **편파 sweep heading 오차의 분포, branch 실패율, 공간 상관**을 측정한다. LoS truth나 truth heading은 추정에 쓰지 않는다.
- Step 2는 Step 1의 sweep 비용 곡선 J(ψ)과 TB3 실측 DR 오차 과정을 **station 단위 반해석 필터**로 결합한다. heading 오차, 교차 station 수 N\*, 필터 일관성을 계산한다.
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
- R4는 anchor당 23개 station 중 10개가 19점·90°를 충족한다. 나머지 13개는 16점·71.4°다. 같은 lane에서 90° station이 연속한 구간은 최대 2개다.
- sweep 사이의 주행 pose는 약 0.04 m 간격이다. S1-4의 공간 상관 계산에 사용한다.

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

### S1-2 Sweep 절대 heading 비용 곡선

그룹마다 첫 pose의 절대 heading ψ₀에 대한 비용을 계산한다.

- 상대 yaw는 로봇이 믿는 sweep 상대각이다. `rel_bel = rel_true + k·|rel_true|`로 교란하며 k ∈ {0, 0.0085}다. 0.0085는 TB3 trackA의 ~2.05°/station ÷ ~240° 회전에 근거한다.
- 비용 함수는 J(ψ) = Σᵢ (s_obs,ᵢ − s_model(x₀, y₀, ψ + rel_bel,ᵢ))²다. case·station·seed·arm마다 **[−180°, 180°)의 0.25° 격자 1,440점**에 J 전체를 저장한다. Step 2는 이 곡선에서 현재 창 안의 최솟값을 고른다.
- **XY-P**는 x, y에 각각 독립 N(0, 0.1²) m 교란을 더하는 1차 위치 조건이다. **XY-T**는 참 station XY를 사용하는 민감도 조건이다.
- 1차 span은 **19점·90°**를 모두 충족하는 station으로 제한한다. R4의 71.4° station은 가운데 40° 민감도에 포함한다. 3점 probe(≈0/10/20°)는 비교 참조로 둔다.
- S1의 sweep 단독 오차 통계에는 독립 prior 중심 ψ_true + e_prior, e_prior ~ N(0, σ_p²), σ_p ∈ {2°, 5°}와 창 W ∈ {±180°, ±30°, ±10°}를 사용한다. 참값이 창 밖에 있는 비율을 따로 집계한다. 이 prior는 Step 2의 입력에서 제외한다.
- 행 단위로 err = wrap(ψ̂₀ − ψ₀,true), J_min, margin(20° 이상 떨어진 두 번째 최소값과의 상대 차), n_valid, 수평거리, θ_geo, 실제 span, window miss를 기록한다.

### S1-3 통계

case × arm(잡음, span, k, σ_p, W, XY)마다 다음을 보고한다.

- median |e|, RMS, P95, 평균 e(bias), bad5, bad10, **branch flip(|e|>45°)**
- 수평거리 구간 [0,5), [5,10), [10,∞) m별
- margin과 |e|의 관계: margin으로 실패를 미리 가를 수 있는지. 단 margin threshold는 train case에서만 정하고 leave-one-route-out으로 평가한다.
- case별로 19점·90°를 충족한 station 수와 parity 통과 여부를 보고한다.
- 불확도는 **물리 station 단위 cluster bootstrap**으로 계산한다(route×XY = 1 cluster, 1000회, seed 20261113). 같은 station의 seed 반복은 동일 클러스터에 둔다.

### S1-4 공간 상관

1. **Sweep 오차의 인접 상관:** 같은 lane에서 인접 station(약 2 m)의 e_k, e_{k+1}의 Pearson·Spearman 상관.
2. **주행 pose의 multipath s 잔차:** δs = s_full − s_LoS(N0)를 복도 방향 lag에 따라 자기상관으로 계산한다(0.04 m 해상도). **lag 0.45 m와 2 m의 값을 보고**하고, 1/e 상관길이 ℓ을 구한다.
3. **Step 2의 Markov 재사용 확률**은 case별 주행 pose δs 자기상관의 0.45 m lag 값으로 정한다. 확률에는 [0, 1] 범위로 제한한 값을 쓰고, 원래 추정값도 함께 보고한다.
4. **heading 등가 변환**은 δψ_eq = δs / (∂s/∂ψ)다. ∂s/∂ψ는 `s_model(with_jac=True)`의 세 번째 성분이며, |∂s/∂ψ|가 작은 pose를 제외하는 기준은 실행 전에 기록한다. 이 결과와 1/e 길이는 공간 상관의 보조 진단이다.

## 5. Step 2 반해석 판정

### 5.1 Station 과정 (간격 Δ = 0.45 m, station당 회전 Σ|dθ| ≈ 240°)

- 참 heading ψ_k. DR heading: ψ_DR,k = ψ_k + E_k, E_k = E_{k−1} + β + w_k.
- TB3 실측 값(§1.3에서 재계산해 고정):

| 파라미터 | 값 | 출처 |
|---|---|---|
| β, DR-uncal | 2.05°/station (TEACH 2.28, REPEAT 1.82의 평균) | teach/repeat |
| β_res, DR-cal | run당 한 번 뽑아 고정하는 N(0, (0.45°/station)²) | REPEAT−TEACH 평균 차를 기준으로 고정한 모형 |
| σ_w | 0.34°/station | 짝 차이 std 0.48 / √2 |
| E₀ | 1차는 0°, 별도 초기 정렬 분석은 N(0, (5°)²) | 지속 heading 성능과 초기 절대 heading 정렬 효과를 분리 |
| 정지 drift | 0.0005°/s (station당 정지 시간을 곱해서 더함) | Allan bag |

- G1은 DR-cal과 동일한 E₀, run별 β_res 및 wₖ 시퀀스를 공유한다. G1에만 편파 측정 갱신을 적용한다.
- 측정 zₖ는 §5.2에 따라 선택한 J(ψ)의 창 내 최소점이다. Gaussian AR(1)(σ_n, ρ)는 민감도 조건이다.

### 5.2 인과적 탐색창, 필터와 비교 arm

- G1은 Kalman filter에서 [E, β_res, (n의 AR 상태)]를 추정한다. nₖ = wrap(zₖ − ψₖ)이고, 측정 잔차 zₖ − ψ_DR,k는 −Eₖ + nₖ에 해당한다.
- 1차 창 중심은 **현재 sweep 직전 G1 필터가 예측한 heading** ψ̂⁻ₖ = ψ_DR,k − Ê⁻ₖ다. 반폭은 **max(3σ_prior, 10°)**이고 σ_prior = √P⁻_EE다. 원형 각도 거리로 창을 적용하며, 반폭이 180° 이상이면 전체 격자를 쓴다.
- 해당 station의 저장된 J 곡선에 이 창을 적용해 argmin을 다시 고른다. 창 안에 참 heading이 없는 **window miss**는 따로 집계하며 그 자체로 측정을 제외하지 않는다. DR heading을 창 중심으로 사용하는 조건은 민감도다.
- 1차는 Mahalanobis χ²₁ 0.99 gate를 적용한다. gate 없는 조건은 민감도다. S1의 margin 기반 기권은 sweep 단독 진단으로 보고한다.
- 비교 대상은 **DR-uncal**, **DR-cal**, **DR-nosweep**(§6)이다. N = 1…50에서 heading RMSE, P95, NEES, 95% 포함률과 window miss를 보고한다. 교차 station 수 N*는 1…N 누적 RMSE 비율의 CI 상한이 1 미만이 되는 첫 N이다.

### 5.3 0.45 m 격자의 J 곡선 상관 모델

한 run의 모든 J 곡선은 단일 anchor의 **같은 case**에서 가져온다. 90° 1차 분석에는 적격 station만 사용한다. 약 2 m 간격의 RT에서 얻은 세 모델을 0.45 m 간격의 직접 RT가 확보되기 전까지 사용한다.

| 모델 | 곡선 선택 | 용도 |
|---|---|---|
| **(a) 셀 재사용** | 같은 lane에서 각 TB3 station에 가장 가까운 RT station의 J를 사용한다. 같은 셀 안에서는 동일한 seed의 동일 곡선을 재사용한다. | 셀 내부에서 완전 재사용을 가정하는 비관적 조건 |
| **(b) 독립** | TB3 station마다 같은 case의 적격 RT station과 seed를 독립적으로 뽑는다. | 상관 0의 낙관적 조건 |
| **(c) Markov 재사용** | case별 ρ(0.45 m)의 확률로 직전 J를 재사용한다. 그 외에는 같은 lane에서 다음 적격 RT station으로 넘어가 새 곡선을 뽑는다. | S1-4의 주행 pose δs 상관을 이용한 조건 |

case별 적격 station 수와 모형별 run 수를 보고한다. 1차 비교에서 case별 run 수는 균등하게 배정한다. 적격 station 수의 차이는 각 case의 RF 표본 불확도에 반영한다.

### 5.4 반해석 확인

Gaussian white 측정에서는 steady-state 분산 P = (−q + √(q² + 4qr))/2 (q = σ_w², r = σ_n²)과 Monte Carlo가 일치해야 한다. 이 식은 β 보정 후를 가정한다. 불일치하면 구현 오류로 보고 중단한다.

## 6. 공정성 arm

sweep을 **편파 정보를 얻으려고 일부러** 하면, DR만 쓰는 로봇은 그 회전을 할 필요가 없다.

- **DR-nosweep:** 회전이 없는 직진만 하는 DR. E_k는 직진 drift κ_m ∈ {0, 0.1, 0.3}°/m × 0.45 m만큼만 증가한다.
- G1이 DR-cal만 이기고 DR-nosweep은 이기지 못하면, 주장은 **"임무상 회전이 원래 있는 경로"**로 한정한다. 이 경우 Step 3에 지그재그·ㄹ자 경로를 포함해야 한다.
- sweep 1회의 시간 비용(TB3 실측 station 체류 시간)을 함께 보고한다.

## 7. 사전등록 판정 규칙

**1차 조건**은 N30, mount 0의 6 case, full H, XY-P, 19점·90°, k = 0.0085, 인과적 필터 prior 창, χ²₁ 0.99 gate, E₀ = 0이다. E₀ ~ N(0, (5°)²)는 초기 절대 heading 정렬의 별도 분석이다. 아래 규칙은 새 S1 결과를 열기 전에 확정했다.

**짝지은 통계량.** 각 run의 station 1–17에서 G1과 DR-cal의 평균 제곱 heading 오차를 각각 구한다. run별 MSE를 합산해 R = √(Σ MSE_G1) / √(Σ MSE_DR-cal)을 계산한다. 각 비교 쌍은 같은 E₀, β_res, wₖ를 사용한다.

**95% 신뢰구간.** 바깥 bootstrap은 case 안에서 물리 station의 J 곡선 집합을 1,000회 재표집한다. 같은 station의 seed는 한 클러스터에 두고, 동일 route·XY를 공유하는 두 anchor의 클러스터는 짝지어 재표집한다. 각 바깥 표본마다 공통 난수를 사용하는 안쪽 경로 M = 200개를 실행하고 R을 구한다. 바깥 분포의 2.5·97.5 백분위를 사용한다.

**DR-cal 통과 기준.** (b)와 (c) **각각** R ≤ 0.8, 95% CI 상한 < 1.0, 평균 heading NEES ∈ [0.5, 2.0], 95% 구간 포함률 ≥ 0.88을 모두 만족해야 한다. NEES는 posterior heading 오차 제곱을 P_EE로 나눈 1자유도 값이다. 포함률은 |heading 오차| ≤ 1.96√P_EE인 비율이다. 두 지표를 station 1–17에서 집계한다.

| 판정 | 기준 |
|---|---|
| **PROCEED (Step 3 후보)** | (b), (c) 모두 DR-cal 기준을 통과하고, 두 모델 모두 station 1–17에서 DR-nosweep(κ_m = 0.1°/m)보다 낮은 heading RMSE를 얻는다. |
| **RESTRICT** | (b), (c) 모두 DR-cal 기준을 통과하고, 둘 중 하나라도 DR-nosweep보다 낮은 RMSE를 얻지 못한다. 주장을 임무상 회전이 원래 있는 경로로 한정한다. |
| **STOP** | (b), (c) 중 하나라도 DR-cal 기준에 미달한다. Step 3를 진행하지 않고 필요한 σ_n·ρ 조합을 보고한다. |

(b), (c)가 모두 DR-cal 기준을 통과하면 (a)의 R < 1.0일 때 **ROBUST**, R ≥ 1.0일 때 **CORRELATION_SENSITIVE**를 병기한다. 후자는 Step 3에서 0.45 m 간격 RT로 확인한다. §4 S1-1의 parity gate로 1차 case가 빠지면 통과 case의 분석에 표본 범위를 표시한다.

N = 17 끝점 오차, N*, 후기 오차, bad5, branch flip, 거리 구간별 결과와 window miss는 보조 지표로 보고한다.

## 8. 알려진 한계와 RT_MISSING

| 항목 | 현재 | 필요 | 처리 |
|---|---|---|---|
| sweep span | 90° | TB3 ±60°(120°) | 90° 결과는 120°의 근사로 표기 |
| station 간격 | 약 2 m | 0.45 m | §5.3의 (a)–(c)로 민감도를 비교하고 (c)의 재사용 확률에 S1-4를 사용 |
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
| `S1_J_<case>.npy`, `S1_J_INDEX_<case>.csv`, `S1_J_GRID.json` | 전체 J 곡선, station·seed·arm 인덱스, 0.25° 격자 |
| `S1_SUMMARY.csv` | S1-3 집계와 bootstrap CI |
| `S1_SPATIAL_CORR.csv` | S1-4: lag별 자기상관, ℓ, ρ(0.45 m) |
| `S2_PARAMS.json` | §5.1 TB3 값의 재계산 결과와 출처 SHA |
| `S2_CURVES.csv` | N별 RMSE/P95/NEES/포함률, arm별 |
| `S2_VERDICT.json` | §7 판정, (a)–(c)의 R, 바깥 bootstrap CI, NEES, 포함률 및 강건성 표기 |
| `MANIFEST.json` | 입력·코드 SHA, 명령, 시각, 설정 snapshot(AGENTS.md 규칙) |

## 10. 참조 구현과 smoke

- `step1_reference.py`는 초판 S1-0(hash gate), S1-1, S1-2의 참조 구현이다. 아래 smoke에 쓰인 스크립트의 범위는 독립 prior를 사용하는 일부 sweep 역산까지다.
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
| 2026-11-13 | 새 S1 결과를 열기 전에 확정한 설계 변경 세 가지를 반영. 인과적 탐색창과 전체 J 저장, (a)–(c) 재사용 모델과 90° 표본 제한, E₀ = 0의 짝지은 1–17 RMSE 비율과 station-cluster 바깥 bootstrap을 명시. | 사용자 결정 반영 |
