# 독립 사전 감사 요청 — DLP-EKF-GAPS-001 P1

**REQUESTED, NOT YET PERFORMED.** 이 문서는 독립 감사자의 신분이나 서명을 대체하지 않는다.

## 독립성 조건

제안자/구현자와 **다른 실행 주체·세션**이 독립 계산을 수행해야 한다. `auditor_actor`, `independent_session_or_runner`, audit commit/receipt ID, 공유한 helper/code를 모두 기록할 것. 같은 세션의 재독해, 작성자가 만든 단위시험만의 재실행, GitHub CI green 또는 위 문서의 재서술은 `SELF_REVIEW_ONLY`이며 `ACCEPT_WITH_BOUNDARIES` 불가.

## 읽을 입력 (읽기 전용)

1. `AGENTS.md` 및 `docs/research-governance/COMMON_CONTRACT.md`, `ROLE_AUDITOR.md`, `GOVERNANCE_APPLICABILITY_KO.md`; source base `6c7200091028fd3f0e55aa83b777d0f10b7cf063`.
2. 이 패키지의 계약, source science specification, `P1_INPUT_LOCK.json`, `P1_CONFIG_LOCK.json`, `P1_NUMERIC_TOLERANCES.json`, `P1_SAMPLE_SPLIT_LOCK.json`, SHA `P1_PROPOSER_LOCK_RECEIPT.json`.
3. Original `P0_INPUT_MANIFEST.json`, `SOURCE_BANK_RECEIPT.json`, pinned `SourceFFD`, `p0_initial`, historical `observation.py` and legacy `FrozenLut`.
4. Independent C0 source/hash/pose checks from P0 prior receipt, but do not mistake them for the auditor's own calculations.
5. Recovered R4/R5 Mount45 case and its `SOURCE_LOCK` CRLF/LF validator issue only to confirm it is excluded from the seven paired P1 cases.

## 필수 독립 감사 항목

| Audit ID | Independent recheck | Stop/verdict if fails |
|---|---|---|
| A00 | Contract/config/input/tolerance/split SHA256 using fresh reader and correct raw bytes; check scope and old DRAFT rule | BLOCKED_EVIDENCE |
| A01 | 39 exact C0 assets, 2 bank binary SHA, real bank staging vs Git LFS pointer; frequencies/scene/antenna frame | BLOCKED_EVIDENCE |
| A02 | Seven cases 9519 Full/LoS pairs; independent pose/time join and 7251/6201 case-time counts | REVISION_REQUIRED |
| A03 | Independent raw H→Hann→IFFT→tap→r/s on random + adversarial case, not merely calling implementer helper | REDESIGN_REQUIRED for wrong physical observer |
| A04 | SourceFFD direct vs NativeLoS complex H and s; pole/seam and same-tap QA; separate tolerance per physical dimension | REVISION_REQUIRED |
| A05 | Independent finite-difference `h_s` Jacobian and analytic `H_r`, all 4D shapes and b_g derivative=0; crossing count | REDESIGN_REQUIRED for mathematical invalidity |
| A06 | Independently derive `e_s_src-e_s_old=h_old-h_src`, `e_r` unchanged, sample covariance `ddof=1`, PSD and units | REDESIGN_REQUIRED |
| A07 | No truth in runtime, retrospective-only C0, no hidden new train/test claim, no row deletion, no SourceFFD 2026-10-16 retrospective PASS relabel | REVISION_REQUIRED |
| A08 | Provenance and engineering tolerances fixed before next P1 execution; their retrospective origin explicitly disclosed | REVISION_REQUIRED |
| A09 | Source code dependencies: `p0_initial.py` loads bank files from repo parent; verify staged manifest/hash and runnable independent environment; historical FFD full runner not fully in Git | BLOCKED_EVIDENCE if unresolved |

An independent *audit* must write its own program/code hash, system versions, full scan coverage, raw measured test values, exact source SHA, input hashes (or state why an input is unavailable), failure rows and a separate provenance receipt.

## Required verdict & gating

Return one of `ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, `BLOCKED_EVIDENCE`. A response must identify `contract_id,contract_sha256,input_hashes_verified,math_checks,data_leakage,unreported_exclusions,matched_design_checks,statistical_independence,claim_overreach,required_remediation,allowed_claims,audit_sha,auditor_actor,independent_session_or_runner`.

An `ACCEPT_WITH_BOUNDARIES` may authorize **P1 only**, after proposer+auditor record a separate **FROZEN ratification** referencing the unchanged contract/input/config/tolerance SHA. It does not approve P2–P4 or imply that P1 scientific hypotheses are supported. Until the independent verdict exists, the documented state is `AUDIT_PENDING; FROZEN=false; P1_NOT_RUN`.

No source/raw/frozen evidence is to be modified by the reviewer.
