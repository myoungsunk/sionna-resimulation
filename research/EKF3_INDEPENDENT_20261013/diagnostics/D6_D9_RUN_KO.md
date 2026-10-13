# EKF3 D6–D9 REDIRECT 보완판 — 사용자 직접 실행 지침

**분리된 상태:** 코드 수정 및 단위 검사용 코드만 준비. 대규모 동결 RF 재실행은 사용자가 직접 시행한다. `D6_D9_FULL_EXPERIMENT=NOT_RUN`, `scientific_PASS=false`.

- 원본 기준: `43f755b75a5ac83fd6e7e67c3ef8f1f0da579d5d` (`701b8d2c29a4` 실행 소스).
- 수정 대상: `research/EKF3_INDEPENDENT_20261013/diagnostics/`의 신규 파일만.
- 원본 EKF3, D0–D5, P0/P1/P2, RF H/LUT, archive sensor-v2 코드는 변경하지 않음. 실행 시 **원본 5개 코드/manifest Git blob SHA-1** 및 **P0 39개 입력의 SHA-256** 사전 검증.
- 완료 매니페스트는 파일 SHA-256, 실행된 code SHA-256, Git commit(조회 가능 시), 기준 소스 SHA, 모든 실행 인자, 과학적 미통과 경고를 포함. 매니페스트 생성 전 오류는 `INCOMPLETE`로 해석. 기존 출력 경로에 덮어쓰기 금지.

## 1. 업데이트 코드 범위

| 파일 | 역할 |
|---|---|
| `d6_d9_common.py` | import 수정, 원본 SHA 고정, 엄격한 JSON 변환, 원자적 출력·매니페스트, F0/UT/BIAS4 지원 |
| `d6_d5_trace_audit.py` | 원본 **로컬 D5 NPZ** 해시 확인, 추적 추정값으로 공분산·NEES·95% 포함률 및 기준 D5 지표 전셀 비교 |
| `d6_nonlinearity_mc.py` | 초기 yaw 불확실성만 변화, EKF/UT/MC/2차 모멘트/해석적 모멘트 비교, 2D 타원·왜도 |
| `d6_bias_observability.py` | 동일 센서 잡음시퀀스에서 gyro bias 분리; gyro vs **wheel yaw 대체 입력** 대조; prior/post 공분산 |
| `d7_cir_multipath_audit.py` | 원 receiver parity; 별도 online CIR vs offline truth label; **원본 P3 E1 Full range 잔차** 별도 생성 |
| `d8_polarization_quality.py` | B_OLD/E1별 서로 다른 range label; 조건부 mean과 중심화 residual scale 학습; route-heldout gate |
| `d9_quality_aware_fusion.py` | F0–F6; 모델·range 보정의 엄격한 일치 검사; 조건부 mean 보정 후 residual R; **요청된 모든 D5 F0 셀** 검사 |
| `d6_d9_verdict.py` | 사용자 실행 결과만 근거로 하는 가설별 탐색적 판정 (독립 RF scene 확증 아님) |
| `test_d6_d9.py`, `test_d6_d9_contracts.py` | import/receiver 모델/최초 EKF3 독립 baseline/JSON·E1 계약·원본 해시·parity 실패 회귀 |

### 원천 데이터 경계

- D7 `D7_ONLINE_CIR_FEATURES.csv`에는 정답거리, 실제 Heading, LoS 전용 counterfactual 또는 error label이 없음.
- D7 `D7_ORACLE_EVALUATION_LABELS.csv`에 B_OLD 및 Full 전용 E1 range 잔차(및 오차 항등식) 저장. D8 훈련·평가에서만 이용.
- D8의 학습 target 및 거리 보정은 **`range_model`에 귀속**. LoS E1은 생성하거나 학습하지 않음.
- D8 Q0은 R0·mean 0, Q1–Q3는 train-only 조건부 편향과 *편향 제거 후* 오차제곱 규모를 각각 추정. 이것 역시 통계적으로 검증된 R은 아님.
- RX1/RX2 물리 ±45° 수신 포트는 회전 시 보편적인 co/cross 채널에 대응하지 않음. 기존 s와 동일 tap의 전력비는 중복 특징임.
- **Q4 phase는 기본 비활성.** 독립 RX 상대위상·신호 잡음 전력에 대한 실제 보정 원본 및 SHA를 담은 JSON을 제공해야만 검토. `phase_valid`만으로는 불충분.
- `--use-trained-rsr`는 **무조건 차단**. 현재 독립 잔차 공분산 교정 없음; `R_sr=0` 대조 가정 유지.

## 2. 우선 실행하는 단위·계약 테스트

```powershell
git fetch origin
git switch research/ekf3-independent-p0-20261013
git pull --ff-only origin research/ekf3-independent-p0-20261013
python -m pip install numpy pytest
python -m pytest -q research/EKF3_INDEPENDENT_20261013/diagnostics/test_d6_d9.py research/EKF3_INDEPENDENT_20261013/diagnostics/test_d6_d9_contracts.py
python research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py
```

1) import/pytest 수집부터 FAIL이면 실행 중단. 2) 원본 Git blob 5개 SHA, P0 39개 입력 무결성 불일치면 실행 중단. 3) 기존 D5 trace가 로컬에 없다면 D6-D5 독립 감사 단계를 `NOT_RUN`으로 남긴다.

## 3. D6-0 기존 D5 trace 독립 감사 (선행 권장)

`LOCAL_TRACE_INDEX.json`에 기록된 원래 로컬 폴더를 `--local-root`로 지정한다. 상대경로 `D5_PARTS/.../evidence/*.npz`를 그대로 보존한다.

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_d5_trace_audit.py --local-root 'D:\SLAM_bot\artifacts\EKF3_P0_VERIFY_20261013_01a132b7\DIAGNOSTICS_701b8d2' --out artifacts/ekf3_D6_D5_TRACE_FULL
```

먼저 한 case만 검사하려면:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_d5_trace_audit.py --local-root 'D:\SLAM_bot\artifacts\EKF3_P0_VERIFY_20261013_01a132b7\DIAGNOSTICS_701b8d2' --out artifacts/ekf3_D6_D5_TRACE_SMOKE --cases R2_aA_m0
```

`--cases`는 **PARTIAL_SMOKE** 판정. 전체로 실행할 때는 index에 등록된 모든 1,134 FILTER trace와 378 motion NPZ를 SHA 검증하고, 4,536개 기준 D5 지표 행과 일치하는지 확인한다. 하나라도 부족하면 FAIL. 결과 `D6_D5_TRACE_COVARIANCE_AUDIT.csv`와 검증 index CSV.

## 4. D6-1 선형화 통제 Monte Carlo

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_nonlinearity_mc.py --out artifacts/ekf3_D6_MC_SMOKE --draws 500 --paths straight --distances 10 --heading-std-deg 17 20
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_nonlinearity_mc.py --out artifacts/ekf3_D6_MC_FULL --draws 5000
```

새 출력 `D6_MC_MOMENT_COMPARISON.csv`: yaw 초기 불확실성만 유지, EKF/UT/MC vs 2차/해석적 모멘트, 2D 95% 위치 타원 포함률, 진행방향 skewness·분산비. Synthetic MC는 RF 검증이 아니다.

## 5. D6-2 편향·운동학 원인 분리

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_bias_observability.py --out artifacts/ekf3_D6_BIAS_SMOKE --cases R2_aA_m0 --seeds 0 --levels 1 --save-step-trace
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_bias_observability.py --out artifacts/ekf3_D6_BIAS_FULL --seeds 0 1 2 --levels 0 1 2
```

출력 `D6_BIAS_ROUTE_ABLATION.csv`, `D6_BIAS_OBSERVABILITY.csv`, `D6_KINEMATIC_CONTRACT.csv`. `--save-step-trace` 사용 시 모든 평가 시점의 `Ppsi_prior/post`, 진행방향 prior/post 분산을 기록. `WHEEL_YAW3`는 **gyro 입력을 wheel yaw 입력으로 대체**하는 민감도 대조군이다. 둘을 독립 측정처럼 동시에 더하지 않으며 slip 강건성의 증거가 아니다. 동결 legacy-Euler과 SE2 궤적 불일치 계산은 별도 offline 기하 진단일 뿐 RF H/진짜 경로를 이동시키지 않음.

## 6. D7 CIR 오염 및 E1 레이블 추출

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d7_cir_multipath_audit.py --out artifacts/ekf3_D7_SMOKE --cases R2_aA_m0
python research/EKF3_INDEPENDENT_20261013/diagnostics/d7_cir_multipath_audit.py --out artifacts/ekf3_D7_FULL
```

이 단계에서는 **반드시 D7_FULL 전체 3 routes**를 D8에 사용한다. online feature의 tap/전력 parity가 달라지면 중단하며, E1 레이블은 동결 LORO 계수로 생성하고 truth는 평가에만 사용한다. `--hybrid-alphas`는 재생 scene이 아닌 수치상 반사실 counterfactual임을 명시한다.

## 7. D8 B_OLD/E1 분리 품질 모델

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d8_polarization_quality.py --d7 artifacts/ekf3_D7_FULL --out artifacts/ekf3_D8_LORO
```

D8은 B_OLD와 Full RF용 E1을 **서로 다른 Range 학습 label**로 학습한다. `D8_FOLD_MODELS.json`의 각 route/channel/`range_model`에 별도 `s,r` 모델과 조건부 편향·중심화 오차 규모를 저장한다. 모든 route 단위 heldout gate는 정해진 Q3 vs Q0 NLL 개선 및 오차분산 비율 임계값을 저장한다.

`Q4_COMPLEX_PHASE`는 독립 보정 증빙 미제공 시 `NOT_RUN...MISSING`으로 명시됨. Phase 모델을 시험하려면 실제 독립 수신기 위상/잡음 보정 원본 파일을 함께 제공하고, 그 SHA 및 캘리브레이션 값을 기록한 `--phase-evidence path.json`이 필요하다. 하드웨어 독립 증빙 없이 수치상의 위상비만으로 Q4를 구동하지 않음.

## 8. D9 재귀 필터 & D5 독립 parity

우선 단위 검증이 끝난 후 **기준선 F0만** 실행:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d9_quality_aware_fusion.py --d7 artifacts/ekf3_D7_FULL --d8 artifacts/ekf3_D8_LORO --out artifacts/ekf3_D9_F0_SMOKE --cases R2_aA_m0 --seeds 0 --levels 1 --conditions noise_pair --methods F0_ORIGINAL --save-trace
```

품질 모델 자체의 route-heldout gate가 통과한 경우만 F3–F6 포함 가능:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d9_quality_aware_fusion.py --d7 artifacts/ekf3_D7_FULL --d8 artifacts/ekf3_D8_LORO --out artifacts/ekf3_D9_SMOKE --cases R2_aA_m0 --seeds 0 --levels 1 --conditions noise_pair --methods F0_ORIGINAL F1_UT F2_BIAS4 F3_CIR_R F4_UT_CIR_R F5_BIAS4_CIR_R F6_UT_BIAS4_CIR_R --save-trace
```

E1 range를 평가할 경우 **선택한 보정에 대해 학습한 `range_model=E1_FULL_LORO` Fold만 허용**:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d9_quality_aware_fusion.py --d7 artifacts/ekf3_D7_FULL --d8 artifacts/ekf3_D8_LORO --out artifacts/ekf3_D9_E1_SMOKE --cases R2_aA_m0 --seeds 0 --levels 1 --conditions noise_pair --range-model E1_FULL_LORO --methods F0_ORIGINAL
```

D9의 `F0_ORIGINAL`은 원본 `EKF3`을 그대로 사용하며, 사용자 지정 **모든** `(case, channel, range_model, condition, level, seed, arm)` 셀에 대해 원본 D5 CSV의 RMSE/NEES/coverage/n/채택·거절 건수와 parity를 확인한다. 하나라도 없거나 불일치하면 중단하고 PASS manifest를 만들지 않는다.

- `--skip-d5-parity`는 새로운 시드·조건 등 원본에 없는 비교에 한해서만 명시적으로 사용. `parity=NOT_RUN`으로 기록. 본 검증 PASS 아님.
- `--exploratory-unvalidated-quality`는 D8 heldout gate가 FAIL이어도 Q3 실험을 강제로 수행할 수 있으나, **탐색적 불확실 모델임을 명시**. 사후 성능 개선 주장의 근거로 사용하지 않음.
- `--use-trained-rsr`는 현재 차단됨.
- `D9_RECURSIVE_FUSION_METRICS.csv`에 Heading·2D RMSE, 95% 오차 분위수, NIS lag1, prior/post Heading 분산, NEES 및 coverage 저장. 선택적 `--save-trace`는 개별 시점 값을 기록.

## 9. 가설별 탐색적 보고

각 실험을 실제 사용자 실행한 후:

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/d6_d9_verdict.py --d6-mc artifacts/ekf3_D6_MC_FULL --d6-bias artifacts/ekf3_D6_BIAS_FULL --d6-d5-trace artifacts/ekf3_D6_D5_TRACE_FULL --d7 artifacts/ekf3_D7_FULL --d8 artifacts/ekf3_D8_LORO --d9 artifacts/ekf3_D9_SMOKE --out artifacts/ekf3_D6_D9_VERDICT
```

아직 실행하지 않은 단계는 해당 옵션을 생략한다. D6 local trace가 없으면 verdict에 `NOT_RUN / INCONCLUSIVE`로 기록한다. `SUPPORTED/PARTIALLY_SUPPORTED/NOT_SUPPORTED/INCONCLUSIVE`는 **같은 RF scene 내 탐색적 지지 여부**를 나타내며, 독립 RF scene/확증 seed의 `scientific_PASS`와 완전히 별개이다.

## 10. 재감사 전제 조건

- 신규 코드의 import, 단위/계약 테스트, 모든 stage의 smoke 실행 증빙.
- 원본 코드/P0 SHA·RF receiver parity·D5 F0 parity.
- D8 보정별 Range 타깃 계약, phase Q4 차단, R_sr 차단.
- 매니페스트의 실제 실행 Git commit과 코드 SHA 및 결과 해시.
- 위 조건 완료 전 `code_audit=REDIRECT`, `execution_ready=false`, `D6_D9_full_experiment=NOT_RUN`, `scientific_PASS=false`.
