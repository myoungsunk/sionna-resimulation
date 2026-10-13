# Huber-only의 D5 gyro_bias 확장 계약

기준 commit: 7a499d760bc645624ac3b1f8f844c657b767c300. M0 및 기존 RF_HUBER_ONLY를 그대로 재사용한다. 원본 FP s, B_OLD/E1 입력, 3-state, R0, Huber delta1.345, 99% NIS gate를 유지한다. 새 학습·파라미터 탐색·ray tracing·Bias 상태 추가는 하지 않는다.

## 범위

- noise_pair level1: 기존7조건, seeds0/1/2, LoS B_OLD 및 Full B_OLD/E1, D0/A/B/C. 2모델×252셀=504셀. 기존 M1_FOLLOWUP 결과와 각모델252셀의 절대1e-8 parity, 수용/거부 횟수 확인.
- gyro_bias level0/1/2: 같은RF·초기조건·경로·seed·관측 구성을 사용해 level당504셀, 합계1512셀.
- 전체2016셀. 먼저 각조건의 R2_aA_m0·seed0 smoke24셀을 통과한다. 원본 D5 run_one에 같은 캐시 관측·Range를 넣어 smoke의 M0를 독립 대조한다. noise_pair 전체재현 통과 후 gyro full을 수행한다.
- D5 generator 정의상 gyro_bias는 gyro bias만 활성화하며 wheel/gyro 백색잡음은 꺼진다. bias크기0.01/0.05/0.20deg/s, 부호는 기존seed stream. noise_pair에 Bias만 추가한 matched ablation이라고 주장하지 않는다.

## 고정·판정

평가시작30초, 기존 초기pose/P와 motion generator, LoS/Full LUT, Range cache 및 gate를 보존한다. C는 공동 Huber block, gate는 보정전 원본 R0 NIS이다. 임계값을 결과에 맞춰 바꾸지 않는다.

Heading/위치RMSE, Pose/Heading NEES, 95%포함률, 수용·거부율, 조건별 악화, p95오차 및 trace 공분산 유효성을 함께 보고한다. D0 두모델은 수치동일해야 한다. M0의 motion/관측 parity 불일치 또는 입력hash 불일치·비유한값·공분산실패는 fail-closed 중단한다. 큰 유한 RMSE/NEES나 낮은 포함률은 결과로 남기며 성능실패를 숨기기 위해 중단하거나 튜닝하지 않는다.

통계단위는 경로조건/seed이며 시점을 독립표본으로 세지 않는다. seed별고정Bias부호와 작은seed수, 단일RF scene, E1모델선택·공간중복 제한을 유지한다. 기존 M0와 Huber-only는 Bias state를 추정하지 않는3-state라는 경계를 명시한다. 이번결과로 scientific_PASS=true를 선언하지 않는다.

## 증빙

원본코드·RF·기존결과를 변경하지 않는 신규runner·테스트·결과폴더를 사용한다. 명령·UTC·종료코드·입출력/소스SHA, smoke/full parity, 원시trace 재계산·감사·프로세스종료를 기록하고 GitHub 연구브랜치에 게시한다. M1/M2재설계 또는추가파라미터 탐색은 이번범위에 포함하지 않는다.
