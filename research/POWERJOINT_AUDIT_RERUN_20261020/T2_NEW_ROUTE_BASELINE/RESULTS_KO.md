# T2 신규 주로 기준선 정본

TECHNICAL_PASS. Actions run39359952488의 6개 성공 artifact에서 요약만 회수했다. BASELINE.csv는 9조건 × 4 bias × 3 arm =108행이다. seed0–4 motion noise 반복 180개 실행의 독립 scorer 최대 차는 1.137e-13, 비RF update는 0이다. 11개 공통 지표를 모두 보존했다.

정본 센서 설정 hash: `b05e7ead6cf658d20a4830094cec56332ffcc839e7dccf04fd4ce3a1f86ccef0`. 실제 엔진 파일 SHA256: `81f275d8697d612418cc4b5759301161ad7973c92d70abc30af0c1891f44ca01`. 전체 .25s motion을 원래 생성기로 재구성했으며 모든 공개 RADIO_POSE CSV와 생성 RF CSV의 byte identity를 인증했다. Sensor-v2 원본 잡음·초기오차 스트림을 사용하고 최대 2µm CSV 반올림 lateral 잔차만 허용했다. RF는 원래 radio pose_id에서만 갱신한다. O03 los_exists=false는 그대로 보존하며 LoS를 생성하지 않는다.

신규 POWER와 MEMORY는 기존 R2/R4/R5 전체로 학습했다. 이전 Chain F의 R2-heldout 학습 및 crosscase 센서와 다른 정의이므로 이전 숫자 parity를 주장하지 않는다. PREVIOUS_COMPARISON.csv에 108행별 이전 수치와 차이를 기록했으며 미공개 이전 값은 공란이다. crosscase 원본 구현은 미확보로 숫자 원인 완전 분해는 NOT_ESTABLISHED다.

|조건|B0 POWER1 Heading RMSE (°)|
|---|---:|
|O01_O0_M45_FULL|0.455960|
|C03_A_M45_FULL|0.610194|
|C03_B_M45_FULL|0.801081|
|O03_O0_M45_FULL|6.868341|
|C02_A_M45_FULL|2.235796|
|C02_B_M45_FULL|1.220517|
|C01_A_M45_FULL|3.966129|
|C01_B_M45_FULL|5.027763|
|O02_O0_M45_FULL|2.220134|

MOTION_NOISE_REPEAT_RANGE.csv는 DR4/JOINT4/POWER1의 seed0–4 범위만 담는다. 나머지 arm의 seed0 단일 값은 MOTION_NOISE_REPEAT_RANGE_ALL_ARMS.csv에 별도로 보존한다. 반복 범위는 같은 RF의 motion noise 및 원래 초기오차 스트림 반복이다. 독립 RF/장면 표본이 아니다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. C01–C03과 기존 주로는 같은 복도, O01–O03은 같은 오피스 장면이다. 조건 수를 독립 표본 수로 쓰거나 p-value를 계산하지 않는다. 이전 실패 기록은 삭제하지 않았다.

MOTION_NOISE_REPEAT_RANGE.csv는 seed0–4가 모두 있는 DR4/JOINT4/POWER1의 108행만 담고 sensor_seed_count=5를 명시했다. 실행 원본의 324행 범위표는 MOTION_NOISE_REPEAT_RANGE_ALL_ARMS.csv에 보존하며 MEMORY 계열의 seed0 한 번만 있는 범위를 반복 실험으로 해석하지 않는다.
