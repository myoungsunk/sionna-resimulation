# R2 단일 능동 문제 해결 trial — 목적함수 유지, step 수용 근거 교체

## D2 근거
D2 run 38519216213 / source ae2c60c2f3a96003778cc52374ad101e1edcd3de에서 두 고정 입력을 진단했다. 원 4.5s 사례는 R1 CONVERGED. 새 6.0s 사례는 R1 LINE_SEARCH_FAILED 재현. 새 입력에서 GN full-step의 실제 80자리 비용 변화 -7.2323459547e-17, double +2.9976021665e-14, 다음 gradient 7.5474e-10로 원 기준 1e-8보다 작음. 정확 Hessian 고유값 1.039/1.095/1.148로 양수. 그러나 GN 곡률 근사와 gradient 변화의 차이가 6.40%여서 R1의 5% 제한에 걸렸다.

이는 GN의 잔차 곡률 생략과 실제 비매끄러움을 혼동한 보호 조건의 한계에 대한 고정 입력 근거다. 기존 함수 자체의 식은 바꾸지 않는다. 진단된 SciPy TRF/dogbox/LM들은 새 입력에서 ftol success였으나 해석 gradient가 약 2.53–2.61e-8로 원 기준보다 커서 단순 교체·success 플래그 채택을 하지 않는다. 진단의 scipy max_nfev=500은 생산 80회 설정을 대체하지 않는다.

## 수정 가설 R2-I
J(y+d)-J(y)=integral grad J(y+t*d).d dt를 실제 기울기로 계산하면, GN Hessian과의 임의 5% 일치 조건 없이 동일한 MAP 목적함수의 감소를 확인할 수 있다. 3점/5점 composite Simpson의 일치, numerical noise estimate, strong-Wolfe directional contraction과 전체 gradient 감소를 검사한다. 기존 tiny-step 1e-6 scale/직접 비용 불확실 64eps 구간/Armijo 1e-4 조건을 유지한다. 이 검사 통과는 convergence가 아니며, 종료는 원래 gradient 1e-8로만 결정한다. 아직 threshold에 도달하지 않은 유효한 감소 스텝도 PROGRESS로 허용하되 종료를 선언하지 않는다.

R2는 tolerance 상향이나 Q/R/prior/측정 수정이 아니다. 정밀한 비선형 문제에 대한 전역 수렴 증명도 아니다. quadrature error와 FP noise는 diagnostics이지 수학적으로 인증된 error bounds가 아니다.

## 실행 순서
1. 같은 R2 커밋에서 기존 P0 16/P1 8/R1 5 전부 회귀검증. 원 실패 스냅샷과 P2 spec 보호.
2. 새 6.0s와 원 4.5s의 원래 Range-first 시작 및 저장 iterate 시작을 모두 검증. 동일 objective/covariance, 양의 Hessian·작은 stationary gradient, 3/5점 integration sign/80자리 D2 부호와 대조.
3. 비종결 감소 스텝 및 uphill/큰스텝/noisy quadrature 거절 대조. convergence criterion을 약하게 만들지 않았음을 확인.
4. 동결 synthetic.py/P2_SPEC/600 paired trial 설정으로 처음부터 P2 재실행. 실패 사례 생략 금지.
5. 이 R2 해결 trial에서 회귀/전체 P2가 다시 막히거나 주가설 미지지라면, 한 번 더 임의 수정하지 않고 STOP. 실패 입력/로그/진행량을 보고한다. 통과한 경우만 기존 P3 단계 검토로 이동.

## 보호 SHA256
P2_SPEC.json 548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7
synthetic.py c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643
R1 baseline core b8cd844003a865fc02b41286233980278b4ea7a2140b1fabe440166d8894afa9
R2 core 46746402e3a40e4acf673ae4fa2ab86dd293f62004632108374349f838ff5ffe

최초 실패·R1 성공·P2 재개 실패·D2를 모두 보존한다. scientific_PASS=false, 현재 수학·합성 범위만 다룬다.
