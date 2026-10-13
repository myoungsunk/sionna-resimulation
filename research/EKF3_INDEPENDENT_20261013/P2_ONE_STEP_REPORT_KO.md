# P2 — 동결 RF/LUT 기반 독립 3-State EKF One-step 공분산 비교: 실행 결과

**시행:** 2026-10-13, GitHub Actions [38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521). 실행 소스는 연구 브랜치의 `p2_frozen_rf_one_step.py`, `ekf3.py`이며 기존 6-State · RF 채널 · P0 동결 파일은 수정하지 않았다.

**판정:** `P2_ONE_STEP_IMPLEMENTED_AND_EXECUTED_MATH_PASS`. **Full-route fused filter / Monte Carlo consistency / physical scientific_PASS = NOT_RUN / NOT_ESTABLISHED / false.**

## 1. 재생 조건

- 기존 P0의 39개 파일 SHA-256·Git blob·NPY shape·Tnone–RF pose_id 정합성: PASS, GitHub Actions 로그 및 artifact의 `P2_VERIFY_P0_RUNTIME.json`.
- 기존 P1 수학 26 tests 다시 실행: `26 passed`.
- RF: R2_aA_m0, R2_aA_m45, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0 (7 conditions), 각 LoS와 Full 원래의 257-bin 복소 `H`/TX0. 기존 frozen observer의 Hann/4N-IFFT/stronger RX 30% leading edge/common tap 규약으로 `s, range, P1/P2`를 새로 추출.
- frozen `hs_lut_2deg.npy`는 **46×180×180 numeric grid**이며 `hs_lut_meta.json`의 theta/phi 축을 재구성해 원래 `HsLut`를 읽기 전용 호출. LUT를 임의 생성하거나 재적합하지 않는다.
- Sensor-v2 `noise_pair`, seed=0, prior 표준편차 (0.1m, 0.1m, 5deg); 원 Tnone route의 `t_s` 사용. 3-State `[x,y,psi]` 원호 Prediction, Wheel 거리 + Gyro 각도 입력. Legacy-Euler truth와 SE2 prediction의 알려진 불일치 유지.
- R0: `Rs=0.0081`, `Rr=0.0068578637 m²`, `R_sr=0`. R_sr=0은 **대조군의 미검증 독립성 가정**이다. Detector mean offset `-0.5315983906250129 m`. `A=direct-s only`, `B=range only`, `C=joint [s,range]`.
- 평가 `t>=30s`: 7 case × 각 두 RF mode = **6,201 one-step 평가 시점/채널**, 두 채널 전체 12,402. 모든 원 시점에서 14,502×3=**43,506건 동일 prior 비교**.

## 2. 중요한 비교의 정의

**같은 DR-only `xminus/Pminus`에서 A,B,C 세 필터를 독립 복제하여 단 한 번 업데이트**한 결과다. 다음 time step의 common prior는 다시 DR-only에서 계산하므로 아래 위치·Heading RMSE는 **One-step counterfactual**이다. Full-route로 A/B/C 사후추정 상태를 재귀 전달한 측위 성능이 아니며 기존 6-State RMSE와 직접 비교할 수 없다.

| RF 데이터 | Arm | one-step 위치 RMSE (m) | one-step Heading RMSE (deg) | 평균 XY 분산합 (m²) | 평균 Heading sigma (deg) | 채택률 (t>=30s) |
|---|---|---:|---:|---:|---:|---:|
| LoS | D0 DR-only | 0.1591 | 0.496 | 0.9728 | 5.003 | - |
| LoS | A `s` only | 0.1439 | 0.444 | 0.6331 | 3.956 | 6201/6201 =100% |
| LoS | B range only | 0.2113 | 0.936 | 0.8174 | 4.500 | 6201/6201 =100% |
| LoS | C joint | 0.1724 | 0.751 | 0.5435 | 3.632 | 6201/6201 =100% |
| Full RF | D0 DR-only | 0.1591 | 0.496 | 0.9728 | 5.003 | - |
| Full RF | A `s` only | 0.5453 | 2.189 | 0.6607 | 4.009 | 5902/6201 =95.18% |
| Full RF | B range only | 0.2733 | 1.203 | 0.8215 | 4.507 | 6084/6201 =98.11% |
| Full RF | C joint | 0.5735 | 2.345 | 0.5773 | 3.696 | 5897/6201 =95.10% |

같은 **noise-pair seed=0**에서 DR prior 자체가 우수하여 Full RF 측정 모델오차를 이용한 보정은 오히려 실제 오차를 크게 했다. **Joint C가 가장 작은 P를 만든 사실만으로 C가 가장 정확하다는 주장은 틀리다.** 단, 이 단일 시드에서 평균 NEES 또는 coverage 일관성을 확증하지 않으므로 해당 수치를 일반화하거나 절대 '과신 PASS/FAIL'이라고 판단하지 않는다.

## 3. Full RF 케이스별 공동 측정 채택 (t>=30s)

| 조건 | C accepted / N | C rejected |
|---|---:|---:|
| R2_aA_m0 | 793 / 829 | 36 |
| R2_aA_m45 | 746 / 829 | 83 |
| R2_aB_m0 | 810 / 829 | 19 |
| R4_aA_m0 | 552 / 592 | 40 |
| R4_aB_m0 | 581 / 592 | 11 |
| R5_aA_m0 | 1181 / 1265 | 84 |
| R5_aB_m0 | 1234 / 1265 | 31 |

LoS 모드에서는 A/B/C 모두 100% 채택됐다. Full RF는 특히 R2_aA_m45와 R5_aA_m0에서 더 많은 Joint NIS 거절이 나타났다. 이 수치는 모델 기반 Gate 동작 결과이지 실제 측정 품질분류 정확도가 아니다.

## 4. 실제 수치 예시 — Full R2_aA_m0, t=30.0s, pose_id=150

동일 predicted state:

`xminus=[5.599821049, 0.541153242, 0.048326382]`

`Pminus=[[0.016314429,-0.030023074,-0.006886193],[-0.030023074,0.154796308,0.033208094],[-0.006886193,0.033208094,0.007617492]]`

**A — s만:**
- `H_A=[0.016453185, 0.052766212, 0.349890271]`
- `R_A=[0.0081]`, `S_A=[0.010562755]`
- `K_A=[-0.352672337, 1.826533745, 0.407493281]^T`
- `nu_A=-0.010351956`, `Pplus_A=[[0.015000657,-0.023218886,-0.005368203],[-0.023218886,0.119556574,0.025346233],[-0.005368203,0.025346233,0.005863538]]`

**B — Range만:**
- `H_B=[0.576824937,0.195116001,0]`
- `R_B=[0.0068578637]`, `S_B=[0.011421189]`
- `K_B=[0.311052330,1.128181882,0.219530776]^T`
- `nu_B=0.001387326m`, `Pplus_B=[[0.015209389,-0.034031039,-0.007666095],[-0.034031039,0.140259482,0.030379401],[-0.007666095,0.030379401,0.007067062]]`

**C — Joint:**
- `H_C=[[0.016453185,0.052766212,0.349890271],[0.576824937,0.195116001,0]]`
- `R_C=[[0.0081,0],[0,0.0068578637]]`
- `S_C=[[0.010562755,0.001615634],[0.001615634,0.011421189]]`
- `K_C=[[-0.409101319,0.368923545],[1.690550307,0.889037702],[0.382184112,0.165467253]]`
- `nu_C=[-0.010351956,0.001387326]`
- `Pplus_C=[[0.013479815,-0.026883834,-0.006050321],[-0.026883834,0.110724724,0.023702454],[-0.006050321,0.023702454,0.005557599]]`.

주의: **C의 R_sr=0이지만 S_sr=0.001615634≠0**. 이는 원래 상태 예측 공분산 `Pminus`가 x/y/Heading 교차항을 갖기 때문이다. Joint covariance를 개별 scalar posterior의 산술 평균으로 만들지 않는다.

## 5. 수학 검증과 증빙

- 전체 시간에서 공통 predicted `xminus/Pminus`를 arm 3개에 전달한 일치 확인: **43,506회**.
- A·B·C가 모두 채택된 시간의 R0 Joint covariance는 단독 A/B보다 Loewner 의미에서 작거나 같음: **14,139회** 확인.
- Joseph posterior 재계산과 실 구현 출력의 최대 절댓값 차이: **4.163336342344337e−17**.
- 14개 NPZ 각각 raw `xminus, Pminus, H,R,S,K, innovation,NIS,Pplus`, 상태/게이트, raw `s/r`, pose_id, offline truth 점수용 필드 포함. 요약 `P2_ONE_STEP_SUMMARY.json`와 함께 Actions artifact [11782748118](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118)에 보존.
- 업로드 artifact ZIP SHA-256(동결 Actions 로그): `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`. 로컬 재검산: 14개 NPZ 각각 요약의 SHA-256과 일치, ZIP 무결성 검사 PASS.

## 6. 실패한 이전 시도와 정정

- 첫 실행 Actions 38331347561: LUT 의존 `pattern_apply.py` 누락으로 실제 RF 단계 실패했지만 `tee` pipefail 누락으로 workflow 상태만 SUCCESS(잘못된 상태). **증거로 사용 금지**.
- 두 번째 실행 Actions 38331443014: Archived source 의존성 확보 후 LUT를 pickled dict라고 가정하여 오류. 실제 LUT는 numeric 3D grid이며 읽기 시 메타데이터를 통해 축을 재구성해야 한다.
- 세 번째 실행 Actions 38331588521: archived 패키지 소스 포함, P0 파이프 및 본 실험 명령에 `set -euo pipefail`, 동결 LUT 메타데이터 파싱 적용. 실제 RF 채널이 연결돼 모두 성공.

## 7. P2 결론 및 미해결

수학적으로 3×3 예측 상태를 복제한 A/B/C의 `H,R,S,K,Pplus`가 기대대로 생성되고, 독립 저장 RF H/동결 LUT/동결 Sensor-v2 동작도 연결됨을 확인했다. 그러나 실험은 **R0가 올바른 RF 확률 모델이라는 검증이 아니고**, 현재 데이터는 한 corridor/한 RF realization/seed=0이다.

다음 후속 검증은 여러 독립 sensor/initial seed의 full-route **recursive** A/B/C, 모델 정합 W0, LoS/Full RF R0→R1→R2→R3 비교, RF–range 동시/시점간 잔차, near-pole slope, 기타 F01/F02 문제를 포함해야 한다. 이번 P2 결과를 재귀적 EKF 운영 성능이나 독립 환경 일반화로 해석할 수 없다.

`scientific_PASS=false` 유지. 
