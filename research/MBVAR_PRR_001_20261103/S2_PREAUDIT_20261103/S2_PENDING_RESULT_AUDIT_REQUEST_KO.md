# MBVAR-PRR-001 — S2 DEV 이후 독립 결과감사 의뢰서

**기존 감사·권한:** 원래 작업 브랜치의 [S2 독립 코드감사](../S2/audit/CODE_FINDINGS_S2.md)와 [GO_S2_DEV](../S2/audit/GO_S2_DEV.json)가 이미 발급된 사실을 확인했다. 이 요청서는 **실행 후 추가 결과감사**만을 대상으로 한다. 이미 완료된 코드감사를 미완료라고 주장하지 않는다.

## 1. 역할과 고정 입력

- 역할: 기존 구현·자체 점수 생성과 분리된 **INDEPENDENT RESULT AUDITOR**.
- Source SHA: **4eeb7f539ea40fbbc4a4d5eb477d788f2d230945**; 독립 감사 전 실제 실행 manifest의 코드 SHA와 비교.
- 고정 승인 규칙: [S2 IMPLEMENTATION_RULES](../S2/IMPLEMENTATION_RULES.json), [원래 전체 계획 §5·§7·§8](../MBVAR_PRR_001_PLAN_20261103/01_EXECUTION_PLAN_KO.md).
- 단일 앵커 B, R4-B/R5-B×B0/L2×Full/Native-LoS. 개발 seed0–9, locked eval seed10–29.
- A=W0, B=S1 W-d0-DS, C_P=W0+P, D_P=B+P. **B는 S1에서 과학적으로 실패한 후보 그대로 유지**.

## 2. 감사 필수 사항

1. **실행 provenance:** 정확한 GO_S2_DEV, code/contract/input/rules SHA, run manifest·320 main traces·등록된 80 ablation·최대 80 snapshot 등록, 원본 기록 SHA/행수 점검. 실패 trace 은폐·무단 재실행/변경 없음.
2. **독립 계산:** production score/update helper를 재사용하지 않는 reference checker로 P injection의 평균 불변·PSD·축·rad²/m², Joseph 식·마스크·NIS, finite 및 covariance symmetry, event state machine을 샘플링 또는 전수 검산. 실제 검증 범위를 정확히 표시.
3. **발동 가능성:** 각 route×bias×channel×seed 별 latch→quiet→near→geometry→commit/cooldown event 수·시각, count0의 조건 보존. 어떤 정책도 실제로 trigger가 없었다면 ‘복구 성능’을 주장 불가.
4. **회복 대조:** 같은 잘못된 상태에서 시작하는 M snapshot의 각 arm Heading/XY 오류 적분·2초 연속 복구시간·right censoring과, 전체 t=0 자연 재귀 P 결과를 분리. 각 arm의 trigger 수가 다른 효과도 별도 제시.
5. **주장 지원:** Full R4 heading/XY, R5/Native-LoS 보호, coverage·NEES(특히 worst seed), False recovery, p95/max errors. D−B는 예방 위 복구의 추가 이득, C−A는 복구만의 효과, D−C는 복구 위 예방의 추가 효과. D가 A보다 낫다는 것만으로 결합 효과를 주장 금지.
6. **A/B 재현:** Stage S2와 Stage S1 원본 W0/W-d0-DS의 state·P·gate가 고정 허용오차 내 같아야 한다. S1 실패를 PASS로 재라벨하지 않는다.
7. **보호·장치:** P 주입에 의한 NIS 완화로 오염 관측 재수용되는 경우를 F 고정 게이트와 O 새 게이트에서 분리. LoS와 정확한 상태에 대한 false recovery와 CPU/latency 성능도 보고한다.
8. **종결판정:** TECHNICAL_ACCEPT/FAIL과 SCIENCE_SUPPORT/PARTIAL/NOT_SUPPORTED를 분리. P 확대가 coverage만 높였다면 **UNCERTAINTY_RELAXED_ONLY**. DEV 기술/과학 감사 통과와 별도 owner 승인 전에 GO_S2_LOCKED_EVAL 발급 금지.

## 3. 산출물 요구

- 코드·입력·결과 SHA를 포함한 JSON verdict / 정밀한 위반 행 번호.
- 독립 auditor ID·별도 runner·독립 검산 코드 SHA·전체 로그.
- Full/Native-LoS/B0/L2/route별 M/P 결과 및 seed별 paired score.
- S2 DEV 전용 최종 판정: 진행/보류/중단. locked-eval 또는 S3 승인과 혼동 금지.

**주의:** 이 요청서 자체는 독립 감사 실행이나 새로운 승인 토큰이 아니다. 기존 S2 개발 승인만 유효하다.
