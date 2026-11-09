# PALO 후보 ② — 지지층 / 적대적 리뷰 / 재지지층 재설계

**문서 성격:** PROPOSED / SCIENTIFIC_DESIGN_REVIEW / NOT_IMPLEMENTED_V2 / NOT_FROZEN. 기존 구현의 오류와 실패를 보존하며, 새 구조가 개선됨을 주장하지 않는다.
검토 단위: 실제 과거 local precheck model.py 의 filter_hypotheses/mixture_moments, experiment.py의 stage2, 선행 R2/R4/R5 GitHub 실험. 원본 필터 16조건 중 15조건 엄격 전체 재귀 parity PASS, Full/B0 S4 1조건 허용치 초과 및 mask 차이 0 — 재현 이상 해결 전 새 과학 결과를 최종 ACCEPT하지 않음.
**정책 목표:** 운동 예측을 기본으로 유지하면서, 다중경로에 의한 RF 오수용과 유익한 RF 오거부의 악순환을 동시에 감소시키고 위치/헤딩/gyro bias/교차공분산의 일관성을 지키는가?

## Round I — 지지층

1. 과거 C·D 같은 RF에서 S4와 DR의 즉시 Heading 보정 손익 부호가 달랐던 사례 B0 420/779, L0 370/779, L1 368/779, L2 359/779. B0의 공분산만 교환하는 국소 요인 실험에서 손익 부호 반전 258건(다른 요인과 중복). 하나의 x,P만 다음 재귀로 남기면 다른 잠재 이력 손실을 회복하기 어려울 수 있다.
2. 기존 NIS≤0.5가 R2-B에서 나쁘지 않았으나 R4-A/L2에서 수용 36/542, 헤딩 RMSE 13.917° vs S4 1.037°, R5-A/L2는 53.4초 연속 미수용, 14.051° vs 5.297°. 하드 거부가 악순환을 만들 수 있어 RF 수용 여부의 이력을 잠시 병존시키는 구조는 타당한 설계 가설.
3. 완전한 혼합 사후확률이라면 p(x|y)=Σ_jπ_j p_j(x), P=Σ_jπ_j[P_j+(μ_j−μ̄)(μ_j−μ̄)ᵀ]로 가설 간 불확실성을 표현한다. 원형 헤딩 통계와 가지 간 교차공분산의 유지가 필요.
4. 기존 mode-switching Gaussian filtering 및 IMM 원리에 기반한다. 그러나 원리의 타당성과 이번 PALO 구현의 성공은 별개.

## Round II — 적대적 리뷰: 실제 코드와 원시 저장 결과를 공격

| 반론/실패 | 직접 근거 | 결론 및 교정 요건 |
|---|---|---|
| 두 가지 보존? | 기존 keep2는 각 부모 ON/OFF 자식을 만들고 현재 posterior 상위 2개를 전역 선택. Full/B0, t≥40의 779시점 중 **459시점(58.92%)에서 모두 OFF**, 두 모드 공존은 320시점(41.08%), 두 ON은 0. k=3도 두 OFF, k=750도 두 OFF. | top-2는 두 모드를 보장하지 않는다. 두 모드의 조건부 posterior를 유지하는 방식으로 변경. |
| 확률질량 유실? | Full/B0 keep2가 매시점 잘라낸 posterior mass는 평균 **0.12038**, 최대 **0.3181** (평가 구간), 평균은 L0 .1202, L1 .1228, L2 .1237. | pruning 후 남은 확률 재정규화는 정규화된 진짜 posterior라고 주장할 수 없음. K=2·4·8 민감도 및 mode-conditioned approximation 평가. |
| MAP1의 OFF 흡수? | stay=.95, bad uniform[-1,1] 밀도 .5, 정상 Rs=.0081의 최대 예측밀도 4.43269. 이전 OFF에서 다음 ON 대 OFF 최대 점수비 = (.05×4.43269)/(.95×.5)=**0.4666<1**. Full의 MAP1은 k=3 이후 OFF에서 복귀 불가. | MAP1은 우연히 약한 게 아니라 설정상 회복 불가능한 잘못된 대조. 이것을 이겼다고 keep2가 좋은 것은 아님. |
| ‘오염’ 모델이 물리적인가? | OFF=Uniform(-1,1)로 측정 자체가 헤딩과 무관함을 가정. 실제 다중경로에서는 FP가 조금이라도 유효할 수 있고, 지속적인 편파 오프셋을 보일 수 있음. | ‘모든 정보 유효 vs 0’ 이분법은 실제 채널을 지나치게 단순화. C모드는 정규화된 넓은/비가우시안 오차분포 또는 지속적 bias 모델로 비교. |
| 가설 확률이 정확도를 알려주는가? | k=483, Full/B0 keep2 잔존 ON 질량 .95897 (OFF .04103). 이는 해당 모델 안의 적합도이지 실제 헤딩 정답 확률이 아님; 기존 S4와 같은 prior도 아님. 과거 rollback에서는 정확한 DROP가 후속 RF 예측 로그점수에서 KEEP에 2/5/10초 모두 패배. | 편파 모델의 예측 가능도만으로 실제 헤딩 보정의 유익함을 보증 불가. 자기확증을 구조상 해결하지 못했다. |
| 이전 정상 likelihood가 맞는가? | R_s=.0081, 매우 좁은 Gaussian, 기존 RF 시계열은 편향·시간상관·공분산 과신. 5Hz 각 프레임을 독립 증거처럼 점수화하면 반복 정보 과신. | 한 스텝 predictive likelihood의 calibration 및 블록 자기상관을 검증하지 않으면 모드확률 미인증. |
| 전이율 stay=.95가 물리적인가? | 0.2초/프레임에서 전이확률 .05는 기하분포 평균 동일모드 20프레임=4초. RF 자료에서 식별/동결한 dwell time이 아니다. | scene/경로 조건에 따른 RF 오염 지속 시간과 모드 전이의 식별 가능성부터 검사; 근거 없는 .95를 ‘확률’로 확정하지 않음. |
| 대조가 공정한가? | 새 filter_hypotheses의 ON 자식은 항상 원래 S4 Gaussian 갱신을 계산하며 **기존 NIS99 게이트를 사용하지 않음**. 따라서 기존 S4 성능과의 차이는 모드 유지 외에 관측 정책 차이도 포함. | 올바른 비교는 동일 emission/전이/게이트를 가진 ‘즉시 축약 vs 두 조건부 posterior’이며, 기존 S4는 외부 기준선으로만 비교. |
| 실제 성능은? | Full B0 S4 1.540°/.308m, keep2 **3.314°/.338m**; Full L2 S4 1.292°/.308m, keep2 **2.977°/.321m**. Full B0 혼합의 heading 95% coverage ≈.307. | 기존 구현은 구조 검증을 통과해도 실제 추정 품질에 실패함. |
| 정보학적 식별이 가능한가? | 선형화된 혁신 ν_k≈H_{p,k}δp_k+H_{ψ,k}δψ_k+c_k+ε_k. 헤딩 감도·위치가 충분히 달라지지 않고 c_k가 지속된다면 δψ와 c는 분리 식별 불가능할 수 있음. | 두 모드만 있다고 구별 정보가 생기지 않는다. 구별 불가 구간을 명시적 결과로 관리하고 손실 위험을 인정해야 함. |

**적대적 리뷰 판정:** 기존 구현의 “두 가설을 보존하면 후속 RF로 올바른 헤딩을 선취할 수 있다”는 논리가 성립하지 않는다. 수학적으로 유효한 혼합분포라는 사실만으로 emitter likelihood가 calibration 되었거나 모드 posterior가 헤딩 보정의 유익성 확률이 되는 것은 아니다. **현재 구현은 V1 FAIL / original hypothesis class not disproven**.

## Round III — 지지층 재검토·양보·수정

### 3-1. 양보해야 할 주장

- “가설을 두 개 유지했으므로 항상 RF ON과 OFF 대안이 살아 있다”: 철회. 실제 459/779 둘 다 OFF.
- “관측 사후 가능도가 높은 가지가 실제 정확한 헤딩이다”: 철회. 상태와 RF 편향의 자기확증 문제.
- “오염되면 RF 정보가 정확히 0이다”: 보편 진술 철회. 명백한 데이터 결손이면 0으로 처리할 수 있으나 일반 Full multipath에는 적용 근거 없음.
- “단일 MAP1 실패가 다른 가설 모델의 근거”: 철회. OFF 흡수는 prior/emission 설계 결함.
- “모드 probability를 직접 ‘유익 보정 확률’로 사용할 수 있다”: 철회. 사후 모드 확률과 보정 utility는 다름.

### 3-2. 남기는 최소 원리

**상태와 확률은 2개의 모드 조건부로 유지**하고, 서로 다른 두 측정 해석의 전체 posterior를 예측 전에 강제로 하나로 합치지 않는다. 처음부터 여러 기능블록을 붙이지 않고, 기존 운동 예측과 RF 측정만 사용한다.

m_k∈{G (normal RF), C (contaminated RF)}. 조건부 상태 분포 p_k^G(x), p_k^C(x). 현재 프레임의 모드 예측은

\[
\pi^-_{j,k}=\sum_{i\in\{G,C\}} T_{ij}\pi_{i,k-1},
\quad
\omega_{i|j,k-1}=\frac{T_{ij}\pi_{i,k-1}}{\pi^-_{j,k}}.
\]

\(\omega_{i|j}\)로 이전 모드 상태·공분산을 **두 번째 모멘트까지** 조건부 혼합하여 각 j의 prior를 만든다(2모드 IMM 근사; 비가우시안/원형량 근사임을 밝힘). 각 모드의 prior에서 동일한 움직임을 전파하되, 예측된 위치·헤딩·bias·P는 독립적으로 유지한다.

**모드에 따라 다른 측정 likelihood**로 증거를 계산한다.

\[
L_{j,k}=\int p(s_k|x,j)\,p^-_{j,k}(x)\,dx,
\qquad
\pi_{j,k}=\frac{L_{j,k}\pi^-_{j,k}}{\sum_\ell L_{\ell,k}\pi^-_{\ell,k}}.
\]

G: 원래 LUT의 정규화된 Gaussian \(\mathcal{N}(s;h(x),R_G)\).
C: 기본 V2-A에서는 **넓지만 정규화된** Gaussian/Student-t 등 한 가지 오염분포 \(\mathcal{E}_C(s-h(x))\)를 실험에 앞서 동결. 단순 Uniform(-1,1)을 유일한 물리적 오염모델로 강제하지 않는다. C에서의 갱신은 오차모형에 맞춰 약하게 처리하거나(상태·P 일관성 보장), 넓은 상태무관 likelihood라면 아예 RF 미수용으로 둔다. 이 둘을 결과에 따라 섞지 않는다.
V2-A가 증거 구분에 실패하면 V2-B 대안으로 **지속적인 RF 오프셋 1개만** 추가: \(s=h(x)+c+\epsilon\), \(c_{k+1}=\rho c_k+\eta_c\). 이때 각 모드의 x–c 교차공분산 및 위치/ψ와 오프셋의 식별성을 검사하고, 수용 기능과 오염항을 동시에 마음대로 조절하지 않는다.

두 조건부 posterior를 계산 중 보존하되, 출력용 혼합분포는
\[
\bar x=\sum_j\pi_j\mu_j,\qquad
P_{\rm mix}=\sum_j\pi_j[P_j+(\mu_j-\bar x)(\mu_j-\bar x)^T]
\]
로 표현. \(\psi\)는 원형 평균·오차. posterior 자체가 별도 모드일 가능성이 있으면 단일 평균만 출력해 불확실성을 지우지 않는다.

**절대 등치하지 말 것:** \(\pi_{G,k}\ne P(\text{이번 헤딩 보정이 유익함}\mid s_{1:k})\). 모드 분류·모드확률 calibration과 실제 Heading/XY 손익 및 그 꼬리 위험은 *별개 검증 목적*이다.

### 3-3. 필터 구현 전에 동결할 4가지 단독 설계 변수

1. G와 C의 likelihood 정의 및 정규화/경계 s∈[-1,1] 처리. 조건·경로별 데이터 평가 전에 동결.
2. T_{ij}: per-frame .95를 그대로 믿지 않고 RF 오염 이벤트 지속성에 맞춘 사전 모형/독립 route 학습. 바이어스·정확도 참값은 online 입력 금지.
3. 조건부 posterior의 근사: 먼저 2-mode IMM, 그리고 **같은 모드모형의 K=2/K=4/K=8 history beam**을 진단 대조해 mode mixing/가지 손실에 따른 차이 확인.
4. 가설별 EKF 갱신과 정보 보존: 균등 C는 상태 정보 0; 넓은 Gaussian C는 작은 K_C로 정보 일부 사용. C의 x/P 갱신은 likelihood와 수학적으로 일치해야 함.

### 3-4. 첫 단계에서 반드시 반증 가능한 검증

- P0: 원래 S4/DR 역사적 exact replay 16/16 PASS. 현재 15/16이므로 과학 성능 CLAIM 전에 재현차 해소. 새로운 모델 계산은 동일 버전의 코드·입력에서 수행.
- P1: synthetic uncontaminated/contaminated with known ground truth; 해석을 교차해 넣어도 posterior 정규화·상태/P 재귀·zero-likelihood·모드 복귀·순서·복제 관측 테스트. Full 초반 k=3에서 반드시 양쪽 모드 posteror 보유; 확률 아주 작아도 표현을 버리지 않는지 확인.
- P2: 실제 저장 R2 Full k=201 및 483–485, R4-A/L2, R5-A/B/L2 같은 대표 사건. 동일 과거 ON/OFF로 실제 참값에서 더 정확한 가지가 살아 있는지 **오프라인 전용** 감사. 적합도/ON posterior와 실제 손익의 상관 및 calibration 별도.
- P3: **원리 ablation** — 동일 emission과 T를 가진 (a) 원래 S4 외부 기준 (b) 단일 robust state (c) 두 모드를 즉시 하나로 축약 (d) 두 모드 분리. d가 c보다 나아야만 ‘가설 보존’의 기여. 비교에서 S4 NIS gate 차이, 관측모형 차이를 섞지 말 것.
- P4: Full/LoS R2/R4/R5 4bias 경로별 Heading·XY·bias RMSE 및 10초 worst-block, q95/99, NEES/95% coverage, 모드복귀시간, 원래 ON 가설 생존율, 계산비용. NIS≤.5/.2는 적대적 실패 대조. R2/R4/R5는 이미 연구된 동일 복도 개발 데이터, 새로운 seed·독립 scene 없이 generalization 주장은 금지.
- P5: RF-only 예측 점수와 실제 상태 손익이 분리될 수 있음을 강제 반례로 유지. **현재 수신 RF만으로 원인 식별이 불가능한 구간은 안전성 검증 FAIL/ABSTAIN**으로 기록하고, 헤딩 진실확률을 발명하지 말 것.

### 최종 재지지층 판정

주개발 후보 ②의 이름을 **“확률적 RF 오염분류기”에서 “두 관측 해석의 상태 이력을 별도로 보존하는 모드 조건부 필터”**로 변경한다. 개선을 약속하지 않으며, 멀티패스 오염과 실제 운동 오류가 구별되지 않는 구간은 알고리즘 한계로 정의한다.
**최초의 구조적 증거 기준:** (a) ON/OFF 조건부 상태 모두 보존 (b) 정상 모드 복귀 가능 (c) 동일 emission/전이에서 즉시축약보다 실제 RMSE·tail·covariance 개선 (d) L2 드리프트 보정 상실 방지.
해당 기준이 충족되지 않으면 2모드 아키텍처를 확대하지 않고, Student-t/일반화 Bayesian 단일 robust filter와 비교하여 복잡도 증가의 정당성을 다시 검토한다.

## Reference provenance

- Full/B0 keep2 구체 데이터는 2026-11-09 선행검증 zip의 S2_full_B0_keep2.npz와 S2_BRANCH_QA.csv에서 원문 수치 재추출; 해당 zip은 로컬 보존이며 **이 GitHub 문서가 코드/원본 데이터를 원격 실행했다고 주장하지 않는다**.
- 기존 GitHub C/D 감사: https://github.com/myoungsunk/sionna-resimulation/blob/1a30b1f44d875d0d5b105584b78d2fb91460c088/research/PALO_MECHANISM_CD_EXEC_20261108/POSTRUN_REVIEW_42453921978_KO.md
- 기존 R2/R4/R5 NIS 고정 게이트: https://github.com/myoungsunk/sionna-resimulation/blob/0e83bd7dbe73f61d79256ee5d140fede60e8e82b/research/PALO_NIS_ROUTE_TRANSFER_20261108/RESULTS_REVIEW_KO.md
- IMM 원리: Blom & Bar-Shalom, “Interacting Multiple Model Algorithm for Systems with Markovian Switching Coefficients,” IEEE TAC, 1988, DOI 10.1109/9.1299.
- Outlier robust filtering 대안: Duran-Martin et al., “Outlier-robust Kalman Filtering through Generalised Bayes,” ICML 2024 (proceedings.mlr.press/v235/duran-martin24a.html).
- Persistent correlated measurement noise 대안: Wang et al., “Outlier-robust Kalman Filter in the Presence of Correlated Measurements,” Signal Processing 193, 108394 (2022).

**판정:** REVISE_V2_CONCEPT / OLD_KEEP2_REJECT / NEW_SCIENCE_NOT_RUN / HISTORICAL_PARITY_HOLD.
