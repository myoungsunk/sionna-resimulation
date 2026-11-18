# M8 Step 3 공정 판정 계획 개정 01 — B단계 시작 전 동결

| 항목 | 내용 |
|---|---|
| 대상 계획 | [PLAN_M8_STEP3_FAIR_KO.md](../PLAN_M8_STEP3_FAIR_KO.md) (`c43168b3`) |
| 작성 시점 | B단계(seed 30–49) 실행 전. A단계(seed 10–29)는 실행을 시작했으나 집계는 보지 않았다 |
| 사전 노출 | 실행기 점검을 위해 **seed 10 B0 1건**의 점수를 봤다. F2SKRW (b)가 pooled Pose95 0.879로 무결성 실패, F2SKRW-V는 0.881로 실패. 이 결과로 바꾼 성분·설정은 없다 |
| 봉인 | G-T2/G-V 미접근. S2′ STOP, Step 3 HOLD, DIAGNOSTIC_ONLY 유지 |

## A3. B단계 online 입력은 제안자(Claude)가 생성한다

- 계획 §5는 "online 입력 생성은 실행자"였다. 사용자 결정(2026-11-18 "직접 만들어서 진행")으로 제안자가 만든다.
- 생성기: [code/gen_inputs_ext.py](code/gen_inputs_ext.py). M7 `m7_inputs.generate_inputs`와 같은 법칙이다.
  - 동결 sensor 모듈 2개를 M7 RUN_CONTRACT 해시로 확인해 쓴다(`sensors.py` 2285db90b465…, `sensor_v2.py` e74cd4657b97…).
  - 짝 설정은 B0 N = 0.015, L2 N = 0.060 deg/√s이고 gyro_N만 다르다.
  - RF 필드(t, pose_id, z, muMB, muBASE, R, D)는 동결 reference packet에서 복사한다.
  - x0는 truth[0] + rng(seed, "initial")·[0.1, 0.1, 5°]이다.
  - seed 격자만 30–49로 바꾼다.
- **parity:** 같은 코드로 seed 10–29를 다시 만들어 M7 입력 120개와 비교했다([INPUT_PARITY_10_29.json](freeze/INPUT_PARITY_10_29.json)).
  - gy, x0, P0, dt, RF 필드는 bit-exact로 일치한다.
  - ds만 최대 1.39e−17 차이가 난다(값 ~0.043 m의 2 ulp). 원인은 Windows와 Linux의 libm `sin`/`cos` 차이다(`motion_increments`).
  - M7 생성기 자체 허용오차는 1e−10이고, 판정은 PASS_TOL_1e-10이다.
- 생성물 120개(B0, L2 × 20 seed × 3 경로)의 경로와 sha256은 [INPUT_INDEX_EXT.json](freeze/INPUT_INDEX_EXT.json)에 있다.
- npz는 LFS 업로드 제한 때문에 올리지 않는다. 생성기와 해시로 재생성할 수 있다.
- stress 조건은 M7처럼 L2 입력을 그대로 쓴다. B단계는 B0와 Q 일치 L2만 판정한다.

## A4. 재가중 (b)의 출처는 2순위 대리값이다

- 1순위 계획 파일 `rf_poses_R{2,4,5}.json`은 이 작업 공간에 없다.
- 계획 §2의 2순위 규칙대로, **평가 궤적의 evaluator 참 yaw**로 10° 구간 36개 히스토그램을 만든다.
  - 이 시뮬레이션에서 RF pose가 곧 계획 경로이므로 두 값은 같은 궤적에서 나온다.
  - 보고서에는 "계획이 아닌 주행값"이라고 표기한다.
- 위치, 순서, 측정, 오차는 쓰지 않는다.
- 히스토그램 해시, 가중 평균 1, 유효 표본 수는 [CAL_B_CHECKS.json](freeze/CAL_B_CHECKS.json)에 있다(C3).

| 경로 | 유효 표본 수 (7,200 중) | 점유 구간 (36 중) |
|---|---|---|
| R2 | 490 | 28 |
| R4 | 1,158 | 9 |
| R5 | 410 | 19 |

## A5. H1S, H2S 정의를 구체화한다

- **H2S:** M7 H2 코드(G0 구조)에 sweep packet을 넣는다.
  - μ_r은 HGB (b), R_rr은 POWER (b)다.
  - μ_s는 POWER (b)를 **모든 거리에서** 쓴다(kriging 없음). R_ss는 POWER (b)다.
  - σ_b = 0이다.
- **H1S:** M7 H1 코드(거리 단독)에 같은 sweep packet을 넣는다. μ_r, R_rr만 쓰인다.
- 근·중거리 kriging을 H2S에 넣지 않는 이유: 계획 §2가 kriging을 F 계열 사다리 3단계 성분으로 정의했고, H2S 정의 행에 kriging이 없다.
- 이 때문에 H2S가 정확도 기준으로서 약할 수 있다. 그래서 M7 H2 기준 판정도 함께 보고한다(판정은 H2S 기준).

## A6. sweep 계열 packet은 측정값만으로 다시 만든다 (C4를 구성으로 보장)

- F2SKR, F2SKRW, F2SKRW-V, H1S, H2S의 packet은 원 packet에서 측정·센서·초기 필드만 가져온다.
  - 가져오는 필드: t, pose_id, z, ds, gy, dt, x0, P0.
- 나머지 필드는 sweep 값 또는 무의미한 값으로 채운다.
  - muMB = [μ_r, μ_s] (sweep), muBASE = muMB, R = diag(R_rr, R_ss) (sweep).
  - D = 0이다. replay가 형식 검사에만 쓰는 필드다.
  - σ_b = 0 표다.
- F2S, F2SB, F2SK는 사다리 정의대로 LORO 성분을 일부 남긴다.
  - F2SB, F2SK의 μ_r은 packet μ_MB[:,0]이다.

## A7. 채점 seed 가드

- M7 `assess_seed`는 seed ∈ 10–29만 받는다. B단계에서는 같은 함수를 seed 10 라벨로 호출하고 결과의 seed 칸만 실제 값으로 바꾼다([code/m8s3_score.py](code/m8s3_score.py)).
- 판정 논리는 바뀌지 않는다.

## A8. V 표 동결 (C6)

- [SWEEP_TABLE_V.json](freeze/SWEEP_TABLE_V.json) `bc918bb2…e2daaf`.
- 근·중거리 bin의 규칙 B를 station 단위 kriging 교차검증 잔차(위치 하나씩 제외, 이웃 150)로 다시 적합했다. 원거리 bin은 그대로 둔다.

| bin | c₁ 미반영 → V | c₀ 미반영 → V | σθ 미반영 → V | σres 미반영 → V |
|---|---|---|---|---|
| [0, 3) m | 2.57e−4 → 7.90e−5 | 1.23e−4 → 3.52e−5 | 0.92° → 0.51° | 0.0111 → 0.0059 |
| [3, 6) m | 3.21e−3 → 1.73e−3 | 2.29e−3 → 1.43e−3 | 3.25° → 2.38° | 0.0478 → 0.0378 |

- 두 bin 모두 c₁, c₀가 미반영 표보다 작다.
- 한계: 이 잔차는 참 station 자세의 kriging 오차다. online 계산은 prior 자세를 쓰므로 실제 잔차는 이보다 클 수 있다.

## A9. 실행 전 검사 결과 (seed 10 B0)

| # | 결과 |
|---|---|
| C1 | H2, H3: Step 1 실행 대비 점수·CI 하한 차이 0, 판정 일치 |
| C2 | F2L = Step 1 F2, F2S = dev F2S: 점수·CI 차이 0, 판정 일치. F2SK 이후는 가중이 (a)→(b)로 바뀌어 재현 대상이 아니다 |
| C3 | 위 A4 표 |
| C4 | A6 구성 |
| C6 | 위 A8 표 |

## 동결 해시

| 파일 | sha256 |
|---|---|
| SWEEP_FEATURES.csv.gz | 2917a06c8317fa81f3729e90d4c65a077af14c73c56137c75777eea6d710c320 |
| KRIGE_PARAMS.json | fad67226ce0607db82fc9710df984d20ba9b7de5c4b20581ccd53f0d762716db |
| SWEEP_TABLE_V.json | bc918bb246e132c19e5ea10573b80e9839a2a6f9286832d3b50522de20e2daaf |
| SWEEP_CAL_B.npz (CSV로 게시) | 2a7be23be7c8b69eaa4712149208862dc55928ddab696f45e664b30f2365c4fb |
| 코드·입력 index | [SHA256SUMS](SHA256SUMS) |
