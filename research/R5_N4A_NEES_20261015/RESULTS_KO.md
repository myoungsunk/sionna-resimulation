# N4-A Full RF Pose NEES 5957 원인 분해 — 실제 실행 결과 (2026-10-15)

## 1. 실행·재현 영수증

- **최종 PASS:** [GitHub Actions Run 38700636145](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38700636145)
- **소스:** [N4-A code](https://github.com/myoungsunk/sionna-resimulation/tree/research/r5-n4a-nees-rootcause-20261015/research/R5_N4A_NEES_20261015)
- **결과 전체:** [artifact 11956721584](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38700636145/artifacts/11956721584), ZIP SHA256 `83735d5551b6a70aec05874c73ac873cc9f4e09b3e45a6900f9af39098ff3ce3`
- 입력: 원본 RF archive SHA `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`, 동결 N1 archive SHA `b633d0af900f26ab7d5a42c905adcb4abc01e5b262a154c774d10d5740fbaa40`, N1 source `e189b444977ac9050e04320c8ee703fa2a5f4337`
- 실패 시행: Run 38700420651은 의존 패키지 누락, Run 38700532862는 불필요한 `stage_c` 모듈의 내부 `common` import 누락으로 중단. 해당 실행의 수치결과는 **무효/미완료**. 의존성을 수정하고 원본 R2 예측기 `predict_one`을 진단용 prior 계산에 사용하도록 개선, 재감사 및 170개 합성 SPD Schur 테스트 후 Run 38700636145 최종 PASS.
- 상태: `N4A_ARCHIVED_POSE_NEES_DECOMPOSITION_COMPLETE`; **후험적 포렌식 감사 완료, 새로운 필터 성능 또는 인과적 물리 원인 확정 아님**.
- 2 mount × 2 LoS/Full × 3 bias (L0/L1/L2) × 4 모델 (R0 J4, G5 Rs-only, G5 Mean-only, G5 Mean+Rs) = 48 그룹. 829 평가 프레임/그룹, 총 39,792 평가 위치. 48개 원본 N1 점수 parity PASS.
- 원본 Joint4/SR4·LUT·R0·G5 모델은 **수정하지 않았다**.

## 2. 정확한 Schur 분해

Pose 3차원 `[x,y,psi]`의 covariance를 psi와 XY 블록으로 나눌 때:

```
P_XY|psi = P_XY - P_XY,psi * inv(P_psipsi) * P_psi,XY
e_XY|psi = e_XY - P_XY,psi * inv(P_psipsi) * e_psi
NEES_pose = e_psi^2/P_psipsi + e_XY|psi' * inv(P_XY|psi) * e_XY|psi
```

Conditional XY와 Heading NEES 합은 원래 3D Pose NEES와 **최대 절대차 1.2660e-9**. 조건부 XY 고유축 분해와 2항 합도 단위테스트 통과. 모든 covariance SPD 검사 통과. 상태의 x/y 단위 m와 psi 단위 rad를 혼용한 단순 condition number 대신, 초기 Pose 표준편차로 정규화한 condition number 추가 기록.

## 3. L2 Full mount0 — 핵심 현상

| 수치 | R0 Joint4 | G5 Mean+Rs |
|---|---:|---:|
| Heading RMSE (°) | 7.520912 | **3.388404** |
| XY RMSE (m) | 0.870991 | **0.496675** |
| Heading NEES | 86.373259 | **12.810428** |
| Conditional XY NEES | 211.479583 | **5944.771702** |
| Pose NEES | 297.852842 | **5957.582130** |
| Conditional XY / Pose NEES | 71.00% | **99.78497%** |
| Pose 95% coverage | 16.767% | 17.612% |
| Conditional XY NEES small-eigen-axis | 132.4841 | **5840.6081** |
| Conditional XY NEES large-eigen-axis | 78.9955 | 104.1636 |
| Conditional XY small eigenvalue median (m²) | 7.9939e−5 | 7.7340e−5 |
| Conditional XY large eigenvalue median (m²) | 3.4028e−3 | 3.9302e−3 |
| Conditional XY eigen-condition p95 | 70.89 | 102.02 |
| Gate accepted / rejected evaluated | 766 / 63 | **809 / 20** |

핵심: 조건부 XY **작은 고유값 방향의 실제 오차 투영**이 NEES의 거의 전부를 차지한다. Heading이 개선됐고 XY RMSE도 감소했으나 방향성/교차공분산과 실제 오류의 정합은 악화.

N1에서 G5 signed mean+Rs의 `L2 Mount0 Pose NEES 5957.58` 수치 independent parity PASS. 해당 Pose NEES는 Heading 오차만으로 설명 불가.

## 4. 극단 시점과 전반적 과신

L2 Full Mount0 Mean+Rs:
- 평가시간 상위 **1%** 시점의 Pose NEES 합 기여 **40.866%**.
- 상위 **5%** 시점 합 기여 **78.392%**.
- 평가 시점의 **57.177%**에서 Pose NEES >100.
- 평가 시점의 **8.565%**에서 Pose NEES >1000.

단일 outlier에만 의존한 평균 왜곡은 아니지만, 높은 꼬리 일부의 영향이 매우 크다. `N4A_TIME_BANDS.csv`, `N4A_TOP_EVENTS.csv`, 원본 48개 `N4A_TRACE_*.csv.gz`에 구간별·시점별 분석 기록 저장. `pose_id`, timestamp, RF 수용, `H_s,psi`, `innov_r,s`, gyro bias/heading 위치 변화, conditional XY 축 분해, prior/post covariance determinant 및 eigen 조건 포함.

## 5. 점추정·공분산 대수적 기여 분해 (L2 Full Mount0)

동결 기존 J4 `(e0,P0)`와 G5 Mean+Rs `(e1,P1)`의 평균 Pose NEES 차이 `+5659.72929`.

- Point-error contribution: **+1273.66048**
- Covariance contribution: **+4386.06881**
- Sum: **+5659.72929**

두 P와 e를 교차 적용한 대칭 2요소 Shapley 대수 분해이며, **물리적으로 각각의 항이 원인이었다는 인과적 증명은 아님**. 4-state 갱신이 변화하면 covariance/innovation/trajectory/gates 모두 연쇄적으로 달라진다. 다만 조건부 XY 추정오차 방향과 자기확신의 비정합을 구분한다는 목적에 부합.

참고 비교:
- L0 Full Mount0 Joint4 Pose NEES **8402.05** vs G5 Mean+Rs **288.62**로 *개선*; L1 383.24 vs 208.83으로 개선; L2만 297.85 vs 5957.58로 매우 악화. 이 `Bias`별 비단조성이 핵심 후속 원인 규명 목표.
- L2 Full Mount45 Joint4 Pose NEES **86.84** vs G5 Mean+Rs **134.36**; 조건부 XY는 각각 82.98, 128.51이고 해당 전체 NEES의 95.55%, 95.65%.

## 6. 해석상 한계와 N4-B 이전 남은 쟁점

- **확정:** NEES 5957.58의 99.785%는 조건부 XY에서, 그중 98.25%는 작은 조건부 XY covariance eigen 방향에서 나온다 (평균 NEES 5840.61/5944.77).
- **확정:** 한정된 시간 구간의 극단 NEES가 평균을 크게 끌어올린다.
- **확정:** Gate 수용 수는 원래 Joint4 766에서 G5 Mean+Rs 809로 달라진다.
- **미확정:** 특정 Gate 전환, 작은 covariance eigenvalue 자체, Range 다중경로 편향, s 편향보정 residual 및 시간상관 중 무엇이 가장 중요한 기계적 인과 원인인지. `A`는 방향성과 발생조건을 진단했지만 실제 원인의 반사실적 분리는 후속 추가 검증 필요.
- **해석 주의:** XY marginal NEES + Heading marginal NEES는 Pose NEES와 일반적으로 같지 않다. 공분산의 교차항을 반드시 포함해야 한다.
- **연구 결정:** N4-B로 곧바로 `R_r,R_s,C_rs`를 학습하기 전에, L2 Mount0의 상위 1/5% 사건 시점에서 Range innovation/FP tap/orientation/gate 차이와 작은 조건부 eigen 방향이 정렬되는지 사건 수준의 추가 감사가 필요. 그렇지 않으면 상관/시간편향을 직접 원인으로 단정해서는 안 됨.

## 7. 최종 판정

`technical_execution_PASS=true`, `N4A_pose_Nees_mechanism_localized=true`,
`full_physical_root_cause_confirmed=false`, `N4B_model_training_GO=CONDITIONAL`.

결론: **N4-A의 첫 목표인 NEES 구성요소와 발생 조건을 정량화했으나, 실제 원인(왜 L2의 특정 시점에서 조건부 XY 작은 eigen 방향으로 오차가 집중되는가)은 추가 사건 분석이 필요하다.**
