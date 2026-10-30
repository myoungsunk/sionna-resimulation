# AMENDMENT-POLX-001 — post-S0 amendment to contract v1.0

- 대상 계약: `EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md` sha256 `c36c1c56d4db59d39ea85e1d87c1efe622325730a6b4fbc595fc95e583cde219` (본문은 수정하지 않음)
- 촉발 결과: S0 run 40989019866 — `H1_FAIL`, `R03 = REDESIGN_REQUIRED`
- **결과 확인 이후의 변경이다.** 아래 조항으로 생긴 모든 run은 `EXPLORATORY_POST_RESULT`다. v1.0 S0의 기계 판정은 그대로 기록에 남는다.
- 근거: `reviews/S0_REVIEW_02.md`, `reviews/PROPOSER_DECISION_04.md`

## A1 — S0 LAW 사양 결함 기록과 탐색적 재정의

| 구분 | 내용 |
|---|---|
| 원 규칙 | handoff/D6 채널식 H(f) = a·e^{−j2πfτ₀} + b·e^{jψ}·e^{−j2πf(τ₀+δ)}, f = 절대 RF 주파수; 적합 [0.05, 1.0] ns; tolerance [1.9, 2.1] |
| 결함 | C1 반송파 위상 결합, C2 대역 하단 기준(복소 펄스), C3 소 δ 영역을 벗어난 적합 구간 (`S0_REVIEW_02` §2) |
| 새 규칙 (EXPLORATORY) | 지연 항 e^{jψ}·e^{−j2π(f − f_c)δ}, f_c = 대역 중심; n₀는 δ = 0 검출값으로 고정; 적합 구간 0.002–0.01 ns; 기준 기울기 [1.9, 2.1] |
| 이미 본 결과 | 예 — 감사 진단에서 중앙값 1.997, p05 1.993 |
| 영향 | 동결 H1 판정 `H1_FAIL`은 유지한다. 원인 분류 `SPEC_DEFECT`를 추가한다. F2 법칙은 `EXPLORATORY_SUPPORTED`로만 기록하고 확증 claim은 하지 않는다 |

## A2 — PHYSICAL 모드 표 무효화

- 결함: 구현이 절대 f 지연 항에 ψ = −2π·f_c·δ를 추가로 넣어 반송파 위상이 이중으로 반영됐다.
- 조치: run 40989019866의 PHYSICAL 행을 `INVALID_SPEC_DEFECT`로 표시한다. 보고 전용이었으므로 판정 영향은 없다. 올바른 PHYSICAL 정의는 원 절대 f 식에서 ψ = 0이다.

## A3 — R-03 결과에 따른 arm 철회 (v1.0 규칙의 이행이지 변경이 아님)

- R-03 = REDESIGN_REQUIRED는 세 가지 채널 구성 모두에서 같다(q_ref 상대 차이 < 1e-6).
- **철회:** E1(primary), E1b, E1c, E2, E1-ctrl/E1-dec — M1(q_W, ε_ρ)과 M2를 쓰는 모든 P1 arm.
- P1은 이 arm들로 실행하지 않는다. label을 열지 않았으므로 철회로 인한 선택 편향은 없다.
- P3의 M1/M2 하드웨어 ablation도 철회한다.

## A4 — E4 기준 모형 변경

- 원 규칙: E4 = ΔAUC(M0 + [q_W] + M4 vs M0 + [q_W])
- 새 규칙: **E4′ = ΔAUC(M0 + M4 vs M0)**. q_W는 A3로 철회됐으므로 기준 모형에서 뺀다.
- 판정 규칙: v1.0 D1(pooled)·D2를 그대로 쓴다. P2a 분리성 gate(ρ_sep ≥ 0.6)도 유지한다.
- 이미 본 결과: 없음(P2는 label 미개방 HOLD 상태).

## A5 — 실행 권한 갱신

| 단계 | 권한 |
|---|---|
| S0 | 종료. 추가 S0 run은 A1 탐색에 한한다 |
| P1 | **CANCELLED for M1/M2.** M0만으로 하는 P1은 이 계약에 estimand가 없으므로 실행하지 않는다 |
| P2 (E3, E4′) | HOLD 유지. 사용자 진행 지시 또는 독립 감사 서명 필요 |
| P3 | P2 생존 지표(M4)만 대상 |
| 결과 라벨 | `TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE` 유지 |

## Signoff

| 역할 | 서명 | 독립성 |
|---|---|---|
| PROPOSER | Claude (Opus 5.5) session `session_01X1n7vLtVgpf8CKd7wVoL2f`. 사용자 MSK의 검토·결정 요청(2026-10-30 11:27 KST)에 따른 결정. 사용자 확인 시 유효 | — |
| AUDITOR | 같은 세션 | SELF_REVIEW_ONLY |
| INDEPENDENT AUDITOR | PENDING (R-10) | — |
