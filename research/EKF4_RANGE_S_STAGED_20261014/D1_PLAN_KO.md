# D1: 최초 P2 중단의 고정 입력 진단

P2의 과학적 효과 판정은 아직 불가능하다. 첫 straight/bias0/trial0의 MAP3, 4.5s에서 LINE_SEARCH_FAILED. 기울기 무한대 norm 5.2679e-8은 동결 기준 1e-8보다 크다. 실패를 PASS로 바꾸지 않는다.

가설 D1-N: 최적점 가까이에서 요구하는 비용 감소가 double 비용 계산의 분해능보다 작아, Armijo 비용 비교가 유효한 Gauss–Newton 스텝을 거부했다. 대립 가능성은 비정상 curvature/잘못된 Jacobian/다른 국소해/실제 발산이다.

고정 실패 snapshot을 사용하여 다음만 GitHub cloud에서 실행한다.
1. 원래 solver를 재실행하고 상태·기울기·실패 여부를 기록한다. 플랫폼 차이로 이번 replay가 통과해도 최초 실패는 유지한다.
2. 저장된 마지막 iterate에서 완전 GN step들의 double 비용·기울기와 80자리 독립 mpmath 목적함수 값을 대조한다. 순수 GN은 진단이며 배포용 대체 solver가 아니다.
3. SciPy least_squares(해석 Jacobian 및 독립 차분)를 동일 목적함수에서 대조한다.
4. 고정밀 stationary point와 Hessian을 확인한다. double에서 거부된 step이 고정밀 비용을 줄이고, 원래 1e-8 기울기 기준을 충족하는지 검사한다.
5. 어떤 경우에도 R,Q,prior,센서,가설의 효과판정 기준 및 원래 결과는 변경하지 않는다. P2 전체/P3 이후는 이 진단 workflow에서 실행하지 않는다.

이것은 실패 후 개발용 수치 진단이다. 독립 과학 확증이나 bias 효과 성공으로 주장하지 않는다. 구현 수정은 증거 확인 후 별도 commit/회귀검증으로 진행한다.
