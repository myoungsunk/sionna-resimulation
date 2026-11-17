# G1-INT-001/M8 — 거리 기반 측정 불확실도의 필터 수준 검증 사양

| 항목 | 정의 |
|---|---|
| 질문 ID | G1-INT-001/M8-DIST-UNC |
| 역할·상태 | PROPOSER · **SPEC_PUBLISHED_NOT_EXECUTED**. 구현·입력 생성·재생·판정은 하지 않았다 |
| 브랜치 | `research/g1-sweep-heading-floor-spec-20261113` |
| 기준 커밋 | `50c12e95eeb13ac3ca317fec4339bd5c098b8282` (M7 결과 `5a33a982` 포함) |
| 범위 | mount **0°**, 앵커 B (10, 0, 2.65 m), robot z = 0.45 m, Full RF, R2/R4/R5, B0와 Q 일치 L2_GYRO_ARW, seed 10–29, 자체 gate |
| 봉인 | G-T2/G-V 미접근. S2′ STOP, Step 3 HOLD, DIAGNOSTIC_ONLY 유지 |
| 순서 | 사용자 지시 "순차적으로 검증 — 1. 필터에 넣었을 때 integrity와 정확도 먼저". 실측 이전·다른 장면 이전은 이 사양의 범위가 아니다 |

## 0. 질문

BLOCK_C 중앙선 station sweep에서만 학습한 거리 기반 측정 불확실도를 동결된 M7 필터에 넣으면, 무결성과 정확도가 M7 판정 규칙을 충족하는가? 그리고 기존 H3(GM-θ + KI, 경로 LORO 학습)와 비교해 어떤가?

측정 수준 근거(논의 정리 `G1_DISCUSSION_20261117_KO` §6–§7, Google Drive 폴더 `G1_TRACE_DIAG_KI_GM_20261117`)는 다음과 같다.

| 확인된 것 (측정 수준) | 이 사양에서 확인할 것 (필터 수준) |
|---|---|
| packet 95% 포함률 C: R2/R4/R5 = 0.97/0.94/0.96 | Pose95·Heading95·NEES3, seed별 판정 |
| 5 s 창 평균 포함률 (N_eff 보정) 0.90–0.97 | 상관 보정 연산자를 필터 안의 causal 형태로 바꿨을 때 |
| 참 자세의 a와 참 이동량 사용 | prior의 a(x⁻)와 odometry 이동량 사용 |
| — | 정확도 비용 (H2 대비), b_g 누설, R5 원거리 heading 이득 |

## 1. 측정 불확실도 모형 (sweep 학습, 동결)

### 1.1 동결 표

출처: `frozen/DIST_UNC_TABLE_SWEEP.csv` (SHA-256 `613619c01e4918aea7ca7cb938e2d8f04ed13fbb9721bbcd8ceb383e65db3c8c`). 이 표는 `source_scripts/dist_uncert.py`가 sweep 오차 파일 `station_sweep_errors.npz` (원본 SHA-256 `5cb9b19cfc7847bb681f850f8518598178fdcd91d3a841ae66ae56f3c97f2e8e`)에서 만든 것이다. 저장소에는 같은 내용을 무손실 CSV `frozen/STATION_SWEEP_ERRORS.csv` (`0e4cef57974a9a15619b71d15cb60c5d618d7e4bc674d0173271eb957b2739b9`)로 넣었다. `pandas.read_csv(..., float_precision='round_trip')`로 읽으면 npz의 float64 열과 bit 단위로 같다(LFS 업로드 권한 문제로 npz 대신 CSV를 쓴다). 아래 수치는 표의 원 정밀도이며, 실행 계약에는 CSV 해시로 묶는다.

| ρ bin (m) | σ_mp (A) | σ_θ (C) [rad] | σ_res (C) | ℓ (m) | ℓ_ψ |
|---|---|---|---|---|---|
| [0, 1.5) | 0.0106138953054432 | 0.0069549752791604 (0.398°) | 0.0045049420697471 | 0.5 | 30° |
| [1.5, 3) | 0.0332541292619756 | 0.0167131336061875 (0.958°) | 0.0237231928938399 | 0.5 | 30° |
| [3, 4.5) | 0.0618507588640638 | 0.0382808481542378 (2.193°) | 0.0307800566338958 | 1.3 | 30° |
| [4.5, 6) | 0.1261091777968691 | 0.0654972105504326 (3.753°) | 0.0866661794385366 | 1.3 | 30° |
| [6, 7.5) | 0.1996217356972229 | 0.0345794804785762 (1.981°) | 0.1937477921976039 | 0.3 | 12° |
| [7.5, 9.01) | 0.2957090214354804 | 0.0205595846302311 (1.178°) | 0.2943227748982208 | 0.3 | 12° |

- **조회 규칙:** 구간별 상수(piecewise constant)다. 측정 수준 평가(§7)와 같은 규칙이다. 보간은 하지 않는다.
- **범위 밖:** ρ ≥ 9.01 m는 마지막 bin 값을 쓰고 노출률을 보고한다. 경로 참 자세의 최대 ρ는 R2 8.85, R4 8.92, R5 8.82 m다.
- **ρ:** 앵커까지의 **수평** 거리다. M7 KI 조회와 같다.
- **ℓ, ℓ_ψ:** sweep 상관 분석에서 정했다. 6 m 이상의 0.3 m는 station 간격 0.45 m로 분해할 수 없어 가정한 값이다.
- σ_θ의 6 m 이상 두 값은 불안정한 적합값이다. 그래도 사후에 바꾸지 않는다.

### 1.2 출처와 독립성

- **sweep 원자료:** `D:\SLAM_bot\blockc_centerline_sweep_20261117`, 실행 `BLOCK_C_CENTERLINE_SWEEP_20261117T0956Z_OT9sPHzh`.
    - 40 station(x = 1.20 + 0.45i, y = 0) × 36 yaw
    - clean H, refraction = false
- **원본 해시:**

| 파일 | SHA-256 |
|---|---|
| `H/BLOCKC_B/H_full.npy` | `b32ede2ee9d3fa60c8eaf0c17b9773892a0ae4f4b094b627d5cf962fcafbf2c7` |
| `H/BLOCKC_B/H_LoS.npy` | `77eaaae4c5a1ed4848beb753384898c5243c0431da7ef45cfc6d63596c725471` |
| `poses/BLOCKC_B/STATIONS.json` | `ac26437fb5d1f2a4ae97486488cdb2510464f8d6c6ec89b9f050b64344b9ff75` |
| `poses/BLOCKC_B/SAMPLES.json` | `a9d6482d0ac3db3b3276db9dfc56a4527cd16a2080e65aa25cd4b8c71ff9c1ad` |
| `poses/BLOCKC_B/SCENE_ENTRY.json` | `1337e66ab399ef7094c0404337c0c57daf89cf440f8748586a08c5b4f3a0ac9a` |
| `G4.json` | `6284e3e20fd4bae6bac4b6bc44ecaae86ce05dae85e9db8529e60b7b315d23e0` |

- **관측 체인:** `source_scripts/station_sweep.py`는 MOUNT45_VALIDATION의 `frozen_model003_src`(O30 leading edge, s = (P0 − P1)/(P0 + P1), LP±45 bank)를 쓴다. a는 LoS 모델의 yaw 중심차분(±0.5°)으로 계산했고 단위는 rad⁻¹이다.
- **독립성의 범위:**
    - σ_θ, σ_res, σ_mp, ℓ, ℓ_ψ는 경로 자료를 쓰지 않았다. 이 모수들에 대해서는 R2/R4/R5가 holdout이다.
    - 단, **모형 형태(A/C, a² 항, 상관 보정)는 경로 포함률을 본 뒤 골랐다**(§7 dist_eval). 완전한 사전 등록 holdout이 아니다.
    - packet μ_MB, μ_BASE, range R_ref의 σ_b는 M7의 경로 LORO 값을 그대로 쓴다. 따라서 **편파 불확실도만 바뀐 부분 holdout**이다.
    - sweep은 y = 0 선만 덮는다. 경로의 |y|는 최대 0.52 m다.

## 2. Arm

M7 재생 코드([m7_replay.py](../m7_final_model_stage1/m7_replay.py))와 그 동결 입력·Q·gate·R_ref 정책을 그대로 쓴다. 바뀌는 것은 편파 채널의 추가 분산과, 그 상관을 넣는 방식뿐이다.

| arm | 정의 | 상태 | 역할 |
|---|---|---|---|
| H0, H1, H2, H3 (H4, H5, H5P) | M7 동결 arm | M7과 같음 | **재생하지 않는다.** M7 attempt_02 trace를 해시로 참조한다(§4 parity 통과 조건) |
| **H6** · M-cov | KI 형태. V_i = a_i²·σ_θ(ρ_i⁻)² + σ_res(ρ_i⁻)², 거리별 kernel | 4 | 주 후보 1 |
| **H7** · M-state | 정규화 GM 상태 η, 적재 a_i·σ_θ(ρ_i⁻). 잔여는 V_i = σ_res(ρ_i⁻)², 같은 kernel의 KI | 5 | 주 후보 2 |
| H6W | H6에서 causal 항만 0 (V_i만 백색으로 더함) | 4 | 상관 보정의 기여 |
| H8 | KI 형태. V_i = σ_mp(ρ_i⁻)² (안 A, 감도 없음), 같은 kernel | 4 | a² 항의 기여 |

H6과 H7은 따로 판정한다. 둘 중 점수가 좋은 쪽을 골라 "통과"라고 주장하지 않는다. 다중 arm이므로 통과한 arm은 **다음 확인 단계의 후보**일 뿐이다.

### 2.1 공통: 거리별 kernel

M7 KI는 누적 hazard `arc + yaw/rad(10°)`의 차로 kernel을 계산했다. 길이가 거리마다 다르면 이 방식을 쓸 수 없다. 그래서 arc와 yaw를 **따로** 누적해 저장한다.

`k_ij = exp(−(arc_i − arc_j)/ℓ(ρ_i⁻) − (yaw_i − yaw_j)/ℓ_ψ(ρ_i⁻))`

- arc, yaw는 M7과 같은 정의다. 자기 controls에서 `|ds|`와 `|wrap(gy − b_g,previous⁺·dt)|`를 누적한다.
- 길이는 **현재 packet i의 prior 거리**로 정한다(causal).
- 이력 규칙은 M7과 같다. 같은 arm에서 수용한 packet만, 직전 10 s, 최대 100개다. 탈락 packet도 arc와 yaw는 진행한다. 과거 V_j는 당시 조회값을 보존한다.

`R_eff,ss = R_ref,ss + V_i + 2·Σ_j √(V_i·V_j)·k_ij`

- R_ref는 M7 own 정책을 그대로 쓴다. packet R에 직전 posterior 거리로 조회한 σ_b²를 더한다.
- 거리 채널과 기존 교차항은 바꾸지 않는다.
- 이 causal 합은 §7 측정 수준 평가의 창 단위 N_eff와 **다른 연산자**다. 필터 수준에서 처음 시험하는 형태임을 보고서에 명시한다.

### 2.2 H6 · M-cov

- 상태 4개, M7 H5와 같은 경로를 쓴다.
- V_i는 prior의 부호 있는 a_i = H_sψ(x_nav⁻)로 계산한다. 쓰는 것은 a_i²이므로 부호는 들어가지 않는다.
- causal 합의 √(V_i·V_j)는 heading 성분의 부호(a_i·a_j)를 무시한다. 같은 부호 쌍에서는 정확하고, 반대 부호 쌍에서는 과보수다. 이 한계는 의도한 것이다.

### 2.3 H7 · M-state

σ_θ가 거리마다 다르므로, 단위 분산의 정규화 상태 η로 쓴다. 이렇게 하면 P가 정상 상태를 유지한다.

- 상태는 `[x, y, ψ, b_g, η]`. η는 무차원이고, η₀ = 0, P_ηη = 1, 초기 교차 공분산은 0이다.
- `α_i = exp(−|ds_i|/ℓ(ρ_i⁻) − turn_i/ℓ_ψ(ρ_i⁻))`, `η⁻ = α_i·η⁺`, `Q_ηη = 1 − α_i²`.
    - turn_i는 M7과 같은 정의다.
    - M7 H3는 α를 길이 1 m/10°로 nav 예측 전에 계산했다. H7은 길이를 prior 거리로 조회하므로 nav 예측 **뒤에** 계산한다.
- 교차 공분산은 F와 α로 전달한다. M7 H3와 같다.
- 편파 예측은 `h_s(x_nav⁻) + a_i·σ_θ(ρ_i⁻)·η⁻`, Jacobian의 η 열은 `(0, a_i·σ_θ(ρ_i⁻))`이다. a는 갱신 동안 고정한다(M6 조건부 선형화).
- 잔여 KI: V_i = σ_res(ρ_i⁻)², §2.1의 kernel과 causal 합.
- GM 몫 a²σ_θ²를 백색 R에 또 더하지 않는다.
- trace에는 `b_theta_equiv = σ_θ(ρ)·η`를 함께 남긴다. M7 H3와 비교하기 위해서다.

### 2.4 대조 arm

- **H6W:** V_i는 더하고, causal 합은 0으로 둔다. §7의 백색 가정에 해당한다.
- **H8:** 감도 a 없이 거리 표 σ_mp(ρ)만 쓴다. §7에서 R4를 과소, R2/R5를 과대 추정했던 형태다.

## 3. 조건·seed·gate·점수

전부 M7 계획([PLAN_M7](../PLAN_M7_FINAL_MODEL_STAGE1_KO.md) §2, §5)과 같다. 바꾸지 않는다.

- **조건:** B0와 Q 일치 L2_GYRO_ARW. 고정 mask 대조와 Q 불일치 stress는 이번에 하지 않는다.
- **입력:** M7 attempt_02의 online 입력을 해시로 재사용한다. 새 seed나 새 초기값은 만들지 않는다.
- **gate:** 자기 2차원 NIS ≤ 9.210340371976184.
- **점수:** M7 `m7_score.py`를 그대로 쓴다. bootstrap seed 20261115, 10 s 블록, 1,500회.
- **재생 수:** 2 조건 × 20 seed × 3 궤적 × 4 arm = **480회**. 기준 arm은 M7 trace를 재사용한다.

### 3.1 판정 (M7 규칙 그대로)

| 범위 | 무결성 | 정확도 (같은 조건·seed의 H2 대비) |
|---|---|---|
| 궤적별 | Pose95·Heading95·XY95 각각 ≥ 75%, 10 s 구간 하한 ≥ 60%, MIRROR_FAIL 0 | heading·XY RMSE 각각 +25% 이하 |
| seed별 pooled | Pose95·Heading95 ≥ 90%, 구간 하한 ≥ 80%, NEES3 ∈ [1.5, 6.0], MIRROR_FAIL 0 | 두 RMSE 각각 +10% 이하 |

- CONDITION_PASS: N_joint ≥ 18/20이고, 60개 궤적 실행 전체에서 거울해 0건.
- arm 통과(M8_PASS): B0와 L2 모두 CONDITION_PASS.
- I/A/J seed 목록과 Clopper–Pearson 구간, seed 10–14와 15–29의 분리 집계를 M7과 같은 표로 보고한다.

### 3.2 보조 판독 (판정에 넣지 않음)

R5 거울해는 초기 heading 오차에서 생기는 별도 문제로 보류했다. 그래서 다음을 **판정과 분리해** 보고한다.

- `N_joint_noMirrorTerm`: 위 규칙에서 MIRROR_FAIL 조건만 뺀 seed 수와, arm별 거울해 건수.
- 이 수치로 M8_PASS를 대체하거나 승격하지 않는다.

## 4. 진입 검사 (재생 전, 모두 통과해야 진행)

| # | 검사 | 기준 |
|---|---|---|
| P1 | **M7 재현:** 새 코드 경로로 H2, H3를 B0·L2의 seed 10, 15에서 다시 재생 | M7 attempt_02 trace와 x/P/prior/Pprior/H/K/R_eff/ν/S 1e−10 이내, mask 완전 일치 |
| P2 | **축약 parity** | 아래 네 경우 모두 1e−10 이내 |
| P3 | **단위와 감도 parity:** sweep 1,440 pose에서 필터 h_s, H_sψ를 계산해 `frozen/STATION_SWEEP_ERRORS.csv`의 s_los, a와 비교 | |a| ≥ 0.2인 pose에서 부호 불일치 0, 상대 오차 중앙값 ≤ 5%. 실패하면 STOP (관측 정의나 단위 불일치) |
| P4 | **kernel·causal 합:** 거리별 길이와 이력 규칙을 독립 직접 합산과 대조 | 1e−12 |
| P5 | **η 상태:** AR 정상 분산 1 유지, 교차 공분산 전달, Joseph 대칭·PSD | M7 구현 검사 2와 같은 항목 |
| P6 | **정보 차단:** 재생 함수가 evaluator, truth, sweep의 e_s를 받지 않는다. 받는 것은 표(CSV)뿐이다 | 코드 경로 검사 |

**P2 축약 parity의 네 경우.**

1. H6에 V = M7 q_s 표(H5와 같은 LORO fold), ℓ = 1 m, ℓ_ψ = 10°를 넣으면 M7 H5와 같다.
2. H7에 σ_θ = M7 fold 상수, σ_res² = M7 q_s 표, ℓ = 1 m, ℓ_ψ = 10°를 넣으면 M7 H3와 같다. 비교는 b_θ = σ_θ·η로 환산해서 한다.
3. H6, H7에서 모든 표가 0이면 H2와 같다.
4. H6W는 causal 항만 다르고 나머지는 H6와 같다.

이 parity들은 같은 수식을 다른 표로 돌리는 구현 검사다. 새 모형의 성능을 재현했다는 뜻이 아니다.

**P7 · 장(field) 일치 진단 (보고 전용).** 경로 pose 중 sweep station에서 5 cm·yaw 5° 이내인 것에 대해, 경로 e_s(CHAR-001)와 sweep e_s를 비교한다. 상관, 차이의 RMS, 쌍 수를 보고한다. 큰 불일치가 나와도 실행을 멈추지는 않는다. 다만 결과 해석에서 "같은 장에서 학습"이라는 전제를 약화한다.

## 5. 필수 보고표

| 표 | 내용 |
|---|---|
| 판정표 | 조건·arm별 N_integrity / N_accuracy / N_joint (/20, 구간), I/A 조합 seed 목록, 거울해 건수, M8_PASS |
| 궤적×arm 표 | H0–H3, H6, H7, H6W, H8의 RMSE, 종료 오차, 세 포함률, NEES3, H2 대비 비용 |
| 짝 비교 | H6 − H3, H7 − H3, H6 − H6W, H6 − H8, H7 − H6. seed별 J 변화(McNemar 형식 2×2)와 10 s 짝 차이 |
| 거리 bin별 편파 채널 | ν_s/√S_ss의 95% 포함률과 평균 제곱, R_eff,ss/R_ref,ss 팽창 분포, 표 bin 노출률 |
| R5 원거리 기전 | 3–6 m, 6–10 m의 prior σ_ψ, \|K_ψ,s\|, R_ss, y RMS (H2/H3/H4/H6/H7) |
| R4 b_g 누설 | 고감도 구간 b_g 누적 흔들림(°/s), b_g RMSE와 종료 오차. M-cov 위험(§8.5)의 직접 확인 |
| R2 취약 창 | 80–120 / 120–160 s의 heading RMS, σ_ψ, 팽창 |
| H7 상태 | b_theta_equiv와 M7 H3 b_θ의 비교, P_ηη/1 (학습 정도) |

## 6. 결과별 해석

| 결과 | 허용 판단 |
|---|---|
| H6 또는 H7이 B0·L2 모두 통과 | 경로 비학습 불확실도로 M7 규칙을 충족한 후보. 확인은 새 seed나 다른 장면에서 별도로 |
| 통과는 없지만 보조 판독에서 거울해 외 기준 충족 | 불확실도 모형은 거울해 밖에서 충분하다는 증거. 거울해 문제의 분리를 지지하되 통과로 부르지 않음 |
| H6/H7이 H3와 비슷 | 경로 LORO 모수를 sweep 학습 모수로 대체 가능하다는 근거 (부분 holdout 한계 포함) |
| H6 ≈ H6W | 필터 수준에서 상관 보정의 기여가 작음. §7 창 단위 결과와 다르면 그대로 보고 |
| H8 ≈ H6 | 필터 수준에서 a² 항의 기여가 작음 |
| H6 통과, H7 실패 (또는 반대) | 상태 표현과 공분산 표현의 차이. b_g 누설 표와 R5 이득 표로 원인을 설명하되 사후 조정 없음 |
| 모두 실패 | 측정 수준 calibration이 필터 수준 무결성으로 이어지지 않음. 원인 표를 근거로 다음 범위 결정 |

어느 결과든 다음은 주장하지 않는다.

- 실측 이전
- 다른 장면·앵커로의 일반화
- 거울해 해결
- 완전한 사전 등록 holdout

20 seed는 같은 RF 실현에서 센서와 초기값만 바꾼 반복이다.

## 7. 실행 순서

| 단계 | 할 일 | 진입 조건 |
|---|---|---|
| 1 | 입력 계약 동결: 이 사양, 동결 표 CSV, sweep 해시, M7 입력·trace 해시, 코드 | 출처 일치 |
| 2 | H6/H7/H6W/H8 구현 (M7 재생 확장) | — |
| 3 | P1–P6 검사, P7 보고 | P1–P6 통과 |
| 4 | B0·L2 × 20 seed × 3 궤적 × 4 arm 재생 | 누락 없음. 실패 seed를 빼지 않음 |
| 5 | M7 점수 코드로 채점, §5 표 작성, 독립 재집계 | 기대 480 cell 완전성 |
| 6 | 판정과 주장 범위 정리 | 실행 성공·검토·채택을 구분 |

- 산출물 위치: `dist_unc_m8/attempt_01/`. RUN_CONTRACT.json, CHECKS.json, trace NPZ, SCORES.json, DECISION.json, REPORT_KO.md, SHA256SUMS.
- 기존 M7 계약과 trace는 덮어쓰지 않는다.
- 모수 grid, 배수 탐색, seed 점수를 보고 표나 길이를 바꾸는 일은 하지 않는다. 바꿔야 하면 새 사양 개정으로 처리한다.

## 8. 첨부

| 파일 | 내용 |
|---|---|
| `frozen/DIST_UNC_TABLE_SWEEP.csv` | 동결 표. 열은 lo, hi, sA = σ_mp, st = σ_θ [rad], sr = σ_res, str_/srr = 중앙값 기반 강건판(이번 사양에서 사용하지 않음) |
| `frozen/STATION_SWEEP_ERRORS.csv` | sweep pose별 x, y, yaw, station ID(st), d, e_s(es), e_s_same(esame), Δtap(dtap), a [rad⁻¹], s_los, s_full. 원본 npz의 무손실 변환 |
| `source_scripts/station_sweep.py` | H → e_s, a 계산 (로컬 경로 기록 포함) |
| `source_scripts/dist_uncert.py` | 표 학습, 상관 분석 |
| `source_scripts/dist_eval.py` | 측정 수준 경로 평가 (§7) |
| `source_scripts/station_decomp.py` | heading 등가 / 잔여 분해 (§6) |
