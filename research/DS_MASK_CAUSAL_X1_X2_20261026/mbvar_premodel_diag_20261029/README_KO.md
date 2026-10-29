# MB_VAR 모델링 전 진단 (마운트 0) — 2026-10-29

경로별 수정에 앞서, 기존 검증에서 다루지 않은 세 문제를 먼저 진단한 기록이다.

- D1 일반화
- D2 고정 gate
- D3 innovation과 RF 잔차의 분리

**진단 전용이다.** 여기서 쓴 m, 시간 구간, σ_b 재적합 값은 필터 설정으로 쓰지 않는다.

## 범위와 재현성

- **기준 코드:** `pol_bias_model/exp_pb.py`를 수정 없이 import했다. 브랜치는 `research/ds-state-info-var-forensics-20261028`, commit `4ad94fe`이다.
- **입력:** `reflect_model/fetch_inputs.sh`로 받았다(commit `9bcd5da`, `FETCH_RF=0`). hash는 `INPUT_LOCK.sha256`에 있다.
- **조건:** R2/R4/R5 × anchor A/B × gyro bias B0/L0/L1/L2로 24조건이다. L0–L2는 B0와 RF packet을 공유하므로 독립 환경이 아니다.
- **Parity:**
  - 저장된 R4_aB_m0 B0 점수를 정확히 재현했다(MB_VAR 1.3914° / 8.8654 cm).
  - BB_ORIG를 자체 gate로 돌리면 BASE mask·궤적과 24/24 일치한다(`results/PARITY.csv`).
  - 저장소 경로판 코드로 R5_aA B0 MB_VAR fixed/self 점수를 재현했다.

## 실행

```
bash reflect_model/fetch_inputs.sh        # REFLECT_ROOT=<inputs>, FETCH_RF=0
REFLECT_ROOT=<inputs> python3 -I mbvar_premodel_diag_20261029/code/diag_mbvar.py --out <out>
REFLECT_ROOT=<inputs> python3 -I mbvar_premodel_diag_20261029/code/diag_overcount.py --out <out>
```

## 결과 파일

| 파일 | 내용 |
|---|---|
| `D1_SIGMA_TABLES.csv` | σ_b(ρ) 비교: hand table vs 참값 상태 잔차분산 적합(전체 경로 / leave-one-route-out) |
| `D1_GENERALIZATION_SCORES.csv` | 위 table별 MB_VAR 점수(고정 gate). NONE = MB_ORIG |
| `D2_GATE_SCORES.csv` | BB/MB × ORIG/VAR를 고정 BASE gate와 자체 NIS gate(9.2103)로 비교. 수용 수, 최장 공백, gate 전 NIS |
| `D2_GATE_FLIPS.csv` | 자체 gate에서 새로 수용·거절된 packet의 시각과 \|ε_s\|/√R_ss |
| `D3_DECOMPOSITION.csv` | ν = ε + [h(x_true) − h(x̂⁻)]의 정확 분해. ε²/R, δh²/HPHᵀ, ν²/S, 몫, n_eff |
| `D3_EPS_BY_DISTANCE.csv` | 거리 bin별 RF 잔차(모든 유한 packet, gate 선택 없음)의 평균·RMS와 √R |
| `D3_EPS_TEMPORAL.csv` | ε의 자기상관(lag-1, 1/e 길이 [s, m]), n_eff |
| `D3_R5A_WINDOWS.csv` | R5_aA B0 시간 구간별 분해 |
| `D3b_OVERCOUNT_TEST.csv` | 정보량 축소 시험. DEC_m = accepted packet m개 중 1개 사용, RSC_m = R×m |

## 주요 수치 (B0, t ≥ 30 s, 고정 gate, s 성분 기준)

### 1. RF 잔차와 state 오차

**RF 잔차는 R 이하이다.**

- ε²/R: MB_ORIG 0.16–1.34, MB_VAR 0.11–0.68
- R을 넘는 조건은 R4_aA(MB_ORIG 1.34) 하나다.
- 거리별로 ε_s RMS가 √R_ss를 넘는 구간은 ≥10 m와 R4의 6–10 m뿐이다.

**State 오차는 HPHᵀ보다 크다.**

- δh²/HPHᵀ: MB_ORIG 1.3–23.3, MB_VAR 0.58–12.6
- R4_aB와 R5_aA가 가장 크다.
- ν² 중 RF 몫은 0.83–1.13이다.
- MB_VAR의 gate 전 NIS 평균은 0.34–1.02로, 기준값 2보다 낮다.

**ε_s는 시간 상관이 강하다.**

- lag-1 상관: 0.73–0.95
- 1/e 상관 길이: 0.4–3.6 s
- n_eff / N = 1/6 – 1/37

**R5_aA 60–120 s 구간:**

- MB_VAR: ε_s²/R = 0.27, δh²/HPHᵀ = 22.7. 다른 구간은 0.64–2.5이다.
- 평균 ε_s = 0.012이다.

**R_rr (MB에서 BASE R 재사용):**

- MB의 ε_r²/R_rr은 0.17–0.41이다. BB는 0.35–0.70이다.
- R_rs = 0으로 가정되어 있지만, ε_r–ε_s 상관은 −0.39 ~ +0.23이다.

### 2. 정보량 축소 시험

정보량을 줄이면 z_ψ와 δh²/HPHᵀ가 1 근처로 내려간다.

- **R5_aA, MB_ORIG:** DEC1 → DEC16에서 4.17° / 41.8 cm → 1.34° / 12.5 cm, z_ψ 2.79 → 0.43
- **R5_aA, MB_VAR DEC16:** 1.11° / 10.6 cm (MB_ORPOL 0.91° / 7.77 cm)
- **R4_aB:** m = 16에서도 z_ψ = 1.22로 1에 도달하지 않는다.
- **예측력:** z_ψ = 1이 되는 m과 (N/n_eff)·(ε²/R)의 Spearman 상관은 0.3이다.

### 3. Gate

MB_VAR 기준이다.

| 항목 | 고정 BASE gate | 자체 gate |
|---|---|---|
| BB_ORIG 대비 Heading·XY 모두 개선 | 19/24 | 8/24 |
| 고정 gate 대비 둘 다 악화 | — | 24/24 |
| 최대 Heading 비율 (BB_ORIG 대비) | 1.01 | 2.09 (R5_aA) |

- 새로 수용된 packet은 조건당 8–47개다.
- 그 packet의 \|ε_s\|/√R_ss 중앙값은 1.5–3.3이다(R2_aB만 1.5, 나머지 2.5–3.3). 공통 수용 packet은 0.19–0.58이다.

### 4. 일반화

**Provenance:**

- μ_B·μ_M·R은 PJ_SEPARATE_RS `fit_models`에서 경로 제외(R2/R4/R5 fold) 방식으로 학습됐다. 단, 같은 corridor 안이다.
- in-sample인 것은 σ_b table과 VAR 형태의 선택이다.

**σ_b 재적합 결과:**

- 잔차분산으로 적합한 σ_b는 0–6 m에서 floor(0.005)이다.
- 10 m 값: 전체 경로 0.109, LORO 0.048–0.140, hand table 0.24

**BB_ORIG 대비 Heading·XY 모두 개선:**

| σ_b table | 개선 조건 수 |
|---|---|
| Hand | 19/24 |
| 전체 경로 적합 | 9/24 |
| LORO 적합 | 8/24 |
| 없음 (MB_ORIG) | 8/24 |

## 주장 경계

- 모든 결과는 단일 corridor의 시뮬레이션 packet에서 나왔다. 실측과 다른 환경에 대한 일반화를 주장하지 않는다.
- DEC/RSC의 m과 R5_aA 구간은 truth를 보고 사후에 고른 값이다. 방법이나 설정이 아니다.
- δh²/HPHᵀ는 측정 공간으로 사영한 state 오차의 일관성 지표다. state 공간의 NEES를 대체하지 않는다. heading z RMS와 XY coverage는 별도 열에 있다.
- 해석과 결론 문장은 저자가 따로 작성한다. 이 문서는 수치 기록이다.
