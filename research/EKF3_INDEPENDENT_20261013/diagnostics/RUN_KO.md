# EKF3 D0–D5 사용자 직접 실행 지침 (Windows PowerShell / Linux)

**코드 준비 완료, 실행은 사용자 담당.** 기존 6-State/P0/P1/P2/기존 RF 원자료를 수정·덮어쓰지 않는다. D0–D4는 원 GitHub Actions P2 아티팩트의 파일을 **입력**으로 사용한다. 수치가 나오기 전에는 성능 개선/과신의 새 판정을 내리지 않는다.

## 0. 브랜치 받기 / 환경

```powershell
git fetch origin
git switch research/ekf3-independent-p0-20261013
git pull --ff-only origin research/ekf3-independent-p0-20261013
python -m pip install numpy pytest
```

Frozen RF H (.npy), LUT 및 P0 소스가 로컬 체크아웃에 존재해야 한다. 기존 동결 입력 확인:

```powershell
python research/EKF3_INDEPENDENT_20261013/p0_verify_inputs.py
```

**확인:** `PASS_LOCAL_SHA256_SHAPE_POSE_PREFLIGHT`. 원본 SHA/shape 오류가 있으면 분석하지 않는다.

## 1. 이미 실행된 P2 One-step 아티팩트 가져오기

공식 P2 GitHub Actions 38331588521 (seed 0, 7 case × LoS/Full):
https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118

GitHub CLI 설치/로그인되어 있다면:

```powershell
gh run download 38331588521 --repo myoungsunk/sionna-resimulation --name ekf3-p2-frozen-rf-one-step --dir research/EKF3_INDEPENDENT_20261013/diagnostics/P2_DOWNLOAD
```

CLI가 없다면 브라우저에서 아티팩트 ZIP을 받아 동일 폴더에 풀어놓는다. 결과적으로 다음 파일이 있어야 한다.

```text
research/EKF3_INDEPENDENT_20261013/diagnostics/P2_DOWNLOAD/P2_OUT/
  P2_ONE_STEP_SUMMARY.json
  R2_aA_m0_full_seed0_ONE_STEP.npz
  R2_aA_m0_los_seed0_ONE_STEP.npz
  ...
  R5_aB_m0_full_seed0_ONE_STEP.npz
  R5_aB_m0_los_seed0_ONE_STEP.npz
```

D0에서 요약 SHA 및 14개 NPZ 해시를 재검증한다.

## 2. 진단 코드 단위 계약 검사 (사용자가 실행)

```powershell
python -m pytest -q research/EKF3_INDEPENDENT_20261013/diagnostics/test_diagnostics.py
```

테스트 코드는 flat 채널, P3 frozen E1 SHA, D1 fractional, 원 observer와 P3 특징 일치, 공분산 Schur 항등식, Range-only 보정 시 A 결과 불변 등을 검사한다. **테스트 통과는 실 RF 연구 결과의 PASS와 다르다.**

## 3. D0–D4 — 최초 1개 센서 seed 진단/재분석 (사용자가 실행)

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/run_d0_d4.py --p2-dir research/EKF3_INDEPENDENT_20261013/diagnostics/P2_DOWNLOAD/P2_OUT --seed 0 --out research/EKF3_INDEPENDENT_20261013/diagnostics/OUTPUT_D0_D4_SEED0
```

**가장 먼저 읽을 파일**

- `D0_D1_METRICS.csv`: 같은 prior A/B/C, corrected B/C의 Heading/XY RMSE·NEES·coverage.
- `D2_HEADING_DECOMPOSITION.csv.gz`: 각 시점의 RF-s/Range Heading Gain 기여 및 실제 오차제곱 변화.
- `D3_FLAT_FFD_MP_AND_POLARIZATION.csv.gz`: e_flat/e_ffd/e_mp, first-path tap 효과 vs 동일 tap 편파 간섭.
- `D4_RANGE_RESIDUAL_BY_DISTANCE.csv`: D1/E1 보정 후 거리별 잔차 RMS/분산.
- `D4_S_RESIDUAL_BY_DISTANCE.csv`: s의 모델오차 vs 원 R0.
- `D4_NIS_VS_HEADING_HARM.csv`: 정규화 측정 잔차 크기와 실제 Heading 악화율.
- `D4_CROSS_CHANNEL_AND_TEMPORAL_AUDIT.csv`: s/r 오차의 상관 및 지속성.
- `D0_D4_ARM_SUMMARY_DESCRIPTIVE.csv`: 전체 case 설명용 표. 시간·seed 독립성 미보장.

**특히 검증할 invariant:** E1/D1 적용 전후 A의 상태/공분산은 완전히 동일(Heading-only는 range 사용 안 함), D0는 그대로, 오직 B/C가 Range 측정 보정에 따라 바뀐다. B_OLD는 기존 P2 행렬·Gate를 1e−9 이내 재현. D3 Flat+FFD+MP 및 두 종류의 s 항등식이 맞지 않으면 즉시 실패.

새 출력 디렉터리가 이미 존재하면 overwrite하지 않고 중단한다. 다른 실행 ID를 지정한다.

## 4. D5 — 재귀적 A/B/C 검증 (초기 smoke, 사용자가 실행)

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/run_d5_regimes.py --out research/EKF3_INDEPENDENT_20261013/diagnostics/OUTPUT_D5_SMOKE --seeds 0 1 2 --levels 0 1 2 --conditions noise_pair all --channels los full --range-models B_OLD E1_FULL_LORO
```

아직 개발 seed 20개/확증 50개를 돌리기 전, 위 3개 seed로 각 팔 데이터의 수학·재현성·종료 코드를 먼저 확인한다. 완료 후 동일 명령에 개발/확증 seed 목록을 독립적으로 넣어 실행하며, 새로운 출력 디렉터리를 사용한다.

특정 DR 오차의 영향을 분리하려면 user-run smoke 성공 후 다음처럼 조건을 독립적으로 선택할 수 있다.

```powershell
python research/EKF3_INDEPENDENT_20261013/diagnostics/run_d5_regimes.py --out research/EKF3_INDEPENDENT_20261013/diagnostics/OUTPUT_D5_ISOLATED --seeds 0 1 2 --levels 0 1 2 --conditions noise_pair gyro_bias gyro_sf wheel_asymmetry slip all --channels los full --range-models B_OLD E1_FULL_LORO
```

D5는 전 시점 posterior를 다음 시점 Prediction으로 전달하는 **재귀적 Full-route EKF**이다. D0–D4는 P2 저장 DR-only prior에서 단 한 번만 보정하는 **One-step Counterfactual**이므로 두 수치를 섞지 않는다.

주요 출력: `D5_MULTI_SEED_FULL_ROUTE_METRICS.csv`, `D5_RUN_MANIFEST.json`. `--save-full-sample-trace`를 사용하면 시점별 전체 추정 궤적 CSV를 추가 저장할 수 있다.

## 5. 실행·보고 계약

1. SHA/P0/source/LUT/observer-parity 실패 시 분석 중단. "PASS"로 기록하지 않음.
2. D4의 Range 수정은 **측정 평균만** 수정하며 `Rr,Rs,Rsr,Q`를 자동 재보정하지 않는다. 이 값의 효과를 독립적으로 식별하기 위함이다.
3. Full에 대해 E1은 route LORO 계수 사용; LoS E1 적용은 D4 음성 대조군만. D5에서는 LoS E1을 우회한다.
4. Truth로 계산한 e_flat, e_mp, e_s, 오차, offline NIS/NEES는 **평가용**이다. 온라인 갱신에 truth 사용 금지.
5. 결과가 좋아도 하나의 corridor에서 반복된 sensor seed / fixed RF H 실험일 뿐 새로운 실환경 일반화가 아니다. `scientific_PASS=false`를 바꾸지 않는다.
6. 테스트 결과를 붙일 때는 `D0_D4_RUN_MANIFEST.json`, `D5_RUN_MANIFEST.json`, 해당 CSV, 실행 stdout/stderr 및 코드 커밋 SHA를 같이 보존한다.

## 6. 주의: 독립 공간 평가의 제한

E1 모델의 학습은 heldout route를 제외하지만, 기존 원래 12-case 학습에서 **다른 route와 같은 XY 한 곳이 학습에 포함된 이력**이 있다. 따라서 동일 scene의 위치/관측 시점을 독립 실험으로 과대해석하지 않으며, 후속 확증에서는 공유 XY 평가 제외·새 scene을 분리한다.

사용자가 실제 실행한 로그와 CSV가 전달되기 전까지 D0–D5는 **NOT_RUN**이다.
