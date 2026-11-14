# G1-DIAG-002 — BLOCK_C 기존 RT 데이터: S2′ integrity 실패 기전 분해 진단 사양서

- 작성: 2026-11-14 KST. 상태: **SPEC_FINAL / NOT_RUN / DIAGNOSTIC_ONLY**
- 대상: G1-MODEL-001 v3.4 S2′ 결과(FULL_6 / STOP, `d7a3529`)와 Q1 사후 진단(`42fe9c7`).
- 목적: integrity 실패를 기전별로 분리하고, G1-MODEL-002의 **구조 선택**(개발 단계)에 쓸 근거를 만든다.
- **주장 경계:** 이 사양의 모든 결과는 `DIAGNOSTIC_ONLY`다. S2′의 판정(STOP)을 바꾸지 않고, Goal 1의 정확도·integrity 주장에 쓰지 않는다. 여기서 얻은 수치(스케일, 편향, 상관)를 G1-MODEL-002의 파라미터로 옮기지 않는다. 파라미터는 새 RT 특성화 단계(G1-RT-TB3-002 §5)에서 다시 추정한다.
- oracle을 쓰는 항목(K4, K5, K7, K8)은 실제 운용에서 얻을 수 없는 정보를 쓴다. 상한·원인 분리용으로만 해석한다.

## 0. 답할 질문과 기전 정의

| 기전 | 정의 | 근거(Q1·Fable 재확인) |
|---|---|---|
| M-a | case 간 측정 분산 스케일 불일치. 전역 c_L로 R4_aB는 과소, 나머지는 과대 | R4_aB 측정 95% 포함 79.5%, RMS z 1.61. 나머지 95.5–100%, 0.52–0.91 |
| M-b | station 고정 오차를 재방문마다 독립 관측으로 계수 | station 분산 비 1.02–1.09. Markov R4 distinct 5/17 |
| M-c | case 평균 부호 편향. β 상태가 흡수하지 못함 | R2_aA station 평균 −2.44°(t ≈ −2.6), 독립 포함 86.2% |
| M-d | 통합 포함률이 case 간 과대·과소를 상쇄 | 독립 89.38% = R4_aB 63.5% + 나머지 86–99% |
| M-e | q95 보정의 과대 분산이 M-b를 가리고 정확도를 깎음 | 5 case RMS z 0.52–0.91, 반폭 5.2–6.6° |
| **M-f (신규)** | R4_aB의 "확신하며 틀린" site가 **관측 모델 오차**인지 **multipath(첫 tap 오염)**인지 | 미확인. M1-R parity 통과는 LoS 모델 오차가 작음을 시사하나 heading 영역에서 미검증 |

M-f를 따로 두는 이유: 모델 오차라면 Goal 1 범위에서 관측 모델을 고친다. multipath라면 Goal 1에서는 integrity로 덮어야 할 오차이고, 감지·기각은 Goal 2다. 다음 구조의 방향이 여기서 갈린다.

## 1. 입력 (고정)

| 항목 | 위치 | 고정값 |
|---|---|---|
| 실행 코드 | `RUN4_20261113T105130Z/s2_code/` | `d7a3529`. 수정 없이 복사 후 flag로만 arm 추가. 복사본 SHA를 `CODE_SHA256.txt`에 기록 |
| S2′ 결과 | `RUN4_20261113T105130Z/s2_out/` | `S2P_DRAWS.npz`, `S2P_BOOTSTRAP.npz`, `B0_NOMINAL.npz`(LFS), `MARKOV_COVERAGE_DIAGNOSTIC.json`, `S1P_ERR_MODEL_LORO.json` |
| Q1 진단 | `DIAG_Q1_20261114/` | `42fe9c7`. `q1_sweep_rows.csv`, `q1_case_table.csv`, `q1_diag.py` |
| BLOCK_C | `codex/post-a23-evidence-20261010` | `047cce2`. `FULL_RF/H_<case>.npy`, `H_LoS_<case>.npy`, `<case>/SAMPLES.json`, `CASES.json` |
| LUT 소스 | `codex/a23-results-20261010` | `f9a7691` |
| FFD bank | 저장소 루트 LFS | `LP_plus45_bank.npz`, `LP_minus45_bank.npz` SHA를 manifest와 대조 |
| 대상 case | mount 0 6개 | R2_aA_m0, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0 |

- `freqs_hz.npy`가 BLOCK_C에 없으면 SUPPLEMENT에서 복사하고 SHA를 기록한다(Q1과 동일).
- 난수: S2′와 같은 seed(`TRAIN_SEED` 2026111336, path 2026111303, xy 2026111322, bootstrap 20261113)를 쓴다. 새 arm의 새 난수는 §2.3의 seed만 쓴다.
- c_L: 동결값(R2 158.842, R4 139.693, R5 160.722)을 다시 학습하지 않는다.

## 2. 공통 규칙

### 2.1 재현 검사 K0 (선행, 실패 시 전체 중단)

동결 코드로 S2′ nominal을 다시 실행해 아래를 비교한다.

| 비교 | 기준 |
|---|---|
| arm별 전체 미포함 수 (독립 361, Markov 531, 셀은 S2′ 값) | 정확히 일치 |
| case별 미포함 수 (`MARKOV_COVERAGE_DIAGNOSTIC.json`) | 정확히 일치 |
| case별 RMSE, 평균 반폭 | 상대 차이 ≤ 1e-9 |

### 2.2 집계 지표 (모든 arm 공통)

case별, arm별로 다음을 낸다. 통합값은 참고로만 내고 해석의 기준으로 쓰지 않는다(M-d).

- 누적 95% 포함률, 미포함 수, 평균 NEES(heading 1자유도), RMS z
- heading RMSE, 평균 오차, 평균 신뢰구간 반폭
- path당 서로 다른 station 수(중앙값, IQR)
- 방문 index(1…N)별 포함률
- 불확실성: S2′와 같은 station-cluster bootstrap(B = 200 outer). 계산량이 부담되면 nominal만 필수, bootstrap은 K3·K4·K6에만 필수

### 2.3 새 경로 규칙

| ID | 규칙 | 용도 |
|---|---|---|
| **NR-rand** | case의 유효 station에서 **비복원 무작위 순열**, 앞 N개 방문. path 수 200, seed 2026111401. DR·열잡음·XY 난수는 S2′ path index와 같은 CRN | 재방문 없는 기준 |
| **NR-seq** | 복도 순서의 연속 N개 창, 양방향. 가능한 모든 시작점 | 공간 순서 보존 대조 |
| 공통 | N = 10(R4 station 수). station이 N보다 적은 case는 해당 N에서 제외. 순환 채우기 금지 | — |

- 이동 간 DR 과정(σ_w, β, σ_β)은 S2′와 같다. station 사이 거리가 달라져도 DR 증분은 방문 단위로 둔다(S2′와 동일 가정).
- 비교용으로 독립·Markov·셀 arm을 N = 10에서 자른 집계도 낸다.

## 3. 진단 항목

### K1. case별 3 arm 분해 (재실행 없음 또는 K0 산출물)

- §2.2 지표를 6 case × {독립, Markov, 셀}로 낸다.
- Fable 미확인 항목: path당 distinct station 수(Markov R4 5, 셀 3–4, 독립 8–9), 셀 arm의 R4_aB 몫.
- 출력: `K1_CASE_ARM.json`, `K1_CASE_ARM.csv`

### K2. 첫 방문/재방문 분리 (재집계만)

- 각 방문을 path 안에서 그 station의 k번째 방문으로 표시한다(k = 1, 2, 3+).
- k별 포함률·NEES를 case × arm으로 낸다.
- "첫 재방문 이전 구간"만의 누적 포함률을 따로 낸다.
- 출력: `K2_REVISIT_SPLIT.json`

### K3. 재방문 제거 (필터 재실행)

- NR-rand, NR-seq에서 동결 c_L로 S2′ 필터를 다시 돌린다.
- 출력: `K3_NR.json`(§2.2 지표, N = 10, Markov·독립의 N = 10 절단과 나란히)

### K4. case별 oracle 스케일 (M-a)

- κ_case = Q1의 station 수준 평균 z²(동결 c_L 기준). `q1_sweep_rows.csv`에서 다시 계산해 기록한다. Fable 재계산값: R2_aA 0.46, R2_aB 0.40, R4_aA 0.14, R4_aB 1.80, R5_aA 0.46, R5_aB 0.44. 차이가 0.01을 넘으면 재계산값을 쓰고 차이를 보고한다.
- 측정 분산을 R ← κ_case · R_E1로 바꾸고, 독립·Markov·NR-rand arm을 재실행한다.
- 출력: `K4_ORACLE_SCALE.json`

### K5. case별 oracle 편향 (M-c)

- μ_case = Q1의 case 평균 station 오차. 측정에서 μ_case를 빼고 재실행한다(스케일은 동결).
- 출력: `K5_ORACLE_BIAS.json`

### K6. 교호작용과 재방문 처리의 상한

| arm | 스케일 | 편향 | 경로 | 재방문 처리 |
|---|---|---|---|---|
| K6-00 | 동결 | — | Markov | 없음 (= S2′) |
| K6-10 | oracle | — | Markov | 없음 |
| K6-01 | 동결 | — | NR-rand | — |
| K6-11 | oracle | — | NR-rand | — |
| K6-OB | oracle | oracle | Markov | 없음 |
| **K6-SKIP** | oracle | oracle | Markov | 재방문 station의 편파 갱신을 생략(DR만) |

- K6-SKIP은 완전 상관 site bias를 이중 계수하지 않는 가장 보수적인 처리다. S-A(재방문 시 b 재사용)는 상대 heading 정보를 더 쓰므로 정확도는 이보다 좋아야 하고, integrity는 비슷해야 한다. 그래서 K6-SKIP은 S-A의 integrity 효과 하한 근사로만 해석한다.
- 출력: `K6_INTERACTION.json`(2 × 2 표, OB, SKIP)

### K7. LoS-only 대체 실행 (M-f: 모델 오차 vs multipath)

- `_train_group`을 `H_full` 대신 `H_LoS`로 돌린다. 열잡음 seed, XY offset, snap, 후보 절차는 Q1과 완전히 같게 둔다. `ObservationCase`의 LoS 입력 경로를 쓰고, 코드 수정은 입력 배열 선택 flag 하나로 제한한다.
- sweep별로 e_LoS, √R_E1,LoS를 얻고 e_mp = e_full − e_LoS로 둔다.
- case별 지표:
  - RMS e_LoS, station 평균 e_LoS의 분포
  - 분산 비 V_model = var(station 평균 e_LoS) / var(station 평균 e_full)
  - √R_E1,full / √R_E1,LoS의 station별 비(multipath가 J를 날카롭게 만드는지)
  - R4_aB에서 |e_full| ≥ 2°인 station 각각의 (e_LoS, e_mp, √R_E1,full, √R_E1,LoS)
- 출력: `K7_LOS_ATTRIBUTION.json`, `K7_station_rows.csv`

### K8. 첫 tap 오염과 near-delay 경로 (M-f, oracle)

- noise-free H에서 관측 체인과 같은 IFFT·창으로 CIR을 만들고, LoS H의 첫 경로 tap index k₀를 쓴다.
  - 오염도 c_p = |h_full,p[k₀] − h_LoS,p[k₀]| / |h_LoS,p[k₀]|, p ∈ {+45, −45}
  - clean s 차이 Δs = s_full,clean − s_LoS,clean(`ObservationCase.full_clean`, `los_clean`)
  - station sweep의 모든 yaw에서 계산하고 station별 최대·평균을 낸다.
- 기하 후보: `CASES.json`의 anchor·robot 높이와 BLOCK_C 형상으로 천장·바닥·측벽 1차 영상의 초과 지연을 해석적으로 계산하고, Δ_tap(0.1496 m) 안에 드는 경로를 station별로 표시한다. 특히 anchor 천장 standoff에 따른 천장 반사의 초과 지연을 기록한다.
- 상관: station 수준 Spearman(|e_full|, max c), (|e_full|, |Δs|), (√R_E1, max c). 6 case 각각과 pooled.
- 출력: `K8_TAP_CONTAMINATION.json`, `K8_station_rows.csv`

### K9. 정확도 horizon 예비 계산 (r2.1.0 DR)

- DR 파라미터를 r2.1.0으로 바꾼다: β 0.482°/station, σ_w 0.40°(G1-MODEL-001 v3.2 §4.5 민감도 값). σ_β는 측정값이 없으므로 격자 {0, 0.05, 0.08, 0.11, 0.15, 0.25, 0.45}°/station.
- NR-rand에서 필터를 재실행한다. horizon N은 case station 수까지(R2 21, R4 10, R5 30). R4는 N = 10까지만 낸다.
- 지표: 방문 index별 RMSE_G1(N), RMSE_DRcal(N; σ_β), 비율, 그리고 교차 index N* = min{N : RMSE_DRcal(N) > RMSE_G1(N)}.
- station 수를 넘는 N에 대해서는 DR만 해석적으로 연장한다: RMSE_DRcal(N)² = N·σ_w² + N²·σ_β². G1 값은 마지막 5 방문 RMSE의 평균을 정상 상태값으로 두고 연장한다. 이 연장은 `EXTRAPOLATED`로 표시한다.
- K4(oracle 스케일) 조건에서도 같은 표를 낸다. 동결 스케일은 M-e로 G1 정확도를 깎으므로 두 조건을 모두 본다.
- 출력: `K9_HORIZON.json`, `K9_horizon.csv`

### K10. 잠재 스케일 수렴 예비 계산 (탐색)

- 사전 고정 추정기: station 수준 z²(동결 c_L 기준)를 distinct station 순서대로 넣는 conjugate 갱신. κ ~ InvGamma(a₀ = 3, b₀ = 2)(평균 1), 각 station은 z² ~ κ·χ²₁로 둔다.
- 각 case에서 NR-rand 순서 200개에 대해 사후 중앙값 κ > 1.5에 처음 도달하는 distinct station 수의 분포를 낸다(R4_aB 중심, 다른 case는 오경보 비율).
- 출력: `K10_KAPPA_CONVERGENCE.json`. **탐색**으로 표시한다. 추정기와 prior는 G1-MODEL-002에서 다시 정한다.

## 4. 해석 규칙 (사전 고정)

결과를 본 뒤 규칙을 바꾸지 않는다. "case 통과"는 누적 포함률 ≥ 0.88이고 평균 NEES ∈ [0.5, 2.0]인 것이다.

| 조건 | 해석 | G1-MODEL-002에 주는 영향 |
|---|---|---|
| K7: R4_aB의 V_model ≥ 0.5 | M-f = 관측 모델 오차 우세 | **Goal 1 관측 모델 수정을 먼저**(고각·거리 의존 LUT 오차). 구조 변경은 그 뒤 |
| K7: R4_aB의 V_model ≤ 0.2 | M-f = multipath site bias 우세 | 관측 모델 유지, 오차 구조(S-A/S-C/S-E)로 진행 |
| 0.2 < V_model < 0.5 | 혼합 | 두 경로를 모두 G1-MODEL-002 개발 arm으로 둔다 |
| K8: Spearman(\|e\|, max c) ≥ 0.5이고 Spearman(√R_E1, max c) ≤ 0.2 | "확신하며 틀림" = near-delay 오염을 J가 반영하지 못함 | Goal 1에서는 κ·heavy-tail로만 덮는다. c를 관측에서 추정해 쓰는 것은 Goal 2로 분류 |
| K8: 천장 반사가 Δ_tap 안에 드는 station에서 \|e\|가 유의하게 큼 | anchor standoff가 오차 원천 후보 | G1-RT-TB3-002 P-F(standoff 대조)의 우선순위를 높인다 |
| K3: NR-rand에서 R4_aB 제외 5 case 통과, R4_aB 미통과 | M-a 단독으로 integrity를 깸 | S-C(잠재 스케일) 필수 |
| K6-10: oracle 스케일 + Markov에서 6 case 통과 | M-b는 M-a가 있을 때만 문제 | S-A는 2차 arm |
| K6-10 미통과, K6-SKIP 통과 | 재방문 이중 계수가 독립 기전 | S-A 필수 |
| K6-SKIP도 미통과 | case 수준 oracle로 설명되지 않는 잔여 기전 | 구조 후보 재검토. G1-MODEL-002 착수 전에 기전을 더 분리 |
| K9: σ_β = 0.11에서 N* ≤ 20 | 정확도 주장은 교차 거리 형식으로 성립 가능 | 정확도 판정을 N* 형식으로 사전등록 |
| K9: σ_β = 0.11에서 N*가 `EXTRAPOLATED` 영역 | BLOCK_C로는 판단 불가 | 새 RT P-C(장거리) 또는 TR 다회 경로에서 판정 |
| K10: R4_aB 중앙 수렴 station 수 > 10 | κ가 run 안에서 제때 커지지 않음 | S-C 단독으로는 부족. κ prior 하한 또는 S-D(heavy-tail) 병행 |

## 5. 출력과 기록

`research/G1_SWEEP_HEADING_FLOOR_20261113/DIAG_K_20261114/` 아래:

```text
SPEC_KO.md            (이 문서)
code/                 (s2_code 복사본 + 진단 스크립트, CODE_SHA256.txt)
out/K0_REPRODUCTION.json
out/K1_…  …  out/K10_…
REPORT_KO.md          (§4 규칙 적용 결과, 표, 해석 경계)
MANIFEST.json         (입력 SHA, 명령, seed, 시각, 패키지 버전)
```

- 대용량 npz는 Git LFS로 둔다.
- REPORT_KO.md 첫 줄에 `DIAGNOSTIC_ONLY — S2′ 판정 불변`을 명시한다.
- §4 표의 각 행에 실제 값과 해당 여부를 채운다. 해당하는 행이 서로 모순되면 모순을 그대로 보고한다.

## 6. 실행 순서

1. K0(재현). 실패 시 중단.
2. K1, K2(재집계, 빠름).
3. K7, K8(관측 단계만, 필터 불필요). 결과가 §4 첫 세 행 중 하나에 해당하는지 먼저 확인한다.
4. K3, K4, K5, K6(필터 재실행).
5. K9, K10.

## 7. 해석 경계

- 6 case, 3 route, 2 m station 간격, 19점·90° sweep의 BLOCK_C 결과다. 0.45 m 간격과 TB3 5점·120° sweep으로 옮겨지지 않는다.
- oracle 항목은 상한·원인 분리용이다. "oracle 스케일이면 통과"는 "Goal 1 구조로 통과 가능"을 뜻하지 않는다.
- K9의 r2.1.0 DR 값은 단일 run(REPEAT 11/13)에서 왔다. σ_β는 격자로만 본다.

## 8. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-14 | 초판. Fable 답변(Q1 기전 분해, K1–K6)에 M-f(모델 오차 vs multipath), K7–K10, 사전 고정 해석 규칙 추가 | Claude |
