# MBVAR-PRR-001 — S1 독립 재검산과 현재 S2 개발 승인 재확인

**기준일:** 2026-11-03  
**판정:** S1 과학적 채택 NO-GO 보존, S2 책임자 별도 승인과 독립 코드감사에 의한 GO_S2_DEV 발급 **확인**, GO_S2_LOCKED_EVAL은 별도 HOLD.

## 1. 동시 업데이트 발견과 감사 범위

이 추가 재검산은 S1 종료 커밋 **e3dfbe8e2d7216ddfa5bf754edb991989856dfd5**에서 시작했다. 그러나 원 작업 브랜치에 후속 네 커밋이 올라와 **13c8ef89ffea3212847fc8e3e257ad55409bfd41**에서 다음 파일이 새로 확인되었다.

- [기존 책임자 승인](../S2/OWNER_APPROVAL.json) 및 [기록](../S2/OWNER_AUTHORIZATION.md) — S2와 S3 *순차적 연구 범위* 승인; S1 실패 유지.
- [기존 독립 S2 코드감사](../S2/audit/CODE_FINDINGS_S2.md) 및 [GO_S2_DEV 토큰](../S2/audit/GO_S2_DEV.json).
- [S2 frozen rules](../S2/IMPLEMENTATION_RULES.json) 및 [S2 복구 코드](../S2/recovery.py), [실행기](../S2/run_stage.py).
- 현재 S2 개발 승인 대상 SHA **4eeb7f539ea40fbbc4a4d5eb477d788f2d230945**. 이 SHA는 현재 작업 HEAD의 조상이며 구현 핵심 다섯 파일(IMPLEMENTATION_RULES.json, recovery.py, run_stage.py, grant.py, test_s2.py)의 blob SHA가 현재 HEAD와 동일함을 **별도로 검산**했다.

**따라서 새 책임자 승인이나 중복 GO_S2_DEV를 발급할 필요가 없다.** 이전부터 존재한 정식 승인 토큰을 확인한 것으로 기록한다. 본 audit branch의 파일은 기존 승인 토큰을 대체하지 않는다.

## 2. S1 독립 점수 재계산 — fail 유지

별도 GitHub Actions Linux runner에서 production score/update/summary helper를 사용하지 않는 Python 표준 라이브러리 검산을 실행했다. [Run #41636627036](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41636627036).

| 잠금 Full / primary t≥30s | 개별 시드 RMSE 쌍대비율 중앙값 | 사전 기준 | 결과 | XY쌍대비율 | Heading95 중앙값 |
|---|---:|---:|---|---:|---:|
| R4-B B0 | 0.9215142735 | ≤0.90 | FAIL | 1.036071 | 0.397804 |
| R4-B L2 | 0.9055490319 | ≤0.90 | FAIL | 1.046165 | 0.407939 |
| R5-B B0 | 1.0622484658 | ≤1.05 | FAIL | 0.983659 | 0.977866 |
| R5-B L2 | 1.0504346648 | ≤1.05 | FAIL | 0.968463 | 0.994071 |

검사 범위: 원본 점수 **1,600행**, paired summary **320행**, trace index/LFS pointer **320건**, 코드/계약/입력 SHA 연결. 불일치 없는 수행 종료. **이 새 runner는 원본 NPZ 320개를 materialize해 345,120회 갱신을 별도로 재실행한 감사는 아니다.** 그 원시 갱신 검산은 기존 [S1 R1 독립감사](../S1/audit/R1_S1_INDEPENDENT.md) 기록의 별도 범위이며 혼동하지 않는다. 자세한 수치와 원본 해시는 [S1 검산 receipt](S1_INDEPENDENT_SCORE_AUDIT_RECEIPT.json).

## 3. S2 별도 승인과 독립 코드 감사의 실제 상태

기존 승인 문서에는 S2 연구 진행이 승인됐고, S3는 **S2 이후 별도 기술적 게이트를 거친다**고 기재되어 있다. 이를 S3 실행 토큰으로 확대 해석하지 않는다.

S2의 실제 독립 코드감사 문서는 다음을 보고한다.

- 외부 WSL **prr31117** 별도 runner로 독립 합성시험 110건, gate/수학·PSD·축·주입·trigger 음성시험 확인.
- 8개 조건의 A/B 35-packet 기준 재현 **560갱신**, 최대 state/P 차이 2.78e-17, mask 일치.
- frozen source blob 41개·FFD bank 2개·입력 132개·epsilon 8개, 규칙 및 owner grant hash 점검.
- 결과 **S2 개발만 승인**. S2 과학적 복구 성공과 잠금 평가는 미검증.

이 문서는 해당 감사 보고와 코드 SHA/소스 일치 여부를 다시 조회했으나, prr31117의 110개 합성시험과 560개 update를 새 별도 runner에서 전부 재실행했다는 주장은 하지 않는다. 현재 독립 감사의 범위를 정직하게 구별해야 한다.

## 4. S2 개발 실행에서 반드시 보고해야 하는 사항

**A=W0, B=기존 고정 W-d0-DS, C_P=W0+P 복구, D_P=B+P 복구.** S2 승인 코드와 원본 [전체 계획서](../MBVAR_PRR_001_PLAN_20261103/01_EXECUTION_PLAN_KO.md)의 가설·평가 기준은 그대로 유지한다.

- **Trigger feasibility:** R4/R5 × B0/L2 × Full/LoS 별 suspect-latch→1s quiet→ρhat≤1.5m→2s geometry guard의 단계별 통과 수. 발동이 없으면 복구 efficacy는 NA/HOLD; 이미 공개된 S1 잠금시드로 trigger/계수를 바꾸지 않는다.
- **동일 손상 snapshot 실험 M:** 같은 (x,P), 같은 일정에서 실제 평균 오차 및 회복시간이 좋아졌는지. P만 커져 coverage↑면 복구 주장 불가.
- **전체 주행 P:** 각 arm 자체 인과 trigger, 실제 Heading/XY RMSE·tail·NEES·coverage, R5-B/Native-LoS 보호, false recovery 및 latency. seed0–9 DEV와 seed10–29 LOCKED 별도.
- **게이트:** fixed mask F vs arm 자체 gate O를 분리. P 확대에 따른 NIS 감소로 오염 관측이 추가 수용되는 효과를 주 처치 효과로 숨기지 않는다.
- **주입 과학:** S2 P 회복은 추가 PSD, 기존 평균·Q·offdiag 유지, 축/단위·near-anchor fallback 검증. 회복이 실제 정답오차 감소인지 확인.
- **후속 잠금 평가:** 독립 S2 DEV 결과·주장 감사 및 코드·manifest 불변을 확인한 뒤에만 별도 GO_S2_LOCKED_EVAL. S1 실패는 여전히 보존.

## 5. 최종 판정

**S1:** 기술적 유효 / 과학적 채택 NO-GO.  
**S2:** 별도 책임자 승인과 독립 코드감사 **GO_S2_DEV 이미 발급됨**. S2 DEV 수행은 동결된 범위에서만 가능.  
**미승인:** GO_S2_LOCKED_EVAL, S2 성능 성공, 무조건적인 S3 DEV/평가, 성능 기준 변경.

[독립 점수 검산 코드](verify_s1_scores_independent.py) · [정식 S2 감사 자료](../S2/audit/CODE_FINDINGS_S2.md) · [S2 grant](../S2/audit/GO_S2_DEV.json).
