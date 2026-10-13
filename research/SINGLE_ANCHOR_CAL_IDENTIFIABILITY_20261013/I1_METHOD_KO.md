# I1 수학·해석 계약

I1은 nominal calibration=0, wheelbase error=0, slip/RW 없음인 모델 일치 설계점에서 수행한다. 생성 단계에서 MOTION의 참 이동량을 noiseless wheel/gyro/odom 관측으로 변환한다. 분석 함수에는 이 관측과 후보 초기 6-state만 전달한다. 기존 D6의 ±drift·slip 세계 전체를 재현한 실험이 아니다. 신규 sensor/PF seed 및 독립 확증 입력은 사용하지 않는다.

## 관측과 미지수

미지수는 초기 [x,y,psi,bg,SFg,eps]이다. bg/eps가 관심 대상이고 초기 pose/SFg를 nuisance로 제거한다. wheelbase는 이 I1 설계에서 정확히 알려진 0.287 m로 고정한다. wheelbase 자체가 미지인 세계의 식별성을 주장하지 않는다.

연속 기준은 동결 센서 모델의 SE(2) 이동과 odometry_model이다. 거리에는 R23에 명시된 anchor A=(4,0,2.65), B=(10,0,2.65), robot z=.45를 사용한다. 사전에 선택한 Ideal Range sigma=.05 m, 5 Hz에서 국소 정보를 계산한다. 실제 RF 채널이나 E1을 사용하지 않는다.

구조적 민감도는 후보 Calibration로 보정한 관측 입력을 전체 시간축에 전파한 비선형 관측 평균의 Jacobian이다. analytic Jacobian을 중앙차분 및 동결 transition과 비교한다. 모든 열을 I1_SPEC의 물리적 척도로 무차원화한다.

## 정보의 정의와 상관

보고하는 수치는 **관측 입력에 조건부인 고정 공분산 Gaussian tangent 모델의 평균 정보**이다. 완전한 비선형 센서 생성 likelihood의 Fisher 정보나 실제 posterior가 아니다. 공분산의 파라미터 의존성에서 오는 정보항은 포함하지 않는다.

입력 잡음을 시계열로 전파하고 odometry와의 C=-GQB를 유지한다. 초기 noise-state covariance는 0으로 두어 미지 초기 상태의 prior와 분리한다. 혁신 whitening으로 시간상관을 제거한 Jacobian을 J라 하면 I=J'J이다. 테스트에서는 짧은 설계의 전체 noise-to-observation 행렬을 직접 구성하여 whitening 후 공분산이 단위행렬인지 검증했다.

Calibration 유효 정보는 nuisance 열의 SVD 직교 투영으로 구한다: E=(I-U_n U_n')J_c, I_eff=E'E. 이는 해당 선형화에서 Schur complement/pseudoinverse와 동치이며 불필요한 정규화나 covariance repair를 적용하지 않는다. 허용 rtol 1e-8/1e-10/1e-12의 rank 안정성을 기록한다. 숫자상 거의 영인 고유값만으로 정확한 비식별성을 선언하지 않는다.

DATA_ONLY는 prior 없음이다. POSE_PRIOR는 S1에서만 기존 초기 pose prior를 추가한다. POSTERIOR는 S0에서 cal prior만, S1에서 pose와 cal prior를 추가한 국소 정보다. POSTERIOR라는 행 이름은 이 국소 Gaussian 근사의 prior 포함 정보이고, 샘플링으로 얻은 posterior 분포가 아니다.

## 정확한 비선형 불변성

S0에서 전체 pose를 anchor 주위로 회전해도 DR+range 관측은 불변이다. Calibration은 바꾸지 않으므로 이 gauge만으로 bg/eps가 비식별이라고 결론 내리지 않는다.

일정속도 직진 nominal 관측 d=v dt, g=o=0에는

bg = eps v (1+SFg) / [b(1-eps²/4)]

라는 연속 Calibration 상태군이 같은 DR 관측을 만든다. 이는 실제 식의 대입과 관측 차이로 검증한다. 가변속도에서는 같은 bg/eps가 모든 시점에서 위 관계를 동시에 만족하지 못할 수 있다.

초기 pose가 anchor의 방사축에 있고 heading이 그 축을 따를 때 ±bg, ±eps의 궤적은 좌우 반사이며 range가 같다. 두 비영 Calibration 값이 구별되지 않는 전역 모호성이다. 영 Calibration 기준 range와는 작지만 차이가 나므로 '연속 Calibration 영공간이 Range에서도 그대로 남는다'고 해석하지 않는다. 국소 rank 결손·고차 구별 가능성·전역 반사 모호성을 구분한다.

## Profile 경계

4개 선택 조건 × S0/S1에서 bg와 eps의 1차원 profile과 자유 최적화를 수행한다. 각 profile은 3개 시작점, 사전 고정 경계/격자를 사용하며 다른 Calibration과 nuisance를 함께 최적화한다. 목적함수는 정확한 비선형 관측 평균에 고정된 tangent covariance를 적용한 것이다. noiseless 설계점의 profile이며 실제 잡음 자료의 likelihood confidence interval이 아니다. 국소 최적화 수렴은 전역 최적성이나 posterior 단봉성을 보장하지 않는다. 실패한 시작점도 모두 보존한다.

F0는 기존 LUT의 최대 보간오차 gate 실패로 NOT_RUN이다. 승인된 LUT 또는 별도로 검증한 direct FFD s 관측모델이 필요하다. 기준을 완화하거나 임의 s 함수를 넣지 않는다. I2와 I7 L1–L7은 실행하지 않는다.
