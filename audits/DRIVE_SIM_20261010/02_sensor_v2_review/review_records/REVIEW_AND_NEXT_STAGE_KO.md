# 1단계 감사 및 sensor-v2 반영 보완

## 판정
제공 보고서의 1단계 산술 검산 설계는 적절하다. 현재 직접 확인한 것은 보고서 및 코드이며 72개 NPZ 독립 재계산은 이번에 반복하지 않았다. 과거 배열을 직접 검산한 것이 아니라 동일 조건 재생으로 대체했다는 경계를 유지한다. NEES 320.776/coverage0은 공유 RF 입력·필터를 이용한 metric 독립 검산 결과이며 RF/필터 타당성 PASS가 아니다.

## 브랜치와 기존 구현
기존 sensor-v2 checkout: D:/SLAM_bot/artifacts/DRIVE_SIM_SENSOR_V2_20261008_01a11a01/checkout. 로컬 branch codex/sensor-model-v2-20261008, HEAD2337c33. 첨부의 구현 전 상태는 오래된 상태다. 현재 4개 tracked 수정과 신규 source/config/test가 있다. 로컬 구현을 remote에 반영했다고 표현하지 않는다. 원격 HEAD는 이 보고서에서 검증 완료로 주장하지 않는다. 기존 미커밋 구현 15파일을 COPIED_SOURCE_MANIFEST.json으로 식별해 별도 checkout으로 복사했다. 다른 작업 checkout은 수정하지 않았다.

## 반영한 코드 수정
sensor_v2 설정/생성 입력/활성 실제 파라미터의 NaN/Inf 및 입력 차원, filter_v2 측정 배열의 길이/유한성 및 초기6상태를 조기에 검사한다. 모델 수식, Q/R, gate, RNG, production default는 변경하지 않는다. 새 입력 회귀4개 및 기존 unittest9그룹 통과. 정상 sensor-v2 입력의 센서 배열·추정·전체 공분산을 기존 구현과 exact 비교했으며 동일했다. original source15파일 hash 유지. git diff --check 성공.

## 다음 단계 실행 시 유의할 점
1. sensor-v2는 이미 구현돼 있다. 다시 작성하지 않고 검증할 세부 조건을 사전 고정한다. v2는 EKF/direct-s만 지원하며 다른 filter로 조용히 fallback하지 않는다.
2. 완전 모델 정합과 현실 모델 불일치를 별도 비교한다. generator true increments로 만든 q와 filter measured increments로 만든 q의 차이는 근사이며 완전 일치라고 부르지 않는다.
3. noise-only/RF없는 조건부터 시작하고 bias/SF/비대칭/wheelbase/RW/slip을 각각 추가한다. common scale은6상태에 없으므로 비중립 실험은 model mismatch다.
4. 정확한 pose 초기화에서도 calibration prior가 남으면 전체 상태 exact가 아니다. 실제 nuisance 초기오차 분포와 P0의 일치 여부를 기록한다.
5. 공유 input의 e=true-est 규약에서 C=-GQB^T 부호 및 전파 시점을 유지한다. known wheelbase correction은 외부 보정값이며 unknown true값을 estimator에 공급하지 않는다.
6. synthetic range 생성 sigma=.05와 기존 filter R(.05²+quantization+extra)은 정합하지 않는다. 진짜 matched-R 대조군은 별도 설정으로 동결하며 production R을 조정하지 않는다.
7. slip heavy-tail은 Gaussian matched 대조군에서 먼저 제외하고 별도 robustness 시험으로 추가한다. RW left-endpoint 적분과 continuous Brownian 적분을 혼동하지 않는다.
8. legacy Euler truth와 v2 SE2 전파의 차이를 RF/LUT 잔차와 분리한다. 원 trajectory를 조용히 바꾸지 않는다.
9. 기존 correlation ablation의 효과가 작았다는 사실을 F02 해결로 확대하지 않는다. scalar RF range/s 시간상관·교차상관은 여전히 미처리다.
10. 다음 matched sensor/filter 시험 뒤에만 원 2×2 RF 비교와 weighting/gating 분리를 이어간다. 기존 R2산술검산과 기존 R1sensor-v2 RFsubset은 데이터/초기화가 달라 직접 전후비교가 아니다. 동일 H/route/prior/control 설정의 별도 비교가 필요하다.

## 종료와 범위
이번에는 기존 sensor-v2를 확인·격리 복사하고 최소 입력 계약을 보완 및 회귀 검증했다. 새로운 localization Monte Carlo/72array 재검산/full RF/새 production 실행은 하지 않았다. F01/F02 유지, sensor-v2 원격 commit/push/merge 미수행. sensor-v2의 기존1–4단계 보고서는 과거 실행 증거이며 이번 재실행으로 표현하지 않는다.
