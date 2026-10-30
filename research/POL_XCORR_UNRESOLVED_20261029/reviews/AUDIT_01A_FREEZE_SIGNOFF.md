# AUDIT-01A — pre-run auditor sign-off on contract v1.0 (SELF_REVIEW_ONLY)

- 대상: `contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md` sha256 **`c36c1c56d4db59d39ea85e1d87c1efe622325730a6b4fbc595fc95e583cde219`**
- config: `config/PLAN_PARAMETERS_v1.0.json` sha256 **`a16e8226f2766f4188c144228f99276c0102532667eb1e46816c0b4e0ff42658`**
- spec: `SCIENCE_SPEC_v0.3.md` `5db75dcc…8450` · governance `d5f84d9d…` · base `250d617a…`
- 선행 감사: `reviews/AUDIT_01.md` (`cdedafef…e9a`), 판정 `REVISION_REQUIRED`
- auditor: Claude (Opus 5.5), session `session_01X1n7vLtVgpf8CKd7wVoL2f`, 2026-10-30 KST — **SELF_REVIEW_ONLY** (같은 세션이 v0.1·v0.2 설계와 v1.0 freeze delta를 작성했다)

## AUDIT-01 blocking 항목 처리 확인

| ID | AUDIT-01 내용 | v1.0 처리 | 감사 확인 |
|---|---|---|---|
| AF-1 | contract sha·서명 미기록 | 위 sha를 이 문서와 `FREEZE_RECORD_v1.0.md`에 기록, proposer 서명(사용자 승인) | RESOLVED |
| AF-2 | F-11 미수행 | Actions [40983557008](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40983557008), [40984998584](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40984998584) — 실제 drive block 구조 + 합성 label·feature, 시나리오별 300 rep, B = 2000. label 없는 G5 상관길이 추정(중앙값 0.96 m) | RESOLVED (해석 경계는 아래) |
| AF-3 | 독립 서명 부재 | 미해결. v1.0 D5가 P1/P2 시작을 사용자 지시 또는 독립 pre-run 서명에 묶고, 모든 결과를 TECHNICAL_QA_ONLY로 제한 | **OPEN** — 이 서명은 AF-3을 해소하지 않는다 |
| AF-4 | R-13b 만료 | `evidence/r13b_run_40983557008/`: key+G5 추출본, 원 sha `6a69a36a…`, label 8열 제외 | RESOLVED |
| AF-5 | governance commit 추적성 | tag push가 이 세션에서 403 → 보존 branch `governance/pol-xcorr-router-d5f84d9d` = `d5f84d9d` | RESOLVED (branch 방식) |
| AF-6 | mount·WEAK_PORT 층별 보고 | D3 | RESOLVED |
| AF-7 | E1-ctrl 요구 철회 | D4는 선택적 secondary | RESOLVED |

## v1.0 delta에 대한 감사 판단

- **D1 (pooled 주 판정):**
  - 동결 전 label 없는 합성 근거로 정했으므로 사전등록 규칙에 맞다.
  - Δ = 0에서 pooled type-I은 최대 0.013(ℓ = 2 m)으로, 일측 2.5% 명목 이하다.
  - **조건:** 시뮬레이션은 route 내 case를 하나만 쓰고, OU 상관(지수 공분산)·1차원 proxy feature를 가정한다. 실제 18차원 M0의 학습 잡음과 case 간 상관은 반영되지 않았다. 따라서 power 수치는 설계 근거일 뿐 보장이 아니다.
- **D2:** `NOT_SUPPORTED_AT_0.05` 기준(CI 상한 < 0.05)은 pooled CI 반폭(ℓ = 1 m에서 0.035–0.049)과 비교할 때 달성 가능한 판정이다. 과소검정력 상태를 "효과 없음"으로 오독하는 것을 막는다.
- **D3:** turn을 판정에서 제외한 것은 block 수(3/13/4)에 비추어 타당하다.
- **D6 모호성 제거:** R-03 입력(TIMELINE pooled q95 하나)과 q_ref 구성(a·b 벡터, τ₀, ψ 격자, 상쇄 제외, 평균)을 S0 실행 전에 고정했다. q_ref는 아직 계산하지 않았다. 사후 선택의 여지가 없다.
- **D5:** 감사 체계의 남은 공백을 숨기지 않고, label을 처음 쓰는 비가역 단계 앞에 잠금을 두었다. governance 규칙(독립 감사 부재 시 TECHNICAL_QA_ONLY)과 일치한다.
- **사전 공개:** proposer가 F-11 결과와 G5 상관길이(label 없음)를 본 뒤 D1을 정한 사실이 `PRE_CONTRACT_DISCLOSURE.md` #13에 기록되어 있어야 한다 → 확인됨.

## Verdict (pre-run, SELF_REVIEW_ONLY)

**`ACCEPT_WITH_BOUNDARIES`**

- 경계 1: 독립성 없음. R-10은 OPEN이다. 이 서명은 FROZEN 기록의 감사자 서명란을 채우지만, 독립 감사로 간주하지 않는다.
- 경계 2: S0만 즉시 실행할 수 있다. P1/P2는 D5 조건을 따른다.
- 경계 3: 결과 claim 승격은 독립 사후 감사 전까지 금지한다.

— Claude (Opus 5.5), session `session_01X1n7vLtVgpf8CKd7wVoL2f`, 2026-10-30 KST, **SELF_REVIEW_ONLY**
