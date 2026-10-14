# G3 Range-aware 적응형 중요도 적분 — 독립 실행·감사 최종 보고 (2026-10-14)

## 1. 최종 판정

**NOT_VALIDATED_AT_PREREGISTERED_BUDGET / FAIL_CLOSED.**

제안한 현재 구현(관측 Range에 집중한 반경 중요도 분포 + S/위치 prior 기반 방위각 적응형 분포 + RQMC)은 **동결된 G3 수치 실패 사례에서 신뢰 가능한 posterior를 계산하지 못했다.**

이는 적응형 중요도 적분이라는 방법군 전체가 불가능하다는 의미는 아니다. 현재 구현의 **반경 제안분포가 위치 prior와 S likelihood를 함께 고려하지 않는다는 결함**이 관측되었다. 새로운 제안분포의 유효성은 이번 실험에서 확인하지 않았다.

요청 범위에 따라 수치 유효성 검증만 수행했다. G2/G3 성능 순위 비교, 재귀 융합 및 새로운 RF 학습은 0건이다. scientific_PASS=false.

## 2. 원본·구현·실행 증빙

- 저장소: myoungsunk/sionna-resimulation
- 브랜치: research/g3-range-aware-qmc-audit-20261014
- 실행 코드 커밋: b29a98136046a9b15d975b0fe97cdbe620d16065
- 기준 부모 커밋: 10d138c787aa5f0a0b3933a03c0be5651df6fa9f
- 동결 연구 원본 커밋: 32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20
- GitHub Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38515429481
- 원시 결과 아티팩트: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38515429481/artifacts/11871726353
- 실행 코드: research/EKF3_INDEPENDENT_20261013/diagnostics/h3_qmc_validity.py
- 워크플로: .github/workflows/h3-g3-importance-validity.yml
- 머신 리시트: 아티팩트 내부 VALIDITY_AUDIT.json
- 전체 posterior/ESS: 아티팩트 내부 qmc_*.npz 및 reference_*.npz

기준 커밋 이후 실험 실행에 사용된 변경사항은 **새 Python 파일과 워크플로 파일 2개 추가**뿐이다. 기존 RF H, LUT, D0, P0, R0 관측 공분산, NIS gate, 허용치 및 실패 기록을 수정하지 않았다.

## 3. 동결 평가 조건과 실제 관측 불일치

R2_aA_m0 / gyro_bias L2 / seed 0 / LoS / B_OLD / sample 978 / t=195.6 s.

- DR prior 평균: (x,y,psi)=(3.7012827074 m, -6.0181823400 m, -2.4914201759 rad)
- Anchor (x,y)=(4 m, 0 m), 높이 차=2.2 m
- 동결된 보정 Range=3.6721958255 m, Rr=0.0068578637 m², 관측 표준편차=0.0828122195 m
- DR 평균에서 예측한 Range=6.4146512530 m
- Range 잔차=-2.7424554275 m, 관측 표준편차 대비 약 -33.1166배
- 예측 Range innovation covariance H P H^T + Rr = 0.0670389863 m²
- NIS=112.18937 > 기존 수용 기준 6.6348966: Range 관측 거부와 일치
- 조건부 위치 공분산 p(XY|psi)의 고유값=(0.01068385, 0.01166421) m²
- 조건부 위치 표준편차는 약 0.1034 / 0.1080 m
- 관측 Range의 수평 원 반경=2.94024 m, DR 평균의 수평 Anchor 거리=6.02559 m

관측값 자체의 Range likelihood를 제안분포로 삼으면 DR 위치 prior와 관측 likelihood의 겹침 영역이 매우 희소해진다. 높은 importance 가중치가 소수 표본에 집중되는 현상을 설명하는 **강력한 후보 원인**이다. 단, 실제 전체 비선형·다봉 posterior의 정확한 모양은 아직 미확정이다.

## 4. 구현 수식·검증 계약 감사

반경 r(3D slant Range)은 r>=2.2 m에서 정규분포 N(z_r,Rr)를 절단한 분포로 정확히 샘플링했다. Heading별 방위각 alpha는 512개 pilot bin에서 S likelihood와 p(XY|psi)에 비례하는 적응형 확률질량을 계산한 후 10% 균등분포를 섞어 전 영역의 지지도를 유지했다.

각 표본 중요도 가중치의 비례식은 다음과 같다.

w = sqrt(2π) * sigma_r * Z * r * p(XY|psi) * L_s / q(alpha|psi)

여기서 Z는 절단 정규화 확률, r은 극좌표 Jacobian이며, Range likelihood는 q_r에 한 번만 포함되어 이중 사용하지 않았다. 원본 s_model, wrapped Heading prior, 전체 위치–Heading 교차공분산을 사용했다. 정답 Heading/위치는 제안분포 학습에 사용하지 않았다.

독립 난수화 Sobol seed=1069/2099, 표본 수 4096/16384/65536, Heading 격자 1440개, TV 허용치 0.001, 상대 evidence 허용치 0.005를 사전에 고정했다. 별도 결정론적 적분은 균등 방위각 × Gauss–Legendre 반경 적분을 적용했다. **결정론적 적분과 RQMC는 방위각 적분법은 독립적이지만 동일한 Range 기반 반경 변수 변환을 공유한다.** 따라서 양쪽이 동시에 미수렴하면 이를 정확한 기준 posterior가 확보됐다는 의미로 해석하지 않는다.

기본 synthetic 검사에서 분석적 Gaussian×Range 적분과 다봉 방위각 함수에 대한 중요도 추정이 일치하여 가중치·Jacobian 대수의 제한적 sanity를 확보했다.

## 5. 실제 실행 수치

| 비교 | 결과 | 기준/판정 |
|---|---:|---|
| Synthetic 상대오차 (seed 1069) | 1.29555e-5 | ≤0.003 PASS |
| Synthetic 상대오차 (seed 2099) | 2.56190e-5 | ≤0.003 PASS |
| 결정론적 1024×12 → 2048×20 TV | 0.02444822 | FAIL |
| 결정론적 2048×20 → 4096×28 TV | 0.01516879 | >0.001 FAIL |
| 결정론적 log evidence 3개 단계 | -295.85506 → -290.01782 → -286.56175 | 심한 비수렴 |
| RQMC 16,384개 / seed 간 posterior TV | 0.81096132 | FAIL |
| RQMC 65,536개 / seed 간 posterior TV | 0.62874648 | >0.001 FAIL |
| RQMC 65,536개와 마지막 결정론적 reference TV, seed 1069 | 0.14114989 | FAIL |
| RQMC 65,536개와 마지막 결정론적 reference TV, seed 2099 | 0.69096482 | FAIL |
| Posterior 가중 ESS/N, seed 1069 (65,536표본) | 1.54163e-5 | FAIL |
| Posterior 가중 ESS/N, seed 2099 (65,536표본) | 1.76395e-5 | FAIL |

65,536표본에서 유효표본수는 평균적으로 약 1.01개 / 1.16개 수준이다. 따라서 추정이 극소수 가중치에 지배되며, 두 독립 난수화의 posterior도 서로 일치하지 않는다.

결정론적 적분도 수렴하지 않았으므로 **그 결과를 참값 또는 신뢰 가능한 기준 posterior로 채택하지 않는다.**

## 6. 확정 / 미확정 / 종료

**확정**
- 실제 GitHub 클라우드 실행과 자료 확인 수행
- 원본 G3 실패 시점의 관측과 DR prior가 극단적으로 불일치함
- 합성 통제 적분에서는 제안밀도·가중치 항등식이 성립함
- 현재 중요도 제안분포는 사전 수치 허용치에 미달하고 ESS가 사실상 1개 수준
- 독립 결정론적 적분도 같은 사례에서 신뢰 가능한 기준을 확보하지 못함

**미확정**
- 충분한 적응형 다중 모드/방어적 mixture 제안분포라면 수렴 가능한가
- 해당 시점의 실제 비선형 G3 Heading posterior
- 다른 시간·RF 채널·Gyro Bias 조건에서의 일반화
- G2/G3 정확도 우열, 전체 3-state 공분산 일관성, 재귀 융합

**종료 규칙 준수:** 이번 요청은 적응형 중요도 적분 유효성 확인만이므로, 위 실패 결과를 남기고 중단한다. 제안분포를 임의로 변경한 추가 실험, G2/G3 성능 비교 또는 재귀 융합은 수행하지 않았다. 새로운 가설이 필요하다면 Range뿐 아니라 위치 prior와 S를 동시에 반영하는 다중 성분/방어적 혼합 제안분포(또는 브리지/SMC)의 지원 영역 검증이 우선이지만, 이는 별도 실험으로 승인받기 전까지 실행하지 않는다.
