# 다음 턴 C/D 인계 — 아직 실행하지 않음

기준: 브랜치 analysis/palo-risk-ab-20261108, A/B 결과 커밋 5d929dcca9005b1ac2147fe155d9ec33ce605ab0.
A/B source 427fa5371511f272e54cb116908f515a2866bfe6; 원본 입력 16450dc14366ba4ed2cb4e151952493f0efc944f.

## 유지할 사항

- results/FROZEN_MODELS.json과 M1/M2/M3_models.joblib을 먼저 고정 대조로 사용한다. 기존 평가결과를 보고 같은 test에 재조정한 모델은 별도 탐색 버전으로 기록한다.
- 특징 순서·단위·lag5(과거5표본, 현재 제외)는 run_ab.py의 features와 일치시킨다. 새로운 정책 자신의 prior/candidate로 특징을 다시 계산한다.
- 순수 DR 참조는 같은 IMU/odom을 공유하므로 독립 참값/독립 센서가 아니다.
- raw d0/CIR/전력은 현재 B에 포함하지 않았다. 추가 시 pose_id·시간·탭 정의와 인과적 가용성 확인.

## C: 실제 폐루프

동결된 POL_HEADING LUT 및 기존 운동·Q/R를 사용한다. 원본 S4 X/P/NIS/mask, DR4를 재현한 뒤 진행한다. 바이너리 거부/전량과 soft alpha={0,.05,.1,.25,.5,1}을 비교한다. soft는 mean만 줄이지 말고 R_alpha=(HPH+R)/alpha-HPH와 일관되는 P를 사용한다.

A/B 모델들은 최종 채택되지 않았다. M2는 DR B0/L0에서 큰 오수용, M3는 DR 모든 조건 거부를 보였다. 자기 궤적이 그러한 prior를 방문하는지 C에서 확인하는 것이 목적이다. A/B의 fixed_prior_heading_rmse를 폐루프 성능으로 인용하지 않는다.

초기부터 선택하는 예방 시험과 t=140 공통 S4 상태에서 전환하는 회복 시험을 분리한다. '현재 factor 제거'는 같은 prior의 OFF 후보로 돌아가는 것이며 과거 RF 영향의 취소가 아니다. 과거 영향 복원은 checkpoint+replay 등의 별도 대조로 설계한다.

soft 위험 판정기는 아직 학습되지 않았다. 첫 대조는 fixed alpha와 multi-alpha 즉시 오라클로 행동공간의 이득을 검증한다. 학습 alpha 정책을 추가한다면 fit/cal에서만 선택하고, 이 확장 자체를 명시한다. 오라클은 전역최적/구현가능 상한으로 주장하지 않는다.

## D: 장기 손익과 신뢰도

동일 prior의 ON/OFF/alpha 개입 후 동일 고정 인과 정책으로 10/20초 추적한다. 미래 참값은 오프라인 점수에만 사용하고 horizon이 분할 경계를 넘지 않게 한다. Heading·XY뿐 아니라 bg, P, NEES, 포함률, 큰 오수용 연속 길이, 첫 재수용을 기록한다.

처음부터의 DR baseline과 hot-start 이후 RF-off를 구분한다. 사후 P 확대만으로 정확도 개선을 주장하지 않는다. 단일 경로/seed의 반복 후보는 독립 표본이 아니다. 미사용 경로·RF/잡음이 없다면 D의 일반화/통계적 보정은 NOT_ESTABLISHED로 남긴다.

## 추가 개선은 별도 버전으로

M2 calibration Heading 순이득의 98.05%가 L2/DR에서 나온 점, B0/DR·L0/DR calibration 수용0인 영역에서 test 큰 손실이 발생한 점을 보존한다. 평균 이득 최대화보다 조건/블록별 손실, 비어 있는 calibration 영역, 유익 보정 기회 하한을 함께 다루는 설계는 별도 사전 계약으로 동결한다. true bias level을 온라인 mode 스위치로 쓰면 안 된다.
