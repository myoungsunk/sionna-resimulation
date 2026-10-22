# d0 + Full-CIR 특징 기반 LoS 편파 복원 및 Heading 정보 보존 결과 — 2026-10-22

## 출처 · 실행 QA
- GitHub Actions: [run 39727492968](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39727492968), 완료 `2026-10-22 14:33:47 KST`, conclusion=success, 9/9 steps success.
- 입력: `results_hpath/HP_PACKETS.csv.gz`, Full–LoS paired 9,519 poses / 7 cases / R2·R4·R5 routes.
- Train / test: R2 holdout 5,610/3,909; R4 7,675/1,844; R5 5,753/3,766.
- 학습: 고정 HGB (160 iterations; 학습 route R2/R4/R5 heldout). 사전 계획 [18](18_D0_CIR_LOS_VALIDATION_PLAN.md).
- 이번 실험이 사용한 Full-CIR 특징은 `s(fp)`, 주변 탭 `s(fp+o)`, signed Δs, `log_fp_power`, `fp_full` 등 **스칼라 파형 특징**이며 복소 CIR의 직접파 분리가 아님.
- 실험 d0는 **GT에서 정확히 ±1° 떨어진 synthetic prior**의 LUT 응답으로 산출됨. 이는 실제 IMU/odom prior의 위치·방향 오차나 재귀 상관관계를 대변하지 않음.
- 산출물: `LOSC_QA.json`, `LOSC_MEASUREMENT.csv`, `LOSC_GAIN.csv`, `LOSC_PACKET_DIAGNOSTIC.csv.gz`.
- 평가 LoS 라벨은 heldout route의 모델 학습에 사용되지 않음. 단, 평가의 synthetic prior 구성 자체는 GT pose를 사용하므로 사용 가능한 상태정보가 강하게 유리한 조건임.

## 고정 사전 판정

| 사전 질문 | 결과 | 이유 |
|---|---|---|
| Q1: CIR_PLUS_D0가 CIR_ONLY보다 모든 heldout route에서 낮은 LoS RMSE | PASS (조건부) | 세 route 모두 감소. 단, Prior-only보다 나쁜 LoS RMSE이므로 **Full CIR로 실제 직접파를 분리했다고 결론 내릴 수 없음** |
| Q2: heading 민감도 보존율 G >= 0.8 + 3-route 진단 RMSE <= prior | FAIL | G=0.193–0.216. 1차 fixed-gain 진단 RMSE는 평균 0.969–0.988°, prior 1°, 그러나 민감도가 78–81% 감소 |
| Q3: D0_DIRECT의 민감도 0 | PASS | 3-route 모두 부동소수점 허용범위에서 0 (부호 포함 약 1e-18) |

## LoS 편파비 복원 RMSE — ±1° 합성 prior 두 조건 평균

| Heldout route | RAW | CIR_ONLY | CIR_PLUS_D0 | PRIOR LUT / D0_DIRECT | CIR_PLUS_D0 / CIR_ONLY | CIR_PLUS_D0 / PRIOR LUT |
|---|---:|---:|---:|---:|---:|---:|
| R2 | 0.188611 | 0.117596 | 0.029151 | **0.020867** | 0.248 | 1.397 |
| R4 | 0.168349 | 0.119778 | 0.032378 | **0.030150** | 0.270 | 1.074 |
| R5 | 0.149475 | 0.092844 | 0.021061 | **0.016296** | 0.227 | 1.292 |

결론: d0를 추가한 HGB는 CIR_ONLY보다 낮은 오차를 얻지만, 정확한 heading prior의 LoS LUT 예측을 넘어선 독립적인 LoS 복원은 보여주지 못함.

## Heading prior ±1° 민감도 검증

| Heldout route | RAW G | CIR_ONLY G | CIR_PLUS_D0 G | D0_DIRECT G | ORACLE G |
|---|---:|---:|---:|---:|---:|
| R2 | 1.000 | 1.000 | **0.216** | 0.000 | 1.000 |
| R4 | 1.000 | 1.000 | **0.205** | 0.000 | 1.000 |
| R5 | 1.000 | 1.000 | **0.193** | 0.000 | 1.000 |

`G`는 ±1° 조건에서의 **innovation 변화에 대한 정규화된 반응 기울기**이며 실제 Fisher 정보량의 비율을 의미하지 않음. CIR_ONLY·RAW의 G=1은 prior에 독립적인 bias 예측에 의한 대수적 결과여서, 좋은 heading 정확도 자체를 보장하지 않음.

## 진단용 고정-gain 단일 heading update RMSE (degree)

- Gain: `K=9*g/(9*g*g+0.01)`, prior σψ=3°, measurement σs=0.1 설정. 위치는 진단 목적상 GT에 고정.
- 아래 수치는 동일 route에서 +1° / -1° heading prior 조건의 RMSE 산술평균.
- 재귀 EKF, NIS/NEES, 실측 성능 아님.

| Route | PRIOR LUT / D0_DIRECT | RAW | CIR_ONLY | CIR_PLUS_D0 | ORACLE_LOS |
|---|---:|---:|---:|---:|---:|
| R2 | 1.000 | 2.184 | 1.659 | **0.988** | 0.816 |
| R4 | 1.000 | 2.434 | 1.829 | **0.969** | 0.630 |
| R5 | 1.000 | 1.610 | 1.203 | **0.986** | 0.879 |

R2의 -1° 단일 조건에서는 CIR_PLUS_D0 RMSE=1.0012° > PRIOR 1°. 평균적으로 1–3% 개선됐지만 Oracle만큼 유용한 heading correction은 확보되지 않음.

## 한계 및 오해 방지

1. 이 실험에서 큰 d0 복원 성능은 **GT±1°로 이미 매우 정확한 prior를 사용한 효과**와 구분되지 않음. 명시적인 PRIOR LUT 기준선과 비교하면 LoS RMSE가 7–40% 더 큼.
2. `d0=sF-h_s(prior)`, `sF-d0=h_s(prior)`이므로 현재 d0를 그대로 빼는 방식은 RF heading innovation이 정확히 0이 됨.
3. 보존율 G=0.19–0.22는 현재 보정기가 prior error까지 흡수함을 시사함. 0.8 사전 기준을 세 route 모두 미달.
4. CIR_ONLY의 G=1은 충분조건이 아님: 오염이 남으면 heading fixed-gain RMSE가 prior보다 커짐.
5. B3(과거 d0에서 현재 bias 예측), ±5°·±10° 실제 LUT, gyro bias가 포함된 주행 prior, 재귀 EKF, full complex-CIR 분리 실험은 실행하지 않았음.
6. heldout 3-route 개발 데이터이므로 독립 새 scene generalization을 주장하지 않음. 시간 블록 CI 및 불확실성 calibration 미실시.

## 다음 검증의 1순위

- **실제 navigation prior**를 고정하여 bias 예측기 입력이 되는 d0를 구성하고, 원래 상태 오차와 편파 오차를 진단 라벨로만 분해.
- `CIR_ONLY`, `CIR + 현재 d0`, `CIR + 과거 d0의 bias prediction`, `CIR + d0 제한 가중치`에 더해 반드시 `PRIOR LUT ONLY`를 동등 기준선으로 설정.
- 평가 heading prior 오차의 크기·부호를 다양하게 하고 (0,±1,±2,±5,±10,±20°), heading correction gain **및** oracle innovation과의 bias/RMSE를 함께 검사.
- 1차 통과 후에도 실제 재귀 EKF의 heading RMSE, NEES(1D 기준 1), nominal 95% 포함률, XY 지표를 별도 검증.

**최종 판정:** 원래 질문인 “실제 편파 bias를 제거하면서 RF heading prior 오차 보정 정보를 유지할 수 있는가”는 본 HGB + 현재 d0 방식에서 **미달/검증 실패**. 단, 해당 원리가 일반적으로 불가능하다는 결론은 아님.
