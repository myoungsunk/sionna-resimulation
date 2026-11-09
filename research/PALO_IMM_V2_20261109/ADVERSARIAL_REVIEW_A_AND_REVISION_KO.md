# V2-A 실제 구현·결과의 적대적 리뷰와 수정 동결

시점: V2-A Actions #42560919706 SUCCESS, 원시 결과 커밋 2e1254e06a8cbcc9fdf2923310fa6f46733f486a를 확인한 뒤 작성. V2-B는 아직 실행하지 않았음. 동일 작성자의 적대적 자기·교차감사이며 외부 독립 리뷰가 아님.

## 1. 먼저 계산 기반을 검정
첫 실행 #42560549334: unit test 8개 통과, 원본 scalar S4 전체 재현이 과거와 동일한 Full/B0 미세 오차로 FAIL. 라이브러리를 맞춰도 X1.664249e-7/P3.193092e-8/NIS4.295312e-7, mask 불일치0. 실패 로그·입력은 보존. 이후 이미 게시·검증됐던 common.py 벡터 LUT/update 수치 경로로 어댑터를 명시적으로 바꿈. Rs/Q/모형/허용치는 변경하지 않음.
재실행 #42560919706: **16/16 원본 재현 PASS**, 최대 X2.830606e-9/P2.486742e-10/NIS1.161381e-8, mask0. numerical implementation ordering의 영향은 분리됐지만 scalar 경로의 모든 미세 오차 원인을 라이브러리 하나로 확정하지 않음.
원본 manifest98파일 무결성, 8개 단위검사, 원시 46992step/960개 성능행 별도 검산 통과. metric 오차1.42e-14, covariance 대체식6.94e-18, loglik3.55e-15. 같은 작성자가 분리 계산한 감사이며 독립 과학 인증 아님.

## 2. 실제 V2-A의 성능: 코드 정상과 연구 효과는 다름
R2-B Full, t>=40 (779시점, 개발구간 포함 기술통계):
|bias|S4 heading/XY|즉시 축약 A|모드별 IMM A|
|--|--|--|--|
|B0|1.540°/.308m|1.833°/.298m|1.777°/.327m|
|L0|1.529°/.304m|1.842°/.304m|1.777°/.326m|
|L1|1.406°/.301m|1.649°/.296m|1.712°/.321m|
|L2|1.292°/.308m|1.528°/.300m|1.540°/.309m|
따라서 A가 S4를 개선했다는 주장은 불가. 같은 emission/T의 collapse 대조와도 Heading/XY 공동 개선은 확인 못함. Full IMM 혼합 헤딩95 포함률64.4–67.9%, nominal95%와 다름.
독립 시간부분 t>=140에서 B0 S4 .5805°/.3484m vs IMM .5843°/.3516m, L2 S4 .6040°/.3464m vs IMM .6897°/.3401m. 이 자료도 이미 여러 번 본 동일 R2이며 새로운 blind test가 아님.

## 3. 지지측이 인정할 구조적 개선
- top2 pruning을 없애고 정상/오염 모드 모두 x,P를 유지함. 유한 가중치의 매우 작은 모드도 삭제하지 않음.
- row-stochastic 비대칭 T 방향과 전체 모멘트 혼합, Joseph 갱신, 로그 확률정규화, synthetic OFF→G 복귀 검사 통과.
- 넓은 C도 정규화된 Gaussian에 해당하는 약한 state/P 갱신을 수행. Uniform 밀도와 MAP-only 영구OFF 설계는 더 이상 없음.
- 즉시축약과 IMM은 같은 likelihood/T/데이터를 사용. S4와 관측정책 차이를 보존 효과로 오인하지 않음.

## 4. 적대적 반론
A1. C는 여전히 평균0의 독립 큰 잡음이다. R2 개발 reference residual lag1=.8562, Full IMM의 정상예측 표준화 혁신 lag1 약.871. 잠재모드가 오래 C라는 사실만으로 잔차값이 같은 부호로 지속되는 구조를 설명하지 못한다.
A2. 개발 C posterior가중 평균 residual +.2282, 유효 C 질량 약45.08/600표본. 폭을 키우는 것만으로는 방향성 잔차가 매번 헤딩·위치·bias로 흡수될 수 있다. 이것이 실패의 유일 인과 원인이라는 주장은 하지 않음.
A3. 후보 하나의 헤딩이 좋아도 전체XY가 더 나빠지며 calibration도 개선되지 않음. IMM 정상모드 확률을 유익 보정 확률이라고 해석 금지.
A4. T/Rc를 같은 R2 개발구간의 reference residual로 fit했으므로 데이터 요구와 한계가 있다. 약45개 C 가중표본으로 여러 parameter를 과신할 수 없다. 오염 event5개 수준, 신환경에서 dwell/variance가 달라질 수 있음.
A5. 물리적으로 s는 [-1,1]이나 Gaussian은 실수축 surrogate이다. 정확 bounded likelihood로 주장하지 않음. 경계에 따른 정규화 문제가 없는지 별도 검사 필요.
A6. non-linear 관측의 EKF likelihood 자체가 근사이고 IMM 조건부 혼합으로 이력정보를 잃는다. 회복가능성·가설보존과 최종 정확도는 별개.

## 5. 수정 B의 범위 — 1개 RF offset 상태만 추가
합의된 V2-B 대안으로 c를 하나 추가:
- G: s=h(x)+ε, 기존 Rs=.0081. 비활성 c는 mean0,var Vc=Rc−Rs,cross0으로 재설정.
- C: s=h(x)+c+ε, c_k=ρc_{k−1}+η, Qc=(1−ρ²)Vc. x-c 교차공분산 보존.
- 동일한 G/C T, pi0, Rs, Rc, 초기 motion x/P, 데이터 split 유지. 새로운 gate/classifier/CIR/LiDAR/강도선택기 추가하지 않음.
- rho만 기존 600개 개발 residual에서 추정. A의 이미 고정된 HMM gamma_C>.5 연속 구간 길이>=2를 사용; stationary latent AR(1)+Rs Kalman marginal likelihood를 [0,.999]에서 최적화. 시험 RMSE에 대한 파라미터 탐색 금지.
- 단순 noise 보정 AR moment 추정은 rho>1이었으므로 그 값을 몰래 clipping하여 채택하지 않음. 사용한 likelihood profile/최적화/구간과 bound 여부를 모두 기록.
- c와 헤딩·gyro bias가 혼동될 위험을 인정. rho=0일 때 C의 c 주변화가 V2-A 넓은 Gaussian과 같은 x-marginal이 되는 제한검사 필수. 정상 G도 기존4D와 일치해야 함.

## 6. 재검정 / 실패 조건
B의 inference에는 truth/LoS/reference bias 입력 금지. 5D 혼합·reset·Pxc 전파·모드복귀·rho0=V2A·원형각·causality·입력 오류를 unit/audit로 검사. R2 Full/LoS×4 bias의 결과는 A/S4/collapse와 모두 비교하고, 가능하면 R4-A/R5-A/R5-B의 기존 실패 경로로 frozen 전이를 평가한다. 새 경로로 rho/T/Rc를 수정하지 않음.
B가 A보다 좋아도 S4보다 불안정하거나 XY/bias/tail/coverage를 악화하면 최종 채택 보류. C에 오차를 흡수시켜 heading 정보를 잃으면 그 실패를 공개. 개선된 숫자만 골라 주장하지 않음.

**판정: V2-A 구현감사 PASS / 연구채택 FAIL. V2-B 단일 persistent-offset 수정 실행 승인 범위이며 성능 결과는 아직 없음.**
