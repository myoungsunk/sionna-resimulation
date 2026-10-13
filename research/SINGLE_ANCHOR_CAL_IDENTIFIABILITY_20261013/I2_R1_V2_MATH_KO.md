# R1 V2 수치 보완의 수식과 판정 범위

본 구현은 DR conditional measured-input target만 다룬다. Range·PF·Batch 전체 참조 승인은 하지 않는다.

## CDF

SF/eps를 prior 표준화 좌표 u,v로 놓으면 bg의 조건부 분포는 Gaussian이다. 정규화 함수 M(u,v)에는 bg prior와 DR likelihood의 bg 적분이 들어간다. 따라서 bg CDF의 분자는 integral phi(u)phi(v) M(u,v) Phi((b-mu(u,v))/sigma(u,v)) du dv이다.

정규화 M의 매끈한 적분이 수렴해도 매우 좁은 조건부 Gaussian의 Phi 전이부는 고정 격자에서 충분히 해상되지 않을 수 있다. V2는 mu(u,v)=b인 위치와 그 주변을 나누고 적응 적분한다. SF와 eps의 CDF는 해당 변수의 적분 상한을 직접 바꾸어 계산한다. PCHIP marginal density 보간은 사용하지 않는다.

QUADPACK 오차는 추정치이다. scan 구간 내부의 복수 교차나 접하는 root를 놓칠 수 있으며, tolerance/domain refinement와 해석 예제 시험은 수치적 증거이지 모든 CDF 오차의 엄밀한 인증이 아니다. 실제 실행 경고와 CDF error estimate도 함께 보존한다.

## Posterior 꼬리 상한

U = product_k (2*pi*qo_k)^(-1/2). 각 S_k >= qo_k > 0이므로 전체 DR likelihood <= U이다.

기존 posterior 평균을 중심으로 한 작은 whitened Calibration 직육면체 A에서 prior*likelihood의 interval 하한 f_lower를 구한다. Z >= volume(A)*f_lower = Z_lower > 0이다. A는 정규화 하한을 얻기 위한 적분 부분집합일 뿐, prior나 추정 공간을 좁히는 제약이 아니다.

SF/eps의 표준화 좌표가 [-B,B]^2 밖인 prior 질량은 union bound로 4*Phi(-B) 이하이며, Mills inequality로 4*exp(-B^2/2)/(B*sqrt(2*pi)) 이하이다. bg는 전체 실수축에서 적분한다.

따라서 posterior outside probability <= min(1, U * 4*exp(-B^2/2)/(B*sqrt(2*pi)) / Z_lower).

Z_lower와 U는 mpmath interval 50자리 계산으로 감싸고, float endpoint 변환과 최종 exp도 바깥 방향으로 반올림한다. 분모에 수치 quadrature evidence를 사용하지 않는다. 이는 명시한 모델과 입력 실수값에 대한 해석적 부등식의 구간연산 평가이며, mpmath 및 부동소수점 실행환경을 별도의 형식 검증기로 검증했다는 뜻은 아니다.

±32와 ±40 비교는 수치 영역 민감도 시험이며 물리적 calibration prior 변경이 아니다. tail 판정은 최종 ±40 상한에 적용한다. 초기 pose, RF, 실제 센서 생성모델, I3/I7 판정으로 일반화하지 않는다.
