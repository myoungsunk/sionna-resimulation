# N4-C — Full RF Joint4/SR4 Joint Range–s Mean / Covariance / Robust 실제 재귀 실험 (2026-10-15)

**핵심 판정: `TECHNICAL_EXECUTION_PASS`, `SCIENTIFIC_DEPLOYMENT_PASS=false`.**

## 1. 원본 동결·실행 증거

- [N4-C 재귀 실행 Run 38714046562](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38714046562): source `7ae79e2372efaef114670f88e5e9be51cb8d3442`, 코드 감사 GO, 원본 RF/R2/N4B ZIP SHA·CRC, 수학 테스트 PASS, 모든 재귀 실행 PASS.
- [N4-C 재귀 추정·공분산 전체 artifact 11962810669](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38714046562/artifacts/11962810669), ZIP SHA256 `f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9`.
- [독립 결과 감사 Run 38715157425](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38715157425), [후속 검증 artifact 11961733993](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38715157425/artifacts/11961733993), SHA256 `7e83aff7c46eac91afb4371e5dcb5eb8464328c661f7d97270ab1f3cb5a8bcd0`.
- 원본 `Joint4,SR4` 직접 재귀 baseline 32개 Source-parity 검사: state/cov max difference ≤1e−6, Gate decision differences 0. 이는 모두 1e−9 strict equivalence였다는 주장은 아님. 원본 R0, P3 observer, LoS FFD 2° LUT, sensor-v2 gyro/wheel stream, initial states, seed=0 변경 없음.
- B0·L0(+0.01°/s)·L1(+0.05°/s)·L2(+0.20°/s), Full/LoS, AnchorA Mount0/45, Joint4/SR4, 829 평가 시점/케이스. 304개 재귀 평가 행, 32개 원본 baseline 대응.
- 11 Full RF 방법×2 solver×2 mount×4bias plus 3 shared-gate counterfactual controls and LoS transfer 5 methods. 전체 raw posterior x/P/status/NIS 보존.
- N4-B 물리 오차모델은 `R2` held-out OOF (훈련 R4+R5) 자료로만 예측하고, GT는 motion simulator/오프라인 성능 계산에만 사용. 같은 복도·단일 RF 환경·단일 motion seed 범위를 넘겨 일반화 주장 불가.

## 2. 구현 계약과 상관 공분산을 반영한 SR4

상태는 `[x,y,ψ,b_g]`. 원래 `z=[r,s]`, LoS LUT `h(x)=[h_r,h_s]`. 관측 평균·공분산 `mu=[mu_r,mu_s]`, `R=[[V_r,C_rs],[C_rs,V_s]]`.

Joint4는 `z-mu`와 `R`로 원래 Joseph EKF Gaussian update.

SR4는 `a=C_rs/V_r`와 `V_s|r=V_s-C_rs²/V_r`로 다음과 같이 같은 packet을 **한 번씩만 조건부 사용**:

1. Range `z_r-mu_r` 대 `h_r(x)`, variance `V_r`.
2. `z_s-mu_s-a(z_r-mu_r)` 대 `h_s(x)-a h_r(x)`, variance `V_s|r`. Range 후 `h_r,h_s,H` 재선형화.
3. 공동 prior innovation NIS로 원래 99% 2DOF gate; 공통 gate 대조에서는 원 R0 수용 시간표 강제.

30개 랜덤 SPD 선형 Gaussian canary에서 Joint EKF/조건부 SR4 posterior 일치(max deviation `<1e−11`) 및 baseline source 코드와의 수치 일치 확인. Nonlinear SR4≠Joint4가 반드시 엄밀 동등해야 한다는 주장은 하지 않음.

## 3. N4-C 정책 목록

| 이름 | Mean | R | 성격 |
|---|---|---|---|
| BASE_R0 | 0 | frozen diag `R0` | 동결 기준 |
| GLOBAL_MEAN_ONLY | Full R4/R5 평균 | original R0 | 평균 보정 단독 |
| GLOBAL_COV_ONLY_DIAG | 0 | 전체 Full 중심분산 대각 | 분산 단독 |
| GLOBAL_MEAN_COV_DIAG | 전체 Full 평균 | 중심분산 대각 | simple unconditional Gaussian 가설 |
| GLOBAL_MEAN_COV_JOINT | 전체 Full 평균 | Range–s full `C_rs` | unconditional joint Gaussian 가설 |
| POWER_JOINT | First-path 전력 조건부 평균 | 전력 구간별 full `C_rs` | **same-packet power conditional exploratory** |
| SIMPLE_DIAG | 전력·early energy·delay spread·FP 편파·anchor/mount | 조건부 중심 대각공분산 | same-packet CIR conditional exploratory |
| SIMPLE_JOINT | 동일 | `C_rs` 포함 조건부 | exploratory |
| SIMPLE_G4 | simple+FP threshold sensitivity | G4 조건부 | exploratory |
| G5_RESEARCH_ONLY | G0–G5 coherent Jones 포함 | full conditional | 시뮬레이션 한정/탐색 |
| ROBUST_GLOBAL_DIAG | Global mean | innovation-based soft downweight | IRLS pseudo-likelihood, 탐색 |

동일 RF 패킷에서 추출한 q가 원래 z와 통계적으로 상관하므로 `p(e|q)`의 held-out residual score가 좋아도 그대로 `p(z|x)` 정규화 likelihood 또는 Bayesian-valid EKF 공분산이라고 보장할 수 없다.

## 4. Full RF L2 비교 (정량 핵심)

| 모델 | J4 M0 Heading ° | J4 M45 Heading ° | J4 M0 bRMSE °/s | J4 M0 Pose NEES | J4 M45 Pose NEES |
|---|---:|---:|---:|---:|---:|
| 원 R0 | 7.52091 | 0.84809 | 0.09608 | 297.85 | 86.84 |
| Global Mean-only | 6.36793 | 2.45911 | 0.08052 | 131.31 | 85.45 |
| Global Cov-only | 7.07974 | 2.05209 | 0.09638 | **5398.49** | 82.03 |
| Global Mean+Diag | 6.01654 | 1.46058 | 0.08341 | 70.99 | 31.00 |
| Global Mean+Joint | 5.22517 | 1.44073 | 0.08251 | 54.00 | 31.33 |
| **POWER_JOINT** | **1.99142** | **0.72743** | **0.03266** | **12.89** | **18.58** |
| SIMPLE_DIAG | **1.59904** | 1.38172 | 0.02257 | 13.84 | 22.03 |
| SIMPLE_G4 | 1.84502 | 1.13310 | 0.02268 | 33.36 | 24.22 |
| G5_RESEARCH_ONLY | 2.15982 | 1.41939 | 0.05057 | 39.20 | 45.80 |
| ROBUST_GLOBAL_DIAG | 5.51972 | 1.32228 | 0.07924 | 689.04 | 41.73 |

**POWER_JOINT Full L2**의 Pose95 포함률: Mount0 **45.72%** (원본 16.77%), Mount45 **12.30%** (원본 0%). 완전한 95% 불확실도 정합 미달.

**SIMPLE_DIAG Full L2**: Mount0 RMSE 7.521→1.599°로 크게 개선되지만 Mount45 0.848→1.382° 악화. LoS 이 방법의 실제 입력 품질모델 inference는 아직 검증되지 않음.

### 가장 중요한 신규 발견: POWER_JOINT의 조건부 성능

본 실험에 고정된 `2 mount×4bias×2 solver = 16` Full RF 조건에서 POWER_JOINT는 모두 원본 R0 대비 Heading RMSE, Gyro Bias RMSE, Pose NEES, Pose95 포함률의 **4개 성능 기준상 비악화 또는 개선**. 별도 독립 후검증 Run 38715157425에서 16/16 재확인:

| L2 기준 | J4 원본 | J4 POWER_JOINT | SR4 원본 | SR4 POWER_JOINT |
|---|---:|---:|---:|---:|
| Mount0 Heading RMSE ° | 7.521 | **1.991** | 7.496 | **1.983** |
| Mount45 Heading RMSE ° | 0.848 | **0.727** | 0.849 | **0.728** |
| Mount0 bias RMSE °/s | 0.09608 | **0.03266** | 0.09610 | **0.03232** |
| Mount0 Pose NEES | 297.85 | **12.89** | 297.20 | **12.76** |
| Mount45 Pose NEES | 86.84 | **18.58** | 86.85 | **18.49** |

연구적으로 POWER_JOINT는 흥미로운 단순 물리 특징량 후보. 하지만 **LoS POWER_JOINT 모델 추론 결과는 현재 N4-C에서 미실행**이며, 실제 hardware power calibration/uncertainty, Mount generalization, normalized measurement likelihood, 독립 RF scene 문제도 미해결이다. 즉 N4-C가 `all-condition scientific deployment PASS`인 것은 아니다.

## 5. Gate 변화와 LoS guard

- L2 Full Mount0 G4 (J4) 개별 gate: accepted 796, Pose NEES 33.36. 원 R0 mask 강제 fixed gate accepted 766 → Pose NEES **19.26**, Heading RMSE 거의 동일(약 +0.0016°). Gate 사용이 과신 정도에 영향을 미치지만 이 대조는 과거 R0 mask를 새 필터에 강제한 비온라인 반사실임.
- L2 Full Mount45 G4 개별 gate: accepted 773, Pose NEES 24.22; 원 R0 gate accepted 649 강제시 Pose NEES **42.28**, Heading RMSE 약 +0.363°. 이 조건에서 gate masking을 줄이면 더 좋은 것은 아님.
- LoS에 Full calibration용 **GLOBAL_MEAN_COV_DIAG**를 그대로 전이시키면 Full L2 Mount0 J4 Heading RMSE 0.243→0.858°, Mount45 0.158→1.430°로 악화. `GLOBAL_MEAN_COV_JOINT`도 Mount0 0.243→0.693°, Mount45 0.158→1.315° 악화.
- **LoS POWER_JOINT/SIMPLE/G4/G5**는 현재 N4B OOF가 Full-only 학습·예측을 저장하고 있으므로, 원 LoS 패킷으로 조건부 모델을 재생성·추론하는 검증은 아직 없음. 기존 Full 조건 모델의 LoS 비악화 성능을 입증했다고 주장하지 않음.

## 6. 핵심 해석

1. 기존 R0의 Full RF 오류는 단순 (R_s) inflation만으로 해결되지 않으며, **Range/s 평균과 중심공분산을 함께 조건화**해야 하는 필요성이 강화됐다.
2. **Range–s 교차항 자체가 항상 유익한 것은 아니다**. Global mean+joint는 Mount0에서 global mean+diag보다 개선했으나 mount45에선 비슷하며, Simple diagonal은 Simple G4보다 Full Mount0 Heading이 더 우수. Conditional power grouping이 오히려 실전적인 신규 후보가 되었다.
3. 단순 전력 기반 POWER_JOINT가 16개 frozen Full RF 조건에서 유의미한 모범 연구 후보임은 사실이나, 시간상관/같은 패킷 조건부 likelihood/LoS/독립 Scene/실제 DWM1000 구현 가능성 때문에 **최종 EKF 채택 미확정**.
4. NEES 개선은 상당하지만 95% calibration을 달성하지 못했으므로 N4-C 종료 의미는 **후보의 반복 비교·실패 조건 확인**이지 확률적 일관성의 완결이 아니다.
5. 다음에는 모델 추가보다 `POWER_JOINT`의 LoS 패킷 입력 정합·native power와 s 관측 종속성을 해소한 likelihood, held-out 장소/seed 및 full covariance calibration을 연구하고, 두 Mount/바이어스에서의 정보를 보존해야 한다.

## 7. 단계 판정 및 다음 Gate

- `N4C_CODE_AUDIT=PASS`, `N4C_BASELINE_PARITY=PASS_WITH_NUMERIC_TOLERANCE`, `N4C_CORRELATED_SR4_MATH=PASS`, `N4C_RECURSIVE_EXECUTION=PASS`.
- `N4C_FULL_RF_RESEARCH_CANDIDATE=POWER_JOINT`, `N4C_DEPLOYABLE_POSTERIOR_CALIBRATED=false`, `N4C_CONDITIONAL_RF_DENSITY_NORMALIZATION_VALIDATED=false`, `N4C_LOS_POWER_GUARD_EVALUATED=false`.
- N4-D는 곧바로 Hard Gate를 학습하기보다 `POWER_JOINT`의 정상 LoS/독립 scene/관측 품질 분리 및 실제 Heading harm과의 관계 평가를 우선해야 함. Heading RMSE만을 위해 기존 Mount45 우수 정보를 버리는 정책은 후보가 아니다.

**전체 원시 산출물:** `N4C_FINAL.json`, `N4C_RECURSIVE_ALL_METRICS.csv`, `N4C_PAIRED_BASELINE_COMPARISONS.csv`, `N4C_ORIGINAL_J4_SR4_PARITY.csv`, `N4C_<case>_<los/full>_<B0/L0/L1/L2>_<J4/SR4>.npz` full x/P/status/NIS. 독립 감사 `N4C_POWER_JOINT.csv`, `N4C_FIXED_GATE_ABLATION.csv`, `N4C_LOS_GLOBAL_TRANSFER.csv`.
