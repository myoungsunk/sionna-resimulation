# G1-RT-TB3-002 — 새 RT 데이터의 검증·진단 추가 사양서 (G1-RT-TB3-001 부속)

- 작성: 2026-11-14 KST. 상태: **SPEC_FINAL / NOT_RUN**
- 상위 사양: `SPEC_KO.md`(G1-RT-TB3-001, SPEC_FINAL). 형상, anchor, pose 집합 P-A/P-A′/P-B/P-C, RT 설정, Gate G0–G6는 **바꾸지 않는다**.
- RT 설정: 상위 [RT v1.1](SPEC_V1_1_KO.md)에서 확정한 F1을 적용한다. 이 사양의 추가 pose는 본 생성과 같은 trace 설정과 manifest 형식으로 별도 batch에서 만든다.
- 목적: G1-MODEL-002가 쓸 데이터를 세 가지로 보강한다.
  1. site bias의 재방문 상관과 공간 상관을 직접 잰다(P-D, P-E).
  2. station 오차가 관측 모델 오차인지, multipath(첫 tap 오염)인지 분리한다(경로 export, P-F).
  3. 특성화와 확인을 형상 단위로 나누고, 확인 데이터를 봉인한다(§4).
- 근거: G1-DIAG-002(BLOCK_C 기전 분해)와 Fable 답변(2026-11-14). BLOCK_C는 0.45 m 상관, cm 단위 재방문 상관, TB3 5점 sweep의 스케일을 줄 수 없다.

## 0. 답할 질문

| Q | 질문 | 데이터 |
|---|---|---|
| Q6 | site bias b는 위치를 몇 cm 어긋나게 하면 풀리는가? (재방문을 같은 b로 볼지, 독립으로 볼지) | P-D |
| Q7 | 실제 TEACH/REPEAT 재배치 오차 수준에서 두 번째 방문의 오차는 첫 방문과 얼마나 같은가? | P-A REPEAT + P-E |
| Q8 | station 오차 중 LoS 모델 오차와 multipath 오차의 몫은? 어떤 경로가 첫 tap을 오염시키는가? | H_LoS, PATHS_NEAR |
| Q9 | anchor 천장 standoff 0.05 m에서 천장 반사가 첫 tap 안에 드는 것이 오차 원천인가? | P-F |
| Q10 | 동결 관측 체인의 스케일이 형상·anchor 조합마다 얼마나 다른가? (S-C의 필요성) | 특성화 → 확인 |

## 1. 추가 pose 집합

공통: 위치·yaw 정의, 관측 순서 표, pose_id 중복 규칙은 G1-RT-TB3-001 §3을 따른다. 추가 집합은 `set` 열에 아래 ID를 쓰고, 기존 pose와 같은 물리 pose이면 기존 pose_id를 참조한다.

### P-D: 위치 어긋남 재방문 sweep (Q6)

| 항목 | 값 |
|---|---|
| 형상·anchor | **G-T1 × A, B, C** (특성화 형상만) |
| station | P-A TEACH 18개 전부 |
| 어긋남 크기 d | 0.005, 0.01, 0.02, 0.05, 0.10 m |
| 방향 | +x, −x, +y, −y (4방향) |
| sweep | TB3 5점(해당 station의 TEACH `achieved_rel_deg`), 회전 중심 = 어긋난 base XY |
| 규모 | 18 × 5 × 4 × 5 = 1,800 pose / anchor, 5,400 pose (full + LoS) |

- 6.5 GHz 파장은 4.61 cm(반파장 2.31 cm)다. d 격자는 반파장 아래·근처·위를 덮는다.
- yaw는 바꾸지 않는다. yaw 재배치 오차는 P-E에서 다룬다.

### P-E: TEACH/REPEAT 재배치 재현 (Q7)

| 항목 | 값 |
|---|---|
| 형상·anchor | **9 조합 전부** |
| station | 18개 |
| 재배치 수 | station당 K = 3 (기존 P-A REPEAT 1개와 합쳐 두 번째 방문 4개) |
| XY 어긋남 | REPEAT 10/04, 11/13 `repeat.json`의 정렬 후 station base XY 잔차(TEACH 대비)를 모은 경험분포에서 크기를 뽑고, 방향은 균일. seed 2026111402 |
| yaw 어긋남 | 같은 두 run의 마지막 ICP yaw 잔차 경험분포에서 뽑는다 |
| sweep | TB3 5점 |
| 규모 | 18 × 3 × 5 = 270 pose / 조합 |

- 경험분포의 표본 값과 출처 파일 SHA를 `POSE_MANIFEST.json`에 기록한다. Fable이 인용한 범위(0.3–7.9 mm)와 다르면 파일 값을 쓰고 차이를 기록한다.

### P-F: anchor standoff 대조 (Q9, 민감도 arm)

| 항목 | 값 |
|---|---|
| 형상·anchor | G-T1 × A, B |
| anchor 높이 | z = **2.40 m**(standoff 0.30 m). 방향·포트는 §2와 동일 |
| pose | P-A TEACH의 TB3 5점 + 조밀 49점 |
| 규모 | 18 × 54 = 972 pose / anchor |

- 이유: standoff 0.05 m에서는 천장 반사의 초과 경로 길이가 수평거리 0–7 m에서 0.03–0.10 m다. Δ_tap 0.1496 m보다 짧아 항상 첫 tap 안에 든다(RX 0.45 m 기준 영상 계산). standoff 0.30 m에서는 수평거리 약 8.5 m까지 Δ_tap보다 길어져 첫 tap 밖으로 나간다.
- anchor 방향이 아래이므로 천장 반사는 back lobe로 나가 약할 수 있다. 그 크기를 이 arm이 직접 잰다.
- P-F는 1차 판정에 쓰지 않는다. 결과는 "anchor 설치 조건 민감도"로만 보고한다.

## 2. 추가 출력: near-delay 경로 export (Q8)

- 대상: P-A, P-D, P-E, P-F의 모든 pose(full trace).
- 범위: LoS 지연 τ₀부터 τ₀ + 2·Δτ_tap(거리 0.299 m)까지 도착하는 모든 경로.
- **H를 만든 trace 실행에서 같이 저장한다.** 별도 trace를 돌리지 않는다(확률 샘플링 차이로 H와 경로 목록이 어긋나는 것을 막는다).
- 필드: pose_id, 경로 index, 지연(m), 포트 쌍별 복소 계수(+45/−45 × +45/−45), 상호작용 수, 상호작용 유형 순서(반사/회절/산란), 상호작용 객체 id, AoD·AoA(방위·고각).
- 파일: `paths/<geom>_<anchor>/PATHS_NEAR.npz` + `PATHS_NEAR_SCHEMA.json`.
- 파생 지표(본 생성 후 계산, 특성화·확인 공통): G1-DIAG-002 K8과 같은 정의의 첫 tap 오염도 c_p와 Δs = s_full,clean − s_LoS,clean.

## 3. 추가 Gate

| Gate | 내용 | 기준 |
|---|---|---|
| G7 | P-D/P-E/P-F pose 검사: G0 항목 전부 + 어긋남 크기·방향 재계산, 경험분포 표본 재현 | 위반 0건 |
| G8 | 경로 export 일관성: LoS 경로 1개로 H_LoS를 재합성해 비교. near 경로 수 분포 기록 | H_LoS 최대 상대 오차 < 1e-6 |
| G9 | 봉인 무결성(§4): 확인 형상 H의 SHA, 접근 로그, 허용 스크립트 목록 | 위반 0건 |
| G3·G4 | 추가 batch에도 G1-RT-TB3-001의 G3(진행 중 G3a 포함, 통과한 설정 그대로)과 G4를 적용 | 기존 기준 |

G8 파일럿은 G1과 같은 G-T1 × A에서 P001–P003의 TEACH·REPEAT 332개 RF pose를 사용한다. 저장 후 다시 읽은 `PATHS_NEAR`의 단일 LoS 경로에서 257 bin의 복소 채널을 재합성한다. G1에서 `max_depth=0`으로 계산한 `H_LoS`를 기준으로 복소 원소별 오차 `|H_reconstructed - H_LoS| / |H_LoS|`의 최댓값을 사용한다. 기준이 정확히 0인 원소는 재합성 값도 0이어야 한다. 같은 F1 trace의 LoS를 Method B로 적용한 결과와의 비교도 기록해 export 자체의 일관성을 확인한다.

## 4. 특성화·확인 분리와 봉인

### 4.1 역할

| 역할 | 형상 | anchor | 용도 |
|---|---|---|---|
| **특성화** | **G-T1** | A, B, C (3 조합) | §5 추정을 한 번만 실행. 결과를 `CHARACTERIZATION.json`으로 동결 |
| **확인** | **G-T2, G-V** | A, B, C (6 조합) | G1-MODEL-002의 첫 integrity·정확도 판정. 파라미터 수정 금지 |

- G1-RT-TB3-001에서 G-T1은 "1차" 형상(pilot·회귀 기준)이었다. 이 사양부터 G-T1은 **특성화 전용**이고, Goal 1의 판정 형상은 G-T2와 G-V다. 확인 쪽이 더 복잡한 형상(오목부·돌출물)과 다른 재질(concrete)을 갖게 되어 판정이 보수적인 방향이 된다.
- 특성화 형상의 결과를 확인 판정에 섞지 않는다.

### 4.2 봉인 규칙

- 확인 형상의 H_full, H_LoS, PATHS_NEAR는 생성 직후 SHA를 `SEAL_MANIFEST.json`에 기록한다.
- G1-MODEL-002 사양과 코드가 동결·커밋되기 전까지, 확인 데이터에 허용하는 계산은 다음뿐이다.
  - G0–G9 gate. G4 parity는 noise-free LoS H에서 관측 모델 parity만 보고 heading 오차를 계산하지 않는다.
  - 저장량·형식 검사
- 금지: 확인 데이터에서 heading 오차, E1 분산, z, 포함률, 오염도 c_p를 계산하는 모든 스크립트.
- 해제: `UNSEAL.json`에 G1-MODEL-002 동결 커밋 hash, `CHARACTERIZATION.json` SHA, 해제 시각을 기록한다. 확인 분석 커밋은 그 동결 커밋의 후손이어야 한다.

## 5. 특성화 추정 (G-T1, 한 번만 실행)

관측 체인은 G1-MODEL-001 v3.4를 동결해서 쓴다: M1-R, J_joint, 원형 yaw 격자, 다중 후보 절차, XY 사전 오차 AR(1)(σ 0.13 m, ρ 0.9)과 snap, 열잡음 SNR 30 dB. station·조건마다 seed 20개다. 같은 계산을 XY 오차 없이(참 위치) 한 번 더 해 둘의 차이를 기록한다.

정의:
- sweep 오차 e = wrap(ψ̂ − ψ_true)
- site bias b(station, anchor, 조건) = seed 20개 평균 e
- E1 형태 r = max(1, χ²_red)·2/J''(c_L 없음)
- z = b / √r̄. r̄는 station의 seed 평균 r이다.

| ID | 추정량 | 방법 | 출력 |
|---|---|---|---|
| C1 | 재방문 상관 ρ(d) | P-D: (station, anchor, 방향) 단위로 b(0)와 b(d)의 Pearson 상관과 variogram γ(d) = ½E[(b(d) − b(0))²]. station-cluster bootstrap 1000 | d별 ρ, γ, 95% CI |
| C2 | 실제 재배치 상관 ρ_TR | P-A REPEAT + P-E: b(TEACH)와 b(재배치)의 상관. 재배치 크기 구간별로도 낸다 | ρ_TR, CI |
| C3 | 공간 상관 | P-A TEACH: station 간격 0.45, 0.90, 1.35, 1.80 m에서 b의 상관 | 간격별 ρ, CI |
| C4 | 조합별 스케일 κ | 조합별 station 평균 z². 5점, 49점 각각 | κ(조합, 프로토콜) |
| C5 | κ prior | log κ ~ Normal(m, s²). m = 3 조합 log κ의 평균. s = max(3 조합 표본 SD, **0.81**). 0.81은 BLOCK_C 6 case의 log(station 평균 z²) 표본 SD이고, 3 조합만으로 분산이 과소 추정되는 것을 막는 하한이다 | (m, s) |
| C6 | 꼬리 | 조합별 κ로 나눈 station z의 초과첨도, \|z\| > 3 비율, Student-t ν 최대우도 | ν, 첨도 |
| C7 | 열잡음 | station 안 seed 간 e의 SD | σ_th |
| C8 | 모델 오차 몫 | H_LoS로 같은 계산 → b_LoS. V_model = var(b_LoS)/var(b) | 조합별 V_model |
| C9 | 오염과 오차 | station 수준 Spearman(\|b\|, max c), (√r̄, max c). 오염 기여가 큰 경로 유형(천장, 바닥, 측벽, 2차 이상)의 비율 | 상관, 유형 표 |
| C10 | standoff 효과 | P-F vs P-A(같은 station, 같은 anchor): \|b\|, κ, max c 비교 | 비교 표(민감도) |

- 모든 추정식, seed, bootstrap 횟수를 실행 전에 `CHARACTERIZATION_PLAN.json`으로 커밋한다. 실행은 한 번만 하고, 재실행은 코드 오류가 있을 때만 허용한다. 재실행하면 사유와 이전 결과를 남긴다.
- `CHARACTERIZATION.json`에 C1–C10 값, 입력 SHA, 코드 SHA를 기록하고 동결한다.

## 6. 특성화 결과에 따른 G1-MODEL-002 구조 결정 (사전 고정)

| 조건 | 결정 |
|---|---|
| ρ(0.02 m)의 95% CI 하한 ≥ 0.8 **그리고** ρ_TR ≥ 0.8 | 재방문은 같은 b. **S-A(재방문 시 b 재사용) 필수**. TR 경로에서 b 상태 유지 |
| ρ(0.005 m)의 95% CI 상한 ≤ 0.5 | 재방문은 사실상 독립. S-A는 쓰지 않고, 재방문 관측을 독립으로 처리 |
| 그 사이 | 부분 상관 모델 b₂ = ρ(d)·b₁ + √(1 − ρ²)·η. ρ(d)는 C1 곡선, d는 TR 재배치 크기 |
| C3: 0.45 m 상관의 95% CI가 0을 포함 | 인접 station b 독립. 아니면 지수 상관 길이 ℓ를 C3에서 최소제곱으로 정해 고정 |
| 3 조합 κ의 max/min > 1.5 (5점 기준) | **S-C(잠재 스케일) 필수**, prior는 C5 |
| max/min ≤ 1.5 | 전역 스케일 + C5 prior를 민감도 arm으로 |
| C8: 어느 조합이든 V_model ≥ 0.5 | 확인 판정 전에 관측 모델(고각·거리 의존)을 개발 단계에서 먼저 고친다. 수정은 특성화 데이터만으로 하고, C 추정을 다시 동결한다 |
| C6: ν < 5 | S-D(Student-t site bias)를 1차 구조에 포함 |
| C9: Spearman(\|b\|, max c) ≥ 0.5이고 Spearman(√r̄, max c) ≤ 0.2 | "확신하며 틀림"이 near-delay 오염에서 온다. Goal 1은 κ·꼬리로 덮는다. c 추정을 관측에 쓰는 것은 Goal 2로 넘긴다 |

## 7. 확인 단계에서 보고할 사전 지표 (해제 후, 판정과 별도)

판정은 G1-MODEL-002에서 정한다. 아래는 판정과 함께 반드시 내는 진단이다. 결과를 보고 모델을 바꾸지 않는다.

- 동결 체인 + C5 prior 중앙값 스케일에서의 조합별 RMS z. RMS z > 1.3인 조합이 있으면 "R4_aB형 기전 재현"으로 표시한다.
- 그 조합에서 κ 사후 중앙값이 1.5를 넘는 데 필요한 distinct station 수(G1-DIAG-002 K10과 같은 추정기, prior는 C5). 18개 안에 들어오지 않으면 "run 안에서 스케일 적응 불가"로 표시한다.
- 조합별 V_model, max c와 \|b\|의 상관(특성화와 같은 정의).

## 8. 출력 위치

`results/G1_RT_TB3_CORRIDOR_<date>/` 아래, G1-RT-TB3-001 §5에 추가:

```text
poses/<geom>_<anchor>/  (P-D, P-E, P-F 행 추가, POSE_MANIFEST.json)
paths/<geom>_<anchor>/PATHS_NEAR.npz, PATHS_NEAR_SCHEMA.json
gates/G7.json, G8.json, G9.json
seal/SEAL_MANIFEST.json, ACCESS_LOG.jsonl, UNSEAL.json(해제 시)
characterization/CHARACTERIZATION_PLAN.json, CHARACTERIZATION.json, REPORT_KO.md
```

## 9. 규모

| 집합 | pose |
|---|---|
| P-D | 5,400 (G-T1 × 3 anchor) |
| P-E | 2,430 (9 조합) |
| P-F | 1,944 (G-T1 × 2 anchor, anchor 높이 다름) |
| 합계 | 약 9,800 pose × (full + LoS) |

본 생성(약 64,000 pose-채널)의 약 15%다. 경로 export의 저장량은 G1 pilot 자료로 추정해 실행 전 `RUN_MANIFEST.json`에 기록한다.

## 10. 해석 경계

- G1-RT-TB3-001 §8을 그대로 따른다(`ENV_ASSUMED`, `GENERALIZATION_NOT_PROVEN`).
- ρ(d), ρ_TR은 RT의 결정론적 채널에서 얻은 값이다. 실측에서는 사람·물체 이동 같은 시간 변화가 재방문 상관을 낮출 수 있다. 실측 TEACH/REPEAT로 확인하기 전까지 `RT_ONLY`로 표기한다.
- P-F는 설치 조건 민감도다. standoff를 바꾼 결과로 Goal 1의 1차 판정을 바꾸지 않는다.

## 11. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-14 | 초판. P-D/P-E/P-F, near-delay 경로 export, G7–G9, 특성화(G-T1)·확인(G-T2, G-V) 분리와 봉인, 특성화 추정 C1–C10, 구조 결정 규칙 | Claude |
