## 2026-10-20 사후 적용성 정정

구현1/canonical의 현재 지위는 검증된 실행 기준이다. 구현2·3은 DEFERRED_SOURCE_UNAVAILABLE이며 원본 비교·동등성 검증을 완료한 것으로 간주하지 않는다. 파일명 CANONICAL_RESULTS.csv와 역사적 정본 표기는 원문 식별자로 보존한다.

아래는 보존된 당시 보고 내용이다. 현재 해석은 이 사후 정정을 우선한다. 원래 숫자 CSV·DECISION·사전 등록 파라미터는 변경하지 않았고 원문 bytes/SHA는 후속 S0_CORRECTIONS/ORIGINALS와 VALIDITY_INDEX.json에 보존했다.

---

# T1 시간 기억 구현 감사

상태: PREPARED_NOT_EXECUTED. 구현 1만 소스를 확보했다. 구현 2·3의 재귀 소스는 `BLOCKED_INPUT`이다. 아래 보고서 기반 정리는 소스 재현 또는 구현 검증이 아니다. 구현 1의 실제 엔진 단위 시험 통과 전에는 정본 지정과 논문 수치 승격을 보류한다.

| 항목 | 구현 1: 3fc70f2280471954f1a0673009812ad75437d9ea | 구현 2: CD_V2, 5d3ffc9 보고서 | 구현 3: fcf0725 보고서 |
|---|---|---|---|
| 관측식 | `pred=h(x)+B beta`, `nu=z-mu-pred`; H의 latent 열=B | 동적 beta 및 covariance 중복 수정 서술만 확인. 평균/Jacobian 소스 미확보 | `nu=z-h(x)-mu-beta`, 평균 및 Jacobian 포함 명시. 물리 단위 beta로 보이나 소스 확인 필요 |
| 분산 분할 | `B=chol(C)@diag(sqrt(fraction*mask))`, `Rwhite=C-B@B.T` | V1 중복 결함 폐기, V2 재실행 서술. 정확한 분할 미확인 | 총 분산 분할 명시. B 정의 및 분할 수치 미확인 |
| rho와 dt | 매 전파 `exp(-controls.dt_s[i]/tau)`; 첫 frame dt=.2지만 첫 frame 전파 없음 | 미확인 | train-route-only rho 서술. dt 변환 미확인 |
| 학습 | train whitened residual의 lag1/2 moment. rho=clip(c2/c1,.02,.995); tau=-median(dt)/log(rho); fraction=clip(c1/(rho*c0),.05,.90) | 미확인 | 관측 ACF와 rho를 동일시하지 않았다고 서술. 추정식 미확인 |
| 초기 latent | beta=0, P_beta=I, P_state,beta=0 | 미확인 | 미확인 |
| process noise | normalized beta: `(1-rho²) I` | 미확인 | 미확인 |
| gate | beta가 nu,H,S에 포함. NIS<=9.210340371976184 | rho0 state 4.12e-14/gate0 보고 | rho0 약1e-14/gate0 보고 |
| rho0 | tau=0에서 매 전파 latent·cross reset; 물리 marginal POWER1와 동치 | 보고 결과만 확인 | 보고 결과만 확인 |

구현 1 학습에는 한 가지 해석 주의가 있다. `fit_memory`는 train case별 sequence의 인접 index가 연속일 때만 lag를 사용하고, 모든 raw packet dt의 중앙값으로 tau를 환산한다. 실행 전파는 실제 control dt를 쓴다. 양자는 서로 다른 역할이며 `.2s 고정 구현`으로 요약하면 부정확하다. fraction은 fold당 공통 스칼라이며 관측 공분산 C(q)의 Cholesky 방향에 적용된다.

구현 1의 기존 train 기록: R2 tau=.6102936623983377s/f=.9, R4 tau=1.066153014034799s/f=.8539096073922738, R5 tau=.6528375345287386s/f=.9. 이 값은 기존 결과 파일의 기록이며 이번 실행으로 확인된 수치가 아니다.

## 근거와 복구 범위

- 구현 1: `research/CHAIN_HYPOTHESIS_20261019/{engine.py,run.py,restore.py}`. 실행 시 SHA256을 manifest에 적고 원본 revision을 검증해야 한다.
- 구현 2: `research/POWERJOINT_CHAIN_A_F_20261019/RESULTS_AND_GO_NOGO_KO.md` §C. 필요한 원본: `POWERJOINT_A_F_CHAIN_CAUSAL_RESULTS_20261019.zip`, SHA256 `6c3150b65078ff62dfcebf5aa8aa95741389a085100b3c8a1f1851a2c967cec3`.
- 구현 3: `research/POWERJOINT_CROSSCASE_20261020/00_ANALYSIS_RESULTS_KO.md` §C. 필요한 원본: `/mnt/data/POWERJOINT_CROSSCASE_HEADING_CAUSES_20261020`의 실제 replay/fit 소스와 파라미터.
- 현재 checkout의 crosscase 폴더에는 물리 이벤트/집계/추출 소스만 있다. Downloads 직하위에서 POWERJOINT 이름의 ZIP을 한 번 조회했으며 요청된 ZIP은 없었다. 광범위 디스크 검색은 하지 않았다.

## 정본 지정 gate

모든 확보 구현을 동일 단위 시험으로 검증한다. 둘 이상 통과하면 데이터·학습·dt·분산분할 차이를 특정하기 전 정본을 지정하지 않는다. 구현 1만 확보되어 실제 엔진 시험을 통과하면 확보 소스 범위의 정본 후보로 지정할 수 있다. 누락 소스의 동일성을 가정하거나 구현 2·3의 시험 완료로 보고하지 않는다. 단위 시험은 `unit_tests.py`, 동결 RF 재귀 준비 코드는 `replay.py`다. T2 canonical 입력과 POWER1 historical gate trace는 외부 의존성이다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, 보고서만으로 구현 2·3의 수학적 동등성 또는 수치 차이 원인을 주장하지 않는다.
