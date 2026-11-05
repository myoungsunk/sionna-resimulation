# FP-SC-DYNAMIC-MAPPING-R1 — 결과 전 동결 계약

기준 커밋 f1f2b4a641aaf8f6498e9d190328627ccd31d14c. 역할 PROPOSER → IMPLEMENTER → 자체검사.
사용자 지시: 동적 mapping 기준 동결 및 로컬 검증, static 48개 준비, GitHub 게시.
E1-02/E2 실행 금지. 원래 E1 실패, VAB 주안, reach 기술 수용을 보존한다.
이 계약을 커밋한 후에만 실제 SourceFFD mapping을 계산한다. 결과에 따른 기준 변경은 금지한다.

## 대상과 고정 recipe

- 기존 canonical 6개 case, R2/R4/R5 × B0 × Full/Native_LoS, 총 6,272개 측정 전 prior/Pprior.
- 원본 모델·FFD bank, source SHA, 주파수 257개·RX 순서·Hann·1028 FFT를 유지한다.
- 7점 중심/±고유축, sigma scale=2, mapping slack=0.15m, 최대 유효 폭=1.5m.
- VAB/TWO_PORT_UNION 유지. 후보 생성·select·detect·EKF replay를 실제 RF에 실행하지 않는다.
- raw/reference tap은 관측/평가용 기존 strongest-RX 30% receiver로만 계산한다.
  truth/LoS는 mapping 입력에 넣지 않고 평가 시에만 사용한다.
- 로컬 Windows Python 3.13.15 / NumPy 2.2.4 / SciPy 1.15.2. 이전 Linux 환경과 구분한다.
  논리 CPU 최대 3개, 계산 라이브러리 스레드 1개. runtime 차이를 숨긴 exact Linux 재현 주장은 금지한다.

## 수용 기준

| 관문 | 결과 전 고정 기준 |
|---|---|
| G0 정체성·분모 | 원본/모델 SHA 일치, 6,272행 exact join, 중복·누락·비유한 0 |
| G1 구현·수학 | 생산 native_support와 독립 batch 집계의 endpoint 차이 ≤1e-10m; 영 공분산, yaw±2π, 순서·중복·비유한/비PSD 거부, 인과성 합성 검사 통과 |
| G2 유한 probe domain | 모든 packet에서 추가 20방향 probe의 envelope 외부 거리 ≤1e-10m. 1건이라도 초과하면 FAIL. 최대·전수 반례 저장 |
| G3 참조 활용 가능성 | route × channel × {normal,one_tap,large_error}의 각 비어 있지 않은 층에서 `참조 포함 AND 폭≤1.5m` / valid-reference ≥0.95. 전체도 동일. 빈 층은 NOT_TESTED |
| G4 음성대조 완전성 | 아래 7개 stress × 6,272개 =43,904행, 누락·비유한 0, width-HOLD/좁지만 참조 배제/포함 전부 공개. 성공률 기준을 사후 추가하지 않음 |
| G5 static 준비 | 24조건 × Full/Native_LoS=48개 canonical, 원본 스펙트럼 exact 일치, 참조 분리, 가짜 time/prior/controls 없음, static C-only loader와 차단 합성 검사 통과 |

G3의 95%는 기존 후보 가용성 목표와 일관되게 이 준비 단계에 새로 정한 개발 데이터
실용성 요구치다. 신뢰수준/보장 확률이 아니다. 폭이 넓어 HOLD된 행도 분모에 남겨 성공에서 제외한다.
invalid raw/reference는 별도 분모로 모두 기록한다. 정상 n0=nL, one=|n0-nL|=1,
large=|n0-nL|≥2를 유지한다. reference 유효하지만 raw invalid이면 별도 층으로 공개한다.

## probe와 음성대조

P[:3,:3]=U diag(λ) Uᵀ, A=U diag(sqrt(max(λ,0))).
기존 7점은 x 및 x±2A e_i. 추가 probe는 d∈{-1,0,1}³에서 nonzero 성분이
2개 또는 3개인 20개 방향의 x+2A d/||d||. gyro-bias 상태는 변경하지 않는다.
연속 타원체 전체의 보장으로 해석하지 않는다. 고유축 부호 변경은 방향 집합을 바꾸지 않는다.

stress는 (dx,dy,dyaw,cov_scale):
(0,0,0,0.01), (±0.5m,0,0,0.01), (0,±0.5m,0,0.01), (0,0,±15deg,0.01).
모든 prior에서 기존 7점 recipe를 다시 평가한다. nominal과 별도 기록하고 제안값을 재조정하지 않는다.
이 out-of-domain 음성대조는 잘못된 prior로 생기는 좁은 잘못된 구간을 드러내기 위한 것이다.
G4 통과는 그 위험의 해소가 아니라 전수 기록의 완전성이다. 잘못된 prior 보호는 후속 별도 관문이다.

## 실행·검산·판정

각 행은 입력 identity, low/high/width, native 중심 tap/range·geometry·offset,
probe 최대/최소·초과량, raw/reference tap·층, HOLD, stress 결과를 남긴다.
고정 source를 재계산하는 구현과 CSV만으로 판정을 재집계하는 자체 checker를 분리한다.
동일 작업자이므로 독립 감사라고 부르지 않는다. native_support 함수가 쓰는 7점을 캡처해
모델 batch에 묶어 보낸 후 생산 함수를 replay하여 원형 recipe와 동일한지 전 행 대조한다.
모델의 continuous surrogate와 native detector range는 별개로 취급한다.

G0/G1 구조 실패는 본 계산을 중단한다. G2/G3 수치 실패는 반례를 숨기지 않도록 전수를 마친다.
실행·수치·기술 수용·과학적 채택을 분리한다. 모든 수치 관문이 통과해도
NUMERICAL_PASS_REVIEW_HOLD만 기록한다. PASS_DYNAMIC_MAPPING_REVIEW나 실행 승인으로 자동 승격하지 않는다.
실패는 FAIL_FROZEN_MAPPING_R1로 보존하고, 수정하려면 새로운 버전·계약·별도 재검증이 필요하다.
