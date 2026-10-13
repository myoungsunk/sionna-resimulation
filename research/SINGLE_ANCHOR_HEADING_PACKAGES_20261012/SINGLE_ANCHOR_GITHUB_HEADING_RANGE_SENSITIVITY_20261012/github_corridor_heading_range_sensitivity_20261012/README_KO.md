# 단일 앵커 복도 환경 — Heading/Ranging 오차 민감도 보고서

## 내용 요약

`myoungsunk/sionna-resimulation`의 복도 환경 정의(20×2.4×2.7m, ceiling anchor (4,0,2.65)m, tag z=0.45m)를 이전 NumPy DR/EKF 실험에 적용한 뒤, **Heading→Range/Localization** 및 **Range→Localization** 관계를 500회 Monte Carlo로 계산하였습니다. 앞선 전체 10m 구간의 Gaussian 기초 실험에서 파라미터 한 축씩만 바꿨습니다.

- `all_scenarios.csv`: 총 37가지 오차 설정별 ranging bias/RMSE/P95, EKF x/y/2D RMSE, 최종 RMSE, NIS/NEES/95% coverage, DR-only 대비 차이, GT 벽 경계 위반 빈도.
- `heading_geometric_effect.csv`: 같은 무작위 주행에서 누적 gyro/yaw 불일치가 실제 최종 위치와 3D 기하 ranging 거리 각각을 얼마나 변경하는지 계산.
- `REPORT_KO.md`: 오차원별 전체 수치표와 수식.
- `01_..05_*.png`: heading↔range/position, ranging error → EKF accuracy/consistency 그래프.
- `RUN_MANIFEST.json`: 실험 설정, 원본 코드의 SHA256, 원 GitHub 소스 파일 blob SHA, 검사 현황.
- `sensitivity_study.py`: 재현 가능한 원시 생성기 및 직접 비교·시각화 코드.

## 검증 핵심 결과

1. 기본 DR-only 전체 2D RMSE 0.365m, range-only EKF 0.351m. GitHub 중심선 앵커-태그 기하는 횡방향 측위 정보를 거의 제공하지 않습니다.
2. 초기 heading 불확실성 0.5°→6°: EKF 2D RMSE 0.167→0.651m, 최종 coverage 94.0→63.2%, NIS 평균은 약 1.005 그대로입니다.
3. 누적 yaw mismatch 5°: 최종 실제 위치 변화 RMS 0.436m, 최종 실제 기하 range 변화 RMS 0.00439m (기본 range σ=0.08m보다 작음).
4. 고정 ranging 편향 +0.2m: EKF 위치 RMSE 0.485m로 DR보다 악화, NEES 평균 81.894, NIS 평균 1.372.
5. 상관 있는 range noise AR(1) ρ=0.98: raw range RMSE 0.077m이나 NEES 10.251 및 최종 coverage 49.0%.
6. 상수 편향 독립 calibration(1000개 synthetic calibration sample) 후 4-state EKF: 2D RMSE 0.351m, 최종 coverage 84.8%.

## 실험의 의미와 한계

- **실측이 아닌 합성**. GitHub `CorridorSetup` 기본 치수 역시 소스에서 측정값이 아닌 placeholder라고 명시합니다.
- 실제 RF ray tracing 또는 CIR 기반 range error를 계산하지 않았습니다. `H4_hypothetical_heading_RF` 그룹의 `A*(dxy/r)*cos(2*(ψ−β))`는 **검증하지 않은 민감도용 가상 모델**입니다. 이 결과를 실제 안테나 방향별 측정 오차 예측으로 해석하지 마십시오.
- 태그의 XY lever arm은 0이므로, 제자리 회전만으로 기하학적 `r`은 변하지 않습니다. 외부 RF 모델이 없으면 heading 자체가 instantaneous true range에 직접 들어가지 않습니다.
- 시뮬레이터는 복도 벽 충돌/제약을 필터와 실제 운동에 강제하지 않습니다. 기준 500회 중 0.2%가 허용 영역을 벗어난 반면 큰 스트레스 조건인 gyro 5° 누적은 10.4%가 이 영역을 벗어났습니다. 이 사례는 '복도 내부 주행 보장' 결과가 아닙니다.
- 전체 2D RMSE는 step 1~100 (모든 500 주행 합침), final RMSE와 final coverage는 step 100만 사용했습니다.
- 모든 오차분포는 임의 설정값으로, 사용자 환경의 실제 UWB 오차분포를 식별한 결과는 아닙니다. `R1_white_gaussian_matched`만 EKF의 R을 실제 노이즈분산에 맞춰 조정했습니다. 기타 계열은 기본 `R=(0.08m)^2`를 유지했습니다.
- 시간적으로 상관된 step 표본을 독립 시행처럼 간주하여 좁은 신뢰구간을 주장하지 않았습니다. 몬테카를로 독립 반복 단위는 주행 500회입니다.

## 재실행

압축을 풀면 `github_corridor_sim/`과 `github_corridor_heading_range_sensitivity_20261012/`가 **나란히** 배치됩니다. 둘의 상대 경로를 그대로 유지합니다.

```bash
python3 -m pip install -r github_corridor_heading_range_sensitivity_20261012/requirements.txt
python3 github_corridor_heading_range_sensitivity_20261012/sensitivity_study.py --runs 500 --seed 20261012
```

기준 소스(`github_corridor_sim/corridor_sim.py`)는 복사된 이전 파일로, 이번 추가 민감도 실험을 위해 수정하지 않았습니다. GitHub 원격 브랜치도 수정하지 않았습니다.
