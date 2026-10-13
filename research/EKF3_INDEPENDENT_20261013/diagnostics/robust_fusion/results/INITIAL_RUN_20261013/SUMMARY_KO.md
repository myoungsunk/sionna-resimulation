# M0–M2 Robust Fusion 초기 실행 결과

## 상태: M0–M1 비교 완료, M2 gate에서 중단

원본 FP s, B_OLD/E1 Range, RF·Wheel·IMU 및 pose 초기조건을 유지했다. 새 s 추출기를 사용하지 않았다. 기준 commit 991d511. 실행 grid는 7조건×seed0/1/2×level1×noise_pair/gyro_bias×(LoS B_OLD, Full B_OLD, Full E1)×D0/A/B/C = 모델당504셀이다. 이 grid는 최초 실행 전에 동결했으며 기존 모든 level/오차유형을 실행한 것은 아니다.

| 단계 | 결과 |
|---|---|
| M0 원본 재현 | 504/504 PASS, 최대 차이0, 기존 허용치1e-8 유지 |
| RF 잔차 구조 | INCONCLUSIVE, 시간 AR(1) 유효성 NOT_ESTABLISHED |
| 공통 RF 오차모델 | outer-route 상수 평균, ddof1 총 잔차 척도, 교차항0, 공동 Huber delta1.345 |
| M1 단위·원본 회귀 검사 | 49 PASS (신규23 + 원본26) |
| M1 수정 smoke | 12셀 완료 |
| M1 실제 RF 비교 | 504셀 완료, M0와 같은 입력·초기 pose·평가 시점 |
| GTSAM 일반 Gaussian fixed-lag | 50update PASS, covariance 기준해 차이1.11e-16 |
| M2-T0 정확한 운동모델 주변화 | NOT_READY: 최초 주변화에서 p0 누락 오류, 실제 RF 실행 안 함 |
| M2-T1 | 구조 gate 미확정으로 보류, 실행 안 함 |
| 독립 RF 환경 확증 | NOT_RUN |
| scientific_PASS | false |

## 실제 Full RF Joint C 비교

아래는 각 행 7조건×3seed의 샘플 수 가중 기술 통계이다. 시간 샘플 또는 sensor seed를 독립 RF 실험으로 간주하지 않는다. 원본→M1 순서다.

| Range·센서 조건 | Heading RMSE (°) | 위치 RMSE (m) | 평균 pose NEES | Pose95 포함률 |
|---|---:|---:|---:|---:|
| B_OLD·noise_pair | 1.2744→4.4082 | 0.2302→0.4513 | 49.750→310.133 | 18.06%→23.95% |
| B_OLD·gyro_bias | 4.3833→4.4243 | 0.4336→0.4543 | 578.387→171.255 | 2.01%→24.64% |
| E1·noise_pair | 0.9414→4.0158 | 0.1531→0.4065 | 24.238→82.196 | 33.14%→24.88% |
| E1·gyro_bias | 4.3552→4.0884 | 0.4249→0.4065 | 484.954→91.901 | 2.66%→24.73% |

유편향 E1에서는 일부 개선이 있으나, 무편향 음성 대조군에서 큰 악화가 확인됐다. M1의 현재 설정을 일반 개선안으로 채택하지 않는다. Bias 상태·평균/척도·Huber를 함께 도입한 비교이므로 어느 한 요소가 원인이라고 단정하지 않는다. RMSE와 NEES·포함률을 함께 개선했다고 주장하지 않는다.

D0/A/B/C 전체 결과는 M0_METRICS.csv, M1_METRICS.csv, PAIRED_CELLS.csv, POOLED_METRICS.csv에 있다. M1_EXTRA_DIAGNOSTICS.csv에는 p95 오차, 기술적 NIS lag1, 평균 Huber 가중치·다운웨이트 비율이 있다. M1_METRICS에는 bias RMSE, bias–heading 상관, 업데이트 시간도 기록했다.

## RF 구조 및 식별성

Full B_OLD s의 lag1 상관은 R2/R4/R5에서 약 .938/.763/.905이며 AR 예측은 홀드아웃 MSE를 줄였다. 하지만 단일 결정론적 scene·고정 traversal 자료에 시간/공간을 구분하는 개입이 없고 지정 조건의 재방문 쌍도 없었다. 순간/지속 분산 분해를 확정하지 않는다. 높은 ACF만으로 M2-T1을 승인하지 않았다.

실제 원본 FP LUT를 사용한 48개 합성 관측가능성 셀에서는 measurement-only와 prior 포함 rank를 분리했다. 초기 pose 자유·지속 RF offset 포함 진단에서 D0 0/4, A5/5, B4/5, C6/6이었다. 이는 특정 합성 선형화 조건의 구조 진단이며 실제 multipath 편향 식별성을 보장하지 않는다.

## 공분산과 수렴 검사

독립 표본3000개씩: Gaussian 기준 포함률95.27%, 깨끗한 Huber95.33%, 이상치 혼합 Huber88.2%. 마지막 결과는 강건 처리 후에도 local Gaussian covariance가 보정됐다고 볼 수 없음을 보여준다.

초기 고정점 IRLS가 일부 독립 합성 표본에서100회 이내 수렴하지 않아, 동일한 고정 prior·고정 Jacobian block-Huber MAP의 스칼라 가중치 근을 구간 탐색으로 풀도록 수정했다. 허용치나 통계 gate를 완화하지 않았다. M1_SMOKE_FIXED/M1_FULL이 최종 코드의 증빙이며 초기15test receipt와 최초 smoke는 대체 이력으로만 보존한다. 최종49test receipt에 현재 소스 해시가 있다.

## M2 중단 증빙

Windows GTSAM4.2 배포 부재 후 WSL Ubuntu22.04의 별도 환경(Python3.10.12, NumPy1.26.4, GTSAM4.2)에서 실제 검사를 수행했다. 일반 Gaussian fixed-lag의 주변화·covariance 조회는 정상이다.

정확한 rank2 motion은 latent input-error2 + SE(2) equality constraint3으로 검사했다. 첫 단계 공분산은 기준 식과1e-8 이내로 정합했으나, lag 경계를 넘는 update3(t≈.6s)에서 `Requested variable 'p0' is not in this VectorValues`가 발생했다. 현재 key만 조회하는 후속 검사에서도 재현돼 중단했다. 이는 해당 constrained 구현의 미해결 문제이며 GTSAM 전체가 불가능하다는 결론이 아니다. 대각 과정잡음·jitter로 모델을 바꾸지 않았다.

M2의 다음 작업은 정확한 운동 factor와 주변화 처리를 수정하고 preflight를 다시 통과시키는 것이다. RF 실험·NEES 비교는 그 이후에만 가능하다. T1은 별도로 잔차 구조 gate 통과가 필요하다.

## E1·일반화 경계

E1은 동일 outer-route 계수를 학습·평가에 적용했다. 공간 buffer 제외 후 E1 잔차 평가 표본은 R2/R4/R5에서105/40/470개다. 전체 재귀 E1 주행은 제외 위치의 이전 관측 영향을 받으므로, scoring mask만 씌워 누출 없는 확증으로 주장하지 않는다. 본 전체 E1 결과는 탐색 전용이다. 독립scene 및 별도 확증 seed 결과는 없다.

## 재현·보존

EVIDENCE.zip에 원래 manifest/입력 cache/trace/실행 로그/소스 snapshot/공분산·관측가능성·GTSAM 실패 증빙을 보존했다. 새 robust_fusion 영역만 추가하고 원본 EKF3, P0/P2, D0–D15, RF 및 이전 결과는 수정하지 않았다. 로컬 관리 대상 실행은 종료하고 reference를 해제했다. 재사용된 supervisor PID는 다른 프로세스이므로 건드리지 않았다. WSL 격리 환경은 재현을 위해 보존한다.

실행 명령은 각 manifest와 receipt에 있다. 재실행 시 새 출력 폴더를 사용한다. 원본 파일 및 기존 결과 덮어쓰기는 하지 않는다. 전체 계획의 완료가 아니라 M0–M1 완료와 M2 gate 중단 상태다.
