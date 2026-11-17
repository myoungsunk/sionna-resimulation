# G1-SIGNED-COV-001 — signed heading 적재의 잔차 공분산 검증 사양

- 작성일: 2026-11-17 KST
- 역할: PROPOSER
- 상태: **SPEC_PUBLISHED_NOT_EXECUTED / NEEDS_INDEPENDENT_PREAUDIT**
- 저장소: `myoungsunk/sionna-resimulation`
- 브랜치: `research/g1-sweep-heading-floor-spec-20261113`
- 근거 스냅샷: **`5a33a982579df2b594224276d286c40d7bbe44b5`**
- 범위: mount 0°, 앵커 B, B0, Full RF, R2/R4/R5의 기존 개발 자료.
- 봉인: **G-T2/G-V를 읽거나 해제하지 않는다.** 기존 S2′ STOP / Step 3 HOLD를 변경하지 않는다.
- 이번 게시 범위: 사양 작성·게시. 구현, 데이터 재생, 수치 판정, 독립 감사 승인, 모델 채택은 수행하지 않았다.
- 데이터 재사용 고지: 기존 CHAR/D1–D3/M1–M7 결과를 본 뒤 설계한 새 기전 진단이다. 이 문서의 선게시가 이미 사용한 개발 자료를 새로운 독립 확인 자료로 바꾸지는 않는다.

## 0. 목적과 범위

핵심 질문은 `Var(slow_s) ∝ g^k`에서 k=2인지 다시 맞추는 것이 아니다.

> 다른 공분산 성분과 평균·기하·평활 효과를 통제한 뒤에도, signed a_i a_j가 느린 편파 잔차의 공분산을 설명하고 미사용 블록/경로의 공분산 예측을 개선하는가?

정의:

\[
 a_i=\left.\frac{\partial h_s}{\partial\psi}\right|_{x_i},\quad g_i=|a_i|,\quad
 e_i=z_{s,i}-h_s(x_i^{truth})-\mu_{M,i}.
\]

주 적재는 참 자세에서 독립적으로 계산한 `a_truth`다. 기존 E0-LORO prior의 `a_ref`는 온라인 적용 가능성의 별도 민감도다. 후보 필터의 posterior에서 얻은 a를 물리 기전의 주 설명변수로 사용하지 않는다. 각도는 rad, a는 rad⁻¹, e와 s는 무차원이다.

가설 모형:

\[
 e_i=a_i b_{\theta,i}+u_i+w_i,
\]
\[
 \operatorname{Cov}(e_i,e_j\mid\mathcal G)
 =\sigma_\theta^2 a_i a_j k_\theta(i,j)+C_u(i,j)+C_w(i,j).
\]

마지막 식은 성분 간 교차 공분산이 없다는 작업 가정을 포함한다. 실제 교차항·평균·커널이 다르면 성립하지 않을 수 있다. a_i a_j<0이어도 **전체** 잔차 공분산이 반드시 음수일 필요는 없다. 검정 대상은 가산형 성분 위에 signed 성분이 제공하는 추가 설명력이다.

### 답을 분리한다

1. **S-existence:** 현재 경로 안에서 signed 공분산 성분의 증분 설명력이 있는가?
2. **S-transfer:** 다른 경로에서 적합한 성분이 평가 경로로 이전되는가?
3. **S-online:** truth 적재에서 얻은 결과가 고정 기준 prior 적재에서도 유지되는가?
4. **S-filter:** 그 표현이 항법 성능까지 개선하는가? 이번 사양의 판정 대상이 아니다.

S-existence 지지가 물리적 yaw 오차의 유일한 원인을 입증하지 않는다. S-transfer 실패가 S-existence 실패를 뜻하지도 않는다. 고정 RF 공간장의 경로 표본에 대한 조건부 모형 비교이며, 센서 seed 반복으로 독립 RF 표본 수를 늘리지 않는다.

## 1. 현재 근거와 사전 기대의 한계

| 근거 | 확인된 내용 | 이번 검증으로 확대하지 않을 주장 |
|---|---|---|
| D1/D3 및 M1–M4 | R4·B에서 잔차 배치/느린 성분/반복 갱신을 바꾸면 heading 과신이 크게 개선됨 | 느린 성분이 반드시 a b_θ라는 결론 |
| M6 K1′ | 공통 k=0.3288; R4의 공통 기울기 기여 1.09%; R4 자체 k=2.381은 기술값 | R4는 순수 heading형, R2/R5는 순수 가산형이라는 분류 |
| M6 K2 | NO_COMMON_SUPPORT; LORO 규모 약 2°는 선택된 고감도 표본의 집계 | 공통 σ_θ의 물리적 일정성 |
| 기존 M6 q_s 적합 | raw 잔차 쌍에서 미리 정한 σ_θ² a_i a_j k를 차감하고 잔여를 비음수 적합 | 차감에 signed 항을 사용했다는 사실 자체가 signed 항의 검증이라는 주장 |
| 초기 SC/KI 비교 | KI는 seed 10의 R2/R5에서 무결성·정확도 기준 동시 충족, R4에서 실패 | R5는 편파를 약화하면 항상 실패한다는 주장 |
| M6/M7 | 결합 구조의 이득과 실패가 함께 존재. 최신 M7 게시 결과는 전 arm M7_PASS=false | 공분산 검증의 양성 결과가 기존 모델 채택 실패를 소급 변경한다는 주장 |

R4를 독립적인 핵심 보고 대상으로 둔다. R2/R5가 지배한 pooled 결과를 R4의 증거로 대체하지 않는다. 성공 또는 실패가 예상되는 경로만 사후 선택하지 않는다.

## 2. 입력 동결·출처·역할 분리 — SC0

### 2.1 허용 입력

기준 경로는 이 문서의 상위 `INTEGRITY_DIAG_001/`다.

| 입력 | 출처/연결 | 용도 |
|---|---|---|
| seed 10 online/evaluator 원본 | `gm_theta_m6/INPUT_LOCATIONS.json`, 해당 characterization RUN_CONTRACT와 원본 release | z_s, μ_M, t, pose_id, truth |
| D3 원본 | `continuation_d2_d3/d3/B_B0_R2.npz`, R4/R5 동명 파일 및 부모 계약 | eps, slow, support, window_n, arc/yaw, centering parity |
| 기존 기준 trace | `attempt_02/d5/B_B0_R*.npz` | 고정 a_ref, prior, gate의 민감도 비교만 |
| SourceFFD 코드·bank | M6 부모 계약의 native source 및 bank SHA | h_s(truth), signed Jacobian, active-set diagnostics |
| M6 특성화 코드 | `gm_theta_m6/run_characterization.py`, `characterize.py` | 잔차·D3·a_ref의 기존 정의 확인 |
| M7 공개 자료 | `m7_final_model_stage1/PUBLICATION_KO.md` 및 brief | 현황 설명만. M7 seed/오차로 쌍·문턱을 선택하지 않음 |

기존 packet 격자는 R2 979, R4 742, R5 1,415개다. 이는 3,136개 독립 RF 실현이 아니다. seed가 다른 파일에서 동일 RF 관측을 중복 집계하지 않는다.

실행자는 원본 계약의 절대 경로를 실제 저장소 파일과 SHA-256으로 연결하는 `INPUT_MANIFEST.json`을 먼저 만든다. Git LFS pointer를 NPZ로 오인하지 않는다. 누락·해시 불일치·관측 정의 불일치 시 중단한다. 기존 출력과 계약을 덮어쓰지 않는다.

이 문서에서 원본 NPZ 바이트를 재검산했다고 주장하지 않는다. `COMMON_CONTRACT.md` 등 로컬 연구 거버넌스는 실행 환경에서 위치·내용·해시를 확인하고 RUN_CONTRACT에 추가한다. 문서에 인용된 과거 정책 해시만으로 현재 정책을 읽었다고 간주하지 않는다.

### 2.2 판정용 입력 차단

- 주 모집단: 유효 원본 packet 전체. E0 NIS gate로 주 표본을 선택하지 않는다.
- E0 고정 gate 수용 표본은 미리 지정한 민감도 표만 만든다.
- 후보별 innovation, heading/XY 오차, MIRROR_FAIL을 쌍 선택·모수 적합·지원 판정에 사용하지 않는다.
- evaluator는 오프라인 기전 분석에만 사용한다. 이 진단은 온라인 알고리즘이 아니다.
- 잔차값/쌍곱을 보기 전에 geometry-only 지원 표와 split·match manifest를 동결한다.
- 현재 코드에 이미 있는 출력은 역사 자료다. 새 signed 검정의 결과 파일은 아직 존재하지 않는 것으로 시작한다.

## 3. signed 미분의 유효성과 식별 지원 — SC1

### 3.1 미분 확인

SourceFFD의 a_truth와 yaw 중심 유한차분을 비교한다. epsilon={1e-5, 5e-6} rad. 각 ±epsilon에서 FFD 보간 active cell, FP tap, strong port 및 cap 구간을 기록한다.

- active set이 바뀌는 점은 NONSMOOTH로 표시한다. 주 미분 비교에서 제외하고 경로/거리/부호별 제외율을 보고한다. gradient=0으로 채우지 않는다.
- 안정 구간 오차 기준: `abs(a_analytic-a_fd) <= 1e-4 + 0.01*abs(a_fd)`.
- 안정 점의 99% 이상이 두 epsilon에서 기준을 충족해야 한다. 주 g 하한을 넘는 안정 점에 부호 불일치가 하나라도 있으면 STOP_DERIVATIVE_MISMATCH.
- 불일치를 줄이려고 유한차분 폭이나 관측 체인을 결과 후 변경하지 않는다. 변경은 별도 개정이다.
- 전역 a→−a에서 a_i a_j는 그대로다. 따라서 전역 부호 반전은 구현 불변성 검사이지 음성 대조가 아니다.

### 3.2 원시 쌍 정의

각 경로의 시작 기준 비중첩 20 s 블록을 사용한다. 끝의 20 s 미만 블록은 기술 표에만 포함한다. 주 쌍은 i<j이며 다음을 만족한다.

- 두 점 모두 미분 안정, `|a_truth| >= 0.2 rad^-1`.
- `0.4 <= t_j-t_i <= 5.0 s`.
- 두 점의 수평거리 ρ가 같은 bin: [0,1.5), [1.5,3), [3,6), [6,10) m.
- 두 점이 같은 20 s 블록 안에 있음.
- M6 기준 kernel `kθ=exp(-Δarc/1m-Δyaw_arc/10deg) >= 0.05`.

arc는 truth XY의 누적 이동거리, yaw_arc는 truth yaw의 wrapped 증분 절댓값 누적이다. 차이를 최단 endpoint 거리나 순 yaw 차이로 대체하지 않는다. M6 control 기반 arc/yaw는 별도 민감도다. ρ와 3차원 거리 d를 혼용하지 않는다.

일차 지표에 e/a를 사용하지 않는다. a≈0 부근에서 발생하는 분모 효과와 `e/a`로 만든 값을 다시 a에 회귀하는 순환 논증을 피한다. g 하한 0.1 및 0.5는 사전 지정 민감도이며 주 하한을 대체하지 않는다.

### 3.3 같은 부호/반대 부호의 공통 지원

같은 경로×20 s 블록×거리 bin×운동 종류 안에서 a_i a_j>0 쌍과 <0 쌍을 매칭한다. 운동 종류는 각 endpoint 간 평균 이동속도 0.02 m/s, 평균 회전속도 0.02 rad/s를 문턱으로 translation/rotation/mixed/stationary로 고정한다.

매칭 caliper:

- pair lag 차이 ≤0.4 s;
- Δarc 차이 ≤0.10 m;
- Δyaw_arc 차이 ≤5°;
- 정렬한 두 endpoint ρ의 각 차이 ≤0.5 m;
- 정렬한 두 endpoint |a|의 각 비율 ≤1.25.

각 차이를 caliper로 나눈 제곱합을 cost로 사용한다. cost 오름차순, 동률은 pose_id 사전순의 결정적 greedy matching을 적용한다. 한 matched comparison의 네 endpoint가 모두 달라야 하고, 지원 수 산정용 matching에서는 endpoint를 다시 쓰지 않는다. 전체 적격 쌍은 별도의 예측 점수에 사용할 수 있지만 독립 표본 수로 세지 않는다.

상대 bearing·고도각·회전방향·직진/회전 비중의 매칭 전후 분포를 공개한다. a는 기하의 함수이므로 모든 자세를 정확히 고정하면서 부호만 바꾸는 실험으로 해석하지 않는다. 상대 bearing의 절댓값 차이 ≤10°, 고도각 차이 ≤5°를 추가한 민감도에서 지원이 사라지면 geometry confounding 한계로 기록한다.

지원 문턱은 실험 설계상 최소 요건이며 독립성의 증명이 아니다.

- 경로별: endpoint-disjoint matched comparison ≥40개, 이들을 제공한 20 s 블록 ≥4개, 각 부호 종류가 최소 4개 블록에 존재.
- pooled 진단: 위 경로 기준을 만족한 경로 ≥2개, 전체 블록 ≥8개.
- R4가 경로 기준을 못 넘으면 R4의 주 판정은 `INCONCLUSIVE_SUPPORT`로 고정한다. R2/R5 결과로 대체하지 않는다.

추가로 실제 평균 제거·평활을 적용한 covariance basis의 식별성을 검사한다. signed basis를 unsigned·가산·단기·백색 basis에 투영한 잔여 Frobenius norm 비율 ≥0.05, 열 정규화 설계의 condition number ≤1e3을 요구한다. 미달이면 `INCONCLUSIVE_DESIGN`이다. 같은 부호 쌍만 있으면 signed와 unsigned가 같거나 거의 같아지는 문제를 반드시 검사한다.

## 4. 원시 잔차·평균·D3 평활의 분리 — SC2

### 4.1 주 분석: raw truth 잔차의 시간 공분산

raw e를 사용한다. 주 결과는 raw 잔차의 비대각 공분산에 대한 held-out 예측이다. 느린 상태가 존재한다는 결론을, 느린 평균을 먼저 만들어 생긴 자기상관만으로 내리지 않는다.

각 block×거리 bin의 유효 점 집합에 대해 n≥10일 때 `M=I-11ᵀ/n`을 적용한다. 관측은 Me, 모든 모형의 예상 공분산은 **M C Mᵀ**로 변환한다. 이 평균 제거는 평가 블록의 nuisance constant를 제거하는 배치 진단이다. 온라인 예측 또는 알려진 평균이라는 주장을 하지 않는다.

평균 제거에 의한 백색 잡음의 음의 비대각항도 M diag(v) Mᵀ에 포함한다. train/test를 합쳐 평균을 빼지 않는다. route 전체 평균을 사용해 test 잔차를 train에 흘려보내지 않는다.

평균 기하 교란 민감도에서는 `F=[1, a, 거리-bin 내부의 ρ]`의 full-rank 열 공간을 제거한 projection을 같은 관측·모형 모두에 적용한다. signed 이득이 이때만 사라지면 `MEAN_DEPENDENT`로 표기한다. 이는 stochastic 공통 편향과 결정론적 평균 기하를 현재 자료로 분리하지 못한다는 뜻이지, 항법에서 a b_θ 표현이 무용하다는 뜻은 아니다.

### 4.2 D3 slow는 보조 분석이며, 필터 연산자 전체를 전달한다

기존 D3 `decompose`의 창, route mean 제거, 지원 slow 평균 제거를 독립 구현으로 복원한다. seed 10의 기존 slow·support·window_n과 parity를 확인한다. 실제 중심화와 평균 연산을 합친 선형 연산자를 **L**로 저장한다.

\[
 e_{slow}=Le,\qquad C_{slow}=LCL^\mathsf T.
\]

signed 성분의 올바른 변환은

\[
 C_{slow,\theta}=\sigma_\theta^2 L A K_\theta A L^\mathsf T,
\quad A=\operatorname{diag}(a).
\]

이를 `σ² a_i a_j k_ij` 또는 `σ² (La)_i(La)_j k_ij`로 임의 대체하지 않는다. 창 안에서 a의 부호·크기가 바뀌면 이들은 같지 않다.

독립 백색 입력에도 `L diag(v) Lᵀ`의 비대각 상관이 생긴다. 이 항을 빼거나 모형에 반영하지 않은 slow 상관은 signed 기전의 증거로 인정하지 않는다. 서로 겹치지 않는 smoothing window를 가진 쌍도 별도로 보고한다. 그 하위 표본의 지원 부족을 전체 효과 부정으로 해석하지 않는다.

분할마다 D3 연산자를 다시 구성한다. train 창은 test/embargo 점을 사용하지 않으며 test 창은 train 점을 사용하지 않는다. 필요한 최대 ±5 s halo는 test 전용으로 보존하고 train에서 제외한다. 끝/지원 부족 처리를 0 채움으로 대체하지 않는다.

## 5. 비교 모형과 공분산 적합 — SC3

### 5.1 커널과 양의 준정부호 구성

주 커널:

\[
 K_\theta(i,j)=\exp(-\Delta arc_{ij}/1m-\Delta yaw_{ij}/10^\circ),
\]
\[
 K_f(i,j)=\exp(-\Delta arc_{ij}/0.03m-\Delta yaw_{ij}/20^\circ).
\]

K_f는 CHAR-001에 근거한 짧은 공간척도 nuisance 모형이다. 제자리 회전에서도 모든 의미에서 K_θ보다 빠른 모형이라는 주장은 하지 않는다. K_θ는 **현재 M6의 지정 커널**이며 모든 가능한 heading형 확률과정을 대표하지 않는다.

각 거리 bin b의 선택 diagonal을 D_b로 둔다. 같은 bin 내부 점과 쌍만 주 적합·점수에 사용한다. bin 사이 공분산의 우열은 이 검증에서 주장하지 않는다.

\[
 C_N=\sum_b\{w_bD_b+f_bD_bK_fD_b+q_bD_bK_\theta D_b\},
\]
\[
 B_S=A K_\theta A,\quad B_U=G K_\theta G,\quad G=\operatorname{diag}(|a|).
\]

모든 w_b,f_b,q_b,θ는 비음수다. θ의 단위는 rad²다. A의 원소가 음수여도 A K A는 PSD다. 음의 off-diagonal을 이유로 절댓값/0 clipping을 하지 않는다.

| ID | 모형 | 역할 |
|---|---|---|
| C-A | C_N | 가산형·단기·백색 대조 |
| C-U | C_N+θ B_U | g 크기는 같고 부호만 버린 동일 복잡도 대조 |
| C-S | C_N+θ B_S | signed 주 후보 |
| C-T | 백색+단기+θ B_S, q_b=0 | 순수 heading형 성분의 충분성, 보고용 |
| C-SU | C_N+θ_s B_S+θ_u B_U | 두 basis의 경쟁·식별성, 보고용 |

R_ref를 순백색 분산이라고 가정하지 않는다. 새 진단의 w/f/q는 관측 잔차에서 적합하는 공분산 모수다. M6의 R_ref·σ_θ·q_s를 정답으로 고정하거나 먼저 차감하고 남은 양으로 가설을 입증하지 않는다. 기존 약 2°를 고정한 forward prediction은 보고용 대조이며 주 적합을 대체하지 않는다.

### 5.2 추정량

train의 각 block×bin에서 Me의 diagonal 제곱과 적격 비대각 쌍곱을 사용한다. 각 covariance basis에도 동일한 M을 적용한다. D3 보조 적합에는 동일한 L을 적용한다.

- 같은 평가 단위 안의 diagonal 항 평균 가중치 0.25, 비대각 항 평균 가중치 0.75.
- 경로 동일 가중 → 지원 거리 bin 동일 가중 → 블록 동일 가중 → 그 안의 항 동일 가중.
- bin별 손실 정규화는 train raw e의 2차 모멘트 제곱을 사용하며 하한 1e-12 s⁴. 모든 후보에 같은 normalizer를 사용한다.
- 비음수 가중 최소제곱(NNLS)으로 선형 covariance basis 계수를 동시 적합한다. 열 scaling과 원단위 복원을 기록한다.
- signed 항을 임의로 먼저 넣고 나머지만 적합하지 않는다. constrained θ=0 경계해도 그대로 보고한다.
- 중심값·분산 모수가 누락된 bin은 지원 부족으로 처리한다. 평가 경로의 잔차로 보충하거나 옆 bin의 값을 사후 대입하지 않는다.

주 적합은 Gaussian 분포 가정을 요구하는 likelihood 검정이 아니라 공분산 모멘트의 작업 모형이다. 두꺼운 꼬리의 영향은 원값 손실과 train-only 99% 절댓값 문턱 winsorized 민감도를 병기한다. winsorized 결과만 양성이면 주 양성 판정을 하지 않는다.

### 5.3 두 분할을 혼합하지 않는다

**A. 경로 내부 존재 검증(주):** leave-one-complete-20s-block-out. train에서 test 블록의 양쪽 10 s embargo를 제거한다. 모든 전처리·평균 제거·모수는 fold 내부에서 재구성한다. test의 경로별 점수는 각각 산출한다.

**B. 경로 간 이전 검증(별도):** LORO 3 folds. 다른 두 경로로 적합한 뒤 남은 경로를 점수화한다. truth pose가 test의 위치 5 cm·yaw 5° 안에 있는 donor 점은 transport 주 표에서 제외하고, 제거 전 결과를 동일 공간장 내 interpolation 민감도로 병기한다. 동일 pose 반복을 독립 이전 증거로 세지 않는다. 지원이 사라지면 NO_COMMON_SUPPORT다.

같은 RF를 공유하는 sensor seed 10–29는 두 분할의 표본 수에 추가하지 않는다. 이미 관측된 개발 경로의 blocked/LORO 결과는 독립 장면 확인이 아니다.

## 6. 주 지표·불확실성·합성 검사 — SC4

### 6.1 예측 지표

각 held-out block×bin의 transformed residual product와 predicted transformed covariance를 비교한다. 주 지표는 **비대각 정규화 squared prediction error**의 평균이다. diagonal 항은 적합 안정성·분산 calibration의 보조 지표이며 주 성능 개선량에 섞지 않는다.

\[
 \Delta_U=(L_U-L_S)/\max(L_U,10^{-12}),\quad
 \Delta_A=(L_A-L_S)/\max(L_A,10^{-12}).
\]

같은 부호/반대 부호별 점수, geometry-matched 쌍의 점수, 각 거리 bin과 각 경로의 점수를 반드시 분리한다. global pooled는 경로 동일 가중이다. 물리적 sign 검증의 핵심은 C-U 대비이며, C-A 대비만 좋아졌다면 `SCALE_ONLY` 가능성을 남긴다.

보조: 평균을 제거한 독립 contrast 좌표에서 covariance log score, empirical/predicted covariance 표, 부호별 calibration, θ profile, 단기·가산·signed 분산 기여. Gaussian log score는 작업 모형의 점수이지 실제 Gaussian성의 증거가 아니다. jitter가 diagonal scale의 1e-6를 초과하면 수치 실패로 처리한다.

### 6.2 불확실성

- bootstrap 2,000회, RNG seed 20261117.
- packet 또는 pair를 IID로 재표집하지 않는다. 원래 시간 순서의 **40 s moving block**을 경로 안에서 재표집하고, 동일 resample을 모든 후보에 적용한다. fold 전체의 전처리와 NNLS를 다시 계산한다.
- 쌍의 두 endpoint는 함께 유지한다. 붙여 만든 블록 경계에 새로운 관측쌍을 만들지 않는다. 겹치는 D3 창은 원래 dependency를 유지하거나 그 표본을 제외한다.
- 20 s 및 60 s block을 민감도로 병기한다. 부호/지원이 불안정하거나 사용 가능한 block 수가 4 미만이면 그 CI를 reference_only로 둔다.
- 경로별 3개 주 판정에는 양측 98.33% percentile 구간을 사용한다(세 경로 다중 보고에 대한 보수적 95% family 수준의 작업 규칙). C-U와 C-A 대비는 **둘 다** 기준을 만족해야 한다. pooled는 보조 95% CI이며 경로별 실패를 덮지 않는다.
- 이 block CI의 정당성에는 국소 교환가능성/의존 길이 가정이 남는다. 단일 결정론적 RF 장에서 엄밀한 빈도론적 모집단 보장을 주장하지 않는다.
- 임의 packet sign permutation이나 전체 잔차 shuffle을 유효한 유의확률로 쓰지 않는다. 전역 sign flip은 공분산 불변이므로 null test가 될 수 없다.

### 6.3 필수 합성 검산과 식별력 검사

실제 잔차의 signed 결과를 열기 전에 geometry와 frozen splits를 사용하여 다음을 확인한다. 실제 관측에 대한 검증 결과와 구분한다.

1. θ=0인 가산형+단기+백색 입력: false-positive 빈도와 Wilson 95% 상한을 기록.
2. signed 입력: 평균 long-component diagonal의 10/30/60%가 θ 항이 되도록 주입. θ 및 예측 부호 회복 확인.
3. unsigned 입력: C-U가 C-S보다 유리한 설정에서 잘못된 signed 채택 여부 확인.
4. 백색 입력을 D3와 동일 L로 평활: 겹침으로 생긴 상관을 signed 신호로 오인하지 않는지 확인.
5. a가 한 부호만 갖거나 모든 적격 kθ가 거의 0인 입력: INCONCLUSIVE가 나와야 함.
6. 전체 a→−a: 모든 covariance·점수가 같아야 함.
7. 같은 RF 배열을 seed 이름만 바꿔 복제: 표본 수·CI가 개선되지 않아야 함.
8. signed mean `e=c a+w`, 비정상 느린 평균, 관측 잡음과 a_ref가 연관된 대조: MEAN_DEPENDENT/내생성 경고 확인.
9. smooth active-set derivative parity, ±180° wrap, m/rad/degree 변환, PSD 및 matrix/element-wise 적재 일치.
10. 미래/test 잔차를 바꿨을 때 train fitted coefficient·선택·manifest가 변하지 않는 누출 검사.

각 통계 대조의 독립 합성 실현은 500회, seed 2026111700+replicate. 합성은 새 물리 RF 데이터가 아니다. θ=0 대조의 false-positive Wilson 상한이 7.5%를 넘으면 실제 양성 판정을 중지한다. 30% 주입 효과의 검출률이 80% 미만이면 실제 음성 결과를 구조 부정으로 해석하지 않고 LOW_POWER로 둔다. 이 문턱은 본 연구의 사전 설계값이며 자연법칙이 아니다.

## 7. 판정 — SC5

한 경로의 `SIGN_SUPPORTED_WITHIN_FIELD`는 다음을 **모두** 만족해야 한다.

1. 미분·입력·geometry 지원·basis 식별 검사 통과.
2. 경로 내부 held-out raw에서 Δ_U와 Δ_A가 각각 ≥5%, 각 family-adjusted CI 하한 >0.
3. 개선이 같은 부호만이 아니라 matched opposite-sign 쌍에서도 같은 방향. opposite-sign 점추정 개선 >0.
4. 지원 있는 평균-기하 제거 민감도에서 방향이 유지됨. 사라지면 MEAN_DEPENDENT.
5. D3 slow에서도 L C Lᵀ로 설명했을 때 부호 방향이 모순되지 않음. D3 지원 부족은 보조 미평가로 표기하되 raw에 근거한 결과를 'D3 slow 성분 확정'으로 격상하지 않음.
6. 합성 false-positive gate 통과. tail/시간 block 민감도에서 방향이 뒤집히면 ROBUSTNESS_FAIL.

5%는 동일 자료의 최적값을 찾기 위한 값이 아니라 사전 선언한 최소 예측 개선량이다. 데이터 결과를 보고 완화하지 않는다.

| 결과 | 허용 판정 |
|---|---|
| 위 조건 통과 | 현재 경로·RF·커널군에서 signed covariance의 증분 예측 지지 |
| C-A만 이기고 C-U를 못 이김 | SCALE_ONLY / SIGN_NOT_IDENTIFIED |
| 반대 부호 또는 basis 지원 부족 | INCONCLUSIVE_SUPPORT / INCONCLUSIVE_DESIGN |
| 충분한 지원·합성 식별력이나 C-S 이득 없음 | NO_INCREMENTAL_SIGN_EVIDENCE; 모든 가능한 heading형 오차의 부정 아님 |
| raw와 D3가 평활 항 처리 후 불일치 | FILTER_DEFINITION_SENSITIVE; 기전 확정 보류 |
| 평균 제거에만 의존 | MEAN_DEPENDENT |
| 커널/꼬리/시간척도에 방향 반전 | MODEL_MISMATCH 또는 ROBUSTNESS_FAIL |
| 존재 검증 통과, LORO 실패 | 국소 존재 지지·이전성 미확인 |
| truth만 통과, a_ref 실패 | 물리 진단의 적재와 온라인 적재 사이 gap |

R4는 자체 판정을 받는다. 다른 경로의 양성으로 R4를 통과시키지 않는다. 어느 경우에도 물리 yaw bias의 유일 원인, σ_θ≈2°의 보편성, 항법 integrity 확보, 거울해 해결, M7 통과를 주장하지 않는다.

### 고정 민감도

주 kernel (1m,10°) 외 (0.5m,10°), (2m,10°), (1m,5°), (1m,20°)를 전부 보고한다. 가장 좋은 것을 골라 주 판정에 대입하지 않는다. 주 kernel 실패/민감도 성공은 다음 가설의 근거이지 이번 성공이 아니다.

## 8. 지원이 부족할 때의 새 개발 자료 설계

부호 반전은 yaw 변화와 함께 일어나므로 kθ가 거의 사라진 뒤의 반대 부호 쌍은 heading 공통 상태를 식별하지 못한다. 이 경우 반복 계산으로 해결하지 않는다.

별도 승인된 신규 개발 데이터에서 같은 수평거리·측면 offset·위치 부근의 yaw sweep가 a의 부호 경계를 양쪽으로 지나도록 설계한다. 각 쪽에서 |a|가 충분한 구간과 kθ≥0.05인 쌍을 확보하고, high-g 지속 구간·near-anchor 통과·직진을 함께 포함한다. 실제 FFD를 이용한 geometry-only 사전 지원 검사로 station/yaw를 정한다.

같은 정적 장의 똑같은 pose 재방문은 반복성 검사일 뿐 독립 RF ensemble이 아니다. 환경/반사 배치/앵커 배치 변화 또는 독립 장면 반복을 별도 인자로 두고, thermal/motion seed와 구분한다. G-T2/G-V를 지원 부족을 해결하기 위한 탐색 자료로 열지 않는다.

## 9. 산출물·실행 순서·감사

예정 실행 순서:

`SC0 입력/정의 확인 → 독립 사전 감사 → 계약 SHA 동결 → SC1 geometry-only 지원 → 합성 구현·식별력 검사 → SC2/SC3 raw 및 D3 비교 → SC4 불확실성 → SC5 판정 → 별도 감사`

geometry 지원 부족이면 그 범위의 본 검정을 중지하고 지원 보고서까지만 게시한다. 테스트를 실행하지 않은 이번 게시물은 실행 계약/감사 통과를 대신하지 않는다.

예정 산출물:

- `RUN_CONTRACT.json`: 이 사양 commit/blob/hash, 입력·코드·bank·환경 hash, 설정, train/test와 권한 경계.
- `INPUT_MANIFEST.json`, `DERIVATIVE_QA.json`, `GEOMETRY_SUPPORT.csv`, `PAIR_MATCH_MANIFEST.csv`, `SPLIT_MANIFEST.json`.
- `OPERATORS.npz`: 평균 제거·D3 연산자의 sparse 표현과 원 packet 인덱스.
- `SYNTHETIC_CHECKS.json`, `POWER_AND_FALSE_POSITIVES.csv`.
- `FITS_BY_FOLD.json`, `HELDOUT_COVARIANCE_PREDICTIONS.csv`, `SCORES_BY_ROUTE_BLOCK_SIGN.csv`.
- `RAW_VS_D3.csv`, `KERNEL_SENSITIVITY.csv`, `TRUTH_VS_REFERENCE_LOADING.csv`.
- `DECISION.json`, `REPORT_KO.md`, `EXECUTION.json`, `VERIFICATION.json`, `SHA256SUMS`.

각 예측 행은 route, pose_i, pose_j, t_i, t_j, input RF ID, block/fold, sign, a_i,a_j,g_i,g_j, ρ_i,ρ_j, Δarc,Δyaw,lag,k, active-set validity, operator definition, target/prediction, weight, acceptance population을 포함한다. 표시용 그래프만 남기지 않는다.

필수 독립 사전 감사 체크:

- raw 진단에 후보 필터 오차/innovation이 들어가지 않는가?
- 단위와 signed Jacobian이 올바른가?
- gate 선택·중복 RF seed·겹치는 창·route demeaning의 누출이 차단됐는가?
- L A K A Lᵀ를 정확히 계산하는가?
- C-S와 C-U의 모수 수·적합 자유도·지원이 같은가?
- q_s를 사전에 차감해 signed 가설을 정답으로 고정하지 않는가?
- 반대 부호의 common support와 커널 크기가 충분한가?
- R4 별도 판정과 NO_SUPPORT/LOW_POWER 분기가 살아 있는가?
- bootstrap이 packet/pair 독립을 가장하지 않는가?
- 기존 역사 결과·판정 기준·봉인 자료를 변경하지 않는가?

현재는 실행 코드 미작성, 독립 사전 감사 미실시다. 구현자는 별도 code SHA와 합성 검사 통과를 제출한 뒤 실제 자료 검정을 시작한다. 미구현 CLI를 실행 가능한 명령처럼 배포하지 않는다.

## 10. 근거 문서

아래 상대 링크는 탐색 편의용이다. 실행 근거는 반드시 위 스냅샷 SHA로 고정한다.

- [D2/D3](../continuation_d2_d3/REPORT_KO.md)
- [초기 SC/KI 비교 — R2/R5 동시 성공과 R4 실패](../structure_sc_ki/REPORT_KO.md)
- [M1–M4](../exposure_m1_m4/run_01/REPORT_KO.md)
- [M6 특성화](../gm_theta_m6/characterization_tables/attempt_02/REPORT_KO.md)
- [M6 입력 구성](../gm_theta_m6/run_characterization.py)
- [M6 기존 q_s 적합](../gm_theta_m6/characterize.py)
- [M6 재생](../gm_theta_m6/gm_replay.py)
- [M7 게시 현황](../m7_final_model_stage1/PUBLICATION_KO.md)
- [M7 요약](../m7_final_model_stage1/attempt_02/brief/REPORT_KO.md)

방법론 참고:

- Winkler et al. (2014), Permutation inference for the general linear model, NeuroImage 92:381–397, doi:10.1016/j.neuroimage.2014.01.060. 의존 자료에서 임의 순열이 유효하지 않고 교환가능성 조건이 필요하다는 근거. https://pmc.ncbi.nlm.nih.gov/articles/PMC4010955/
- Roberts et al. (2017), Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure, Ecography 40:913–929, doi:10.1111/ecog.02881. 의존 구조와 예측 목표에 맞춘 분할의 근거. https://nsojournals.onlinelibrary.wiley.com/doi/10.1111/ecog.02881

본문의 지원 수·미분 오차·5% 개선·합성 문턱은 이번 검증의 사전 설계 선택이다. 위 논문이 이 숫자를 보증한다는 주장을 하지 않는다.
