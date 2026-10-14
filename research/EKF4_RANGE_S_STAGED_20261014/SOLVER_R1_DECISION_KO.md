# EKF4 R1 — 목적함수 감사·solver 선택·중단 계약 (2026-10-14)

## 목적함수 재검토
국소 angle branch에서 Cholesky 인자 `Lp Lpᵀ=P⁻`, `Lr Lrᵀ=R`, `x=mu⁻+Lp y`를 사용한다.

`rho(y)=[y; solve(Lr, z-h(mu⁻+Lp y))]`, `J(y)=0.5*||rho(y)||²`, `grad J = Aᵀrho`, `A=∂rho/∂y`.

이는 **고정 Gaussian 운동 prior·상태 독립 Gaussian [range,s] 측정 공분산**에 대한 (상수항을 제외한) 음의 로그 posterior다. R과 P를 반복 중 변경하지 않으며 range-first는 초기 후보만 생성한다. 같은 r,s의 반복적 재투입, bias 직접 RF 측정 취급, RF Heading 독립 의사관측은 금지한다. `P_local=Lp (AᵀA)^-1 Lpᵀ`는 국소 GN 근사이며 비선형·다봉 posterior의 보장된 공분산이 아니다. 기존 목적함수는 변경하지 않는다.

## 선택한 solver
**prior-whitened safeguarded Gauss–Newton + 일반 구간 기존 Armijo backtracking + 매우 작은 마지막 스텝에서만 기울기 적분을 이용한 비용 변화 검사.** 이유: 목적함수가 비선형 least squares이며 원 실패는 곡률 폭주가 아닌 부동소수점 두 큰 비용값의 차를 비교하는 해상도 문제였다.

동일 목적함수에서 `J(y+d)-J(y)=∫₀¹ grad J(y+t d)ᵀ d dt`이므로, 국소 스텝에 대해 t=0, 1/2, 1의 Simpson 적분과 trapezoid 교차 검사를 사용한다. 이 검사는 다음 모든 조건에서만 작동한다: (1) 후보 gradient infinity norm ≤ **원래 1e-8**; (2) 백색화 좌표의 작은 스텝; (3) 직접 cost 차이는 machine-epsilon 규모 안에서만 불분명; (4) gradient의 국소 곡률 변화가 GN 예측과 부합; (5) Simpson과 trapezoid 일치; (6) 적분된 비용 감소가 기존 Armijo 요구를 충족. 어떤 조건이라도 실패하면 기존 backtracking/명시적인 미수렴 처리. 임계값 1e-8, 모든 Q/R, RF 함수, 초기조건, P2 사전등록 가설과 seed는 변경하지 않는다. 독립적인 GN full-step 무조건 허용이나 tolerance 상향은 하지 않는다.

## 동결 실패 및 확인 지표
기존 P2 run 38514443823: straight, bias=0, trial=0, MAP3, t=4.5s에서 `LINE_SEARCH_FAILED`, gradient 5.2678999634681034e-8. D1 run 38514766913 고정 입력에서 완전 GN step에 대한 double ΔJ=+4.6629367034256575e-15, 독립 80자리 ΔJ=-1.6056697178966146e-15, 다음 gradient 5.739139719018738e-10로 확인됐다. 기존 FAIL은 변경하지 않고 R1이 이 스냅샷을 해소하는지만 검증한다.

## 실행·중단 계약
GitHub Actions에서 동일 커밋 P0 16, P1 8 회귀 통과 후 **frozen failure 단독 regression**만 수행한다. 실패 마지막 iterate 출발, 원래 range-first 출발, 원래 gradient criterion, 독립 80자리 ΔJ와 적분 일치, 비수렴·angle chart 음성 대조, 원 목적함수·공분산 불변을 확인. 기존 failure snapshot / D1 ref 원본, P2 spec, synthetic.py, RF H/LUT, 데이터 및 과거 결과 수정 금지.

**이 작업은 P2 전체 synthetic 재실행, RF P3–P6, 재귀 성능, 다봉/거리 적분, factor graph 실험을 전혀 실행하지 않는다.** 해당 단계는 모두 NOT_RUN. Numerical PASS와 scientific_PASS는 분리하며 scientific_PASS=false. 실행 ID·Git SHA·입출력 해시·로그·JUnit과 실패 원본/성공 증빙을 별도로 남긴다. R1 PASS 시 즉시 STOP, 미통과 시 FAIL_CLOSED 및 원인 보고 후 STOP.
