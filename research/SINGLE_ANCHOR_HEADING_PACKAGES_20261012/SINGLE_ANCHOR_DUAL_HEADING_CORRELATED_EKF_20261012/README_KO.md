# Single-anchor DR + 2 Headings + UWB Range 공동 EKF (2026-10-12)

합성 Monte Carlo 실험 전용 패키지입니다. **RF 절대 Heading은 가정한 관측**이며 Sionna 추정값이나 실제 RF 측정값이 아닙니다. 동일한 GitHub 복도 기하와 네 가지 10m 경로를 사용합니다.

## 권장 읽기 순서
1. `SUMMARY_KO.md` — 핵심 수치·모델·의미·제한점
2. `REPORT_KO.md` — 수학 관계식·기본 sweep 상세 표
3. `01`–`13` CSV — 404개 코어/추가 필터조건 및 검증 데이터
4. PNG 파일 — 경로·정확도·편향·상관관계·Heading observability 비교

## 의존성
`pip install numpy pandas matplotlib`

## 재현 명령
```bash
python dual_heading_sim.py --runs 1000 --out .
python relationship_audit.py --runs 1000 --out .
python cadence_and_jointcov.py
python paired_bootstrap.py
python qa_independent.py
```

처음 명령이 전체 348개 코어 조건을 실행합니다. 이어서 관계 검증과 희소 RF 관측 48조건 및 동시 복합 상관 8조건을 계산합니다. 다른 난수 시드나 반복 횟수는 `--seed`, `--runs` 옵션을 사용하면 됩니다. 보조 코드에는 기본 `runs=1000` 설정이 있습니다.

좌표계 x=복도 진행, y=복도 횡방향, z=수직. 앵커 (4,0,2.65)m, 로봇 태그 높이 z=0.45m, 수평 lever arm=0. 복도 20×2.4×2.7m. 네모·ㄹ자 회전은 이상화된 급회전입니다. 복도 벽 충돌·지면 SLAM·NLoS·듀얼 LP polarization·RF 원시 신호는 모델링하지 않습니다.

### 과학적 제한
- IMU/Odom 상대 Heading 오차와 RF 절대 Heading의 오차를 별도 합성했습니다.
- `rho_range_rf` = 같은 시각 RF ranging noise와 RF yaw noise의 상관계수.
- `rho_gyro_rf` = 같은 시각 gyro **입력 증분 noise**와 RF yaw noise의 상관계수.
- 위 두 상관관계는 서로 다르며, 시간적 AR(1) 자기상관도 아닙니다.
- RF 관측이 anchor-relative bearing만 제공한다면 결과가 크게 다릅니다(`08_absolute_vs_relative_heading.csv`).
- 공식 연구 claim에서는 RF 절대 yaw 관측 가능성을 별도로 검증해야 합니다.

GitHub 코드는 수정하지 않았습니다.
