# B-MCG v1 검증 보고서 및 원본 데이터 인계

**Actions 계산은 성공했지만 능동 가드 정책 채택은 보류입니다.** 사전 유용성 검증에서 R2/R4/R5 모두 선택 정책이 OFF였습니다.

원본 Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209
기존 구현 코드 커밋: e3ddc9fa4371d899a08a2a873d2ee5cf32074a01

## 전체 3,136시점 결과 (MSE 가중 풀링 후 제곱근)

| 보정 | 가드 | Heading RMSE | XY RMSE | 평균 NEES3 | Pose95 | 감쇠 시점 |
|---|---|---:|---:|---:|---:|---:|
| B_FROZEN | OFF | 1.5566° | 12.809cm | 25.123 | 46.1% | 0 |
| B_FROZEN | ACTIVE_RS | 1.5356° | 12.652cm | 24.806 | 47.6% | 12 |
| B_BIAS_COV | OFF | 0.9992° | 10.131cm | 14.484 | 30.3% | 0 |
| B_BIAS_COV | ACTIVE_RS | 1.0006° | 10.327cm | 14.729 | 28.2% | 11 |

## 경로별 결과

| 경로 | 보정 | 가드 | Heading RMSE (°) | XY RMSE (cm) | Pose95 | 감쇠 수 |
|---|---|---|---:|---:|---:|---:|
| R2 | B_FROZEN | OFF | 2.1616 | 18.027 | 49.7% | 0 |
| R2 | B_FROZEN | ACTIVE_RS | 2.1550 | 17.943 | 51.4% | 1 |
| R2 | B_BIAS_COV | OFF | 0.9422 | 9.713 | 40.0% | 0 |
| R2 | B_BIAS_COV | ACTIVE_RS | 0.9422 | 9.713 | 40.0% | 0 |
| R4 | B_FROZEN | OFF | 1.2623 | 10.623 | 20.8% | 0 |
| R4 | B_FROZEN | ACTIVE_RS | 1.2629 | 10.647 | 21.0% | 2 |
| R4 | B_BIAS_COV | OFF | 1.3550 | 11.616 | 21.7% | 0 |
| R4 | B_BIAS_COV | ACTIVE_RS | 1.3550 | 11.616 | 21.7% | 0 |
| R5 | B_FROZEN | OFF | 1.1411 | 8.922 | 56.9% | 0 |
| R5 | B_FROZEN | ACTIVE_RS | 1.0847 | 8.517 | 58.9% | 9 |
| R5 | B_BIAS_COV | OFF | 0.7973 | 9.562 | 28.1% | 0 |
| R5 | B_BIAS_COV | ACTIVE_RS | 0.8012 | 10.017 | 23.5% | 11 |

## 채택 보류와 적대적 실패
B_FROZEN의 전체 Heading/XY 오차는 소폭 감소했지만 R4가 악화했습니다. B_BIAS_COV의 R5 XY와 포함률은 악화하고 전체 pooled도 나빠졌습니다.
과거 RF 오염에 의해 잘못된 정렬 기준이 형성되면 정상 RF 복귀를 억제하는 실패가 발견됐습니다. 제한된 profile 후보 탐색이 허용 해를 놓칠 가능성도 확인했습니다. 운동과 일관된 편향은 가드로 식별하지 못할 수 있습니다.
따라서 ACTIVE_RS는 사전 지정된 진단용 개입이며 생산용 정책으로 승인하지 않습니다.

## 코드·데이터 재현성
상위 research/B_MCG_V1_20261109 폴더에 mcg.py, experiment.py, ci_route.py 및 원본 실험 계약·코드 감사·테스트가 있습니다.
이 폴더에 각 경로의 CI_ROUTE_SUMMARY, 원본 baseline NPZ, OFF/ACTIVE_RS 원본 재귀 NPZ·JSON을 변경 없이 보관합니다.
모든 게시 파일 SHA256은 SHA256.json에 기록합니다. 온라인 입력과 FFD bank는 기존 pinned GitHub Release/원본 SHA LOCK을 사용합니다.
신규 독립 RF 재시뮬레이션이나 새로운 환경 일반화 검증은 수행하지 않았습니다.
