# EKF4 Solver R1 — 목적함수 감사, solver 수정, 최초 실패 회귀검증

## 완료 범위
본 결과는 기존 `research/ekf4-range-s-staged-20261014`의 첫 MAP3 수치 실패만을 고친 후 원본 회귀검증까지 수행한 결과다. **P2 전체 실험, P3–P6, 실제 RF, 다봉 또는 factor graph 구현은 수행하지 않았다.**

실행 소스 commit: `4fa3970808fdd75e9ae3d4c8081c547f1c3f033f`; 사전 결정 기록: `SOLVER_R1_DECISION_KO.md`.
실행: [GitHub Actions Run 38517841360](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38517841360), job 115700559264, GitHub-hosted Ubuntu 24.04, Python 3.11.11, NumPy 1.26.4, SciPy 1.13.1, pytest 8.3.5. 실행 종료 `success`, 회귀 stage `REGRESSION_PASS`.

## 1. 목적함수 검토
원 priors `mu_minus, P_minus`, 고정 관측 오차 `R`, 측정 `z=[r,s]`를 사용한 `J(y)=0.5||[y; Lr^-1(z-h(mu_minus+Lp*y))]||^2`. 모델의 목표와 경계는 그대로 유지했다. `range-first`는 초기값만 바꾸며, prior를 다시 바꾸거나 r,s를 반복 누적하지 않았다. RF 관측이 gyro bias를 직접 측정하지 않더라도 pose–bias 공분산이 간접 갱신을 설명한다. 국소 MAP와 GN 공분산은 **전체 다봉 posterior 또는 Full RF 오차분포의 검증이 아니다**.

## 2. solver 수정
기존 prior-whitened Gauss–Newton 및 일반적인 Armijo/backtracking은 유지했다. 원인 D1에서 제기된 double 비용 뺄셈 오차가 발생하는 **작은 종결 스텝에 한해서**, `ΔJ=∫_0^1 grad J(y+t d)·d dt`를 3점 Simpson과 trapezoid로 교차 검사했다. 계산상의 불확실 구간, 충분히 작은 스텝, 매끄러운 국소 기울기 변화, Simpson/trapezoid 일치, 원 Armijo 감소 요구, 그리고 후보의 **원래 gradient infinity norm ≤1e-8**을 모두 만족할 때만 적용한다. 임계값을 올리거나, 원래 R/Q·RF 모델·P2 spec·seed를 바꾸지 않았다. 일반적으로는 근사 적분 기반 안전장치이며 전역 수렴 보증이 아니다.

변경: `core.py`의 terminal acceptance 및 명시적인 재현용 `initial_delta` warm-start, `test_solver_regression.py`, `solver_regression.py`, `pytest.ini`, 테스트 전용 GitHub Actions workflow. 원본 `FAILURE_SNAPSHOT.json`, `D1_RESULT_SUMMARY.json`, `synthetic.py`, `P2_SPEC.json`, EKF3/6-state, RF/LUT와 과거 결과는 보존했다.

## 3. 실제 클라우드 실행·회귀검증
| Gate | 결과 |
|---|---|
| P0 수학·단위·공분산 | **16/16 PASS** |
| P1 국소 MAP·SciPy 대조 | **8/8 PASS** |
| R1 동결 실패 회귀 | **5/5 PASS** |
| GitHub Actions job | **success** |
| scientific_PASS | **false** |

원래 실패: `straight/bias0/trial0/MAP3/t=4.5s`, `LINE_SEARCH_FAILED`, `||g||∞=5.2678999634681034e-8` (요구 `1e-8`).

새 solver에서:
- **저장된 실패 최종 iterate에서 시작:** `CONVERGED`, `||g||∞=5.739139719018738e-10`; acceptance=`GRADIENT_INTEGRAL_TERMINAL`.
- **원래 prior에서 Range-first 시작:** `CONVERGED`, `||g||∞=5.739052566511305e-10`, 4회 GN 반복.
- 마지막 스텝의 double 원가 계산 `ΔJ=+4.6629367034256575e-15`; gradient line-integral `ΔJ=-1.6056697364134464e-15`; 원 D1 80자리 `ΔJ=-1.6056697178966146e-15`과 동의.
- 국소 곡률 변화 오차 비율 약 `0.0109` (guard 0.05 미만).
- 훨씬 엄격한 `1e-16` 기울기 요구를 허위 통과시키지 않았고, warm start–range first 충돌 및 chart 이탈은 거부했다.

원본 숫자가 한 표본에서 고쳐진 것이고 그 외 데이터의 재귀 추정 통계가 개선됐다는 뜻은 아니다. `SOLVER_R1_CLOUD_RECEIPT.json`과 cloud JUnit·로그·해시를 확인한다.

## 4. 증빙 및 제한
- [Run](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38517841360)
- [다운로드 가능한 원시 ZIP](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38517841360/artifacts/11873035416), artifact ID 11873035416, SHA256 `21d79eb427f5d4017b50f2853415b2e21ce47084fae6bd8b57884a12018b039b`, 30일 보존.
- 원본 P2 실패 [Run 38514443823](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514443823)과 D1 [Run 38514766913](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38514766913)은 이 보고서로 대체되지 않는다.

**확정:** 기존 가우시안 MAP 목표를 변경하지 않고 특정 수치적 스텝 거절 결함을 고정 입력에서 해소함. P0/P1 회귀를 유지하고 변경 내용을 cloud에서 실행·검증함.

**미확정:** P2에서 4-state bias 개선, 다른 경로·seed에서 solver 수렴, RF LoS/Full 성능과 실제 posterior 포함률, G3 위치 적분 수렴 및 다중 branch 유지.

**최종 상태:** `P0=PASS, P1=PASS, R1=REGRESSION_PASS, P2=INCOMPLETE_BLOCKED (original, not rerun), P3-P6=NOT_RUN, scientific_PASS=false`. 요청에 따라 **여기서 STOP**. P2 전체 재실행이나 추가 가설 시험을 시작하지 않는다.
