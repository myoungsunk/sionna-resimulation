# Governance applicability — DLP-EKF-GAPS-001

상태: **DRAFT / PROPOSER-only**. 본 문서는 governance 문서나 root AGENTS를 수정하지 않는다.

## 기존 역할 규정의 범위

`docs/research-governance/COMMON_CONTRACT.md` 및 세 역할 파일은 **MBVAR-INFO-001** 실험을 대상으로 작성되었다. `AGENTS.md`의 scoped routing은 MBVAR-INFO/POL-XCORR 파일·계약에 대해서만 직접 적용된다. 따라서 이 신규 계약 `DLP-EKF-GAPS-001`에 같은 강제권이 자동 발생한다고 주장하지 않는다. 아래는 제안자 단계에서 **자율적으로 채택한 품질·역할 분리 규약**이다.

| 기존 규정 | 판정 | 본 프로젝트 적용/대응 |
|---|---|---|
| 원본 보호, append-only, hash/provenance | APPLY | C0 원본과 과거 evidence 불변; 별도 docs-only 브랜치 |
| PROPOSER/IMPLEMENTER/AUDITOR 역할 분리 | APPLY | 이번 작성자는 PROPOSER만; 다른 역할 서명 금지 |
| DRAFT/FROZEN 분리와 독립 pre-run 감사 | APPLY | DRAFT라서 과학 실행/RT/replay 금지; 후속 계약 동결 별도 필요 |
| Original MB_VAR R4-B/R5-A parity | ADAPT | C0 4-State DR4/J4 및 해당 Range-only baseline의 상태·P·gate 정합성 |
| 특정 S0 상관계수 .5263/10 수학 실험 | NOT_APPLICABLE | 3-D는 별도 연구·계약에 남겨둠 |
| 새 scene GP/OU 정보량 Track S/R | NOT_APPLICABLE | 기존 MBVAR-INFO 계약 범위로 이관; 이 패키지 중복 수행 금지 |
| RT C00/C01/C10/C11 구성 | ADAPT | 3+ 앵커 데이터가 부족할 경우 **동일 Corridor·궤적** 신규 Anchor H의 canary QA만 별도 승인 요청 |
| CAL/DEV/HOLDOUT 누출 방지 | APPLY | route/scene 구분; 기존 Corridor는 retrospective/DEV, 새 holdout 없으면 일반화 주장 금지 |
| packet/seed/anchor 독립성 경고 | APPLY | 동일 scene의 anchor·route·seed는 독립 RF 환경 수가 아님 |
| RT 예산/throughput 측정 후 승인 | APPLY | 새로운 RF 생성이 필요한 경우만, 사용자 비용 승인 전 실행 금지 |
| ROLE_AUDITOR 진짜 독립 검증 | APPLY | 기획자의 계산/구현자의 시험만으로 독립 인증 불가 |
| CI_REQUIREMENTS.md | REFERENCE_ONLY | 현재 DESIGN_ONLY이며 설치된 자동 집행이라고 주장하지 않음 |
| 기존 MBVAR/POL-XCORR claim register | PROTECTED | 읽기 전용; 상태 변경·과거 결론 승격 금지 |

## 해당 역할의 사전 참고 문서 (읽음)

1. root `AGENTS.md`
2. `docs/research-governance/COMMON_CONTRACT.md`
3. `ROLE_PROPOSER.md`, `ROLE_IMPLEMENTER.md`, `ROLE_AUDITOR.md`
4. `CI_REQUIREMENTS.md`, `CLAIM_REGISTER.md`, `PROPOSER_FREEZE_CHECKLIST.md`
5. `docs/research-governance/templates/{experiment-contract,audit-report}.md`
6. MBVAR 기존 E4 `DECISIONS.json`, E5 정정 `README_KO.md`, `MBVAR_CONTROLLED_INFO_20261029/{PLAN_P0_P6,SCIENCE_SPEC,contracts/EXPERIMENT_CONTRACT_MBVAR-INFO-001}.md`

## 승인 구조

- Proposer: estimand·데이터 계열·중단 조건·사전 성능 판정 체계 설계
- Implementer (미할당): P0 원본 탐색과 필요한 최소 코드/자료 작성, 입력·결과 hash 및 전 단계 parity
- Independent auditor (미할당): source/scene/anchor/time 정합, 경로 재계산, 누출 및 공정성 감사. 독립 세션과 별도 계산 경로 필요.
- User: 최종 데이터 범위, 새 Anchor 위치/자원 공정성, 신생 RF 비용, 계약 동결 여부 승인

**현재 실제 승인 또는 auditor verdict: 없음.**
