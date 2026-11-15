# G1-MODEL-003 v3 — 새 RT(G1-RT-TB3)에서 packet 단위 EKF의 Goal 1 검증 사양서 (개정)

- 작성: 2026-11-15 KST. 상태: **SPEC_DRAFT_V3 / NOT_RUN / 연구자 승인 대기**
- 갈래: **새 RT 갈래.** 기존 데이터 갈래는 [SPEC_A_BLOCKC_KO.md](SPEC_A_BLOCKC_KO.md)(G1-DIAG-003)다.
- 대체 관계:
  - 이 문서는 [SPEC_B_NEW_RT_KO.md](SPEC_B_NEW_RT_KO.md)(이하 v2)를 대체한다. v2 본문과 v2 실행 산출물(`MODEL_003/`, `research/g1-model003-s0-20261115` @ `1e59fc0`, S3 `DEV_FAIL`)은 수정하지 않고 보존한다.
  - v2에서 바뀐 항목과 그 계기는 [AMENDMENTS_V3_KO.md](AMENDMENTS_V3_KO.md)에 기록한다. v3의 변경은 모두 **v2 G-T1 결과를 본 뒤의 변경**이다.
  - G-T2·G-V 봉인, pose 집합, 경로 export, G0–G9, packet timeline(S0)은 v2와 같다.
- 근거: v2 S3 DEV_FAIL 감사(2026-11-15, 연구자·Claude·Fable).

## 0. 이 개정의 목적

**목적: v2 DEV_FAIL의 원인이 "관측 오차 모형의 결함"인지 "편파 구조의 한계"인지를 G-T1에서 가른 뒤, 통과한 구조만 봉인 데이터에서 한 번 판정한다.**

v2 S3(B0, 30 dB, G-T1 LOAO)에서 확인된 것:

| 관측 | 값 | v3의 대응 |
|---|---|---|
| range만 쓰는 R4가 이미 실패 | heading 포함률 38.3%, NEES 134, XY RMSE 1.04 m (DR 0.69 m) | range 모형을 먼저 고치고, 통과해야 s arm으로 간다 (S3-R) |
| σ_b(ρ) 절점 붕괴 | 1.5 m 절점 7/7, 6 m 절점 4/7이 사실상 0 | C2 적합 규칙 교체 (§3 S2) |
| range 잔차의 거리 의존 평균 | +0.002 / +0.026 / +0.099 / +0.189 m (1.5–3 / 3–6 / 6–10 / > 10 m, ABC) | 거리 함수 보정 + consider 잔여 (§2.3) |
| ranging 규칙 선택이 상수 offset에 지배됨 | 전 후보 RMSE ≈ \|bias\| (−0.49 ~ −0.73 m) | LoS offset 제거 후 잔차로 재선택 (S1′) |
| 같은 XY의 반복 packet | TEACH 2,637 packet 중 약 82%가 18개 station의 XY (이동 7.65 m ÷ 0.08 m/s에서 계산한 추정) | 유색 상태가 Δd = 0에서 φ = 1이 되도록 명시 (§2.2) |
| s 꼬리 | Student-t ν 1.30–1.62 (거리 정규화 전) | 정규화 후 재추정, 꼬리 arm 추가 (§2.4) |
| J-CI 수치 실패 | M1-R 5점 거리 노드 ≤ 0 | 노드 절단 규칙 (§2.5) |
| B0 비열등 판정의 검정력 부족 | J4 비율 0.999, CI [0.79, 1.30] | 판정 순서와 무해성 기준 개정 (§4) |

| 단계 | 답하는 질문 |
|---|---|
| S0 | (재사용) 회귀와 timeline |
| S1′ | 상수 offset을 뺀 뒤에도 30% 규칙이 거리 오차 최소인가 |
| S2′ | 개정한 적합 규칙으로 s·range 오차의 크기·상관·평균·꼬리는 어떤가 |
| S2-F | 지속 성분의 heading 바닥이 DR보다 작은 경로·수준은 어디인가 |
| S3-R | range만으로 integrity를 통과하는 range 모형이 있는가 |
| S3-J | 그 range 모형 위에서 integrity를 통과하는 편파 구조가 있는가 |
| S4 | 고른 구조가 처음 보는 6조합에서 통과하는가 |

**개발 반복 한도.** v3는 G-T1에서의 마지막 개발 반복이다. v3가 DEV_FAIL이면 "이 RT·mount 0·Goal 1 범위에서 구조 불가"로 결론내고, 이후 작업은 새 질문 ID로 연다. G-T1 LOAO 수치는 v2·v3 모두 주장 근거가 아니다. 주장 근거는 S4뿐이다.

## 0.1 연구 질문과 결정 사항

**질문.** mount 0 tag에서, packet 단위 재귀 EKF가 dual-LP 편파를 multipath 완화 없이 정직하게 모델링했을 때 DR 대비 integrity와 정확도를 확보할 수 있는가?

| 결정 | 내용 | v2 대비 |
|---|---|---|
| 추정기 | packet 단위 재귀 EKF. sweep 중 각 packet이 개별 관측 | 동일 |
| mount | 0°만 | 동일 |
| integrity | 공분산 일관성(NEES, 명목 95% 포함률) | 동일 |
| integrity 판정 방식 | B: pooled + case 심각 실패, P-C 포함 | 동일. 순서와 항목은 §4에서 개정 |
| ranging 첫 경로 규칙 | 거리 오차 기준으로 선택 | 선택 지표 개정 (S1′) |
| range 평균 보정 | 허용 (ranging 완화) | **신규 적용** |
| 꼬리 모형 | 허용 (불확도 표현). §0.2의 기준을 충족하는 형태만 | **신규 arm** |
| DR 시나리오 | B0/L0/L1/L2 주 축, TB3 점 | 동일 |

### 0.2 Goal 1 경계

| 허용 | 제외 (Goal 2) |
|---|---|
| ranging 완화(첫 경로 규칙, range 평균 보정) | s 평균 편향 보정(μ_s 학습·차감) |
| 불확도 표현: 상관 상태, Schmidt/consider, 분산 스케일, 거리 의존 분산, 꼬리 | 반사 경로를 명시한 편파 관측 모델 |
| DR 오차 모델링(b_g, k_r) | 오염 감지 기반 s 가중·기각. heading/s 오차로 규칙·모수 선택 |

**꼬리 모형이 Goal 1에 속하기 위한 조건(모두 충족).**

1. 가중의 입력은 그 packet의 혁신과 사전 고정한 우도뿐이다. CIR 형태, tap 불일치, 경로 예측 같은 오염 지표를 쓰지 않는다.
2. 우도 모수는 G-T1에서 한 번 추정해 고정한다. site·시간에 따른 온라인 적응을 하지 않는다.
3. 모든 s packet에 같은 규칙을 적용한다. 분류 후 다른 모델을 쓰지 않는다.
4. 가중이 줄어든 만큼 공분산 축소도 줄어든다(§2.4).

## 1. 데이터

| 항목 | 값 |
|---|---|
| 생산 | `evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa`. 11 조합, 61,992 pose |
| 특성화·개발 | G-T1 × A/B/C (P-A, P-A′, P-B, P-C, P-D, P-E, P-F) |
| 확인 (봉인) | G-T2 × A/B/C, G-V × A/B/C. 봉인 SHA는 v2 S1 진입 기록과 같아야 한다 |
| G6 | G-T2 × B/C의 유한 반사면 매칭 실패 4건은 `G6_REGENERATION_KO.md` 절차로 **S4 전에** 처리한다. 처리 전에는 해당 2 조합을 S4에서 쓸 수 없다 |
| RF | 257 bin, 6.2504–6.7496 GHz, TX +45°, RX ±45°, mount 0, SNR 30 dB(민감도 20 dB) |
| 운동 | 직진 0.08 m/s, 회전 0.3 rad/s, RF 주기 0.2 s |
| packet timeline | v2 S0 동결본을 그대로 쓴다(165,933 packet, `timeline_sha256 = 4d591aa6…3d4cfd`). 다시 만들지 않는다 |

같은 pose의 반복 packet은 같은 clean H를 공유한다. 독립 공간 표본으로 세지 않는다(§3 S2′의 솎기 규칙, §4.1의 site 정의).

## 2. 추정기와 arm

### 2.1 상태와 관측

| 상태 | 쓰는 곳 |
|---|---|
| 4-state [x, y, ψ, b_g] | B0/L0/L1/L2 |
| 5-state [x, y, ψ, b_g, k_r] | TB3 점 |
| c_r, c_s (유색 잡음) | R-MC, J-C, J-CS |
| Schmidt: K_r, K_s (consider), b_site (site 기억) | R-MC, +K, J-CS |

관측은 packet마다 [range, s]다. LUT/M1-R 관측함수와 초기 P0는 v2와 같다. range gate는 χ²₁ 99%다. s gate는 §2.4를 따른다.

### 2.2 유색 잡음 전이 (range·s 공통)

- φ = exp(−Δd/ℓ_d − |Δψ|/ℓ_ψ). Δd, Δψ는 직전 packet과의 **참 운동이 아니라 필터 입력(odometry·gyro)으로 계산한** 이동거리와 회전량이다.
- Δd = 0이고 Δψ = 0이면 φ = 1이며 과정잡음은 0이다. 정지 중 반복 packet은 유색 상태를 새로 뽑지 않는다.
- 정상 분산은 §3 S2′의 거리별 분산이다. 과정잡음은 σ²(1 − φ²)다.

### 2.3 range 모형

1. **상수 offset o.** S1′에서 정한다(noise-free LoS 기준). 모든 arm에 적용한다.
2. **거리 의존 평균 b_r(r̃).** r̃ = r_meas − o. S2′ C6의 거리 구간 평균을 지원 절점에서 구간 선형으로 잇는다. 관측에서 뺀다. 지원 구간 밖은 끝 절점 값으로 고정하고 그 packet 수를 집계한다.
3. **분산.** 백색 arm은 통합 분산, 유색 arm은 거리별 분산(§3 S2′ C2).
4. **consider 잔여 K_r.** b_r 보정 뒤 남는 anchor 간 차이의 분산. 추정하지 않고 교차공분산만 유지한다.

b_r를 상태로 두지 않는 이유: 단일 anchor에서 range 편향은 LoS 방향 위치와 구분되지 않는다.

| arm | 내용 | 역할 |
|---|---|---|
| R4 | offset o + 백색 통합 분산. b_r 없음 | v2 기준선 재현 |
| R-M | R4 + b_r(r̃) | 평균 보정의 효과 |
| R-MC | R-M + c_r 유색 상태 + K_r | 상관·잔여 편향까지 표현 |

### 2.4 편파 arm

S3-R에서 고른 range 모형 위에 얹는다.

| arm | 내용 | 역할 |
|---|---|---|
| J4 | 백색 통합 분산 | 원래 접근, 기준선 |
| J-V | 거리 의존 분산 σ_b(ρ)² | 분산 크기만 |
| J-C | J-V + c_s 유색 상태 | 이동·sweep·정지 상관 |
| J-CS | J-C + Schmidt site 기억(C4의 재방문 상관) | 재방문 상관 |
| J-CI | covariance-intersection형 갱신(가중 0.5/0.5) | integrity 하한 대조 |
| +K | consider bias K_s(5 m 창 평균 성분의 분산) | 지속 평균 성분 |
| +T | s 우도를 Student-t로 교체 | 꼬리 |

선택 후보(12개): J-V, J-C, J-CS, J-CI와 각 +K(8개), J-C+T, J-CS+T, J-C+K+T, J-CS+K+T(4개). J4와 J4+K는 기준선이다.

**+T 갱신 규칙(사전 고정).**

- ν는 S2′ C7 값이며 하한은 3이다.
- packet마다 3회 반복한다: w = min(1, (ν + 1) / (ν + ν_s² / S_s)). ν_s는 s 혁신, S_s는 현재 R_s로 계산한 s 혁신 분산이다. R_s ← R_s,기준 / w로 바꿔 다시 계산한다.
- 마지막 R_s로 Joseph form 갱신을 한다. 가중이 작을수록 P가 덜 줄어든다.
- +T arm에서는 s의 χ² gate를 쓰지 않는다. range gate는 유지한다.
- w < 0.1인 packet을 "유효 기각"으로 집계한다.

### 2.5 M1-R 거리 노드 절단

- 5점 Gauss–Hermite 노드 d_i = d̂ + σ_d ξ_i (최대 |ξ| = 2.857).
- d_floor = 0.5 m. 노드가 d_floor보다 작아지면 σ_clip = (d̂ − d_floor) / 2.857로 줄여 적분한다.
- 줄인 만큼의 분산은 선형항으로 R에 더한다: g_d² (σ_d² − σ_clip²), g_d = ∂s/∂d (d̂에서).
- d̂ ≤ d_floor이면 그 packet의 s 갱신을 생략하고 "사용 불가"로 집계한다.
- 절단이 적용된 packet 수를 arm·경로별로 보고한다.

### 2.6 DR 시나리오

| 축 | 값 |
|---|---|
| gyro bias | B0, L0 = 0.01, L1 = 0.05, L2 = 0.20 °/s, 부호 ± |
| sensor seed | **40** (v2는 20) |
| TB3 점 | k: r1.3.1 = 0.0085 °/°, r2.1.0 = 0.0020 °/° (`PRELIMINARY`) |
| 등가 bias | b_eq = k · Σ\|dθ\| / T, 경로별 |
| 초기 오차 | 원래 EKF4 초기 표준편차. **초기 heading 오차 0 조건을 B0에서 함께 실행한다(보고용)** |

v2 B0에서 DR heading RMSE 4.69°는 초기 오차였다(DR heading NEES 0.15). B0 비교는 drift가 아니라 초기 정렬을 재므로, 초기 오차 0 조건을 따로 낸다.

## 3. 단계

### S0. 회귀와 timeline (재사용)

v2 S0 결과를 SHA로 인용한다. 코드가 바뀐 부분(§2)에 대해 다음 회귀를 추가한다.

- v3 코드에서 b_r = 0, K_r = 0, v2의 백색 분산을 넣으면 v2의 R4·J4 fold 결과와 일치해야 한다(상대 1e-9).
- ℓ → 하한이면 J-C가 J-V와, +T에서 ν → ∞이면 Gaussian 갱신과 일치해야 한다.

### S1′. ranging 규칙 재선택 (G-T1만)

1. 지연 원점 일치(6,012/6,012)는 v2 결과를 인용한다.
2. 후보는 v2와 같다: O30, O20, O10, O30 − 0.5 tap, O30 − 1 tap, sub-tap.
3. 후보마다 **noise-free LoS H**에서 평균 거리 오차를 구해 상수 offset o로 둔다.
4. 선택 지표: full H에서 e_r − o의 RMS(두 SNR 평균)와 검출 실패율.
5. 규칙: 검출 실패율 ≤ 1%인 후보 중 RMS 최소. 최소와의 차이가 5 mm 미만이면 O30을 유지한다.
6. **heading과 s 오차는 계산하지 않는다.**
7. 선택한 규칙으로 LUT/M1-R 예측을 다시 만들고 parity(p90 |Δs| ≤ 0.005)를 확인한다.

v2 수치로 계산한 bias 제거 표준편차는 O30 0.120 m, O20 0.110 m, O10 0.087 m였다. 이 값은 full-H bias를 뺀 것이라 위 3–4의 정의와 다르며, v3 선택은 S1′ 실행 결과로만 정한다.

### S2′. 특성화 (G-T1, 계획 선커밋, v3에서 한 번)

`CHARACTERIZATION_PLAN_003_V3.json`에 추정식, seed, 아래 규칙의 구현과 합성 검산을 먼저 커밋한다. v2의 `CHARACTERIZATION_003.json`은 보존한다.

**공통 규칙.**

- **솎기:** pose 키(위치 + wrap한 yaw)당 한 번만 센다.
- **지원 구간:** 채널·anchor 조합마다 관측된 거리 범위 [d_min, d_max]. 절점은 이 구간 안에만 둔다.
- **구간 최소 표본:** 솎은 뒤 200 packet 이상, 독립 site(§4.1) 10개 이상. 미달 구간은 이웃 구간과 합친다.

| ID | 추정량 | v3 규칙 |
|---|---|---|
| C1 | 열잡음 σ_s, σ_r | v2와 같음 |
| C2 | 거리별 분산 σ_b(ρ)², σ_r(ρ)² | 구간마다 σ_95 = q95(\|e\|) / 1.96. log σ²를 지원 절점에서 구간 선형으로 적합. 2차 차분 벌점, 강도 λ ∈ {0.1, 1, 10}은 LOAO 제외 anchor의 Gaussian 로그우도로 선택. 하한 max(열잡음, 통합 σ_95의 0.5배). 단조 제약 없음. 지원 구간 밖 packet은 s를 쓰지 않고 "사용 불가"로 집계 |
| C2-w | 백색 통합 분산 | 솎은 전체 잔차의 σ_95². 절점 적합과 무관하게 직접 계산 |
| C3 | 상관 kernel | ρ(Δ) = (1 − n)·exp(−Δ/ℓ), nugget n ∈ [0, 1). 쌍 수 가중. 범위: ℓ_d ∈ [0.016 m, 경로 길이/3], ℓ_ψ ∈ [2.5°, 60°] |
| C3 경계 | 미식별 처리 | 상한 도달: ℓ = 상한으로 두고 그 채널은 **+K가 있는 arm만 선택 후보**로 둔다. 하한 도달: 그 채널은 백색으로 둔다. 도달 여부를 채널·fold별로 기록 |
| C4 | 재방문 상관 ρ(d), ρ_TR | v2와 같음 |
| C5 | 5 m 창 평균 성분 | v2와 같음. anchor별 창 평균과 K_s 분산을 함께 낸다 |
| C6 | range 잔차 평균 b_r(r̃) | 지원 구간 안의 거리 구간 평균. offset o 제거 후 계산 |
| C6-K | K_r 분산 | b_r 보정 뒤 구간 평균의 anchor 간 분산(학습 anchor 2개면 차이²/2의 구간 평균) |
| C7 | 꼬리 ν | z = e / σ_b(ρ)로 정규화하고 site당 1개로 솎은 뒤, 위치 0·scale 자유의 Student-t 최우도. ν_use = max(ν̂, 3). ν̂ < 3이면 `TAIL_BELOW_FLOOR` 기록 |
| C8 | \|∂s/∂ψ\| 분포 | v2와 같음 |

**합성 검산(실행 전 필수).**

| 검산 | 기대 |
|---|---|
| 알려진 σ(ρ)(3 절점, 10배 변화)에서 뽑은 표본 | 적합 σ가 절점마다 ±15% 이내, 0 근처 절점 없음 |
| 지원 구간 밖에 절점을 준 입력 | 그 절점이 적합에서 제거됨 |
| nugget 0.3, ℓ = 0.1 m인 합성 상관 | ℓ ±20%, n ±0.1 |
| ℓ이 경로보다 긴 합성 상관 | 상한 도달로 기록되고 +K 제한이 걸림 |
| ν = 4 Student-t 표본 | ν̂ ∈ [3, 5.5] |
| 이분산 Gaussian(σ 10배 변화)을 합친 표본 | 정규화 전 초과첨도 > 3, 정규화 후 \|초과첨도\| < 0.5 |

### S2-T. 이전 가능성 사전 기록 (필터 실행 전, 판정 아님)

LOAO fold마다 다음을 계산해 `TRANSFER_PRECHECK.json`으로 S3 전에 커밋한다.

- Z_s = (제외 anchor의 5 m 창 평균 s) / (학습 anchor로 정한 √K_s)
- Z_r = (제외 anchor의 b_r 보정 후 구간 평균) / (학습 anchor로 정한 √K_r)

|Z| > 2인 fold는 "실패 예측"으로 기록한다. S3 결과와 대조해 §9의 가설을 검정한다.

### S2-F. 사전 무용성 검사

v2 §S2-F의 정의를 그대로 쓰고, S1′의 체인과 S2′의 값으로 다시 계산한다. v2의 `FUTILITY.json`은 보존한다.

### S3. 개발 (G-T1, LOAO)

- 30 dB에서 **모든 bias 수준과 TB3 점을 실행한다.** 한 수준에서 탈락해도 나머지를 실행한다(진단 목적). 20 dB는 보고용이다.
- 모수는 두 anchor로 맞추고 나머지 anchor에서 평가한다.

**S3-R (range 먼저).**

1. R4, R-M, R-MC를 실행한다.
2. §4.2의 integrity 항목(heading, XY, b_g)을 모든 수준에서 통과한 arm 중 가장 단순한 것을 고른다(R4 < R-M < R-MC).
3. 통과 arm이 없으면 `DEV_FAIL_RANGE`로 기록하고 봉인을 유지한다. 이때 s만 쓰는 arm(S-V, S-C)을 `DIAGNOSTIC_ONLY`로 실행해 편파 채널 단독의 일관성을 보고한다.

**S3-J (편파).**

1. S3-R에서 고른 range 모형을 고정한다.
2. §2.4의 선택 후보 12개와 기준선을 실행한다.
3. 1차 arm 선택 규칙:
   1. §4.2의 integrity와 무해성을 모두 통과한 arm만 후보로 둔다.
   2. 그중 L1에서 pooled heading RMSE가 가장 낮은 arm을 고른다.
   3. 차이가 0.1° 미만이면 더 단순한 arm을 고른다. 순서: J-V < J-C < J-CS < J-CI, +K와 +T는 없는 쪽이 단순.
4. 후보가 없으면 `DEV_FAIL`로 기록하고 봉인을 유지한다.
5. 선택한 range 모형과 1차 arm의 모수를 G-T1 전체로 다시 맞춰 동결한다.

### S4. 확인 (봉인 해제, 한 번)

v2 §S4와 같다. `UNSEAL.json`에 S3 동결 커밋, `CHARACTERIZATION_003_V3.json` SHA, `AMENDMENTS_V3_KO.md` SHA, 해제 시각을 기록한다.

## 4. Integrity 판정 (B 방식)

### 4.1 평가 단위

v2 §4.1과 같다. CI는 2단계 bootstrap(조합 안의 site × seed, B = 2,000)이다.

### 4.2 판정 순서와 규칙

**1단계: integrity (모든 bias 수준과 TB3 점에서 충족).**

| 항목 | 기준 | v2 대비 |
|---|---|---|
| pooled heading 포함률 | 점추정 ≥ 0.92 그리고 95% CI 상한 ≥ 0.95 | 동일 |
| pooled XY 포함률 | 점추정 ≥ 0.90 | **신규** |
| pooled 평균 NEES | heading, XY(2 dof로 나눔), b_g 각각 ∈ [0.5, 2.0] | 동일 |
| case 심각 실패 | heading 또는 XY 포함률의 95% CI 상한 < 0.80인 조합이 없음 | 동일 |
| s 사용률 | (gate 기각 + 유효 기각 + 사용 불가) ≤ 20% (pooled) | 사용 불가·유효 기각 포함 |

**2단계: 무해성 (S2-F가 정확도 범위에서 제외한 수준. B0 포함).**

| 항목 | 기준 |
|---|---|
| heading RMSE 비 (arm / DR) | 점추정 ≤ 1.10 그리고 paired 95% CI 상한 ≤ 1.25 |
| XY RMSE 비 | 같은 기준 |

**3단계: 정확도 (S2-F가 포함한 수준).** §5.

v2의 "B0 비열등: paired CI 상한 ≤ 1.10"은 20 seed에서 검정력이 없었다(J4 점추정 0.999, CI 상한 1.30). v3는 seed를 40으로 늘리고 점추정과 CI 상한을 나눠 둔다.

### 4.3 함께 보고할 것 (판정 아님)

- 조합별·경로별 포함률과 NEES
- 직진·회전·정지 구간별 갱신 기여(정의를 `LOAO_PLAN`에 필드 이름과 함께 명시)
- miss의 방향(위·아래)과 연속 miss 길이
- J − R(선택한 range arm)의 heading·XY 차이
- +T arm의 가중 분포
- M1-R 절단 packet 수
- 초기 heading 오차 0 조건의 B0 결과

## 5. 정확도 (integrity·무해성 통과 arm만)

v2 §5와 같다. 주장 문장 형식:

"mount 0, [형상] 조건에서 DR 등가 bias가 b* 이상이고 horizon이 N† 이상이면 1차 arm이 DR보다 heading RMSE가 낮으며, integrity 기준을 충족한다."

정확도 주장은 S2-F가 포함한 경로·수준으로 한정한다. v2 S2-F에서 B0, L0, TB3 r2.1.0은 전 경로에서 제외됐다. v3 S2-F에서도 같으면 TB3 r2.1.0 수준의 우위는 주장하지 않는다.

## 6. 모수 출처 규칙

| 모수 | 허용 출처 |
|---|---|
| 관측 체인, offset, b_r, 열잡음, 분산·상관 kernel, consider 분산, 꼬리 | G-T1(S1′·S2′)만 |
| DR 모수 | Sensor-v2 정의, TB3 실측 |
| BLOCK_C·K 진단·G1-DIAG-003 수치 | 사용 금지 |
| v2 G-T1 결과 | 사양 결함의 식별에만 사용. 모수 값으로 옮기지 않는다 |
| 확인 데이터 | 판정에만 사용 |

## 7. 실행 순서와 중단 조건

| 단계 | 중단 조건 |
|---|---|
| S0 | 추가 회귀 불일치 |
| S1′ | parity 실패 |
| S2′ | 계획 미커밋 또는 합성 검산 미통과 |
| S2-T | 미커밋 상태로 S3 시작 |
| S2-F | 범위만 조정(중단 아님) |
| S3-R | 통과 arm 없음 → `DEV_FAIL_RANGE`, 봉인 유지 |
| S3-J | 후보 없음 → `DEV_FAIL`, 봉인 유지 |
| S4 | 해제 순서 위반, 동결 SHA 불일치, G6 미처리 조합 사용 |

## 8. 외부 의존과 병행 작업

| 작업 | 내용 | 이 사양과의 관계 |
|---|---|---|
| TB3 r2.1.0 반복 | trackA REPEAT 5회 이상, 3일 이상, bag 포함 | TB3 점의 `PRELIMINARY` 해제 |
| TB3 CIR 기록 | trackA에서 CIR과 LiDAR 기준 자세를 함께 기록해 s 잔차의 상관길이·꼬리·창 평균을 잰다 | RT의 대표성 판정. 미측정 시 결론은 "이 RT에서"로 한정 |
| BLOCK_C 동일 정의 특성화 | BLOCK_C 주행 pose에 S2′의 C2·C3·C5·C7을 적용 | 두 RT의 차이가 실제인지 정의 차이인지 확인. `DIAGNOSTIC_ONLY` |
| F1 대조 | BLOCK_C 일부 pose를 F1으로 재생성해 Δs 비교 | 같음 |
| mount 45 민감도 | 같은 경로에서 mount 45 재합성 | 권고 사항. 연구자 결정 필요 |

## 9. v3로도 integrity가 성립하지 않을 가장 강한 이유

지속 성분의 크기가 anchor마다 크게 다르다. v2 C5에서 s의 5 m 창 평균은 anchor B 0.009, A 0.047, C 0.158로 17배 차이가 났고, range 잔차 평균도 anchor마다 달랐다. LOAO에서는 두 anchor로 정한 consider 분산이 세 번째 anchor에 맞지 않을 수 있다. v2에서 miss가 한쪽으로 쏠린 것(anchor A REPEAT: 아래 1,104건, 위 0건)이 이 기전과 일치한다. anchor 3개로는 이 분포를 배울 수 없다.

확인 방법은 S2-T다. 필터를 돌리기 전에 fold별 Z_s, Z_r을 기록하고, |Z| > 2인 fold가 실제로 실패하는지 S3에서 대조한다. S4에서는 6 조합의 같은 비율 분포와 miss의 부호 쏠림을 함께 보고한다.

v2 §9의 가설(경로 길이만큼 지속되는 0이 아닌 평균 성분)은 유지한다. 위 가설은 그 성분의 **크기가 조합마다 다르다**는 점을 더한 것이다.

## 10. 출력 위치

`research/G1_PACKET_EKF_20261114/MODEL_003_V3/` 아래:

```text
S0/REGRESSION_V3.json
S1/RANGING_RULE_SELECTION_V3.json, S1/PARITY_V3.json
S2/CHARACTERIZATION_PLAN_003_V3.json, S2/CHARACTERIZATION_003_V3.json
S2/TRANSFER_PRECHECK.json, S2/FUTILITY_V3.json
S3/LOAO_PLAN_V3_KO.md, S3/RANGE_STAGE.json, S3/LOAO_RESULTS_V3.json, S3/PRIMARY_ARM_V3.json, S3/FROZEN_MANIFEST_V3.json
S4/UNSEAL.json, S4/INTEGRITY.json, S4/ACCURACY.json, S4/checkpoint_rows.csv(LFS)
REPORT_KO.md, MANIFEST.json
```

## 11. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-15 | v3 초안. v2 S3 DEV_FAIL 감사를 반영: range 선행 단계(S3-R), b_r 보정과 K_r, S1′ 선택 지표, C2·C3·C7 적합 규칙과 합성 검산, 꼬리 arm(+T), M1-R 절단, 판정 순서(integrity → 무해성 → 정확도), seed 40, 전 수준 실행, S2-T 사전 기록, 개발 반복 한도. 항목별 계기는 `AMENDMENTS_V3_KO.md` | Fable (proposer) |

### 연구자 승인이 필요한 값

| 항목 | 제안값 | 위치 |
|---|---|---|
| sensor seed 수 | 40 | §2.6 |
| pooled XY 포함률 기준 | ≥ 0.90 | §4.2 |
| 무해성 기준 | 점추정 ≤ 1.10, CI 상한 ≤ 1.25 | §4.2 |
| ν 하한 | 3 | §2.4, S2′ C7 |
| M1-R d_floor | 0.5 m | §2.5 |
| ranging 재선택의 동률 폭 | 5 mm | S1′ |
| C2 구간 최소 표본 | 200 packet, 10 site | S2′ |
| 개발 반복 한도 | v3가 마지막 | §0 |
| mount 45 민감도 실행 여부 | 권고 | §8 |
