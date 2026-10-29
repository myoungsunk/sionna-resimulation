# RA3 원 구현 정의 및 분산 조회 시점 차이 검증

**감사 대상:** `pol_bias_model/exp_pb.py`의 MB_VAR / BB_VAR, `mbvar_control_correction_20261029/ctl_core.py`, `ds_state_info_forensics/run_four_priorities.py`의 분산 조회 시점 차이.

## 명세상·실행상 차이

원 `exp_pb.py`의 설명부에는 `rho_hat`를 “predicted state”라 표현하지만, 본문 `run()`의 각 단계는 **이전 시점 posterior x에서 먼저 `rho` 및 `sigma_b`를 계산하고, 그 후 `predict`**를 수행한다. 즉 현재 수용 packet k에 쓰는 분산은 다음과 같다.

- **MB_VAR-LEGACY / BB_VAR-LEGACY (원래 실제 코드):** `rho(x_{k-1}^+)`에서 `sigma_b` 조회. `k=0`일 때 x0 사용.
- **MB_VAR-PRIOR / BB_VAR-PRIOR (비교 Arm):** 제어 입력으로 예측한 `rho(x_k^-)`에서 `sigma_b` 조회.
- 두 Arm 모두 `R_ss <- R_ss + sigma_b(rho)^2` 외의 센서, 예측, μ, Q, FFD model, baseline 수용 mask, Joseph covariance 갱신은 동일. 기존 원본 평균·gate 학습이나 score 분모는 변경하지 않는다.

원래 구현이 갑자기 잘못됐다고 단정할 수는 없다. **동일 `MB_VAR`라는 이름 아래 두 정의를 혼용하면 재현 불가능해지는 것이 문제**이므로 명칭과 정의를 구분해야 한다. 원 결과를 새 방식으로 사후 교체하거나 원래의 23/28 개선 결과를 새 모델의 결과로 표기하지 말 것.

## R4-B / R5-A B0,L2 canary 결과

실제 source CONTROL B0/L2를 받아 원 `exp_pb.run`과 독립 수식 재구성의 **전체 state/P 재현이 최대 절대차 0**임을 확인했다. 고정 BASE gate와 입력은 동일하고, 분산 조회 시점만 바꾸어 8개 arm(두 case×두 bias×BB/MB)을 재실행했다.

- 최대 `|sigma_b(pre)-sigma_b(prior)|`: **0.001281**
- 최악 Heading RMSE 변화 절대값: **0.005490°**
- 최악 XY RMSE 변화 절대값: **0.090752 cm**
- 동일 시간 프레임의 최대 Heading state 차이: **0.026717°**
- 동일 시간 프레임의 최대 x/y state 성분 차이: **0.004085 m**
- 결과는 0은 아니지만, 이 두 canary로 전체 28조건 변화나 과학적 효용을 외삽하지 않는다.

실행 기록 [RA3 canary #40851671917](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40851671917). 독립 산술 체크 receipt `AUDITOR_ARITHMETIC_RECEIPT.json`에 출력 해시·집계 검사를 기록. 

## 전체 7 cases×4 biases 확대 비교

[전체 28조건 실행 #40852149539](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40852149539) **실제 completed/success 검증.** 7개 case × 4 gyro × BB_VAR·MB_VAR 총 **56개의 원자료 재실행**이며 모든 조건에서 레거시 원 `exp_pb.run()`과 별도 수식 재구성의 **전체 state/P 최대 차이 0**. BASE gate와 원 mean/R/Q, 센서, 초기 상태를 동일하게 고정했다.

| BB_ORIG 대비 MB_VAR 개선 개수 | 원 LEGACY 조회 | 현재 predicted prior 조회 | 변경 여부 |
|---|---:|---:|---|
| Heading RMSE | **23/28** | **23/28** | 없음 |
| XY RMSE | **20/28** | **20/28** | 없음 |
| Heading+XY 동시 | **19/28** | **19/28** | 없음 |

**28개 중 개선/미개선 이진 판정이 달라진 조건은 0개.** 단, 연속적인 성능 수치는 동일하지 않다. 56개 Arm 전체에서 Heading RMSE 변화 절대값 최대 **0.010476°**(R2-A m0/L2, BB_VAR), XY RMSE 최대 **0.237204 cm**(같은 조건). 주요 MB_VAR 28개만 보면 Heading RMSE 변화 최대 **0.006278°**(R2-B m0/B0), XY RMSE 최대 **0.060967 cm**(R4-B m0/B0). 경로 중 최대 Heading state 차이는 **0.068130°**, x/y 단일 state 차이는 **0.009926 m**. `sigma_b` 최대 조회 차이는 **0.0012973**이다.

해석: 검증된 28조건의 **'개선 비율' 주장은 분산 조회 시점 혼동만으로 뒤집히지 않는다.** 그러나 구현 정의 차이 자체는 실재하고 연속점수 및 state/P는 다르므로, 원 MB_VAR 결과에는 원 LEGACY 정의를 고정하고 prior 조회 버전은 별도 Arm으로 표기해야 한다. 두 의미를 혼합해 재현성 있는 물리 주장이나 일반화 결과로 사용할 수 없다.

제한: B0/L0/L1/L2는 동일 RF packet을 공유하며 독립 환경이 아니다. 이 시험은 기존 시뮬레이션 packet 재생에 관한 후향적 정의 민감도 검사이지 새로운 외부·물리 성능 검증이 아니다.

## 유지해야 할 주장 경계

이 시험은 **동일 저장 packet을 사용하는 필터 구현 정의 민감도**다. G3의 RT 물리적 타당성·원시 H 여부 또는 외부 환경에서의 일반화는 입증하지 않는다. G3 physical QA와 분리해야 인과 해석을 보존할 수 있다. 비교 Arm의 사후 성공/실패는 사전등록 성능 입증이 아니다.