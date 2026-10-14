# R3 대표 P2 실패 5건: 고정입력 재현 및 수치적 원인 확정

## 0. 출처·수행 범위

- 대상: 원본 GitHub Actions [run 38562146793](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38562146793), source `2547f147ea347563a186a886bd25a543871825f3`. 원 artifact `11892566974` (SHA256 `931ee7cd8552820f3b6311877bb6ccc4ecc910669231290efb82e5868756c9b4`).
- 독립 진단: [run 38564525148](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38564525148), source `195264021da76ee6da8cc2cb31e30a004959e0d7`, [artifacts/11893444649](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38564525148/artifacts/11893444649), SHA256 `fedf1127c1a04d1dbad6c565f76054563740ff0343e5efe5d30b0df6abdba8c0`.
- 원본 5건 `FAILURE.json` / `FAILED_STEP.npz`의 prior / covariance / z / R / 저장 iterate를 원본 소스로 재실행. 모두 `NUMERICALLY_STALLED`, 최종 gradient / state / iteration history 재현. 원본 ZIP SHA/CRC, source commit, run ID, five unique failure keys 감사 PASS.
- 실행 **전 코드 감사 GO**, R3 및 기존 `core.py`·`stable_descent.py`·`P2_SPEC.json`·`synthetic.py` **원본 불변**. 고정 `MAP_gradient_tol=1e-8` 및 `MAP_max_iter=80` 유지.
- 독립 80-digit mpmath는 동일한 수학적 목적함수를 **원본 double Cholesky 인자를 고정해** 재평가. 다만 원본 double 연산 경로와 다른 정밀도의 함수 평가이며 formal interval certificate가 아님.

## 1. 5개 실패 상세

모두 `trial=0`. `ΔJ=J(y+d)-J(y)`. 첫 숫자는 R3의 **float64 full GN step** 변화, 둘째는 **80-digit 고정밀 동일 full GN step** 변화. 양수/음수 부호 비교가 핵심.

| 번호 | 경로 / bias(°/s) / estimator | 실패 시각 | 직전 gradient∞ | double GN ΔJ | 80digit GN ΔJ | 64eps 비용 편차 허용폭 | 완전스텝 허용폭 초과 |
|---|---|---:|---:|---:|---:|---:|---:|
| F1 | straight / 0 / MAP3 | 42.5s | 1.33175e−7 | +5.14033e−14 | −1.05695e−14 | 1.42109e−14 | 3.62× |
| F2 | straight / 0 / MAP4 | 37.5s | 4.87888e−8 | +2.56184e−14 | −1.53815e−15 | 1.42109e−14 | 1.80× |
| F3 | straight / +0.05 / MAP4 | 30.5s | 1.78366e−8 | +3.08642e−14 | −2.62696e−16 | 2.67480e−14 | 1.15× |
| F4 | turn / +0.05 / MAP3 | 32.0s | 1.22144e−8 | +4.50751e−14 | −7.43577e−17 | 1.97344e−14 | 2.28× |
| F5 | return / +0.05 / MAP3 | 32.0s | 2.26341e−8 | +1.00808e−13 | −4.54779e−16 | 2.47330e−14 | 4.08× |

같은 GN full-step에 대해 기록된 후속 gradient∞는 F1 `6.51e−10`, F2 `1.38e−10`, F3 `1.95e−10`, F4 `8.47e−11`, F5 `1.95e−10`, 모두 원래 요구 `1e−8` 미만이다. 단, 이 값은 수용되지 않은 후보의 평가로 **실제 필터의 성공값이 아니다**.

## 2. 오류를 세 부분으로 분해한 판정

### A. 스텝 방향 계산: 원인 아님 (이 5개 고정 입력의 국소 범위)

- GN / R3의 중앙차분 정확 Hessian Newton / 독립 80-digit Hessian Newton **세 방향 모두** 원래 iterate에서 고정밀 목적함수를 감소시킨다. 각 방향에 대해 `j=0..24` 25개 후보 모두 80-digit ΔJ<0. R3의 원래 두 방향에서 저장된 최종 iterate의 **50개 후보 모두 비용 기반 direct 및 적분 기반 수용에서 거절**됨.
- 독립 exact Hessian 최소 고유값: F1 `0.997597`, F2 `0.998174`, F3 `1.000000`, F4 `0.997957`, F5 `1.002997`; Hessian condition number 각각 약 1.040, 1.062, 1.072, 1.054, 1.038. 부정정부호·열악한 조건수에 의한 방향 불량은 관찰되지 않았다.

### B. 부동소수점 비용 평가·스텝 수용: **실패를 직접 유발한 결함**

실제 소스 `core.map_update`의 `resolved_armijo`는 double objective가 수치적으로 분명한 감소를 보인 경우에만 direct accept한다. 여기서는 double ΔJ가 **모두 양수**라서 거절되는 것이 의도대로다. 문제는 보조 `stable_descent.integrated_descent`가 double 평가의 불일치를 해결하려 하면서도 다음 **직접 비용의 absolute-difference 제한**을 먼저 요구한다는 점이다.

```python
if abs(c1 - c0) > 64*eps*max(1., abs(c0), abs(c1)):
    return None
```

모든 5건의 GN 및 R3 exact Newton **full-step**에서 관찰된 double |ΔJ|가 이 진입 제한을 초과한다(표 마지막 열). 즉 검증 가능한 true-gradient 적분을 수행할 수 있는 구간에서도 **오염된 double 목적함수 차이에 재의존하여 실제 하강 후보를 원천 차단**한다. 각 실패의 전체 halving-grid 반려 기록과 고정밀 감소 부호가 이를 뒷받침한다.

주의: 이는 5건의 **full-step 차단 원인**을 확정한 것이다. 작은 fraction의 추가 quadrature/noise/slope 검사 중 어느 것이 각각 처음 실패했는지까지 증명했다고 주장하지 않는다. 모든 fraction의 내부 조건별 진단이 추가되면 보다 완전한 guard-level 분해가 가능하다.

### C. 실제 정체/수렴 불가능: 반증됨 (국소 고정 입력)

- 현재 iterate의 80-digit gradient∞는 각각 약 `1.33175e−7, 4.87888e−8, 1.78366e−8, 1.22144e−8, 2.26341e−8`. 즉 **현재 iterate가 이미 수렴한 것은 아니다**.
- double gradient와 independent 80-digit gradient의 차이는 `0.85~3.63e−15`에 불과하다. **gradient 자체가 1e−8을 잘못 상회한 것이 주원인은 아니다**.
- 80-digit exact-Hessian Newton으로 근처의 stationary point를 각각 발견했고, 기존 prior-whitened `y` 좌표에서 그 지점까지 ∞-거리 `1.33047e−7, 4.83399e−8, 1.74412e−8, 1.21317e−8, 2.23849e−8`. 해당 stationary point를 double로 평가해도 gradient∞는 각각 `3.75e−15, 3.91e−15, 1.83e−15, 5.61e−15, 1.22e−15`로 원래 임계값보다 충분히 작다.
- 결론: 이 사례들은 과학적 MAP 가설 자체의 반례나 local optimizer의 불가능 문제가 아니라, **충분한 하강 방향이 존재하지만 실제 목적함수 감소의 증거를 인정하지 못한 수치적 step acceptance failure**다.

## 3. 추가적인 원인 구조

현재 목적함수는 `0.5*(y@y+v@v)`이며, `v=solve(Lr,z-h(mu+Lp@y))`. 상태 이동량이 `~1e−8`로 작아지면 `mu+Lp@y`, 관측 전방 함수 `h`, whitened residual `v` 등 중간 double 연산의 반올림이 새로운 모델 비용 계산에 누적되어 double ΔJ가 `+1e−14..+1e−13`으로 보이기도 한다. 이는 **단순한 두 최종 비용 숫자의 subtraction만**의 문제가 아니라 각 비용 평가 경로 자체의 유효 자릿수와 관련된 문제다. 그 사이 독립 고정밀 ΔJ는 `−1e−14..−1e−17` 수준이다.

R3의 "direct cost 감소 엄격화" 자체를 오류로 보아 완화해서는 안 된다. 수치적으로 불분명한 비용 변화에서는 실제 true-gradient 기반 수용 경로가 적절히 동작하도록 하되, 고정밀 고정 입력·음성 대조·원 gradient/covariance 독립 회귀로 검증해야 한다.

## 4. 다음 수정의 필수 검증 계약 (이 보고서에서 수정/재실행하지 않음)

1. 원본 5건 및 기존 4.5s/6.0s 저장입력을 **독립 회귀**에 추가. full GN/Newton step의 double/80-digit ΔJ, gradient integral quadrature, noise estimates, 각 guard FAIL 이유를 분리 기록.
2. `integrated_descent`의 원시 double 차이 제한과 실제 하강 검사 간 **논리적 순환을 제거**. 단순히 `64eps` 임계값을 크게 조정하거나 기준 `1e-8`을 완화하는 방식 금지. 유효한 감소만 수용; 불확실한 경우 명시적 invalid.
3. 원본 P0/P1/R1/R2/R3, 5개 fixture, downhill/uphill negative control을 모두 통과한 후 동일 6대표 P2, 마지막으로 원본 600 trial 실행. 적합한 수렴 상태·독립 gradient/covariance와 실제 paired denominator까지 확인.
4. 합성 단계는 실측 RF/LoS/Full 검증이 아니다. P3–P6의 원본 frozen input/scene, RF 추정, multimodal reference, 독립성 확인은 별도의 계약으로 진행. 어떤 수치 해결도 자동으로 `scientific_PASS`를 만들지 않음.

## 5. 미해결·실행 이력

- 첫 독립 진단(run 38563965657): `mpmath.lu_solve`의 matrix RHS 미지원 오류. original solver 아님. 원본 artifact·첫 실패 재현 다음 단계에서 중단.
- 두 번째(run 38564362660): 불필요하게 넓은 사전 AST 검사로 vector RHS 계산을 오인, 감사가 HOLD. 추정/진단 실행 전 차단.
- 세 번째(run 38564525148): 수정·사전감사 재시행 후 5/5 source status/gradient/terminal iterate 독립 80자리 진단 완료, GO + Actions PASS.
- 이 단계에서는 R3 solvers를 다시 수정하지 않았고 원본 P2 전체 600 paired trial은 실행하지 않았다.
- `scientific_PASS=false`; 원본 5개 모델 결과는 계속 `INVALID`이며, 재해결 전의 추정치를 성공 결과로 합산하지 않는다.
