# EKF3 D6–D9 신규 진단 코드 — 사용자 직접 실행 절차

> **2026-10-13: 코드만 작성. D6/D7/D8/D9 신규 시뮬레이션 및 테스트는 작성자가 실행하지 않음. `NOT_RUN`; `scientific_PASS=false`.**
>
> 기준 연구 커밋 `43f755b75a5ac83fd6e7e67c3ef8f1f0da579d5d`, 기준 실행 코드 `701b8d2c29a4b3b879c4e27096168d6be463559b`.

## 0. 무엇을 수정했는가

신규 파일은 `diagnostics/`에만 작성했으며 기존 `ekf3.py`, `run_d0_d4.py`, `run_d5_regimes.py`, P0/P1/P2, RF `.npy`, LUT 및 D0–D5 결과를 **변경하지 않는다**.

| 파일 | 목적 | 실행 요건 |
|---|---|---|
| `d6_d9_common.py` | 동결 자산 SHA·shape 검사, Arc/UT3/4state-bias 프로토타입, 공통 출력 | 직접 실행 명령 없음 |
| `d6_nonlinearity_mc.py` | RF/bias 없는 통제 MC: 1차/UT/MC 공분산, 바나나형 오차 | NumPy |
| `d6_bias_observability.py` | paired noise에서 bias 삽입, 3state/UT/4state/진단용 oracle 대조, 관측가능성 선형화 | 동결 P0·RF H·LUT |
| `d7_cir_multipath_audit.py` | RX1/RX2 CIR 특징, tap/채널 오차항 분해, optional hybrid H | 동결 P0·RF H·LUT |
| `d8_polarization_quality.py` | LORO route-heldout 조건부 잔차 2차 모멘트 모델 (Q0–Q4) | D7 출력 |
| `d9_quality_aware_fusion.py` | F0–F6 재귀 필터 및 D5 F0 parity 검사 | P0·RF H·D7·D8 출력 |
| `test_d6_d9.py` | 모델·schema·oracle 방지 관련 synthetic 단위 테스트 | pytest, NumPy |

`d7`의 온라인 특징 CSV에는 `truth`, `error`, LoS counterfactual이 **일절 없다**. 정답을 이용한 평가 레이블은 별도 CSV에 저장되며 D8 **훈련/평가용**으로만 사용한다. D9는 레이블 CSV를 읽지 않는다.

**해석 주의:** 두 수신 포트는 물리적 ±45° RX1/RX2이다. RX1을 임의로 co-pol, RX2를 cross-pol이라고 고정 해석하지 않는다. 기존 `s`와 같은 tap의 전력비는 동등한 관측이므로 새로운 독립 정보를 제공하지 않는다.

## 1. 소스 준비 및 환경

```powershell
git fetch origin
git switch research/ekf3-d6-d9-diagnostic-code-20261013
python -m pip install numpy pytest
python research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py
```

먼저 39개 동결 P0 입력(일부 대용량 `.npy`)과 기존 archive source가 로컬에 있는지 확인한다. P0가 일치하지 않으면 D6-bias / D7 / D9는 중단한다. 각 스크립트는 별도 출력 디렉터리를 생성하며 **기존 경로를 덮어쓰지 않는다**.

## 2. Synthetic 단위 검사 및 D6 MC

```powershell
python -m pytest -q research/EKF3_INDEPENDENT_20261013/diagnostics/test_d6_d9.py
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_nonlinearity_mc.py --out artifacts/ekf3_D6_MC_01 --draws 5000
```

D6 MC는 RF 없는 순수 가우시안 초기 heading → nonlinear SE(2) 이동이다. 결과 `D6_MC_MOMENT_COMPARISON.csv`. 제로 process noise/zero bias로 nonlinear **원인만** 분리한다. 직진 평균 진행방향 오차는 정규분포에서는 이론식 `L(exp(-sigma_psi^2/2)-1)`과 비교한다. MC 샘플 5,000개가 독립 RF 장면을 뜻하지 않는다.

## 3. D6 실제 경로 — gyro bias/선형화 원인 분리

1개 case·seed의 실행 예시:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_bias_observability.py --out artifacts/ekf3_D6_BIAS_SMOKE --cases R2_aA_m0 --seeds 0 --levels 1
```

전체 개발 묶음 예시:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_bias_observability.py --out artifacts/ekf3_D6_BIAS_FULL --seeds 0 1 2 --levels 0 1 2
```

`M0` noise-only DR, `M1` noise-only LoS, `M2` additive bias DR, `M3` bias LoS, `M4` bias Full, `M5` bias + **oracle-model-consistent RF**이다. 조건마다 EKF3/UT3/BIAS4/BIAS4_UT와 oracle debias control을 비교한다. 최초 센서 noise stream은 고정하고 gyro-bias increment만 추가한다. Bias prior SD 기본 0.1°/s는 **사용자가 설정한 가정**이지 하드웨어 보정값이 아니다. `BIAS4`는 wheel yaw를 별도 관측으로 사용하지 않으며, bias 식별성이 자동 확보되는 것은 아니다.

출력 `D6_BIAS_ROUTE_ABLATION.csv`, `D6_BIAS_OBSERVABILITY.csv`. Observability 특이값은 true-state 선형화 + R0 iid의 낙관적 **상한 진단**으로만 해석한다. Gyro oracle 보정과 정답으로 만든 RF는 deployable 알고리즘의 성능으로 보고하지 않는다.

## 4. D7 CIR 물리 원인·온라인 품질 특징 추출

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d7_cir_multipath_audit.py --out artifacts/ekf3_D7_CIR_SMOKE --cases R2_aA_m0
python research/EKF3_INDEPENDENT_20261013/diagnostics/d7_cir_multipath_audit.py --out artifacts/ekf3_D7_CIR_FULL
```

D7 전체 실행 결과:

- `D7_ONLINE_CIR_FEATURES.csv`: Full/LoS RX1/RX2의 **진짜 측정으로 만들 수 있는** 특징만 저장. D9는 t0부터 전 시점의 이 CSV를 사용한다.
- `D7_ORACLE_EVALUATION_LABELS.csv`: 정답 거리/Heading/LUT 오차, flat/FFD/MP 거리 항등식, LoS tap에서의 Full s 대조(offline 전용).
- `D7_MANIFEST.json`: 코드, 출력 SHA 및 `scientific_PASS=false`.

동일 case의 채널 보간 수치 대조를 *추가로* 하려면 별도 출력 디렉터리로:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d7_cir_multipath_audit.py --out artifacts/ekf3_D7_HYBRID --hybrid-alphas 0 0.25 0.5 1
```

이 alpha 보간은 주어진 LoS/Full H의 수치상 반사실 결합이며 독립된 새 RF scene이 아니다. Delay spread/late-energy에는 Hann sidelobe 및 유한 bandwidth 누설도 들어가므로 단독으로 MP 검출 정답이라고 부르면 안 된다.

## 5. D8 경로 단위 홀드아웃 학습·검증

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d8_polarization_quality.py --d7 artifacts/ekf3_D7_CIR_FULL --out artifacts/ekf3_D8_LORO
```

D8은 **3개 route R2/R4/R5 모두 포함된 D7_FULL**로 실행한다. 학습 route와 평가 route를 완전히 분리하며, 평가 route의 XY 반경 `1e-4 m`와 겹치는 학습 샘플을 제외하고, 학습에서 동일 `case+pose_id` 반복은 한 번만 사용한다. Q0 고정 R0, Q1 s-only, Q2 CIR power/delay, Q3 CIR 편파 변화, Q4 복소 상대 위상을 비교한다. 기본 ridge penalty는 사전 고정 10이며 검증 성능으로 모델을 재선택하지 않는다.

주요 산출물: `D8_CIR_QUALITY_VALIDATION.csv`, `D8_HELDOUT_PREDICTIONS.csv`, `D8_FOLD_MODELS.json`. 학습 target은 편향을 포함한 `log(error^2+floor)`이므로 출력은 **조건부 제곱오차 규모(proxy second moment)**이지 엄밀한 무편향 관측분산이 아니다. 학습 route의 e_s/e_r 상관 추정은 저장하지만 보정되지 않은 same-time R_sr로 해석하지 않는다.

## 6. D9 재귀 융합 + 원래 D5 F0 parity

먼저 seed 0, level 1, 한 case, LoS/Full 비교:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d9_quality_aware_fusion.py --d7 artifacts/ekf3_D7_CIR_FULL --d8 artifacts/ekf3_D8_LORO --out artifacts/ekf3_D9_SMOKE --cases R2_aA_m0 --seeds 0 --levels 1 --conditions noise_pair --save-trace
```

D5 기준 실험 조건의 전체 재귀 비교:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d9_quality_aware_fusion.py --d7 artifacts/ekf3_D7_CIR_FULL --d8 artifacts/ekf3_D8_LORO --out artifacts/ekf3_D9_FULL --seeds 0 1 2 --levels 0 1 2 --conditions noise_pair gyro_bias gyro_sf all
```

F0 baseline / F1 UT / F2 4state bias / F3 Q3 RF R / F4 UT+R / F5 bias+R / F6 UT+bias+R, 각각 D0/A/B/C. 기본값은 `B_OLD` 거리 평균보정 및 `R_sr=0` **(미검증 대조 가정)**. `--range-model E1_FULL_LORO`는 Full RF에서만 E1을 사용하고 LoS는 B_OLD 유지한다. `--use-trained-rsr`는 **학습 route의 상관계수를 써 보는 실험적 옵션**이며 기본값 OFF다.

D9는 `F0_ORIGINAL`의 일치하는 조건이 있는 경우 게시된 D5 원본의 case·seed·channel·arm별 Heading/XY RMSE, pose/heading NEES, coverage와 `1e-8` 이내 일치하는지 검증한다. 실패하면 출력 폴더를 만들기 전에 중단한다. `--skip-d5-parity`는 D5에 없는 새 seed/조건을 별도로 평가하는 경우에만 사용하고 그 경우 parity를 `NOT_RUN`으로 기록한다. **실제 계산을 하지 않고 PASS를 기록하지 않는다**.

D9에 공급되는 품질 특징은 D7 `ONLINE` CSV에서만 오고 Q3 계수는 D8 `heldout_route`가 현재 case의 route인 fold만 선택한다. 실험 중 학습·refit은 일절 하지 않는다.

## 7. 완료 판정과 한계

- PASS 실행 증빙은 사용자 실행 후 실제 exit code, SHA, csv row count, 원본 P0와 P3 checksum, 기준 D5 parity를 검증한 경우에만 기록한다.
- D6–D9의 결과가 좋더라도 기존 Full RF H는 하나의 corridor에서 생성된 것이며, 여러 motion seed와 LORO route는 독립 RF 환경이 아니다.
- D6 bias 조건은 drift/step noise 분리용 구성이고, `all`에는 다른 미모델링 오차가 공존한다. 3state EKF에는 gyro bias 상태가 없다.
- 단일 측정의 error RMSE 감소와 통계적 일관성·독립 환경 일반화는 별도 문제이다. `scientific_PASS=false` 유지.
- 코드는 추후 사용자가 직접 실행 후 로그를 전달할 때만 새 실험의 결과를 평가한다.
