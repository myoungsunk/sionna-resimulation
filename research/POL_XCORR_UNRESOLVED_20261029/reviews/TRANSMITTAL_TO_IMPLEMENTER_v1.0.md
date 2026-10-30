# TRANSMITTAL — 제안자·감사자 → 구현자 (POL-XCORR-001 v1.0)

- 발신: Claude (Opus 5.5) session `session_01X1n7vLtVgpf8CKd7wVoL2f` — PROPOSER(사용자 승인) 겸 AUDITOR(SELF_REVIEW_ONLY)
- 수신: IMPLEMENTER (P0V3를 수행한 세션 또는 후속 구현 세션)
- 일자: 2026-10-30 KST
- 기준 branch: `research/pol-xcorr-freeze-v1-20261030`

## 1. 전달 문서

| # | 문서 | 성격 | 구현자 조치 |
|---|---|---|---|
| 1 | `FREEZE_RECORD_v1.0.md` | 동결 기록·서명 원장 | hash 확인 |
| 2 | `contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md` | **구속 계약** (D1–D8) | 숙지 |
| 3 | `contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.3.md`, `SCIENCE_SPEC_v0.3.md` | 승계 본문 | 숙지 |
| 4 | `config/PLAN_PARAMETERS_v1.0.json` | 수치 설정 | 코드에서 직접 읽기(하드코딩 금지) |
| 5 | `TASK_HANDOFF_v1.0.md` | **작업 지시** | S0 수행 |
| 6 | `reviews/AUDIT_01.md` | 감사 보고 (`REVISION_REQUIRED` → v1.0에서 처리) | AF 항목 확인 |
| 7 | `reviews/AUDIT_01A_FREEZE_SIGNOFF.md` | pre-run 감사 서명(SELF_REVIEW_ONLY, `ACCEPT_WITH_BOUNDARIES`) | 경계 확인 |
| 8 | `audit/audit01_recompute.py`, `audit/results_audit01/run_40982122546/` | 감사 재계산 코드·결과 | P0V3 출력과의 교차 확인 근거 |
| 9 | `power/f11_power_sim.py`, `power/results_f11/run_40984998584/`, `power/results_f11_corrlen/` | F-11 근거 | D1 판정식의 기준 구현 참고 |
| 10 | `evidence/r13b_run_40983557008/` | R-13b 보존본 | 이후 R-13b 재검증 입력 |
| 11 | `PRE_CONTRACT_DISCLOSURE.md` #13–#14, `CLAIMS.md` | 사전 공개·claim 원장 | 금지 표현 확인 |

## 2. 제안자 입장 — 결정 사항

1. **주 판정은 pooled ΔAUC(D1)다.** v0.3 route별 규칙은 보조로 보고만 한다. 판정 코드는 `power/f11_power_sim.py`의 pooled 계산(replicate별 가중 결합)과 같은 방식으로 구현하되, P1 코드는 새로 작성한다.
2. **판정은 세 가지뿐이다(D2):** SUPPORTED_RETROSPECTIVE / NOT_SUPPORTED_AT_0.05 / INCONCLUSIVE_UNDERPOWERED. ΔAUC ≈ 0.02는 검출 불가로 사전 명시했다.
3. **turn은 판정하지 않는다.** mount 45°는 case가 하나이므로 효과로 해석하지 않는다.
4. **WEAK_PORT 행은 삭제하지 않는다.** strong-only 분석은 같은 key로만 수행한다.
5. **q_ref는 D6 구성 그대로** S0에서 처음 계산한다. 결과가 `REDESIGN_REQUIRED`면 기준을 바꾸지 말고 M1/M2를 멈춘 뒤 보고한다.

## 3. 감사자 입장 — 요구 사항

1. 결과에는 `TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE` 라벨을 붙인다. 독립 사후 감사 전에는 claim을 승격하지 않는다.
2. **P1/P2는 HOLD다.** 사용자 지시 또는 독립 감사자 서명이 `reviews/`에 기록된 뒤에만 시작한다. S0 PR에 P1 trigger를 넣지 않는다.
3. 사후 감사 항목은 `TASK_HANDOFF_v1.0.md` §7에 미리 공지했다. 특히 다음을 구현에 포함한다.
   - split manifest(train/test key)
   - bootstrap replicate 저장(`P1_BOOT.npz`)
   - 실패 run 보존
4. P0V3 코드는 감사 재계산과 기계 정밀도로 일치했다(AUDIT-01 D 항목: n₀·branch 불일치 0, u·q·ε 오차 ≤ 1.2e-15). S0·P1 observer는 이 구현을 재사용해도 된다. 재사용한 경우 sha를 MANIFEST에 기록한다.

## 4. 열린 항목

| ID | 상태 | 담당 |
|---|---|---|
| R-10 독립 감사자 | OPEN — FROZEN 기록의 유일한 미충족 서명 | 사용자 지정 |
| R-01 T4 | T4_ONLY_BLOCKED | (선택) LFS bank 접근 시 |
| R-07 DW1000 jitter | OPEN_EXTERNAL | P3 해석에 필요 |
| R-08 VNA | OPEN_EXTERNAL | P4 |
| R-11 신규 scene | DEFERRED | 사용자 |

## 5. 첫 명령

S0만 수행한다. 새 branch를 `research/pol-xcorr-freeze-v1-20261030`에서 분기하고, `TASK_HANDOFF_v1.0.md` §2를 구현해 Actions로 실행한다. 결과와 `reviews/IMPLEMENTER_REPORT_S0.md`를 커밋한 뒤 멈춘다.
