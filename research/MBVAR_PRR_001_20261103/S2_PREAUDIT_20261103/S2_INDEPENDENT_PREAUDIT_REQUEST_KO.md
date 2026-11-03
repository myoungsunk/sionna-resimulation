# MBVAR-PRR-001 / S2 — 독립 사전감사 에이전트 요청

**역할: INDEPENDENT SCIENCE / CODE PREAUDITOR (기존 구현자와 별도 컨텍스트·별도 runner)**

**현재:** S1 기술적 결과 VALID, 사전 과학적 채택 NO-GO. 별도 책임자 결정으로 **S2 설계·격리 구현 준비만 허용**. **S2 GO_S2_DEV 또는 GO_S2_LOCKED_EVAL 토큰 발급 전 반드시 이 감사 수행**.

## 1. 먼저 읽을 고정 원본

- [원본 전체 실행계획](../MBVAR_PRR_001_PLAN_20261103/01_EXECUTION_PLAN_KO.md), §3, §5, §7–§10
- [독립 S1 결과감사](../S1/audit/R1_S1_INDEPENDENT.md)
- [S1 동결 코드](../S1/online.py), [잠금 manifest](../S1/runs/EVAL_001/RUN_MANIFEST.json)
- [S1 잠금 점수](../S1/runs/EVAL_001/SCORES_PER_SEED.csv) 및 기존 독립 점수 검산 [Actions 41636627036](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41636627036)
- [조건부 S2 연구 진입 결정](S1_REAUDIT_AND_S2_SCOPE_DECISION_KO.md)
- [S2 기존 구현 코드감사 요청](../MBVAR_PRR_001_PLAN_20261103/audit_requests/S2_CODE_AUDIT_REQUEST_KO.md)

## 2. 감사 질문 (제안자·구현자 요약을 신뢰하지 말 것)

**G0 SCIENCE JUSTIFICATION**
- S1-C3 실패 4개 조건을 변경 없이 인정하는가? 그 실패 후 S2-H(이미 손상된 상태 복구)는 분리된 인과 질문인가?
- R4-B Heading 약 40% coverage를 단지 P inflation만으로 "회복"했다고 주장하지 않도록 평가 설계가 보호되는가?
- R5-B와 Native-LoS 보호(특히 worst-seed NEES)를 실패로 보고하는가?

**G1 TRIGGER FEASIBILITY — FAIL/HOLD 중요한 항목**
- seed0–9 개발 로그 또는 동등한 원본 replay에서, GT 정보 없이, 고정된 trigger가 실제 R4-B/R5-B에서 발생하는지 독립적으로 계수.
- suspect latch(5s에 1−w≥0.5 3회), clean 1s(1−w≤0.25), rho_hat≤1.5m, 2s data geometry rank guard, 60s expiry, 20s cooldown, route 3회 제한을 **순서대로 적용**하고 단계별 event 감소를 보고.
- S2 온라인 policy의 trigger가 너무 적거나 없어도 threshold를 바꾸지 말고 NOT_EVALUABLE 또는 HOLD로 판정.
- S1 잠금 seed10–29를 trigger/계수 탐색에 사용하지 말 것.

**G2 MATH / CAUSAL**
- P injection은 delta P PSD, heading rad² / tangent m², near-axis fallback; P 교차항·bias mean·Q 보존.
- before vs after 주입의 x_mean 동일; measurement OFF / nu=0 음성시험.
- 고정 BASE acceptance와 S2 정책 자체 gate는 별도. P 확대가 NIS를 낮춰 기존 오염을 더 수용하는 경로를 독립 진단.
- same snapshot M vs natural recursion P 분리; M에서는 공통 trigger schedule 사용. GT로 snapshot 평가점과 arm selection을 선택하지 않음.
- A(W0)/B(S1 W-d0-DS)/C_P(P only)/D_P(B+P); S1의 이미 실패한 B를 통계적으로 소급 통과시킬 수 없음.
- 외생 위험도 모델의 정확한 normalized likelihood 주장은 금지.

**G3 RELEASE GOVERNANCE**
- 원본 RF/mean/R/observations/seed 등 provenance·SHA 동결, S1 baseline zero-intervention 패킷별 parity.
- 개발 seed0–9와 locked seed10–29 구분. 이미 S1 평가에서 locked seed가 공개된 상태임을 명시.
- S2 구현자가 production score/update helper로만 parity를 계산했으면 독립 PASS 금지. auditor 코드/runner/로그와 정밀도 수치 제출.
- 신규 코드 SHA·계약 SHA·데이터 SHA·runner 환경 / audit identity 없이는 GO_S2_DEV 금지.
- S2 independent result audit가 없으면 GO_S2_LOCKED_EVAL 승인 금지.

## 3. 필수 산출물

1. TECH_AUDIT.json — STATUS PASS/FAIL/HOLD, 검증된 코드·계약 SHA, 별도 checker와 runner reference, 수학 QA.
2. SCIENCE_AUDIT.md — 남은 연구 질문의 식별성과 대조의 충분성; 사전 fail criteria 유지 여부.
3. TRIGGER_FEASIBILITY.csv — 각 단계 후보 수/시각, route/bias/Full/LoS, 개발 seed별, actual/no_trigger 모두.
4. SOURCE_LOCK.json — code/model/RF/mean/R/seed/calibration/accept-mask SHA와 데이터 provenance.
5. 명시적 VERDICT: **GO_S2_DEV** 또는 **HOLD_S2** 또는 **BLOCKED**, 별도 책임자 승인 범위보다 확대 금지.

## 4. 자동 중단 기준

- 기준 S1 잠금 실패를 PASS로 재해석.
- GT/미래/LoS 정답을 online trigger 입력으로 이용.
- 무처치 재현 실패, 새 P injection 후 평균 변동, PSD/단위 오류, 중복 관측 또는 새 gate 혼용, 근거 없이 바꾼 σ 목표·λmin·threshold.
- 독립 감사자·runner 식별 실패 또는 실제 원시 packet에 대한 검증 없이 검증했다고 주장.
- 개발후 locked seed 선택·threshold 변경 또는 보호조건 삭제.

**감사자는 구현자 branch에 직접 수정을 하지 말고, 별도 audit branch에서 독립 결과를 제출해야 합니다.** 이번 요청서는 미래 감사 결과를 대신하지 않습니다.
