# P4: 동결 LoS/Full RF와 4-state 공동 관측의 동일 prior 단일갱신 검증

이 단계는 **합성 P2의 과학 효과와 독립**이며 P3 원본 39개 파일의 데이터 적격성 감사 결과를 참고한다. 첫 cloud 실행은 `R2_aA_m0`, `seed0`, 두 채널(LoS/Full), 5개 사전 선정 시점만 대상으로 한다. 원본 7case 전수·재귀 P6 또는 실제 기하 오차의 일반화 주장 불가.

각 시점에는 원래 3-state DR-only prior와 4-state bias 예측 prior를 별도로 계산. 4state `P_{pose,bias}`를 유지하고, raw Range/s의 같은 RF 묶음을 중복 사용하지 않는다. frozen archived LUT `s_model(x,y,psi)`와 offset Range `r=sqrt(...)+offset`, 상관 `R_sr=0`은 **원래 R0**로 명시, Full calibration의 진실이라고 주장하지 않는다.

비교:
- Frozen independent EKF3 Joint C vs 새 3state R0 공동 Gaussian: 동일 prior/관측/게이트 OFF의 수치 parity <1e-8.
- 4state 공동 Gaussian vs *고정 선형화* Range→s 순차 Gaussian: 동일 prior/관측/noise의 수치 parity <1e-8.
- 4state Range-first 이후 s 재선형화 및 원 prior 고정 반복 MAP: 수치 상태와 목적함수, 원시 관측 각 1회, t/route/seed 고정. Nonconvergence는 해당 경우만 무효. 성능은 truth scoring에만 사용.
- 관측별 gate 변화와 solver 선형화 효과를 혼동하지 않도록 먼저 **gate OFF** 결과만 비교; 이후 동일 R0 99% gate는 별도 축으로 기록.
- 4state prior는 frozen motion/gyro/초기 noise에서 0 bias prior와 0.1deg/s 불확실성을 사용. 정확한 true bias는 estimator 입력에 사용하지 않는다.

**사전 감사**: 해당 run 소스, P0 manifest, archived read-only qclean source 및 선택된 원본 자산의 SHA/array shape를 `p4_one_step.py audit`로 먼저 검사. 그 다음 클라우드에서만 스냅샷 모델·센서 생성기를 실행하고 결과/실패/출처를 보존. 감사 실패=해당 P4 실행 중단, 이미 확인된 합성 P2 결과까지 무효화하지 않음.

이 단계가 PASS여도 P5 2D 위치 적분의 TV 수렴, P6 재귀 전체 궤적의 RF 정확도는 **별도**. 앞선 G3 TV 0.387065라는 미수렴 결과를 소급 PASS로 만들지 않는다.
