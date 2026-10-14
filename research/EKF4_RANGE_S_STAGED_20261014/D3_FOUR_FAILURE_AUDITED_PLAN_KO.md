# D3 — P2 네 미수렴 스텝 고정 수치 원인 감사·분석 (사전등록)

2026-10-14. 원본 브랜치 `research/ekf4-range-s-staged-20261014`, 기준 커밋 `99be5e38f8b68d2ed441b75222d8ff599db40a52`.
D3 작업 브랜치: `research/ekf4-d3-four-failure-rootcause-20261014`. 사용자 요청은 **기존 네 실패 수치 원인 확인**과 **다른 RF 연구 결과를 향후 계획에 반영**. R3 solver 코드를 수정하거나 P2 전체를 재실행하는 일은 이 요청에 포함하지 않는다.

## 결정 문장
**“원본 입력 네 건의 수치 종료가 실제 목적함수의 국소 한계/그라디언트 계산 불능 때문인가, 부동소수점 비용 비교·Armijo/가드 분기 때문에 유효한 스텝을 잃은 것인가?”** 결과에 따라 solver 수정 필요 지점을 선택한다. 답하지 못한 사건은 UNSOLVED로 분류해 관련 과학 주장을 보류하며, 진단 오류 자체가 기존 과학 데이터 전체를 무효화하지 않는다.

## 원본과 4건 입력 고정
GitHub Actions 원본: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38526390416
artifact ID 11875912063, ZIP SHA256 `d25e96077a6b487fd0d90591362e141ee3908457808edf8688a7d3a480bad26b`.
원 `FINAL.json`의 source SHA: `core.py=46746402e3a40e4acf673ae4fa2ab86dd293f62004632108374349f838ff5ffe`, `stable_descent.py=57271cef8fc828b383153642db812a2e537730689d46974b17f6c9b778608089`, `synthetic.py=c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643`, `P2_SPEC.json=548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7`.
원 네 경우의 NPZ SHA256 (이 값들을 변경하거나 재생성하지 않는다):
- straight / true bias +0.05 / trial0 / MAP3 / 28.0 s: `f8fd1d3f0ceeebfda3322ca8a03c3eddbeb663d1078e39db342c3ec23cf2bb55`.
- straight / true bias +0.05 / trial0 / MAP4 / 30.5 s: `77415d27128ba08ba193bab632fed98a858aeec530f64d0963c2331e5e080dd2`.
- turn / true bias +0.05 / trial0 / MAP3 / 32.0 s: `ea1298400b662769466fc3219c3ec8ad32be3a9da3119e0af855e7bfafd3755a`.
- return / true bias +0.05 / trial0 / MAP3 / 32.0 s: `b43db01f7bbc59cd2f27a553c2841173392342416b4a609001c2abecae96f16c`.
아카이브의 `FAILURE.json`, `FAILED_STEP.npz`, `FINAL.json`를 직접 사용한다. 실패 history, `prior_x,P,z,R,prior_delta` 및 covariance output을 절대로 바꾸지 않는다.

## 실행 전 두 단계 감사
1. **소스 사전감사**: GitHub Actions checkout 이후, 수학/진단 코드 실행보다 먼저 `d3_pre_audit.py --phase source` 수행. 목적함수·core·실험 계약의 SHA/AST, 진단 코드의 원자료 경로, 영수증·workflow 순서, 결론과 STOP 범위를 검사한다. `HOLD`라면 다른 검증/진단 실행 없이 종료하고 해당 결함만 수정한다.
2. **원본 입력 사전감사**: GitHub Actions `gh run download`로 보존된 artifact를 가져온 뒤 `d3_pre_audit.py --phase input` 수행. 원 `FINAL.json`과 네 NPZ 및 JSON의 byte SHA, source run/step/모델, `scientific_PASS=false`를 대조. `HOLD`는 해당 D3 계산만 중단.
3. **검증된 한정 진단**: 사전감사 GO 영수증 두 개와 소스 동일성 확인 후에만 `d3_fixed_four.py` 실행. GitHub 클라우드 외 수학 진단 실행하지 않음. 이전 R1/R2 시험 재실행/대형 P2 재실행 불필요.

## 사전 결정된 수치 비교
A. 원 소스의 `MAP` 실패 상태·최종 목적함수·gradient/history를 동일 고정 입력에서 재현하여 NPZ와 비교.
B. prior-whitened Gaussian `J(y)=1/2||[y,Lr^-1(z-h(mu+Lp y))]||²`에서 float64 `J,g,B`와 독립 80자리 `J,g`를 비교. 독립 RF 식은 `s=0.8 sin(psi)+0.15 dy/sqrt(dx²+dy²)`; h_range는 slant range. 원 모델 `SyntheticRF`와 forward parity 필수.
C. **저장된 마지막 iterate**에서 full GN/damped 후보의 float64 cost, 고정밀 cost, 분석 gradient를 비교. 실제 `ΔJ`의 부호와 `||g_next||∞<=1e-8` 여부를 별도로 판정한다.
D. `history`의 모든 accepted step을 초기 range-first 부터 재구성하고 직접 Armijo, `roundoff` 허용, 높은 정밀도의 `ΔJ` 및 기울기 개선, 첫 guard 거절 지점을 분류한다. 저장 `prior_delta`로부터 재현 오차를 보고한다.
E. 저장 입력에서 독립 root/Hessian 또는 SciPy 잔차 최소화 비교. SciPy success flag만으로 수렴 판정하지 않는다. 고정밀 root가 실패하더라도 A–D 범위의 결론만 확정하고 해당 root 검사를 UNRESOLVED로 기록한다.

## 판정·영향 범위
- **CONFIRMED_NUMERICAL_ACCEPTANCE_FAILURE**: 원 고정 입력에서 고정밀로 실제 감소하고 원 gradient 기준을 만족하는 스텝이 존재하는데 코드의 cost/guard가 거절함. 특정 solver 동작에 대한 결론으로 제한.
- **CONFIRMED_SPURIOUS_ACCEPTANCE**: 원 코드가 accepted한 스텝에서 고정밀 실제 J가 증가했음을 확인. 원 계약이 허용한 `roundoff` 분기는 증상과 함께 기록.
- **NUMERICAL_GRADIENT_FLOOR**: 고정밀 g와 double g 불일치로 double의 정지 판단이 불안정함을 확인.
- **UNRESOLVED**: 입력 parity/재현/고정밀 계산이 결론을 지지하지 못함. 실패 결과를 채택하지 않는다.

이 진단은 **MAP4 vs MAP3 정확도 비교나 실제 RF 실험이 아니다.** `P2=INCOMPLETE`, `P3-P6=NOT_RUN`, `scientific_PASS=false`를 유지.

## 별도 RF 연구 향후 반영 (실험 미실행)
참고 브랜치: `research/rf-range-sign-audit-g2g3-20261014`, `e7ee115836bce20188f6d2942f34f0d7a75ddc39`. 원 signed RF/range 비교는 GitHub run 38523237789에서 성공했지만 **새 G2/G3 모델은 NOT_IMPLEMENTED**.
큰 DR-RF positive conflict/L2에서 RF가 훨씬 정확한 관측 다수, 동시에 보정 E1의 negative-tail 반례도 있다. 향후 사전등록은 `DR fault vs RF outlier` 잠재 모드와 **signed corrected RF likelihood**를 분리, Range 한번만 사용하고 full pose–yaw–bias covariance 유지. True bias label/정답 Range를 온라인 분기 선택에 사용하지 않음. 단순 `RF shorter ⇒ always trust RF`는 금지. 먼저 독립 scene/held-out, 음성 C3/C4, 정확 G2=G3 Bayes 동일성과 충분한 posterior 적분 수렴을 검증. 이번 D3의 `SyntheticRF`나 Q/R, 기존 P2 비교 조건에는 혼합하지 않는다.

## 예산과 종료
단일 GitHub hosted D3 job, 네 동결 입력과 1회 소스/입력 감사. 실패 시 해당 범위의 코드·자료 원인만 제한적으로 진단, 과학 가설 변경/새 solver 수정/전체 P2 run 없이 확정·미확정 보고 후 종료. 원시 각 step·MP/float delta와 SHA 영수증 보존. 완료 시 STOP.
