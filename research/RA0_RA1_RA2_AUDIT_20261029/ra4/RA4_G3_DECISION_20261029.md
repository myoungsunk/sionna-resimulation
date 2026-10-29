# RA4 평균·분산·gate 효과 분리 및 G3 25-ray 원자료 게이트

작성 기준 2026-10-29 · 저장소 `myoungsunk/sionna-resimulation`, 브랜치 `audit/ra4-factorial-g3-precision-20261029`.

## 판정
- **RA4 원본 점수표 분해: PASS_RETROSPECTIVE_SOURCE_392**, 실제 검산 [#40859618029](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859618029).
- **RA4 새 336-arm 전수 자기-gate / PRIOR 의미론 비교: 별도 workflow 실행. 완성본 및 독립 검증 전 결과 주장 금지.** 기존 역사적 효과 분해와 구분.
- **G3 25개 원시 ray의 물리적 원인: BLOCKED_ORIGINAL_RAW_TAU.** [숫자 경계 실험 #40858412070](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40858412070), 23개 SHA-고정 receipt 검증.
- **H 국소 수정 결정: NOT_JUSTIFIED_BY_G3_ALONE / CONDITIONAL_ON_PHYSICAL_RAY_RECONCILIATION.** H가 반드시 정확하다는 뜻이 아님.
- 역할별 작성/검산은 같은 ChatGPT 세션 안에서 수행됨: **SELF_REVIEW_ONLY**, independent scientific release 불가.

## MB_VAR 실행 명명 통일
- 원 `pol_bias_model/exp_pb.py::run`: 분산 조회 전 상태는 **이전 posterior**. `MB_VAR_LEGACY`로 고정. `BB_VAR_LEGACY`도 같은 의미.
- 변형: predict 후 `rho(x_k^-)`에서 분산 조회 = `MB_VAR_PRIOR`/`BB_VAR_PRIOR`. 같은 `MB_VAR`라는 이름으로 소급 혼용 금지. 원래 RA3 56 arm 재검산에서는 수정 전·후 개선/미개선 방향 0/28 변화, 실제 RMSE 수치는 변함.
- `BB_ORIG` vs `MB_ORIG`는 packet-aligned `mu_B` vs `mu_M` 배경 평균 변화. `BB_VAR` vs `BB_ORIG`는 동일 평균 하 `R_{ss}` 증대. `MB_VAR` vs `BB_ORIG`는 평균과 분산의 **결합 결과**, 어느 단일 항의 개선으로 주장 금지.
- `BASE_FIXED`는 BB_ORIG의 NIS accept-mask를 모든 arm에 재사용한 분석 통제군; `SELF_NIS`는 각 arm 자신의 gate를 계산한다. `mu`는 archived packet-keyed 자료이므로 SELF_NIS만으로 실제 온라인 deployability 검증 완료가 아님.

## 원 392행 통계 (28 correlated condition rows, 7 case/mount variants in 1 corridor)
| 개입 (BB_ORIG 대비) | Heading 개선 | XY 개선 | Mean ΔHeading (deg) | Mean ΔXY (cm) |
|---|---:|---:|---:|---:|
| `MB_ORIG` 평균만 | 9/28 | 17/28 | +0.03408 | −0.59518 |
| `BB_VAR_LEGACY` 분산만 | 20/28 | 12/28 | −0.02048 | +0.99389 |
| `MB_VAR_LEGACY` 둘 다 | 23/28 | 20/28 | −0.04540 | −1.02426 |

상호작용 `Y11−Y10−Y01+Y00`의 condition-average는 Heading −0.05900°, XY −1.42298 cm. 이는 비선형 estimator의 관측 RMSE 대비 계산된 interaction이며 각 물리 요소의 additivity 또는 통계적 유의성 증명이 아님. 특히 `R2_aA_m45` B0에서는 두 지표가 모두 악화한다.

이전 별도 D2 자기-gate 진단은 24/24조건에서 `MB_VAR`이 fixed 대비 Heading/XY 동시 악화, 추가 수용 8–47 packet; 이는 **24개 과거 데이터**이지 RA4의 새로운 28개 전수 자기-gate 결과가 아니다.

증거: [SHA-고정 28조건 factor 원장](RA4_HISTORICAL_2X2_EFFECTS.json), [독립 stdlib auditor](ra4_historical_auditor.py), [RA4 정의 계약](RA4_CONTRACT.md), 기존 `PB_SCORES.csv` blob `10cab3f8ab2a08750669877f80f60a055e1b605d`.

## G3 25개 raw ray 수치 검사
- Original file receipts 23/23 SHA 검증; 원 strict 초과 ray 합 25개. **실제 offending raw tau는 25/25 미확보** (별도 R2-A는 확보됨).
- 원 image-method 후보를 실제 원 receipt x/y에서 재계산 후 float32로 *최종 1회 캐스팅*했을 때 최대 오차 **1.01464×10⁻¹⁴초**, strict **5×10⁻¹⁴초**보다 작다. 단순 최종 float32 변환만으로 엄밀 초과를 설명할 수 없음.
- timeline-source 좌표 차이 지연 영향 상한 **1.99674×10⁻¹⁵초**. 이것만으로도 엄밀 초과 설명 불가.
- 23/23 위치에는 `TIE_S=10⁻¹³초` class 병합으로 엄밀 초과가 발생할 수 있는 **후보**가 있으나, 원 25개의 path index와 tau를 알 수 없으므로 실제 원인 배정 불가.
- Sionna 내부 누적 정밀도/경로 유효성/반사 순서/경로 solver 문제는 여전히 `UNKNOWN`. 단순 오차 상한이 작다고 모든 H가 물리적으로 옳다고 단정 금지.

증거: [23개 원 receipt 수치 검사](g3/../g3/g3_numeric_bounds.py), [원 original_relpath 23개와 receipt SHA 동결](../g3/G3_23_ORIGINAL_SOURCE_LOCK.json), [원시 데이터 요청](../g3/REQUEST_25_ORIGINAL_RAW_RAYS.md).

## H 수정과 재실행의 두 단계 gate
1. **검사기-only 결함** (`stations=0` PASS 수정, 경로 중복 class attribution 수정): 원 H/Jones/packet은 그대로 — 기존 BB/MB_VAR H 기반 성능 재실행 필요 없음.
2. **국소 원 ray tau/Jones 물리 오류가 실제 확인됨**: 23 원 NPZ를 확보해 trace→H row parity 재구성. 필요한 24 trace 위치의 2 mount 합계 **최대 48 H row**는 *국소 교정 가정에서만* 상한. 원래 H/packet과 차이가 없는 row는 필터에 영향 없으며 수정하지 않음. 관측이 달라진 case에서는 최초 변경 시점 이전 checkpoint부터 끝까지 EKF state/P/mask를 재생하고 성능 분모·누락 로그를 재집계.
3. **source solver/재질/FFD/주파수 공통 오류가 확인됨**: 48행 상한은 무효. 원 H 전체 12 store/16,432 row source-/bit-/numerical-diff 검사와 upstream 학습 모델 fit 영향 감사가 선행. `mu_B,mu_M,R`를 다른 route에 대한 LORO fold로 재적합해야 하면 데이터 영향은 direct changed packet의 7 case 외 다른 fold까지 전파 가능. 사전 H/packet/fit/source SHA 재동결 없이 BB/MB_VAR 실험 수치 소급 수정 금지.
4. **원 source H의 정확성을 입증하기 전** `physical G3 PASSED`, `H_PHYSICALLY_VALID`, `25-ray_ROOT_CAUSE_PROVEN` 주장 금지.

## 요구한 최소 추가 데이터
[23 original trace NPZ + 대응 receipt 23개 요청서](../g3/REQUEST_25_ORIGINAL_RAW_RAYS.md)를 참조. 원본 위치 `SNOWBALL_ROUTES_01a11669/results/S2/traces_R2_aB`, `traces_R4_aA`, `traces_R4_aB`, `traces_R5_aA`, `traces_R5_aB` 중 지정된 23개 tag. 기존 GitHub와 Google Drive 명칭 검색에서 원 23 NPZ를 확인하지 못했다. 제공 가능하면 [검증용 ZIP 패키저](../g3/package_g3_23.py)를 이용해 `G3_ORIGINAL_23_TRACE_PAIRS.zip`으로 전달. original raw SHA가 published package에 없어 receipt SHA 외 반드시 H 재합성 비교 필요.

## 역할과 인계
- PROPOSER: `RA4_CONTRACT.md`에서 2(mean)×3(variance)×2(gate) 및 검증 경계를 사전 고정.
- IMPLEMENTER: 392행 2×2 factor 계산 + 24 과거 self gate, SHA 검증과 fail-close; 새 336-arm 코드는 별도 관측 증거/테스트 후만 승격.
- AUDITOR: 독립 표준 라이브러리 계산 프로그램으로 392행/56 metric contrasts/24 gate와 identity/원본 blob SHA 검증, G3 raw 25개 누락 공개. **실행 경로는 분리되어도 독립 감사인/세션이 아니므로 `SELF_REVIEW_ONLY`**.
