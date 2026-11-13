# G1-MODEL-001 — 편파 관측·오차 모델 보강 후 Step 1–2 재판정 계산 사양서 (사양서 2)

- 작성: 2026-11-13 KST. 상태: **SPEC_READY / NOT_RUN / scientific_PASS=false**
- 선행: G1-FLOOR-001(`SPEC_KO.md`, `PREREG_KO.md`), 결과 `RUN_20261113T052908Z`(커밋 `9924f1b`), 진단 `DIAG_PARITY_20261113T055513Z`, `DIAG_MARKOV_20261113`.
- 원칙: Goal 1은 **multipath 완화 없이 편파 정보를 모델에 정직하게 넣어 정확도와 integrity를 확보하는 것**이다. 이 사양은 관측을 고르거나 고치지 않는다. 관측 모델과 오차 모델, 추정기 구조만 바꾼다. 관측을 감지·보정하는 방법은 Goal 2로 남긴다.
- 판정 규칙(§7)은 결과를 보기 전에만 바꾼다. 변경은 §11에 기록한다.

## 0. G1-FLOOR-001이 멈춘 이유 (이 사양이 겨냥하는 결함)

| ID | 관찰 (G1-FLOOR-001) | 해석 | 이 사양의 대응 |
|---|---|---|---|
| D1 | Markov 95% 포함률 85.6% < 88% → STOP. 이탈 491개 중 418개가 음의 오차 쪽, 추가 이탈의 92%가 R4 두 case. gate 해제 86.4%, 순서 교란 86.4%, **같은 분산·상관의 Gaussian AR로 교체하면 93.9%** | 측정 오차가 **평균 0의 Gaussian이 아니다**(비대칭 꼬리, case별 편향). 필터 구조가 아니라 **측정 오차 모델의 오지정** | M-ERR (§3) |
| D2 | R2_aB_m0 parity p90 0.0209 > 0.02. 원인: LUT 기준 거리 10 m 고정. 이산 first-path tap의 상대 위치가 거리에 따라 바뀌어 s가 거리에 의존. 거리를 맞추면 p90 0.0013 | **관측 모델에 거리(sub-tap) 축이 없다.** 6 case 모두 p90 0.014–0.021의 체계 오차를 갖고 있었다 | M-OBS (§2) |
| D3 | G1 누적 RMSE 2.3–4.0° vs DR-nosweep(κ=0.1°/m) 0.46° | sweep을 heading 획득만을 위해 하면 회전 없는 DR에 진다 | 주장 축 분리 (§6) |
| D4 | 짝 차이 SD: endpoint 정의 0.687° → σ_w 0.486°. 사양 값 0.34°는 재현되지 않음 | 측정 시점 정의와 DR 증분 정의가 어긋남 | §4 측정 시점 고정 |
| D5 | σ_β가 판정을 지배(Fable: σ_β 0.45/0.32/0에서 R 0.39–0.43/0.49–0.53/0.89–0.91) | n=2로 정한 baseline knob | §4 σ_β 민감도와 σ_β\* |
| D6 | 0.45 m δs 상관 −0.14–0.52, 1/e 길이 0.08–0.40 m | 0.45 m에서 상관은 짧지만 0이 아님 | 기존 (b)/(c) 유지 |
| D7 | 초기 정렬 축(E₀~N(0,5²)): 비율 0.446, 포함률 88.4% | A1 축은 현재 모델로도 경계선 통과 | §6 A1 별도 판정 |

## 1. 입력

G1-FLOOR-001 §1과 같다(BLOCK_C @ `047cce2`, LUT·관측 소스 @ `f9a7691`, TB3 @ `3018bb5`/`14f8a76`/`1809fa7`). 추가 입력:

- FFD bank: `LP_plus45_bank.npz`, `LP_minus45_bank.npz`(저장소 루트, Git LFS). SHA는 A23 `FFD_RESTORE_MANIFEST`의 값과 대조한다(`DIAG_PARITY`에서 일치 확인됨).
- G1-FLOOR-001의 J 곡선은 **재사용하지 않는다**. 관측 모델이 바뀌므로 S1을 다시 계산한다. 단 M0 arm(아래)은 기존 J와 비트 단위로 같아야 한다(회귀 검사).

## 2. M-OBS: 거리 인지 관측 모델

### 2.1 모델

s는 sub-tap 위치에 의존한다. 이산 first-path tap 간격 Δ_tap ≈ 0.149 m(관측 체인 기준)에서, 거리 d의 분수 위치 f = frac(d/Δ_tap)가 s를 바꾼다.

| Arm | 관측 모델 s_model | 용도 |
|---|---|---|
| **M0** | 기존 LUT(10 m 고정) | 회귀 기준. G1-FLOOR-001 재현 |
| **M1-T** | FFD bank 직접 계산 `los_h(..., dist_m=d_true)` → `observe` | 상한(참 거리 사용, 비인과) |
| **M1-R** | 같은 직접 계산, d = 측정 range 기반 거리. 거리 불확도를 적분: s̄ = E_d[s(d)], d ~ N(d̂, σ_d²), 5점 Gauss–Hermite. 분산 Var_d[s(d)]를 측정 분산에 더한다 | **1차** |
| M2 | 4차원 LUT s[θ, φ_tx, φ_rx, f], f 16 bin(주기 경계). M1-R과 같은 적분 | 온라인 필터용 근사. M1-R과의 parity만 검사 |

- d̂: 같은 station에서 측정된 range의 평균에서 range offset(기존 `range_offset_m = −0.5316`)을 보정한 값. σ_d는 range 잡음 0.05 m/√n_range와 offset 불확도를 합친다. **참 거리는 M1-T에서만 쓴다.**
- 직접 계산은 `hs_lut.build_lut`의 φ_rx 벡터화를 재사용한다. station마다 LoS 방향은 하나이고 yaw 후보 1,440개는 φ_rx만 바뀌므로 비용이 작다.

### 2.2 Gate

| Gate | 조건 | 실패 시 |
|---|---|---|
| G-OBS-0 | M0 J 곡선이 G1-FLOOR-001과 동일(최대 절대차 < 1e-12) | 구현 오류로 중단 |
| G-OBS-1 | M1-T: noise-free LoS H vs 모델, **p90 \|Δs\| ≤ 0.005, median ≤ 0.002**, 7 case 모두 | 해당 case 중단 |
| G-OBS-2 | M2 vs M1-R: p90 ≤ 0.002 | M2 사용 금지(M1-R만) |
| G-OBS-3 | 7 case 모두 G-OBS-1 통과(R2_aB_m0 포함) | `INCOMPLETE_PARITY_GATE` |

### 2.3 M-OBS가 D1에 미치는 영향 검사 (사전 고정)

case별 평균 sweep 오차(bias)와 음의 꼬리 비율을 M0와 M1-R에서 비교한다. **편향의 일부가 거리 모델 오차에서 왔는지**를 판정한다: case별 |bias| 감소가 6 case 중 5개 이상이고 평균 감소가 30% 이상이면 "D1의 일부는 관측 모델 결함"으로 기록한다.

## 3. M-ERR: 정직한 측정 오차 모델

G1-FLOOR-001의 측정 분산은 평가 route를 제외한 J 곡선의 ±10° 정렬 2차 모멘트(17–21 deg², σ ≈ 4.1–4.6°)였고, 분포 형태는 평균 0 Gaussian이었다. 다음 arm으로 바꾼다. 모든 파라미터는 **route 단위 홀드아웃(LORO: R2/R4/R5)**으로 정하며, 평가 route의 오차를 쓰지 않는다.

| Arm | 측정 우도 | 파라미터 | 필터 갱신 |
|---|---|---|---|
| E0 | N(0, σ²) | σ² LORO 2차 모멘트 | 기존 KF (회귀 기준) |
| **E1** | **Laplace 국소 분산**: R = 2σ_s² / J''(ψ̂). σ_s²는 sweep 잔차 분산(관측에서 직접), J''는 J 곡선의 최소점 곡률 | 스케일 계수 c_L 하나를 LORO로 보정 (R ← c_L·R) | KF, station마다 다른 R |
| **E2** | 2성분 혼합: (1−π)·N(0, R_E1) + π·N(μ_o, σ_o²) | π, μ_o, σ_o LORO | Gaussian-sum 2성분, 갱신 후 moment matching |
| E3 | Student-t(ν), scale R_E1 | ν LORO | IRLS 가중 KF |
| E4 | E1 + margin 의존 스케일: R ← R·g(margin), g는 단조 증가 계단 3단 | g LORO | KF |

- **E1이 핵심이다.** 편파 관측 자체가 주는 정보량(J 곡선의 날카로움)으로 station마다 불확도를 정한다. 라벨 없이 관측과 모델만으로 계산되므로 Goal 1의 원칙("편파 정보를 모델에 정직하게 넣는다")에 해당한다.
- E2 μ_o는 비대칭 꼬리(D1)를 표현한다. μ_o를 0으로 고정한 민감도도 보고한다.
- E4의 margin 사용은 관측 품질을 **분산으로만** 반영한다(기각 없음). 기각·보정은 Goal 2의 영역이므로 쓰지 않는다. 경계 사례로 표기한다.
- **case별 평균 편향을 학습해 빼는 방법은 Goal 2(보정)로 분류해 이 사양에서 제외한다.**

## 4. 추정기와 DR 과정

### 4.1 측정 시점과 DR 정의 (D4)

- z_k는 **station k의 sweep 시작 직전 base 자세의 heading**에 대한 측정이다. sweep 상대각은 base 기준이다.
- DR 증분 E_k − E_{k−1}은 **base(k−1) → base(k)**로 정의한다. 이 정의로 TEACH/REPEAT에서 재계산한 σ_w(endpoint) = **0.486°를 1차**로 쓰고, 0.34°는 민감도로 둔다.
- β_DR-uncal은 같은 정의로 재계산한다(TEACH 2.278, REPEAT 1.813 → 2.046°/station).

### 4.2 σ_β (D5)

- 1차 σ_β = 0.45°/station(run 1회 보정). 민감도 {0, 0.32}.
- **σ_β\***(G1/DR-cal 비율 = 0.8이 되는 σ_β)를 각 J 모델·E arm마다 보고한다.
- run 안 β 변화(Fable 진단: 짝 차이 앞 10개 −0.27°, 뒤 7개 −0.72°): β를 run 내 random walk(σ_βw = 0.037°/station, 짝 차이 기울기에서)로 두는 민감도를 추가한다.

### 4.3 위치 오차 지속성

- XY-P(station마다 독립 N(0, 0.1²) m)를 1차에서 **XY-RW**로 바꾼다. 위치 오차 δp_k = δp_{k−1} + η_k, η ~ N(0, 0.03²) m/station, δp_0 ~ N(0, 0.1²). 위치가 heading으로 새는 효과를 station 간에 지속시킨다.
- XY-P는 민감도로 유지한다.

### 4.4 Branch 다봉성

- 창 안 J 곡선의 국소 최소를 최대 3개까지 가설로 둔다. 가중치는 exp(−(J_i − J_min)/(2σ_s²))로 하고, 가중치 0.05 미만은 버린다.
- 갱신은 Gaussian-sum이며, station마다 moment matching으로 다시 하나의 Gaussian으로 합친다.
- 단일 최소(G1-FLOOR-001 방식)는 민감도로 둔다.
- 탐색창 중심과 폭은 PREREG(필터 예측 ψ_DR − Ê⁻, 반폭 min(180°, max(3√P⁻, 10°)))를 유지한다. window miss 최장 연속 길이를 지표로 추가한다.

## 5. 계산 절차

1. **S1′**: 6 mount-0 case + R2_aA_m0 m45(민감도). M0, M1-T, M1-R(필요 시 M2)로 J 곡선과 σ_s², J''(ψ̂), margin을 저장한다. 나머지 S1 조건(잡음 N30/N10/N0, seed 0–19, span 19점·90°/40°, k {0, 0.0085})은 G1-FLOOR-001 PREREG와 같다.
2. **S1′-diag**: §2.3 편향 검사, E1 분산의 보정도(표준화 오차 분포, LORO).
3. **S2′**: PREREG의 Markov/독립/셀 3 모델 × {M0, M1-R} × {E0, E1, E2, E3, E4}. DR과 bootstrap 난수 흐름은 PREREG와 같다.

## 6. 주장 축과 판정 대상

| 축 | 판정 대상 | 이 사양에서의 판정 |
|---|---|---|
| A1 초기 절대 heading | E₀~N(0, 5²), Markov | 포함률 ≥ 0.88, NEES [0.5, 2.0], station 1–5 내 \|e\| < 5° 비율 ≥ 0.95 |
| A2 sweep 운용 heading(DR-cal 대비) | E₀ = 0, §7 1차 | §7 |
| A2′ DR-nosweep 대비 | κ_m ∈ {0, 0.1, 0.3}°/m | 판정 없이 손익분기 κ_m\*만 보고. **D3 때문에 sweep 경로로 이 축을 주장하지 않는다.** passive 경로는 새 RT(G1-RT-TB3-001)에서 판정 |
| A3 절대 XY | — | 이 사양 범위 밖(6-state 폐루프 필요) |
| A4 장시간 유계 | N = 1…50 곡선 | 보고만 |

## 7. 사전등록 판정 규칙

**1차 조건:** N30, mount 0의 6 case(7번째 case 포함을 위해 G-OBS-3 필요), **M1-R**, **E1**, XY-RW, 19점·90°, k = 0.0085, E₀ = 0, σ_w = 0.486°, σ_β = 0.45°, Gaussian-sum branch, gate χ²₁(0.99).

| 판정 | 조건 (모델 (b) 독립과 (c) Markov 각각에서) |
|---|---|
| **INTEGRITY_PASS** | 평균 NEES ∈ [0.5, 2.0], 95% 포함률 ≥ 0.88(1–17 누적), station 17 끝점 포함률 ≥ 0.80 |
| **ACCURACY_PASS** | INTEGRITY_PASS이고, RMSE 비율 ≤ 0.8, bootstrap CI 상한 < 1.0, **G1 절대 누적 RMSE ≤ 3.0°**, 3 route 모두 비율 < 1.0, gate 기각률 ≤ 20% |
| **PROCEED_A2** | (b)와 (c) 모두 ACCURACY_PASS. (a) 셀 비율 < 1.0이면 ROBUST, 아니면 CORRELATION_SENSITIVE |
| **INTEGRITY_ONLY** | (b)와 (c) 모두 INTEGRITY_PASS이지만 ACCURACY_PASS가 아님 → "편파를 정직하게 쓰지만 정확도 이득은 σ_β에 의존"으로 기록, σ_β\* 보고 |
| **STOP** | (b) 또는 (c)에서 INTEGRITY_PASS 실패 |

- E1이 STOP이고 E2 또는 E3가 INTEGRITY_PASS이면, 그 arm을 다음 단계의 1차 오차 모델 **후보**로 기록한다. 이 사양 안에서 1차 판정을 바꾸지는 않는다.
- M0 × E0는 G1-FLOOR-001의 수치를 재현해야 한다(회귀). 재현되지 않으면 전체를 무효로 한다.

## 8. 한계

- RT station 간격 2 m, sweep 90°, 복도 형상 1개, R4의 90° station 10개라는 G1-FLOOR-001의 한계가 그대로 남는다. **최종 판정은 새 RT(G1-RT-TB3-001)에서 반복한다.** 이 사양의 결과는 모델 선택용이다.
- E1의 σ_s²와 J''는 multipath가 있을 때 편향될 수 있다(잘못된 최소에서 날카로운 곡률). c_L LORO 보정과 E2/E3 비교로 검사한다.
- M1-R은 range를 쓰므로 range의 multipath 편향이 s 모델로 들어간다. M1-T와의 차이로 크기를 보고한다.

## 9. 출력

`RUN2_<id>/` 아래:

| 파일 | 내용 |
|---|---|
| `S1P_OBS_PARITY.json` | G-OBS-0…3 |
| `S1P_J_<case>_<obs>.npy`, `S1P_J_INDEX_<case>_<obs>.csv` | J 곡선, σ_s², J'', margin |
| `S1P_BIAS_CHECK.json` | §2.3 |
| `S1P_ERR_MODEL_LORO.json` | E0–E4 파라미터와 LORO 보정도 |
| `S2P_CURVES.csv`, `S2P_BOOTSTRAP.npz` | N별 지표, arm별 |
| `S2P_SIGMA_BETA_STAR.csv` | σ_β\* |
| `S2P_VERDICT.json` | §7 |
| `MANIFEST.json` | 입력·코드 SHA, 명령, 시각, 설정 snapshot |

## 10. 다음 단계와의 연결

- PROCEED_A2 또는 INTEGRITY_ONLY → 선택된 (M-OBS, M-ERR) 조합을 G1-RT-TB3-001 데이터에서 동일 규칙으로 재판정하고, passive 경로 arm을 추가한다.
- STOP → 오차 모델 후보(E2/E3)와 실패 case를 정리하고 G1-RT-TB3-001에서 원인(형상 vs 모델)을 분리한다.
- 어느 경우든 TB3 측정 두 가지를 병행한다: 다른 날 REPEAT ≥ 3회(σ_β), 왕복 직진(κ_m).

## 11. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-13 | 초판. G1-FLOOR-001 STOP 원인(D1–D7) 반영 | Claude (proposer 초안) |
