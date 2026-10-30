# FREEZE_RECORD — POL-XCORR-001 v1.0

**Status: `FROZEN_V1_0` — proposer SIGNED · auditor SIGNED (`SELF_REVIEW_ONLY`) · independent auditor (R-10) OUTSTANDING**

## Frozen artifacts

| 파일 | sha256 |
|---|---|
| `contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md` | `c36c1c56d4db59d39ea85e1d87c1efe622325730a6b4fbc595fc95e583cde219` |
| `contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.3.md` (승계 본문) | `39c396c72688d88efa84d0fcb7779ad2b5b693891ab87aaae803bd26793cb76e` |
| `SCIENCE_SPEC_v0.3.md` | `5db75dcc0a332833de50d87ba2081bea5ca0cd74e7e093ae00ce987728368450` |
| `config/PLAN_PARAMETERS_v1.0.json` | `a16e8226f2766f4188c144228f99276c0102532667eb1e46816c0b4e0ff42658` |
| `config/INPUT_LOCK_v2.json` | `bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184` |
| `config/P0_REFERENCES_v0.2.json` | 기존 커밋 값 유지 |
| governance commit | `d5f84d9d04d28d465f3357e9299352eb184e6bfc` (branch `governance/pol-xcorr-router-d5f84d9d`) |
| base data/source commit | `250d617ad89a4105fa1af546cc83ceed9de98f42` |

## Signatures

| 역할 | 서명자 | 독립성 | 판정 | 날짜 |
|---|---|---|---|---|
| PROPOSER | Claude (Opus 5.5) session `session_01X1n7vLtVgpf8CKd7wVoL2f`, **사용자 MSK 지시(2026-10-30 09:57 KST)로 승인** | — | 계약 v1.0 확정 | 2026-10-30 |
| AUDITOR (pre-run) | 같은 세션 | **SELF_REVIEW_ONLY** | `ACCEPT_WITH_BOUNDARIES` (`reviews/AUDIT_01A_FREEZE_SIGNOFF.md`) | 2026-10-30 |
| INDEPENDENT AUDITOR (R-10) | — | 제안자·구현자와 다른 세션 필요 | **PENDING** | — |
| IMPLEMENTER (상태 확인) | v0.3 P0V3 세션 | 별도 | P0V3 `CLOSED_TECHNICAL` (`reviews/IMPLEMENTER_REVIEW_02.md`) | 2026-10-29 |

## 이 FROZEN의 효력과 한계

- 계약 본문, 수치 규칙, 판정 규칙이 고정된다. 이후 변경은 amendment로만 할 수 있다.
- **governance 예외 공개:** COMMON_CONTRACT·router는 FROZEN에 독립 감사 서명을 요구한다. 이 기록의 감사자 서명은 SELF_REVIEW_ONLY다. 사용자 지시에 따라 freeze를 진행하되 아래 제한을 건다.
  - S0: 실행 가능.
  - P1/P2: label을 처음 여는 단계다. 사용자의 명시적 진행 지시 **또는** 독립 pre-run 감사 서명 이후에만 시작한다(계약 D5).
  - 모든 결과: `TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE`. 독립 사후 감사 전까지 CLAIM 승격과 RESEARCH_RELEASE를 금지한다.
- 독립 감사자가 나중에 이 v1.0을 재검토해 `REVISION_REQUIRED`를 내리면, 그 이전 run은 그대로 보존하고 amendment로 처리한다.

## Pre-freeze evidence index

- P0: `results_p0/run_40867521966`
- P0V3: `results_p0_v03/run_40884686972` (재현 `run_40884328487`)
- 감사 재계산: `audit/results_audit01/run_40982122546` (실패 run `run_40981740739` 보존)
- F-11: `power/results_f11/run_40983557008`(v0.3 규칙), `power/results_f11/run_40984998584`(pooled 포함, 판정 근거), `power/results_f11_corrlen/`
- R-13b 보존: `evidence/r13b_run_40983557008/`
