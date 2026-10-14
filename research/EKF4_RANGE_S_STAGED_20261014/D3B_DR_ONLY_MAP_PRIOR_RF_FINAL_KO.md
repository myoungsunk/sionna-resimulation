# D3B 보완 — 독립 DR-only / RF / 이미 융합한 MAP prior를 구분한 원본 4실패 분석
2026-10-14 · 기존 D3 수치 원인 확정 후 동일 4사례만 재분석

## 가장 중요한 정정
앞의 D3 본문에서 `r_DR_prior`라고 쓴 값은 **RF를 한 번도 사용하지 않은 DR-only 추정이 아니다**. 그 값은 이전의 RF Range/`s` 갱신이 반영된 MAP3 또는 MAP4의 현재 운동 예측 `mu^-`에서 계산한 Range였다. 따라서 **'DR-only가 RF보다 정확한 4/4'라는 주장은 부정확하다**. 옳은 기존 판정은 **'이미 융합된 MAP prior가 새 RF Range보다 정확한 4/4'**다.

이 구분을 바로잡기 위해, 원 P2 아티팩트 `38526390416`의 똑같은 `initial`, `ds_odom`에 대응하는 `ds`, `dtheta_gyro`에 대응하는 `gyro`, `dt`, `Q2`만 적분하여 **RF를 전혀 업데이트하지 않는 독립 3-state DR-only 궤적**을 구성했다. 실제 bias `+0.05deg/s`는 DR 추정기에 알려주지 않았으며 참값은 사후 채점에서만 사용했다. 구현 모델은 원 frozen `core.predict`이고 별도 복소 원호 적분으로 모든 이동 예측 parity를 확인했다.

## 1. GitHub 감사/실행
- 소스·진단 스크립트 사전감사 `SOURCE_AUDIT.json: GO 13개`, 동결 RF input/원시 실패 스냅샷 감사 `INPUT_AUDIT.json: GO 10개`.
- [GitHub Actions D3B Run 38532174700](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38532174700): `success`.
- [원시 아티팩트 11878691886](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38532174700/artifacts/11878691886), SHA256 `bfb7fe5fa0c681f5715bd804ea5c9c5839be9e6e8637793ede7798fefd00bd86`, 다운받은 ZIP의 SHA256/CRC 일치.
- R3 솔버 수정, P2 전체 재실행, 다른 G2/G3 실험은 수행하지 않았다.

## 2. 같은 실패 시점의 세 거리 추정치 (m)
| 실패 시점 | 정답 Range | 독립 DR-only Range | 현재 RF Range | MAP prior Range |
|---|---:|---:|---:|---:|
| straight/MAP3, 28s | 8.6331 | 8.7902 | 8.6827 | 8.6221 |
| straight/MAP4, 30.5s | 9.1062 | 9.2686 | 9.0029 | 9.1019 |
| turn/MAP3, 32s | 8.8589 | 8.7507 | 8.9368 | 8.8540 |
| return/MAP3, 32s | 8.6331 | 8.5472 | 8.5322 | 8.6221 |

| 실패 시점 | 독립 DR-only 절대 Range 오차 | RF 절대 Range 오차 | MAP prior 절대 Range 오차 |
|---|---:|---:|---:|
| straight/MAP3 | 0.1571 | **0.0496** | 0.0109 |
| straight/MAP4 | 0.1624 | **0.1033** | 0.0043 |
| turn/MAP3 | 0.1082 | **0.0779** | 0.0049 |
| return/MAP3 | **0.0859** | 0.1008 | 0.0110 |

**RF vs 독립 DR-only: RF가 정확한 사례 3/4.** 그러나 **RF vs 이미 RF로 갱신한 MAP prior: MAP prior가 정확한 사례 4/4.**

대표 4건의 `DR-only Range NIS`는 **0.421, 2.471, 0.588, 0.006**이고 `MAP prior Range NIS`는 **1.394, 3.735, 2.603, 3.105**. 두 종류 모두 기존 1차원 99% 기준 약 6.635 아래다. **별도 RF 연구에서 관찰한 수미터 DR–RF 충돌/높은 NIS와 같은 현상이 아니다**. DR-only와 RF 차이는 약 0.015–0.266 m였다.

진단 시점 DR-only Heading 실제 오차는 **-5.04°, -4.90°, +5.44°, +1.02°**이고, MAP prior의 오차는 **+0.81°, -0.08°, +0.68°, +0.97°**였다. 이는 재귀 RF 융합을 거친 prior가 순수 DR보다 참값에 가까워졌다는 제한적 근거이지만 **Range와 `s` 가운데 어느 하나의 개별 기여도를 분리한 실험은 아니다.**

## 3. 이 DR-only/RF 불일치가 '네 MAP 솔버 미수렴' 원인인가?
**직접 원인은 아니다.** 이 네 MAP 솔버는 RF 없는 DR-only 상태가 아니라 **이미 RF로 보정된 MAP prior**에서 출발한다. 해당 prior와 이번 RF Range의 불일치는 약 0.061–0.099m 및 NIS<6.635였고, RF보다 prior Range 오차가 네 건 모두 작았다.

독립 D3 [Run 38530999947](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38530999947)에서는 **네 실패 모두 같은 동결 MAP 입력에서 80자리 실제 비용을 감소시키고 기존 gradient 1e-8에 도달하는 full Gauss–Newton step이 존재**함을 확인했다. float64 직접 비용 차의 부호 오류 때문에 그 큰 step이 거부되고 미세 스텝 후퇴 후 `LINE_SEARCH_FAILED`가 발생했다. 이는 물리 관측값을 바꿔야 해결되는 현상이 아니고 **수치적 line-search/cost 계산 문제**다.

독립 DR-only가 오차가 큰 사례 3/4는 RF가 상태 정정에 기여할 수 있음을 설명하지만, '큰 충돌이 솔버의 원인' 또는 'RF를 우선 가중하면 수렴 문제가 해결된다'는 결론을 허용하지 않는다. 현재 P2는 `gate=OFF`이고 `R=diag(0.05²,0.03²)`로 RF likelihood를 이미 매 순간 포함한다. 이 네 실패에서 RF를 무조건 더 강하게 가중하면 오히려 잘 정렬된 MAP prior를 오염시킬 수 있다.

## 4. 별도 RF 연구와의 관계
`research/rf-range-sign-audit-g2g3-20261014`의 수미터 급 DR-only drift/작은 RF 오차 사례는 실제로 다른 진단 세계다. 그 연구가 보여준 RF의 상대적 정확도는 향후 **큰 DR bias와 독립적으로 품질을 확인한 RF 우위**라는 조건에서 적용할 가치가 있다. 다만 signed corrected RF는 DR보다 나쁜 반례도 있으므로, 온라인에서 정답을 알고 고르는 방식이나 `RF shorter ⇒ RF 우선`의 무조건 스위치는 권하지 않는다.

**이번 P2에는 다른 브랜치의 확률모델이나 gate 정책을 그대로 이식하지 않는다.** 필요할 때 별도 사전등록한 경쟁 모형으로 검증한다.

## 5. 확정·미확정
- **확정:** 네 오류의 80자리 수치 원인, 독립 DR-only/RF/MAP-prior의 동일 시점 오차, 3/4와 0/4의 구분, MAP prior가 과거 RF를 이미 흡수했다는 코드 구조, 큰 높은-NIS 불일치가 네 수치 실패에서 부재.
- **미확정:** 현재 P2 600 trial 전체에서 RF 우위 비율, P2 MAP4의 gyro-bias 이득, 독립 실 RF 세계의 bias/fault 혼합효과, 실제 heading/position 전체 우열과 공분산 일관성, 새 R3 솔버의 일반 수렴.
- **종료:** D3B는 원본 데이터를 변경하지 않은 해석 구분용 한정 진단이며 실험 P2/R3/다른 RF 연구는 NOT_RUN. 과학 가설 verdict는 `NOT_EVALUATED`를 유지한다.
