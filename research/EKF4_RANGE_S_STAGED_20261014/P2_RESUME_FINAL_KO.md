# P2 재개 → D2 진단 → R2 능동 수정 trial: 최종 중단 보고

## 결론
P2를 GitHub-hosted Actions에서 재개했다. R1은 원 4.5초 실패를 해소했지만 같은 첫 trial의 6.0초에서 다시 미수렴했다. 이를 고정 입력으로 진단한 뒤 한 번의 R2 문제 해결 trial을 실행했다.

**R2는 알려진 두 입력의 수렴을 확인했지만, 추가한 회귀검사가 특정 내부 로그 필드를 항상 기대한 오류로 실패했다. 이 FAIL을 지우거나 회귀검사를 고쳐 한 번 더 실행하지 않고, 사용자 중단 규칙에 따라 멈췄다.** R2 전체 P2는 회귀 gate에 막혀 미실행이다. Bias 개선과 실제 RF 효능에 대한 결론은 내릴 수 없다.

현재 R2 core는 연구 브랜치의 미채택 후보다. main 병합·배포·P3 이후 실행은 하지 않았다. scientific_PASS=false.

## 1. 동결 조건과 GitHub 실행 기록
P2_SPEC.json, synthetic.py, 기존 Q/R, 초기오차, seed, 60초/0.5초 간격, 3경로×2bias×100trial, EKF3/EKF4/MAP3/MAP4의 대응 비교는 변경하지 않았다. 목적함수는 고정 Gaussian prior와 원시 [range,s] likelihood의 음의 로그 posterior이고, 수렴 기준 gradient infinity norm 1e-8 및 solver 한도 80회도 유지했다. 합성 RF이며 실제 FFD/LoS/Full 실험이 아니다.

| 실행 | 소스 commit | Run ID | 결과 |
|---|---|---|---|
| R1으로 P2 재개 | e4084b58e544735bc5ef8213c025c2989b0c6a95 | 38518908286 | P0/P1/R1 PASS, P2 수치 FAIL |
| D2 고정 입력 진단 | ae2c60c2f3a96003778cc52374ad101e1edcd3de | 38519216213 | 두 스냅샷 진단 실행 완료 |
| R2 수정·회귀 trial | 408020395928706cf38d56d29608058ad4b033ef | 38519821321 | P0/P1/R1 PASS, R2 9/10 PASS 및 1 FAIL, P2 skipped |

- [P2 재개](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38518908286)
- [D2 진단](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38519216213)
- [R2 해결 trial](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38519821321)

## 2. P2 재개에서 실제로 발생한 문제
straight / true bias 0 / trial 0 / MAP3에서 t=6.0s, step index 11의 갱신이 LINE_SEARCH_FAILED. 최종 gradient infinity norm 1.179021813513259e-8로 원래 기준 1e-8보다 크다.

같은 trial의 EKF3와 EKF4만 60초 실행을 완료했다. MAP3는 실패 직전까지의 부분 trace를 저장했고 MAP4는 아직 실행하지 못했다. **완전한 4모델 paired trial은 0개**다. 두 model-trial 완료를 두 독립 trial 또는 bias 효과의 증거로 해석하지 않는다.

## 3. D2 원인 분석: 어떤 가정이 잘못됐는가?
고정된 원 4.5s 스냅샷과 새 6.0s 스냅샷을 사용해 R1, 실제 gradient 변화, 80자리 독립 목적함수, 고정밀 stationary point/Hessian, SciPy TRF/dogbox/LM을 비교했다. 이 진단에서 P2를 추가 실행하지 않았다.

새 6.0s 입력에서 저장된 마지막 iterate의 full GN step:

| 지표 | D2 기록 |
|---|---:|
| double 비용 변화 | +2.9976021664879227e-14 |
| 80자리 비용 변화 | -7.232345954719164e-17 |
| step 적용 후 gradient infinity norm | 7.547387261604838e-10 |
| 실제 gradient 변화와 GN 곡률 예측의 상대 차이 | 0.06401397495 |
| R1의 곡률 일치 제한 | 0.05 |
| 정확 Hessian 고유값 | 1.038972, 1.094740, 1.148468 |

실제 감소 스텝이 있고 국소 Hessian도 양수지만 R1의 GN 곡률 근사 일치 조건에 맞지 않았다. 비선형 least squares의 정확 Hessian은 GN 항 외에도 잔차의 2차 미분 항을 포함하므로, GN과 5% 이상 다르다는 사실만으로 함수가 비매끄럽거나 스텝이 위험하다고 단정할 수 없다.

**다만 5% 조건 하나만이 유일 원인이라고 확정하지 않는다.** 기록된 D2 비용 변화는 64eps×기록된 비용(약 2.82737e-14)보다 약 6.0% 크기도 하다. D2의 합산 순서와 생산 코드의 합산 순서에는 ulp 수준 차이가 있을 수 있으며, 이 수치는 기록된 진단값에 대한 산술 감사다. 생산 실행의 모든 guard 분기 telemetry를 완전히 복원한 것은 아니다.

SciPy TRF(analytic/3-point), dogbox, LM도 새 입력에서는 ftol success를 반환했으나, 원 좌표의 해석 gradient는 약 2.53–2.61e-8로 요구 기준보다 컸다. **solver.success만으로 통과시키는 교체는 하지 않았다.**

## 4. 능동 해결 trial R2
목적함수·수렴 기준을 바꾸는 대신, 비용 뺄셈이 불명확한 작은 스텝에서 다음 항등식에 근거한 수용 검사를 적용했다.

`J(y+d)-J(y) = integral_0^1 grad J(y+t*d).d dt`

GN 곡률과의 임의 5% 일치 조건 대신 실제 gradient의 3점/5점 Simpson 일치, 감소 부호, numerical-noise 추정, directional contraction을 검사한다. gradient가 아직 1e-8에 도달하지 않아도 검증된 감소 스텝은 PROGRESS로 허용하되, convergence 선언은 원래 기준으로만 한다. 기존 tiny-step/비용 불확실 구간/Armijo 조건은 유지했다.

이는 수치적 근사 안전장치이며 인증된 적분 오차 경계나 전역 수렴 보증이 아니다. 변경은 core.py의 해당 수용 분기와 새 stable_descent.py에 한정했다. 실험 생성기, RF 관측 함수, R/Q, 전체 P와 최종 covariance 계산은 그대로다.

## 5. R2 회귀 결과와 새 중단 원인

| 검사 | 결과 |
|---|---|
| P0 | 16/16 PASS |
| P1 | 8/8 PASS |
| 기존 R1 회귀 | 5/5 PASS |
| 새 R2 검사 | **9 PASS / 1 FAIL** |
| R2 적용 전체 P2 | **NOT_RUN: 이전 step FAIL로 skipped** |

개별 고정 입력:

| 입력과 시작점 | 수렴 결과 |
|---|---|
| 원 4.5s / 원래 Range-first | CONVERGED, gradient 5.739052566511305e-10 |
| 원 4.5s / 저장 iterate | CONVERGED, gradient 5.739139719018738e-10 |
| 새 6.0s / 원래 Range-first | CONVERGED, gradient 7.806982282865249e-10 |
| 새 6.0s / 저장 iterate | 수렴·gradient≤1e-8·목적함수·공분산 assert를 통과한 뒤 진단 로그 검사에서 KeyError |

네 번째 사례의 정확한 최종 gradient 수치는 실패 전에 출력하지 않아 이번 로그에 없다. 통과한 assert를 근거로 ≤1e-8까지만 주장한다.

실패 위치는 `test_solver_r2.py:27`의 다음 검사다.

```python
first = a.history[0]
assert first['curvature_ratio'] > .05
```

`curvature_ratio`는 gradient-integral 분기의 진단 필드이며 모든 유효한 스텝에 존재하지 않는다. **제가 작성한 검사가 '첫 스텝은 반드시 그 분기를 쓸 것'이라고 가정한 것이 문제다.** 수렴 상태·독립 gradient·동일 목적함수·동일 공분산 검사를 지난 다음 이 메타데이터 가정에서 실패했다. 이것을 R2 solver가 다시 미수렴했다고 보고하면 부정확하다.

원래 prior에서 두 고정 입력이 수렴했다는 제한적 긍정 결과는 있지만, 전체 회귀 gate는 FAIL이고 이를 채택 PASS로 승격하지 않았다. 저장 iterate의 전체 history를 실패 전에 보존하는 보강도 필요하다. 이번에는 테스트를 사후 수정하거나 추가 trial을 실행하지 않는다.

## 6. 확정 / 미확정
확정: GitHub 게시·세 번의 클라우드 실행; R1 P2의 6.0s 수치 중단; 국소 감소 방향의 존재; GN 곡률 일치 proxy의 한계; R2 고정 입력 수렴 assert 통과; 새 회귀검사의 특정 로그 키 가정 오류; P2 이후 차단 동작.

미확정: R2 전체 trial/모든 seed의 수렴 안정성; 4-state gyro bias 개선 효과; 정상조건 손실; 실제 RF LoS/Full 성능; 비선형 위치 적분·다봉 posterior; 재귀 일관성과 독립 환경 일반화.

단 하나의 수치 실패 또는 이 테스트 오류를 목적함수 자체나 bias 추정 원리의 반증으로 해석하지 않는다. 반대로 고정 입력 수렴을 전체 필터의 성공으로 해석하지 않는다.

## 7. 보존 및 감사
다운로드한 3개 신규 cloud ZIP의 SHA256/CRC를 검사했다. 두 결과 묶음의 FINAL manifest에 열거된 출력 29건의 SHA를 대조했으며 불일치 0건이었다. 보호한 P2_SPEC/synthetic/원 failure/D1 summary/기존 test_core/기존 R1 test의 6파일은 재개 전후 동일 바이트다. 이는 다운로드·증빙 감사이며 로컬에서 solver나 실험을 재실행한 것이 아니다.

| 산출물 | artifact ID | ZIP SHA256 |
|---|---|---|
| P2 재개 실패 | 11873285696 | 776d624bedd8ebd6086e833e46519d9880a81ab5cb92669d221f81df361a83fd |
| D2 진단 | 11873161275 | 7b4e8bd8b72a20308db579cc68565560efa0f3279e25c2420db078a59cd64e29 |
| R2 수정 trial | 11873770297 | af04e92c9b503dc3faaaf73d0319ea678fd058194f1ec846eea3b5a1673060c3 |

[새 실패 스냅샷](RESUME_FAILURE_SNAPSHOT.json), [D2 계획](D2_PLAN_KO.md), [R2 계획](R2_PLAN_KO.md), [기계 판독 상태](P2_RESUME_STOP.json), [원 회귀 실패 로그](evidence/R2_TESTS.log).

**최종 상태: STOPPED_AFTER_REPAIR_TRIAL_REGRESSION_FAILURE. P2=INCOMPLETE, R2_P2=NOT_RUN, P3-P6=NOT_RUN, scientific_PASS=false.**

다음에 진행한다면 '동일 목적함수·수렴을 검사하는 회귀'와 '특정 내부 분기 coverage를 검사하는 시험'을 분리하고 실제 history를 먼저 보존해야 한다. 이 변경·재검증·P2 재실행은 이번 요청에서 더 진행하지 않았다.
