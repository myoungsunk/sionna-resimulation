# HEADING-DIR-001 — 실제 Heading 방향별 Dual-LP 오차·EKF 재귀 추적 (2026-11-05)

**상태:** `EXECUTED_NONINDEPENDENT_EXPLORATORY` · `POWER1_ORIGIN_TRACE_PARITY_PASS` · `JOINT4_UPDATE_ORIGIN_NOT_PARITY` · `NO_NEW_RT` · `NO_NEW_4D_RECURSIVE_COUNTERFACTUAL`.

이 문서는 원본 영구 데이터 및 기존 분석 결과를 교체하지 않는다. 신규 RT 400개 원장은 기존 GitHub Actions #41958274374, 과거 Full/LoS EKF 재귀 trace는 Actions #39376076166, 기존 관측 체인 C0-A는 Actions #41783949902에 있다. 분석 코드는 `heading_direction_diagnostics.py`이고 신규 RF 154쌍 결과는 `PR36_FULL_SHARDS_PAIRED.csv`를 참조한다.

## 1. 어떤 각도에서 실제 Heading 오차가 큰가?

- 좌표계: 0° = +X 축, 반시계(+)이며 ±180°가 같은 방향. 평가 기준은 *실제 GT Heading*이고, 주행 시작 0–30초는 방향별 주 분석에서 제외한다. 단, 초기 상태오차의 영향은 30초 이후에도 남는다.
- 조건: R4-B/R5-B, Anchor B, mount 0°, B0, 원래 Full RF의 **기존 4상태 EKF 자연 재귀**. 모델은 `POWER1` 및 `JOINT4`. 각각 742 / 1,415 시점의 noise seed 1개 (B0)의 직렬 상관 표본이다. 30개의 독립 시드나 다른 환경 일반화로 취급하지 않는다.

| 경로·모델 | 최대 절대 오차가 난 시점 | GT | 최종 추정 | signed error | 1σ | Heading NEES | NIS |
|---|---:|---:|---:|---:|---:|---:|---:|
| R4 POWER1 | 38.0 s | −38.356° | −41.674° | −3.317° | 0.516° | 41.28 | 0.211 |
| R4 JOINT4 | 38.6 s | −39.150° | −42.268° | −3.117° | 0.460° | 46.01 | 2.829 |
| R5 POWER1 | 32.4 s | −2.373° | −5.847° | −3.474° | 1.774° | 3.84 | 0.025 |
| R5 JOINT4 | 104.6 s | −176.335° | −170.635° | +5.700° | 0.634° | 80.86 | 1.500 |

15° GT Heading bin (t≥30, n≥20):

| 경로·모델 | 방향 구간 | n | RMSE | 명목 Heading95 |
|---|---|---:|---:|---:|
| R4 POWER1 | [30,45)° | 206 | 1.551° | 20.4% |
| R4 POWER1 | [−45,−30)° | 246 | 1.528° | 3.7% |
| R5 POWER1 | [−15,0)° | 360 | 1.311° | 98.9% |
| R5 POWER1 | [165,180)° | 228 | 0.802° | 89.0% |
| R5 JOINT4 | [−180,−165)° | 218 | 3.372° | 16.1% |
| R5 JOINT4 | [165,180)° | 228 | 3.256° | 20.6% |

**주의:** 방향과 위치·시간·측정 기하가 강하게 결합되어 있으므로 위 표는 *어떤 방향에서 오류가 관측되는가*에 대한 기술 통계이지, *그 방향을 향해서 생긴 오류*라는 각도만의 인과 증거가 아니다. 특히 R4 GT Heading 범위는 대략 ±39.7°에 제한되고 R5는 0°/180° 주변에 편중된다.

## 2. 지난 Heading → prior → 관측 영향 → posterior

다음은 **기존 POWER1** `UPDATE_ORIGINS.csv.gz`와 저장된 `TRACE.npz`가 전수 NIS·gate 일치한 0.4초 간격 1,079개 갱신의 결과다. 반면 모든 0.2초 시점의 최종 상태오차는 trace 자체로 분석했다. `prior`는 동일 갱신에 대해 `posterior - K_ψ,rν_r - K_ψ,sν_s`로 **후처리 복원**했으므로 운동 입력 원본을 독립 재생하지 않았음을 밝힌다.

각도는 전부 degrees, 원래 전역 좌표계.

| 사례 | GT | 직전 posterior | DR prior | Range 관측 Heading 기여 | 편파 관측 Heading 기여 | 갱신 후 Heading | 오차 |
|---|---:|---:|---:|---:|---:|---:|---:|
| R4 POWER1 t=0.0 | +39.496 | 없음 | +39.957 | −0.656 | +3.491 | +42.792 | +3.296 |
| R4 POWER1 t=33.6 | −31.700 | −33.142 | −33.126 | +0.073 | −0.328 | −33.380 | −1.680 |
| R4 POWER1 t=38.0 | −38.356 | −41.293 | −41.646 | −0.001 | −0.027 | −41.674 | −3.317 |
| R4 POWER1 t=59.6 | −37.723 | −36.305 | −35.944 | +0.011 | −0.005 | −35.939 | +1.785 |
| R4 POWER1 t=100.0 | −31.782 | −30.337 | −30.392 | −0.002 | +0.00008 | −30.394 | +1.388 |
| R5 POWER1 t=32.4 | −2.373 | −6.166 | −5.869 | +0.008 | +0.014 | −5.847 | −3.474 |
| R5 POWER1 t=104.8 | −176.522 | −176.583 | −176.769 | −0.031 | −0.007 | −176.807 | −0.285 |
| R5 POWER1 t=196.4 | +2.991 | +2.538 | +2.290 | −0.005 | +0.009 | +2.294 | −0.697 |

**'관측으로 추정되는 각도' 정의**: `prior_plus_s_component_deg = wrap(prior + K_ψ,s ν_s)`는 *기존 gain으로 편파 관측이 현재 prior에 가하는 Heading 정보의 효과*를 나타낸다. 독립된 절대 Heading 측정치 `s^{-1}`는 아니다. 실제 편파 관측 s는 위치·yaw에 결합하고 역변환은 비단사/다봉일 수 있다. `prior_plus_range_component_deg`도 유사하게 제공한다. 두 기여의 합은 실제 posterior를 최대 2.84×10⁻¹⁴° 오차로 재현했다.

## 3. 오차의 물리적 원인과 EKF 과신

- **R4 t=38.0 s / x≈5.98m, y≈−0.17m, GT −38.36°:** FP Full 28 vs Native-LoS 27(+1 tap), Full−LoS 편파비 +0.14595, 그중 FP 선택 성분 +0.11612, 같은 LoS tap 복소 성분 +0.02983. 현재 측정의 NIS=0.211로 수용. 하지만 prior 이미 −41.646°, Heading 실제오차 ≈−3.290°였고, 현재 수용된 range+s 갱신은 −0.02786°에 불과했다. posterior의 σψ 0.516°에 실제오차 −3.317° → Heading NEES 41.28. 따라서 *이 시점의 편파 오염만*으로 전체 −3.317°가 발생했다고 주장할 수 없다. **이미 틀어진 prior와 작은 현재 innovation이 상태오차를 감춘 사례**다.
- **R4 t=99.4–100.0 s / x≈13m:** FP Full=LoS인 구간에서도 Full−LoS 편파비는 −0.04~−0.055. t=100.0 기준 NIS 0.070, Heading오차 +1.388°, σ 0.211°. detector tap이 같아도 간섭 오염과 과신이 공존한다.
- **R5 t=32.4 s / GT −2.373°:** FP 이동=0, Full−LoS 편파비 −0.00247로 작다. NIS=0.025, 이전 posterior −6.166°, 현재 DR prior −5.869°, posterior −5.847°. **새 오염이 거의 없는 현재 시점에서도 이전 상태오차가 남는 사례**다.
- **R5 JOINT4 t=104.6 s / GT −176.335°:** posterior −170.635°, 1σ 0.634°, NEES 80.86, NIS 1.500. 같은 x/y/yaw의 R5 POWER1 시점(104.8s) 최종 오류는 −0.285°. 큰 오차가 그 방향의 불가피한 RF 현상이라기보다 필터 모델·이력에 민감하다는 반례다. JOINT4의 정밀 update-origin 분해는 아래 QA 실패 때문에 하지 않았다.

### QA에서 새로 발견한 원본-기록 충돌

동일 파일 패키지에서 `JOINT4` UPDATE_ORIGINS와 `TRACE`의 joint NIS가 R4 371개 중 370개, R5 708개 중 707개에서 불일치한다(허용오차 1e−10). 게이트 불일치는 각각 14개, 6개다. 따라서 **JOINT4 방향별 최종오차·NEES·NIS는 직접 TRACE만 사용**했고, JOINT4의 이전 상태→prior→관측별 Heading 기여라는 인과표를 만들지 않았다. `POWER1`의 371+708개 NIS와 acceptance는 일치한다. 이 문제는 기존 저장 결과의 원인 진단 사항이며 기존 실험의 전체 PASS/FAIL 상태를 변경하지 않는다.

## 4. 과학적 해석 범위 및 후속 작업

1. 현재 가능: 원본 GT yaw별 오차 분포, 기존 재귀 추정값의 prior/posterior 단계, 범위·편파 관측의 실제 gain-weighted Heading 갱신, FP 이동과 같은 tap 오염 비교.
2. 아직 미완료: 동일 위치에서 yaw만 바꾼 대조 데이터와 원래 자연 재귀 경로의 방향만 개입한 인과 비교. `s`만으로 절대각을 결정하는 의미의 수신기 방향 추정은 미검증.
3. 현재 수행한 `fixed_prior_s_LoS_posterior_deg`는 기록된 Kalman gain을 고정해 LoS 관측으로 선형 치환한 *국소 oracle 진단*일 뿐, 미래 전 구간을 갱신하는 새로운 4상태 EKF recursive counterfactual이 아니다.
4. 표본 각도별 비교는 독립 실험 반복이 아니라 경로·시점으로 결합된 1회 주행 trace다. 위치나 안테나 민감도의 각도별 인과 주장은 고정 XY yaw factorial 및 실제 완전 재귀 개입이 있어야 한다.

**재현 절차:** GitHub Actions #39376076166에서 R4/R5의 `...TRACE.npz`, `...UPDATE_ORIGINS.csv.gz`를 다운로드해 `/mnt/data/replay_r4`, `/mnt/data/replay_r5`에 풀고, #41783949902의 C0-A CSV를 `/mnt/data/c0a/c0a_outputs`에 풀어둔다. `python heading_direction_diagnostics.py --root /mnt/data --out /mnt/data/fp_ekf_verification`을 실행한다. 필요한 Python 패키지는 numpy, pandas, matplotlib(그림 선택)이다. 원본 `TRACE`의 GT는 오프라인 검증에서만 이용된다.

**관련 CSV:** `HEADING_DIRECTION_15DEG_BINS.csv`, `HEADING_EXAMPLE_UPDATES.csv`, `HEADING_TOP_POST30_ERRORS.csv`, `HEADING_UPDATE_PRIOR_OBSERVATION_POSTERIOR.csv` (전체 1,079개), `HEADING_DIRECTION_ALL_STEPS.csv` (12,942개), `HEADING_DIRECTION_QA.json` 및 그림 3개. 가장 큰 숫자는 t=30초 이후 조건으로 선택한 사후 탐색적 예시이며 새 holdout 검증이 아니다.
