# VAB 후보–후속 선택기 연결: 소스 분석 및 검증 제안

상태: PROPOSAL / 코드 변경·선택기 실행·E2 실행 없음. 역할 PROPOSER, 질문 FP-SC-SELECTOR-BRIDGE-R1: VAB가 인정한 후보를 의미 손실 없이 전달하면서 선택 안전성을 별도로 검증하려면 무엇이 필요한가?

## 근거와 적용 범위

- E1 결과 기준: 0df23a953bb3a3bb98133d07ed0271d7832528b0, implement/fp-sc-001-e1-run-20261105. 분석 시 로컬 HEAD 확인.
- 후속 코드: Git 객체 486f0b6c008e7a953ada75a03a941ffa46994985의 followup 소스를 git show로 직접 확인. 이 문서는 해당 버전에 대한 분석이며 GitHub의 최신 버전이라고 주장하지 않는다. 현재 E1 checkout에 후속 코드를 합치거나 설치하지 않았다.
- VAB 코드: src/qclean_uwb/fp_sc/candidate_revision.py. 기존 E1 실패와 R1 50,560행 결과는 그대로 보존.
- 적용 지침: 로컬 RESEARCH-GOVERNANCE-v1 COMMON_CONTRACT SHA256 a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb; ROLE_PROPOSER SHA256 e7c4e6efa050448fc1624c9fe28c227b948631f189531ce75c7c6c0a695bc53e. 저장소 MBVAR-INFO 전용 라우팅은 이 질문에 적용하지 않는다.
- 소스 검토는 동일 작업자 분석이며 독립 감사가 아니다. 아래 검증은 계획이고 아직 실행하지 않았다.

## 확인된 연결 단절

1. followup/engine.py의 OriginalAdapter는 candidates.generate_candidates를 가져온다. evidence(cir, variance)는 기존 생성기를 부르고 from_pool로 변환한다. generate_revision(..., 'VAB')는 호출하지 않는다. 따라서 E1 R1 완료만으로 운영 경로가 VAB로 바뀌지 않는다.
2. selection.py:53–75의 from_pool은 support_records를 `max[min(1,prominence/G) exp(-|tap-edge|)]`라는 단일 support로 압축한다. VAB의 support_kind, left_rise, candidate_revision, candidate_config_sha256, support_semantics_version은 Evidence에 전달되지 않는다. lobe/RX별 출처도 groups 외에는 사라진다.
3. selection.py:150의 선택 자격은 supported AND support>=0.15다. 모든 지지 edge에서 2 tap 이상 떨어진 후보는 support<=exp(-2)=0.135335이므로 반드시 탈락한다. 단, 다른 지지 edge가 가까우면 탈락하지 않을 수 있다. prominence/G=0.10이면 edge 자체에서도 탈락한다. 이는 생성 문턱 0.06과도 별개다.
4. VAB가 LEFT_RISE로 인정한 봉우리도 adapter는 낮은 양측 prominence만 사용한다. 구제된 후보가 다시 자격에서 빠질 수 있다. 실제 87개 또는 누락 8개 중 몇 개가 재탈락하는지는 이번 소스 검토만으로 확정하지 않는다.
5. selection.py:157–170은 전체 후보 1·2위 tap margin과 다른 group의 margin 모두에 같은 Policy.margin을 적용한다. 상승 구간 내 이웃 tap이 늘면 같은 봉우리 내부의 경쟁만으로 ABSTAIN_AMBIGUOUS가 늘 수 있다. 이는 예상 영향이며 현 corpus에서 증가량을 측정한 것은 아니다. group은 겹치는 basin의 연결 성분이므로 물리 경로와 동일하지 않다. R1에서 발생한 group 병합도 반영해야 한다.
6. selection.py:217–230 TrustedHistory.observe도 support>=min_support를 재사용한다. 선발 자격만 바꿔서는 이력 bootstrap 연결이 해결되지 않는다. 반대로 VAB supported만으로 이력을 신뢰하면 잘못된 선택의 자기강화 위험이 생긴다.
7. rf=-log(max(support,1e-12))는 raw에도 적용된다. raw-only fallback의 support=0이면 큰 wrong/gain이 생길 수 있다. 지원 부족을 원본 오류의 강한 증거와 동일시하지 않도록 별도 진단해야 한다. 기존 구조에서도 존재하는 문제이며 VAB의 신규 결함이라고 단정하지 않는다.
8. Evidence는 모든 signed_s를 float로 받지만 생성기는 polarization_valid=false에서 signed_s=None을 남길 수 있다. 명시적 invalid/hold 변환이 필요하다. 현재 50,560행에서 실제 예외가 났다는 의미는 아니다. candidate_revision도 현재 V0/invalid early-return에서는 생략되므로 명시적 envelope에서 버전을 결속해야 한다.
9. contracts.Policy.sha는 수치 정책만 결속하고, numerics의 residual model 검사는 policy_sha/extractor/domain 등을 검사한다. 같은 수치 정책으로 후보·점수 의미만 바꿨을 때까지 동일 모델로 취급하지 않도록 식별자를 확장해야 한다. 기존 readiness/adopt_e1은 원래 E1-01 receipt와 HOLD를 다루므로 R1 결과를 여기에 PASS로 덮어쓸 수 없다.

## 권고 수정 범위

|위치|수정 제안|유지 사항|
|---|---|---|
|engine.OriginalAdapter|generator revision/arm/mode를 명시적으로 주입. VAB와 두 모드를 명시 선택; V0 경로 유지|원본 CIR 변환·noise variance·raw detector·B0/B37 유지|
|selection.Candidate/Evidence/from_pool|cir_supported, selection_eligible, rf_score, history_trust_eligible 분리. lobe/RX/support_kind/left_rise/group provenance 및 버전 envelope 전달|tap·signed_s·raw·pool hash·overflow 정확 보존|
|selection.select|CIR 자격과 순위 계산 분리. 거리 감쇠를 자격 문턱으로 사용하지 않음. raw 지원 부족과 wrongness 구분|invalid/overflow hold, prior/history hold 및 기존 안전 관문을 임의로 완화하지 않음|
|Policy 및 Decision|tap_margin/group_margin 별도 이름·의미·설정. 각 점수와 자격 제외 사유 기록|동점이면 작은 tap이라는 구현 규칙을 과학적 확신으로 해석하지 않음|
|TrustedHistory|선택 여부와 별도의 이력 신뢰 조건, bootstrap/age/motion 검사; 버전 변경 시 기존 이력 무효화|현재 시각 이전 정보만 사용, 참조·미래·posterior 누출 금지|
|contracts/readiness/study/numerics|candidate revision/config, support semantics, selector recipe, mapping recipe를 execution identity로 결속; residual model도 일치 요구|기존 실패·HOLD·모델 보존, E2 자동 GO 금지|

### 점수식은 어떻게 다룰 것인가

우선 연결 자격은 `valid AND NOT overflow AND polarization_valid AND cir_supported`로 정의하는 안을 권고한다. 이는 교체 승인 조건이 아니라 순위 계산에 들어갈 자격이다. 순위·교체·이력은 별도다. raw fallback은 지원이 없어도 KEEP 대상에 보존한다.

거리 감쇠를 제거하고 support_kind를 반영하는 구체적 RF 순위 초안은 다음과 같다. G는 기존 전체 CIR peak, A는 해당 RX의 tap 진폭, H는 해당 lobe peak다.

`b_l = prominence_l (BILATERAL), left_rise_l (LEFT_RISE)`

`q(n) = max_l [clip(b_l/G,0,1) * clip(A(n,rx_l)/H_l,0,1)]`

`rf_cost(n) = -log(max(q(n),epsilon))`

이는 검증할 초안이지 확정·보정된 신뢰도나 확률이 아니다. peak 선호가 생겨 앞쪽 참조를 밀어낼 가능성, 양측 prominence와 left-rise의 비동등성, 약한 RX의 억제를 반드시 검증해야 한다. q>=0.15를 새 자격 문턱으로 되붙이지 않는다. 이 점수를 택하더라도 기존 wrong_cut/replace_gain/margin을 그대로 과학적으로 유효하다고 간주할 수 없다.

권고 구조는 먼저 group별 최선 후보를 비교하고, 선택된 group 내부에서 tap 식별성을 따로 평가하는 것이다. group_margin만 통과했다고 exact tap을 강제 선택하지 않는다. 내부 식별성이 낮으면 KEEP/ABSTAIN 또는 명시적 tap 불확실성으로 남긴다. 탭별 후보가 늘었다는 이유로 margin 검사를 삭제하지 않는다. 구체 문턱과 raw wrongness 대체식은 본 실행 전 별도 동결 대상이다.

## 검증 순서와 중단 조건 — 모두 미실행 계획

### 1. 소스·스키마 연결 검사 (E2 아님)

- 두 버전의 정확한 SHA를 결속하고 기존 generator+legacy adapter 경로가 기존 출력을 재현하는지 확인한다.
- VAB 12,640 packet-mode행의 tap, supported, raw, signed_s, overflow 및 group/lobe 관계가 변환 전후 정확히 보존되는지 검사한다. V0/VA/VB/VAB 전체 50,560행은 대조 진단으로 동일 변환 검사한다. 새 RF는 생성하지 않는다.
- invalid/zero/nonfinite/overflow/raw-only/한 RX null/polarization denominator 실패를 명시적 hold 또는 contract error로 처리하고 float(None) 같은 우발 예외를 금지한다.
- 후보 또는 의미 버전·해시·모드 불일치와 누락은 fail closed. 무음 V0 fallback 금지. V0를 의도한 경우만 legacy 경로 허용.
- 통과 조건: 누락·추가·중복·수치/출처 불일치 0; 기존 B0 raw 출력 변화 0. 실패 시 다음 검사 중지.

### 2. 합성 반례 검사 (선택기 연결 단위 검사)

- 강한 edge+2/+3 후보, 낮은 bilateral/높은 left-rise, noise-only, 단일 RX null, 두 RX 중복 지지, plateau, boundary, 64/65개 경계.
- 같은 lobe 이웃 tap 동점, 서로 다른 group 경쟁, 연결 성분 병합/다중 lobe, 단일 후보. 단일 후보에 무한 confidence를 만들지 않는다.
- raw 지원 부족만으로 강제 정정하지 않음; prior와 motion의 충돌 및 missing/stale history에서 hold 유지.
- 합성 시간열에서 신뢰 불충분 후보가 history bootstrap을 만들지 않음, 중복/역순/지연에서 이력 오염 없음. 점수 스케일 변화가 history 허가를 우회하지 않음.
- 검산은 별도 scalar 수식과 손계산 예제를 사용한다. wrapper 재호출만으로 독립 검산이라 부르지 않는다.

### 3. 전체 기존 corpus의 비재귀 연결 진단 (별도 승인 후, E2 아님)

- 데이터/변환/모드/분모를 E1 R1과 고정하고 50,560행에 대해 `generated → CIR-supported → legacy-score-eligible → revised-eligible`를 기록한다. 이 단계에서는 select/open_loop/ArmProcessor를 호출하거나 상태·이력을 갱신하지 않는다.
- ref label은 adapter 출력 고정 후 별도 평가기에만 join한다. 모든 파형을 평가하고 누락 8건만 튜닝하지 않는다.
- 참조의 각 단계 생존 여부, 제외 이유, 지원 RX/kind/edge 거리, 정상·오류별 후보 수 및 group 병합·시간·메모리를 공개한다. VAB 전체87/R2 19/R4 14/R5 54 분모를 그대로 확인한다.
- 명시한 자격 정의를 채택할 경우 기존 VAB usable-supported 참조는 새 자격에도 100% 남아야 한다. 이것은 연결 무손실 검사이며 선택 성공 기준이 아니다. 안전 필터를 더 추가한다면 분모와 제외를 따로 기록하고 계약을 사전에 수정한다.
- VAB 주안 유지. VA/VB가 좋아 보여도 사후 교체하지 않는다. 이번 6,320파형은 모두 노출 개발 데이터다.

### 4. 선택 안전성 검증 (향후 별도 단계, 이번에는 미실행)

- 먼저 새 점수·raw wrongness·tap/group margin·이력 조건과 calibration 분할/정책 선택 규칙을 동결한다. 기존 27개 grid에 새 수치를 무한 추가하지 않는다.
- 고정된 이전시각 prior 아래 비재귀 선택을 먼저 검사하고, 이후에만 self-history 영향 검사를 설계한다. 기존 성공의 신규 오정정, wrong→correct, correct→wrong, abstain, 참조 후보는 있으나 미선택인 경우를 경로/모드별 공개한다.
- 개발 보호 관문 초안은 기존 usable-reference 성공의 신규 오정정 0이며, 만족하지 못하면 채택 HOLD로 남긴다. 가용성 95% 또는 100%를 선택 정확도 목표로 재사용하지 않는다. 정책 수정 후 같은 노출 corpus 재통과만으로 일반화 주장 금지.
- E2에 속하는 open_loop/recursive study나 downstream model 실행은 새 승인 전 금지. 인터페이스 검사 통과는 E2_GO가 아니다. 기존 residual model은 새 의미에 자동 재사용하지 않는다.

## 결론

최소 수정은 import 교체가 아니라 생성기 선택, 의미 보존 adapter, 자격/점수 분리, margin/이력 규칙, 버전 결속의 다섯 연결이다. 현재 확정 가능한 것은 기존 adapter와 VAB 의미가 맞지 않는다는 코드 근거다. 실제 추가 후보가 얼마나 선택되고 FP/EKF가 개선되는지는 미검증이며, 이 문서로 E1 실패를 변경하거나 E2를 시작하지 않는다.
