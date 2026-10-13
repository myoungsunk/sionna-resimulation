# I2 S0 참조 추정기 실패 감사와 보완 계획

작성일: 2026-10-13. 범위: 기존 코드·원시 표본·진단 기록의 읽기 전용 감사와 후속 계획. 추정기 수정, 새 posterior 실행, I3/I7은 수행하지 않았다. 기존 결과를 본 뒤 작성하는 개발 계획이며 사전등록이나 확증 결과가 아니다.

결론: **현 PF는 정적 Calibration 표본의 재생 없이 재표집하여 다양성이 소실된다. Batch는 상관된 변수의 좌표별 이동과 초기 반경 독립 제안, 작은 잠재 잡음 이동에서 혼합 병목의 증거가 있다.** 참조 승인은 계속 REFERENCE_NOT_VALIDATED이다. 정보 부족, 실제 다봉성, RF 원인을 이번 실패만으로 확정할 수 없다.

## 1. 감사 기준과 증거

원격 기준은 `codex/dr-ekf-causal-followup-v2-20261013`, `3b705cff883d3e126457d076d852721bba0b4c18`로 조회했다. 로컬 HEAD는 `3032a58925ad4d1e3acec85865958e6580d79be7`이고 출판된 작업 파일과 다르므로 로컬 HEAD를 실행 코드의 동일성 증거로 사용하지 않는다. 이번에 소비한 파일의 바이트 SHA256은 `out/I2_S0_REFERENCE_FAILURE_AUDIT.json`에 있다. 기존 검증과 출판 영수증은 보존한다.

감사 구현 `audit_i2_s0_reference_records.py`는 기존 Batch JSON/NPZ 8쌍, 대표 PF checkpoint 4개와 관련 코드·계약을 읽어 수락률 범위, 체인 내 상관, checkpoint 계보를 산출한다. 새 Monte Carlo 실행은 없다. `i2_s0.py:27–77`, `i2_s0_batch.py:95–222`, `i2_batch.py:59–79`를 직접 대조했다.

## 2. PF 원인: 확인된 기전과 아직 모르는 부분

**확인된 기전.** `pf_s0`는 처음에 3개 Calibration 값을 prior에서 추출한다. 이후 pose만 움직이고 Calibration 값은 수정하지 않는다. ESS가 N/2 미만이면 전체 입자를 복제·제거하며 Calibration을 복원하는 posterior-invariant move가 없다. 조상 1개가 남으면 Calibration의 지지집합도 한 점이다. 이후 동적 입력 잡음을 새로 뽑아 pose가 분산되어도 Calibration 폭은 복구되지 않는다. 이는 수치 공분산 수리로 해결할 문제가 아니다.

| Gaussian seed8000, 8192 PF | 첫 중간 checkpoint | 마지막 checkpoint |
|---|---|---|
| R2 Range .05m/5Hz | 19.6초: 조상 4, ESS 6970.4 | 195.6초: 조상 1, ESS 7961.6 |
| R4 Range .05m/5Hz | 14.8초: 조상 34, ESS 5080.0 | 148.2초: 조상 1, ESS 7526.0 |
| R2 DR | 19.6초: 조상 783 | 마지막 조상 170 |
| R4 DR | 14.8초: 조상 833 | 마지막 조상 93 |

ESS는 현재 입자 가중치의 균등도를 나타내므로 높은 ESS를 Calibration 다양성으로 해석하면 안 된다. 선별 80k Range도 조상 1–3개였다. 따라서 입자 수만 늘리는 보완을 우선하지 않는다.

**강한 원인 후보.** 현재 proposal은 odometry innovation에 조건화하지만 현재 Range에는 조건화하지 않는다. 넓은 초기 Heading과 정적 Calibration을 유지한 채 Range likelihood로만 선택하므로 초기·누적 관측에서 급격한 선택 압력이 생길 수 있다. DR보다 Range에서 빨리 소실되는 기록이 이를 지지하지만 Range-aware proposal 개입 비교를 하지 않았으므로 기여율은 미확정이다.

**기록 한계.** 6개 checkpoint만 있어 최초 급락 시점을 정확히 찾거나 odometry와 Range 각각의 log-weight 분산을 분해할 수 없다. 단일 조상 이후 95% 포함률 0/4는 현 알고리즘의 실패 증거이며 정답 posterior가 좁다는 증거가 아니다.

## 3. Batch 원인: 낮은 수락률만의 문제가 아니다

Batch는 초기화 4chain, burn 2000, retained 2000/chain이고, rho 독립 제안·delta 혼합 제안·Calibration 좌표별 MH·전체 잠재 잡음 pCN을 순차 적용한다.

| area 조건 | rho 수락률 | bg/eps 체인 내 상관 | 잠재 pCN 수락률 | 최대 classical Rhat |
|---|---:|---:|---:|---:|
| R2 DR | 해당 없음 | .9905–.9949 | 1.000 | 2.0563 |
| R4 DR | 해당 없음 | .9565–.9867 | 1.000 | 1.1073 |
| R2 Range | .0075–.0395 | .5424–.7622 | .8855–.9075 | 14.5940 |
| R4 Range | .0340–.0450 | .6762–.7325 | .9285–.9435 | 1.3219 |

1. **DR의 가늘고 상관된 방향:** bg와 eps를 따로 이동한다. 관측된 높은 체인 내 상관은 좌표별 random walk가 약한 방향을 느리게 탐색한다는 설명을 강하게 지지한다. 표의 상관은 미수렴 체인 내부 통계이며 참 posterior 상관의 확증값은 아니다.
2. **rho 제안의 불일치:** 첫 Range posterior에서만 rho를 다시 뽑고 나머지 변수는 고정한다. 전체 관측 posterior의 조건부 rho와 맞지 않을 수 있다. 실제 수락률 .6–4.6%(모든 Range prior 조건)로 병목이 확인된다. 낮은 수락률이 혼합 실패 전체를 설명하는지는 별도 개입이 필요하다.
3. **높은 수락률과 느린 이동:** pCN beta=.03이면 제안 단계의 이전 잡음 계수는 sqrt(1-beta²)≈.99955다. 높은 수락률은 충분한 이동의 증거가 아니다. 이 값은 제안의 계수이지 실제 MCMC 자기상관 추정값은 아니다. beta 조정·시간 블록화의 효과는 미실험이다.
4. **전 구간 결합과 모드 탐색:** Heading·Calibration·잠재 잡음을 한 번에 재조정하지 않아 변화가 전체 궤적에 누적된다. 10% uniform Heading 제안은 있지만 그 부분의 수락률·모드 전환은 따로 기록되지 않았다. 서로 다른 체인이 다른 진짜 모드에 있는지, 같은 모드에 접근 중인지 구분되지 않는다.
5. **DR의 불필요한 잠재 차원:** DR likelihood는 `conditional(state)`의 odometry 항만이며 잡음 궤적에 의존하지 않는다. 잠재 잡음은 적분하면 1이다. Calibration 기준 분포는 3변수 posterior로 정확히 축약할 수 있다. 현재 DR의 pCN 수락률 1은 정상이나 Calibration 혼합을 개선하지 않는다. 이것이 가장 저렴하고 독립적인 검증 출발점이다.

현재 감사에서 첫 Range 중복 사용이나 MH 보정항 누락을 확인하지 않았다. rho 독립 제안의 초기 posterior 항, pCN의 Gaussian prior 항, 대칭 Heading 제안은 해당 수락비에서 상쇄되고 Calibration prior 비는 적용된다. 다만 역 CDF의 유한 격자는 수치 근사이고, 표적 보존의 전 범위 증명·통계적 검증을 대신하지 않는다. PF의 invalid-support 즉시 중단과 Batch의 -inf 거절 정책도 향후 동일 계약으로 검사해야 한다(이번 실패의 관측 원인으로 확인된 것은 아님).

## 4. 먼저 분리할 두 가지 참조 승인

- **알고리즘 참조:** 두 방법이 동결된 conditional measured-input posterior를 충분히 정확히 계산하는가?
- **생성모델·일관성:** 그 likelihood가 실제 센서 생성 세계와 일치하며 반복 episode에서 coverage가 유지되는가?

동일 코드 계보의 PF와 Batch가 합의해도 두 번째 항목은 자동 승인되지 않는다. measured-input Q, 공유 입력 상관, drift·slip·wheelbase 처리와 Gaussian 세계의 실제 일치 범위를 다시 명시한다. B0 mismatch를 숨기거나 기존 입력을 바꿔 성공시키지 않는다. 수렴 실패와 모델 불일치를 서로 대체 설명으로 사용하지 않는다.

## 5. 보완 순서와 단계별 종료 조건 — 제안, 아직 미실행

### R0. 계약·진단을 먼저 동결

새 `I2_REFERENCE_REPAIR_DESIGN.json`과 새 출력 폴더를 만든다. 기존 8셀과 20k/80k 결과는 보존하고 새 결과를 별도 버전으로 기록한다. seed8000 Gaussian R2/R4 DR와 .05m/5Hz area를 중심 4셀로 고정한다. 첫 Range 제외 규칙, 정규화·prior·horizon·invalid-support 정의를 같은 수식으로 기록한다.

매 RF-off Ideal Range 갱신에 odometry 전후/Range 후 ESS, log-weight 분산, 최대 가중치, 재표집 횟수, Calibration 다양성·계보·mode 질량을 저장한다. Batch는 log-density 성분, rank/trace, local/global Heading 수락률, jump distance, rho와 Calibration 공동 이동, burn 종료 시점을 저장한다. 코드·입력·출력 SHA, 실행 시간·종료 코드·메모리 비용도 기록한다. 첫 급락 구간은 이 진단으로 식별하며 truth로 셀을 선택하지 않는다.

### R1. 저차원 DR 기준 분포 검증

DR의 정확한 표적을 `p(c|d,g,o) ∝ p(c) ∏ Normal(o_k;h_k(c),S_k(c))`로 별도 구현한다. 잠재 궤적을 적분 제거하고 bg/SF/eps 3차원 adaptive quadrature 또는 독립 importance integration을 사용한다. 계산 범위 확장·격자 세분화·정규화 오차와 tail 질량을 함께 점검한다. 최적점과 역 Hessian만으로 통과시키지 않는다.

현재 Batch와 별도 구현의 log-density를 여러 유효 parameter 점에서 대조하고, 알려진 저차원 Gaussian/상관 posterior에서도 평균·분산·quantile을 검사한다. 제안 허용 오차는 실행 전에 수치 예제에서 고정한다(초안: 상대정규화 변화≤1e-6, 주요 quantile 변화≤.01 posterior SD). DR 기준이 실패하면 Range 대규모 재실행을 중단한다.

### R2. Range Batch의 결합 이동 보완

먼저 Calibration 3변수 joint whitening/block MH와 rho·delta·Calibration 결합 proposal을 도입한다. covariance/preconditioner는 burn에서만 학습하고 production에서 동결한다. 독립 rho 제안을 없애기보다 전역 이동 성분으로 유지하되 local/blocked 이동을 추가하며 정확한 proposal ratio를 적용한다.

잠재 잡음은 시간 블록 pCN과 전 구간 pCN을 혼합하고 burn에서 step을 조정한다. 개선이 부족할 때만 별도 lane으로 tempered MCMC 또는 미분 검증된 HMC를 검토한다. tempering은 최종 온도 1의 원래 posterior로 돌아와야 하며, 평탄화한 posterior를 최종 결과로 사용하지 않는다. 최적화는 초기값/proposal 구성에만 사용할 수 있고 mode 질량·불확실성을 대신하지 않는다. 서로 떨어진 Heading 초기값과 독립 반복을 유지한다.

예산 초안: 4chain, 각 burn4000+retained8000에서 진단; 필요시 결과 선택 없이 전 체인을 동일하게 2배 연장, 최대 retained32000/chain. 벽시간·메모리 상한은 R1 비용 측정 뒤 production 전에 동결한다. 한도 도달 시 미승인으로 종료한다.

### R3. PF 정적 상태의 표적 보존 재생

우선 retained observation prefix를 대상으로 한 resample-move SMC를 개발한다. move는 Calibration만 임의로 흔드는 jitter가 아니라 **초기 rho/delta·Calibration·잠재 궤적의 현재 prefix posterior를 불변으로 하는 MH/MCMC kernel**이어야 한다. Calibration 변화에 대응하는 궤적 재생과 과거 likelihood를 포함한다. 저장된 path 없이 현재 pose에만 perturbation을 넣는 shortcut은 허용하지 않는다.

Range-aware/auxiliary proposal은 그 다음 별도 개입으로 비교하고 proposal importance 보정을 검증한다. likelihood tempering은 중간 가중치 선택 압력을 나누는 데 사용할 수 있지만 move 없이 소실된 값을 복구하지 못한다. 데이터·R·Q·prior는 그대로 둔다.

현재와 같은 20k/80k, 각 독립 난수 4반복을 제안한다. 알고리즘 수정별 비교는 중심 4셀의 동일 prefix에서 한다. 비용이 부족하면 셀을 사후 제거해 승인하지 않고 미완료를 표시한다. rejuvenation 이후 초기 조상 수≥100은 현재 Calibration 다양성의 충분·필요 조건이 아니므로 기존 지표를 보존하되 새 표본의 다양성·mode 혼합·독립 반복 오차로 추가 검증한다. 옛 실행의 실패 판정은 변경하지 않는다.

### R4. 독립 합의와 prior/domain 민감도 재검증

DR 검증 후 Range의 초기 prefix 및 전체 horizon을 모두 사용한다. Batch 전체 smoother와 PF 중간 필터를 직접 비교하지 않는다. 중간 k에서는 Batch 입력도 k까지만 자르고 terminal에서 동일 horizon을 비교한다. PF/Batch는 동일 관측·prior를 쓰되 난수와 가능하면 density 구현을 독립화한다.

area/radius/half-normal10/half-normal100을 동일 셀·동일 horizon으로 검증한다. 현재 Batch에 없는 half-normal10도 포함한다. numerical cutoff 6/10/12sigma와 더 넓은 적분을 대조하되 의도적인 prior 변경과 영역 절단을 구분한다. 각 prior에서 먼저 수렴을 통과시킨 후 paired posterior 차이에 MC 오차를 붙인다. 초기 CDF의 작은 차이가 소실된 계보를 바꾼 것만으로 prior 민감도를 선언하지 않는다.

### R5. 승인 기준 동결 후 제한된 재검증

아래는 신규 개발 참조 승인을 위한 **제안 기준**이다. 옛 기준 Rhat<1.05 등의 소급 변경이 아니다. 실행 전에 버전·수치·예산을 동결해야 한다.

- 4개 이상 분산 초기 chain의 rank-normalized/folded split Rhat<1.01, bulk/tail ESS≥400. bg/SF/eps/rho/sin(delta)/cos(delta), log-density 및 주요 예측량을 검사한다. DR의 고정 gauge 좌표는 제외한다.
- 평균 MCSE≤.05 posterior SD; 2.5/97.5% quantile MCSE≤.1 posterior SD. posterior variance·credible region·mode 질량도 반복 안정성을 확인한다. 진단 수치만으로 미방문 mode 부재를 증명하지 않는다.
- PF 입자 수/독립 반복 및 Batch 독립 반복 사이 기존 평균≤.25 pooled SD·SD비≤1.25 조건을 유지하면서 MC 오차를 병기한다. 평균만 맞는 다봉 분포를 방지하기 위해 CDF/quantile, joint 영역과 mode 질량까지 비교한다. 추가 분포 거리 허용치는 R1 검증 예제에서 동결한다.
- posterior-invariant move의 수식·단위시험, toy exact posterior, 독립 log-density 대조를 모두 통과해야 한다. 현재 40개 구현 테스트 통과만으로 승인하지 않는다.
- 먼저 알고리즘 참조를 승인한 다음 정확히 일치하는 별도 생성 계약에서 episode 단위 coverage 검증을 한다. 4개 seed의 0/4 또는 4/4는 정확한 95% coverage 보장이 아니다. 표본 수·검정력은 별도 동결하며 I7 reserved seed를 열지 않는다.

## 6. 필요한 산출물과 중단 규칙

새 구현/실행이 승인되면 `I2_REFERENCE_REPAIR_DESIGN.json`, `TARGET_DENSITY_CHECKS.json`, `DR_REFERENCE_INTEGRATION.json`, `PF_EVENT_DIAGNOSTICS.csv`, `BATCH_MIXING.json`, `REFERENCE_AGREEMENT.json`, `PRIOR_DOMAIN_SENSITIVITY.json`, `I2_REFERENCE_REVALIDATION_GATE.json`과 raw samples·로그·해시를 별도 폴더에 남긴다.

현재 완료된 것은 원인 감사와 계획뿐이다. R0–R5는 NOT_RUN이다. 개선 커널의 수렴·독립 합의가 부족하면 REFERENCE_NOT_VALIDATED를 유지한다. 검증된 posterior가 확보되어도 운용 요구 정밀도 미정 상태에서 실용적 충분/부족을 판정하지 않는다. I3 진입과 실행은 별도 사용자 지시로만 수행한다.

## 방법 근거

- [Doucet의 SMC 자료 및 resample-move 설명](https://www.stats.ox.ac.uk/~doucet/smc_resources.html): 정적 parameter 다양성을 위한 불변 MCMC move의 근거. 본 코드에 효과가 있다는 실행 결과는 아직 없다.
- [Vehtari 등, rank-normalization/folding/localization 논문](https://sites.stat.columbia.edu/gelman/research/published/Vehtari_etal_2020_rhat_ess.pdf) 및 [저자 검증 예제](https://avehtari.github.io/rhat_ess/rhat_ess.html): 개선 Rhat와 bulk/tail 진단의 근거. 본 계획의 MCSE 예산·셀·연장 한도는 연구 개발상의 제안이다.
