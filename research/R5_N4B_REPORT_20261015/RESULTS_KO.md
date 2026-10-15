# N4-B 실집행 결과 — RF Range·편파 공동 잔차, Mean/Covariance/Temporal & held-out likelihood (2026-10-15)

**최종 연구 판정: TECHNICAL PASS / SCIENTIFIC PARTIAL GO.** 동결된 Full RF의 `R0` 평균 0·독립 등분산 모델은 실제 잔차분포를 잘 설명하지 못했고, **단순 물리 조건부 오차 모델은 경로별 held-out NLL을 개선**했다. 그러나 이것은 `p(e_r,e_s|q)`의 조건부 적합성이며, 정상화된 `p(z|x)`로 EKF에 투입할 수 있거나 Pose NEES가 개선됐음을 입증하지 않는다.

## 1. 코드·실험 출처

- [N4-B 본 실험 Actions Run 38711275905](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38711275905), [7.25 MB 원시 artifact 11960766768](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38711275905/artifacts/11960766768), ZIP SHA256 `170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b`.
- [조건·Anchor별 후속 감사 Run 38711761751](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38711761751), [추가 검증 artifact 11960627530](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38711761751/artifacts/11960627530), ZIP SHA256 `196cb8578d953c3d7737d1f481a5ccd3eb4d5782376cf137873c91af00a0b9c4`.
- [실행 코드](../R5_N4B_20261015/n4b_rf_errors.py), [추가 검증 코드](n4b_verify_report.py). N4-B 본 실험 commit `7d8d20c9a95364fb6a9ae7caa720b2b22019ecab`·추가 검증 commit `ee7b0b3b46dd21fb71c0ca3d5f67ce9f8873a64b`.
- 원본 Frozen H 22자산 SHA, 14채널의 원 P3 관측 14,502/14,502 Range·s 실수 관측 parity, Full/LoS 9,519 paired pose, synthetic centered covariance/PD/loss test PASS.
- 첫 Run `38711132546`은 synthetic-test G5 import 순서 오류로 중단되어 과학 결과로 사용하지 않음. 수정 후 preaudit/검사/실행을 모두 다시 통과한 Run 38711275905 결과만 인용.
- 모델은 `x,y,psi,b_g` Joint4를 **변경하지 않음**. 원 관측 `z=[range_raw,s]`·LoS FFD LUT·원 `R0=diag(0.0068578637 m²,0.0081)` 보존. 실제 Gyro Bias가 아니라 **RF 모델 오차 자체**를 분석하므로 L0/L1/L2 조건은 이 N4-B에서 분리하지 않음.

## 2. RF 측정오차의 정의와 실제 조건별 분포

오프라인 GT 위치·자세에서 동결 LoS EKF forward `h=[h_r,h_s]`를 평가하고,
`e_r=z_r-h_r(x_GT)`, `e_s=z_s-h_s(x_GT)`로 정의. GT는 regression target/오프라인 검증에만 사용하고 predictor에는 사용하지 않는다. 관측의 원 Range detector bias, LoS LUT 보간 차이, 물리 Full–native LoS 차이를 **분리해서 저장**했다. 따라서 `e_r,e_s`는 순수 MP만을 측정한 양이 아니다.

중심화 정의: `mu_r=E[e_r]`, `mu_s=E[e_s]`, `Vr=Var(e_r)`, `Vs=Var(e_s)`, `C_rs=Cov(e_r,e_s)`.

| R2 Full RF 사례 | μr (m) | μs | Vr (m²) | Vs | C_rs (m) | ρrs |
|---|---:|---:|---:|---:|---:|---:|
| Anchor A, Mount 0° | +0.05225 | +0.04850 | 0.01708 | 0.03935 | +0.01361 | **+0.525** |
| Anchor A, Mount 45° | +0.07187 | +0.00692 | 0.01658 | 0.05234 | +0.00182 | +0.062 |
| Anchor B, Mount 0° | +0.03069 | +0.02274 | 0.00807 | 0.01098 | +0.00090 | +0.096 |

동일 Anchor A에서 Mount 0/45의 교차상관 크기가 매우 다르다. 따라서 일정 `C_rs`만 추가해 전 Mount를 개선할 수 있다는 주장은 **지지되지 않음**. 훈련 경로 R4/R5의 Full–native LoS 오차 상관 역시 위치·Anchor에 따라 양/음 방향으로 달라짐.

이 값은 주어진 scene·경로 평균이며, 실제 UWB thermal noise 분산이 아니다.

## 3. R0와 간단한 물리 모델의 held-out joint Gaussian likelihood

R2/R4/R5 중 하나의 경로를 완전 평가용으로 분리하고 나머지 경로에서 학습. 같은 GT 좌표 중복을 학습에서 제외. 각 arm은 동일 학습 알고리즘/정규화 제약/구간별 공분산 수축 규칙을 사용. `Simple`의 물리 입력은 총 first-path power, first-window energy, delay spread, first-window polarization mismatch, 알려진 mount/anchor 설정. 추가 G4는 FP threshold sensitivity; G5에는 `range_m,abs(s)`와 coherent-frequency Jones 등 연구용 특징 포함.

| 방법 | 9,519 held-out 공동 NLL↓ | Joint95 포함률 |
|---|---:|---:|
| 기존 R0 (μ=0, diagonal) | +0.0170 | 85.28% |
| Global constant μ/diagonal covariance | −0.9758 | 94.11% |
| Global constant μ/**joint** covariance | −0.9772 | 93.75% |
| First-path power 3구간 joint | −1.5898 | 94.51% |
| **Simple physical, diagonal** | **−1.5972** | **94.66%** |
| Simple physical, joint | −1.5815 | 94.11% |
| Simple physical + G4 threshold sensitivity | **−1.7038** | 92.58% |
| G5 coherent-frequency research-only | −1.4586 | 87.00% |

**공동 NLL이 음수인 것은 연속 확률밀도에서는 가능하며 계산 오류가 아니다.**

해석:
- R0에 비해 간단한 조건부 오차모델이 동일 복도 내 held-route conditional NLL과 95% inclusion을 개선.
- `GLOBAL_JOINT` vs `GLOBAL_DIAG`, `SIMPLE_JOINT` vs `SIMPLE_DIAG`의 비교에서는 **공분산 비대각항이 자동으로 이득을 주지 않음**.
- G4의 전체 평균 NLL이 가장 낮으나, **G4-SIMPLE_JOINT 증분 평균 NLL −0.1224, 180개 같은 복도 spatial-block 95% CI [−0.2688,+0.0209]**로 구간이 0을 포함: **G4의 일관된 증분 이득은 확정하지 못함.**
- G5−G4 평균 NLL은 **+0.2452, 95% CI [+0.1190,+0.3853]**로 오히려 악화. 특히 R4 AnchorA m0에선 `G5 NLL +1.299`, `G4 −0.790`, `Simple diagonal −1.282`: 전 특징량 결합을 최선으로 주장하지 않는다.
- `G4−R0 = −1.7208`, 180개 같은 복도 공간블록 재표본화 95% CI [−2.5320,−1.0338]. **독립적인 새 multipath 장면의 효과구간은 아니다.**

### Anchor/Mount별 확인 (R2 완전 보류 평가)

| Held-out R2 case | R0 NLL | Simple diagonal NLL | Simple+G4 NLL | Simple+G4 Joint95 포함률 |
|---|---:|---:|---:|---:|
| AnchorA Mount0 | +0.958 | −1.455 | **−1.774** | 91.94% |
| AnchorA Mount45 | +1.758 | **−1.269** | −1.109 | 86.88% |
| AnchorB Mount0 | −1.695 | −2.045 | −2.122 | 94.24% |

**Mount45**는 R4/R5 학습에 존재하지 않는 장착각이므로 `Simple+G4`가 simple diagonal보다 악화한다. 범용 정책 선택 시 mount45 비악화 기준을 강하게 유지해야 한다.

## 4. 시간상관과 FP detector tap 전환

기존 Full RF 순서에 따른 9,512 인접 시점. 관측 쌍은 독립 sample이 아니고 실제 시간이 같은 구간에서 단순히 영상을 반복 촬영한 것이 아닌 **연속 이동+정지 Yaw 회전 구간**을 혼합한 기록이다.

| 분해 | Range lag1 corr | s lag1 corr |
|---|---:|---:|
| Raw Full RF error, 전체 | +0.677 | +0.845 |
| Simple physical mean 제거 후 | +0.634 | +0.844 |
| Mean 제거 후 이동 구간 | +0.563 | +0.816 |
| Mean 제거 후 고정위치 Yaw sweep | +0.789 | +0.891 |
| Mean 제거 후 동일 FP tap | +0.954 | +0.933 |
| Mean 제거 후 **FP tap 전환 시점** | +0.307 | +0.672 |

9,512 인접쌍 중 **2,128쌍**에서 FP tap index 변경 발생. Range 상관이 FP tap 유지/전환 상태에 따라 크게 달라짐. 하지만 이 상관은 연속 위치·안테나 패턴·Yaw·detector jump에 의해 나타날 수 있으므로 **독립 stochastic temporal-noise autocorrelation**로 확정하지 않음.

## 5. b_site 지속 교란 가설 감사

Simple Physical model의 heldout 잔차를 GT 좌표 기반 **1.5m×1.5m×case 블록**으로 그룹화: 전체 180개 site block(5개 이상 관측 포함). 같은 block에서 oracle 평균을 빼면 보이는 오차분산 감소율:

- Range residual: **21.02%**
- s residual: **25.87%**

즉, 위치 블록별로 반복되는 잔차 패턴이 존재한다는 **서술적 증거**가 있다.

그러나 같은 장소에서 Yaw를 스캔하면 FFD 안테나 상대각·MP 응답·first-path detection이 바뀐다. Oracle site mean은 test GT label을 사용하므로 온라인에서 알 수 없다. 따라서 `e_k=μ(q_k)+b_site+η_k` 중 site random-effect가 확률적으로 따로 관측된 사실이라고 단정할 수 없다. 이는 N4-C 등에서 **관측가능한 정보로 추정 가능한 site disturbance**인지를 추가 확인하는 가설로만 유지한다.

## 6. 결론과 진행 Gate

1. **N4-B의 기술적 목표:** `μ_r,μ_s,V_r,V_s,C_rs`, FP tap별 오차 구조, lag1/구간별 지속성, R0 대비 held-out conditional likelihood — **계산·검증 PASS**.
2. **N4-B의 해석상 한계:** 독립 scene이 아님; Range·s와 같은 패킷에서 추출된 q로 조건화한 밀도는 그대로 normalized `p(z|x)`가 되지 않는다. 실제 N4-C EKF에는 double counting/normalization 주의.
3. **현재 단순 후보 우선순위:** R0 → global mean/centered covariance → **simple diagonal** → simple q-dependent covariance + G4. Joint `C_rs`와 G5는 조건부 차별성·보정성 검증 전 범용 채택 보류.
4. **N4-C 진행 조건:** 별도 LoS false-rejection, Mount0/45, Bias L0/L1/L2에 대해 **같은 측정 재사용 없이** RF mean/cov 활용법을 정당화하고, 실제 recursive Heading/Bias/XY/NEES/coverage 개선을 별도로 검증. 해당 전엔 `new EKF model scientific PASS=false`.

재현 산출물: `N4B_FINAL.json`, `N4B_HELDOUT_LIKELIHOOD.csv`, `N4B_EMPIRICAL_JOINT_RS.csv`, `N4B_FULL_MINUS_NATIVE_LOS.csv`, `N4B_TEMPORAL_ACF_STRATA.csv`, `N4B_SITE_BLOCK_MEANS_ORACLE.csv`, `N4B_OOF_PREDICTIONS.csv.gz`, `N4B_HELDOUT_NLL_BLOCK_CI.csv`, 별도 조건별 `N4B_CASE_REVIEW.json`.
