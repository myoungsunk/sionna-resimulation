# PROPOSER_DECISION_04 — S0 결과에 따른 M1/M2 계속 사용 여부

- 역할: PROPOSER (Claude, session `session_01X1n7vLtVgpf8CKd7wVoL2f`). 감사 근거는 `reviews/S0_REVIEW_02.md`(SELF_REVIEW_ONLY).
- 입력: S0 run 40989019866, 구현자 보고 `IMPLEMENTER_REPORT_S0.md`, 감사 진단 `audit/results_s0_review/`.
- 조치 문서: `contracts/AMENDMENT-POLX-001.md`

## 1. 책임 소재

- H1_FAIL의 직접 원인(C1 반송파 위상 결합, C2 기준 주파수, C3 적합 구간)은 **제안자가 작성한 사양**에 있다. 구현자는 사양을 충실히 따랐다.
- 이 결함은 R-03 판정에 영향을 주지 않는다. q_ref는 세 구성 모두 0.0010961이다.

## 2. 결정

| # | 결정 | 근거 |
|---|---|---|
| 1 | **M1(q_W, ε_ρ)·M2를 이 계약에서 중단(STOP)한다.** P1 E1/E1b/E1c/E2와 해당 P3 ablation을 철회한다 | v1.0 R-03 규칙(q95 > q_ref → REDESIGN_REQUIRED). 사후 완화는 금지돼 있다 |
| 2 | H1은 `H1_FAIL (SPEC_DEFECT)`로 기록한다. F2 법칙은 수정 사양에서 `EXPLORATORY_SUPPORTED`(기울기 1.997)로만 둔다 | 결과를 본 뒤의 재정의 |
| 3 | P2 경로(M4, power-only)는 유지하고, E4를 **M0 + M4 vs M0**로 바꾼다. **P2 HOLD는 유지한다** | M4는 coherency floor와 다른 관측량이다(s_fp·펄스 형태의 공간 변동). P2a gate가 별도로 판단한다 |
| 4 | M0만으로 하는 P1은 실행하지 않는다 | estimand 없음 |

## 3. 이번 결과가 말하는 것 (TECHNICAL_QA_ONLY, label 미사용)

- 이 corpus(SourceFFD ±45 안테나, 복도 RT)에서 FP 7-tap 창의 **LoS coherency floor**(TIMELINE q95 0.0062)는 기준 unresolved 반사(δ = 1 ns, −10 dB, wedge 0.3)의 q_W보다 **5.7배 크다**.
- floor 위로 보이려면 반사가 **≥ −3.7 dB(wedge 0.3)** 이거나, **직교 Jones 성분이 ≥ −13 dB**여야 한다.
- floor는 방향에 따라 변하는 포트 응답 분산이다. 합성 기준으로 포트 간 시간 오프셋 약 200–250 ps와 같은 크기다(250 ps에서 q95 0.0071).
- 방향 무관 정적 등화로는 6.8%만 줄어든다.
- 즉 q_W의 한계는 **알고리즘이 아니라 안테나 포트의 분산 정합**에 있다. 이는 "안테나 물리로 알고리즘 복잡도를 대체한다"는 연구 방향에서 하드웨어 요구조건으로 바꿔 쓸 수 있는 결과다. 단, 독립 감사 전이므로 claim으로 승격하지 않는다.

## 4. 재설계 선택지 (새 계약 POL-XCORR-002, 사용자 결정)

| 선택지 | 내용 | prior 필요 | label | 비용 |
|---|---|---|---|---|
| **R-B 안테나 요구조건 도출** | floor < 0.1·q_ref를 만족하는 포트 group-delay·패턴 정합 허용치를 합성/SourceFFD로 도출 | 불필요 | 불필요 | 낮음 |
| **R-C M4 경로만 진행** | AMENDMENT A4의 E4′로 P2 수행(HOLD 해제 필요) | 불필요 | 필요 | 중간 |
| R-A 방향 인지 floor 모형 | 예측 pose에서 SourceFFD로 LoS q_W를 계산해 floor를 차감 | **필요**(d0형 재귀 문제 재발) | 필요 | 중간 |
| R-D 종결 | 위 §3을 부정적 설계 결과로 기록하고 종료 | — | — | 없음 |

**제안자 권고:** R-B(label 없이 바로 가능)와 R-C(P2 HOLD 해제 시)를 병행한다. R-A는 heading prior 없이 동작한다는 이 연구의 전제와 충돌하므로 권고하지 않는다.

## 5. 구현자 전달 사항

1. S0 구현은 사양에 충실했다. **재실행할 필요가 없다.** 결함 기록은 AMENDMENT A1·A2를 따른다.
2. 수정 LAW(A1)를 독립적으로 재현하고 싶다면 `audit/s0_review_diag.py`와 다른 코드로 EXPLORATORY run을 해도 된다(선택).
3. **P1은 실행하지 않는다**(A3·A5). P2는 HOLD다. HOLD가 풀리면 E4′ 정의(A4)로 구현한다.
4. 모든 문서에서 E1/E2를 "효과 없음"으로 쓰지 않는다. 판정 문구는 "R-03 설계 gate로 실행 중단(STOPPED_BY_R03)"이다.
