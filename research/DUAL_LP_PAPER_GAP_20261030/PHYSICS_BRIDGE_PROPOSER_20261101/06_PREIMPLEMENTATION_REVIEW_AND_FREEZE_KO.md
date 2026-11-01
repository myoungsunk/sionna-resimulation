# 구현 전 감사·동결 준비표

2026-11-01 · contract `DLP-PHYS-BRIDGE-012-001` · 작성 역할 PROPOSER

## 1. 현재 준비 상태

| 항목 | 이번 제출 상태 | 의미 |
|---|---|---|
| 연구 범위/주 결과/비교군 | PROPOSER_DEFINED | 세 B-route·12조건·현재 MB_VAR 유지 |
| 물리/갱신/거리조건 검증 절차 | PROPOSER_DEFINED | 02의 PB0–PB5 |
| 실험 수치 설정 | PROPOSED_VALUES_FIXED_IN_DRAFT | CONFIG_PROPOSED.json; 결과 보기 전 개정 가능하지만 기록 필요 |
| Git source reference | REFERENCE_PINNED | 원고/진단/role 파일 full commit와 blob |
| 실제 모든 H/controls/FFD/weights byte SHA | NOT_MATERIALIZED_IN_THIS_TASK | 후속 source preflight 필요 |
| 구현 모듈·테스트 실행 | NOT_RUN | 사용자가 다른 객체에게 위임할 범위 |
| 독립 pre-run auditor | NOT_ASSIGNED | 어떤 승인 서명도 대신하지 않음 |
| contract freeze | NOT_FROZEN | 문서 checksum은 무결성일 뿐 scientific freeze 아님 |
| 새 필터/RT 결과 | NOT_RUN | 기존 수치 외 새 결과 없음 |
| 원고 v5 적용 | PLAN_ONLY | 원고 v4 파일은 그대로 유지 |

## 2. 독립 검토자가 확인할 질문

실제 감사자는 actor/session/runner와 공유 helper를 기록해야 한다. 이 목록을 작성한 것 자체가 auditor verdict는 아니다.

### 설계/수학

- 포트 power derivative와 gain-column 축소식을 구현자 helper 없이 독립 유도한다.
- range mean 교체의 same-prior state difference가 −K[:,r]Δμr인지 검산한다.
- 공통 복소 scalar 불변성이 어디까지 성립하는지, frequency-selective common filter에 잘못 확장하지 않았는지 확인한다.
- GT sensitivity, prior sensitivity, inverse-angle diagnostic, nuisance-marginal information의 조건이 분리됐는지 확인한다.
- xprior뿐 아니라 직전 posterior lookup state까지 동일해야 same-prior 2×2가 되는지 확인한다.
- mean/variance factorial의 최종 RMSE 상호작용과 고유 causal percentage를 구분한다.

### 데이터/통계

- 범위가 정확히 R2_aB_m0/R4_aB_m0/R5_aB_m0×B0/L0/L1/L2인지, R4-B를 제외하지 않았는지 확인한다.
- 학습예측 μM, 기존 RB, original state/control, extractor/SourceFFD hash가 실제로 동일 계보인지 확인한다.
- Table1 accepted t≥30, Table2 full-axis, 거리별 ungated t≥30를 합치지 않는지 확인한다.
- 상수는 평가 route 제외한 두 source route B0 lookup에서 sigma²의 route-balanced 평균으로 계산됐는지 확인한다.
- raw/conditioned/gain-projected ACF의 의미가 다르고, packet·gyro를 독립 RF 환경으로 계산하지 않았는지 확인한다.
- 이미 분석된 결과·선택한12조건을 독립 prospective validation으로 다시 명명하지 않았는지 확인한다.

### 실행/원고

- 원본 parity와 음성 시험이 끝나기 전 결과를 승인하지 않는다.
- source-fail, branch-switch, sparse bin, nonfinite, missing field를 명시적으로 보존하는지 확인한다.
- weak denominator 또는 tap change를 silent clamp로 숨기지 않는다.
- 비교에 추가 eligibility가 생기면 fixed라고 이름 붙여도 실제 mask가 다름을 명시한다.
- 새 source h/새 σ/새 observer로 기존 성능표를 소급 해석하지 않는다.
- CI green과 independent scientific verdict를 분리한다.

## 3. 동결 절차 — 순환 승인 방지

1. 별도 실행 위임을 받은 IMPLEMENTER가 PB0 입력·source inventories를 채우고 missing 항목을 보고한다. scientific effects는 아직 계산하지 않는다.
2. PROPOSER가 과학 의미에 영향을 주는 입력/lookup/fold/tolerance 해석을 확정하고 `v0.2_FREEZE_CANDIDATE`를 새 파일로 낸다. 이번 v0.1을 덮어쓰지 않는다.
3. 독립 reviewer가 candidate SHA와 source lock SHA를 대상으로 `ACCEPT_WITH_BOUNDARIES / REVISION_REQUIRED / REDESIGN_REQUIRED / BLOCKED_EVIDENCE` 중 판정한다. 리뷰 시 candidate가 아직 FROZEN이 아님을 이유로 무한 순환시키지 않는다. acceptance는 지정 checksum에 대한 pre-run review다.
4. Proposer·auditor가 같은 candidate 및 input/config checksum을 가리키는 별도 서명 기록을 남긴 때에만 `FROZEN_FOR_PB1_PB3`를 선언한다. 새 RT나 optional ablation은 이 권한에 포함되지 않는다.
5. 구현자는 signed scope에서만 실행하고, 결과를 바꿀 수 있는 변경은 AMENDMENT-xxx에 기록한다. 산출물 serialization 수정과 연구 규약 변경을 구분한다.
6. post-run 독립 감사가 raw 근거를 재검산한 후 04의 claim ledger를 승인하거나 제한한다.

## 4. 수신 객체의 최소 응답

`role, actor/session, contract_id, candidate_or_frozen_contract_hash, input_lock_hash, config_hash, source_sha, allowed_phase, unresolved_items, files_to_change, files_protected, run_plan, budget_RT=0`.

현재 package의 plain metadata/CSV/Markdown은 새 실험 실행용 코드가 아니다. 기존 검토 패키지 안의 재집계 스크립트가 제공되는 경우에도 역사적 참고자료이며 실행 승인으로 해석하지 않는다.

**서명:** PROPOSER=DRAFT_AUTHOR_ONLY; IMPLEMENTER=UNASSIGNED; AUDITOR=PENDING. 어떤 문서에도 이미 수행하지 않은 독립감사를 PASS로 적지 않는다.
