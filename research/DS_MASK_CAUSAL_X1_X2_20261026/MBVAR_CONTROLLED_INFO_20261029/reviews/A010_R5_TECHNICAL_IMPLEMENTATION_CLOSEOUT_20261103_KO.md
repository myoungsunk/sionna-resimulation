# MBVAR-INFO-001 — R5 기술 구현 종결 근거 (독립 감사 승인 전)

**기준일:** 2026-11-03 | **역할:** IMPLEMENTER / SELF_REVIEW_ONLY | **PR:** #18.
**결과:** `R5_IMPLEMENTATION_TECHNICAL_VALIDATED` (아카이브·SMOKE 범위), `INDEPENDENT_AUDITOR_SIGNED=false`, `A010_SCIENCE_DRAFT`, `DEV3/HOLDOUT2/RT=NO-GO`.

## 1. 정식 제안자 계약

- `contracts/AMENDMENT-010-R5-PROPOSER-DECISION-FINAL-PREFREEZE-20261103.md` / `AMENDMENT-010-R5-PROPOSER-SPEC-V1.json`. 원본 계약 Git blob `6c1fb6e215809f0ca3a830e72e29e014511fed88`.
- 운영 E′ 그대로; truth-free 9 starts 진단; 10개 전체 terminal cap/finite/common eight-pair probe threshold χ²=1e-3, 최대 F2 30 steps; 하나라도 미인증이면 `UNRESOLVED_PRECISION`. 유일 MAP 주장 불허.
- R5-02: field-block bootstrap B=4000, seed 20261029, H1/H2/H3/CAL/H4/H4_REPRO의 부호·95% CI 0 포함 여부·기존 categorical verdict를 기존 E′ 전수 행과 paired alternative scenario로 비교. 가능한 보수적 변형도 별도 `REVIEW_REQUIRED_POSSIBLE_CHANGE`.

## 2. 구현 코드·테스트 SHA

| 파일 | Git blob SHA |
|---|---|
| `code/a10_r5.py` | `125460cc34574d789f693203a0d58bccf93a8dff` |
| `code/c3v5.py` | `1f9f93830139464a88e71fe957a43b83e9b7fcd8` |
| `code/s1v5.py` (기존 운영 E′ 불변) | `01c84e028ee2326d5127ecdaa62d74fcd697ce54` |
| `tests/test_a10_r5.py` | `fbb206a7398703e53c864450a257ebd66e9c06b0` |

**기존 LOCK 보호:** `RUN_REQUEST.json` blob `2e8c23e8212ab8717c7b513045c02247e2a77146`, `contract_lock.py` blob `a62d43dfce65d7a9ec9cc061916ecc836960d4e9`, `AMENDMENT-010.md` blob `3ee2e9995f46bfbe8e6e563fb18605feb47ba56f` 변경 없음.

## 3. 핵심 원본 실행 증거 (성공과 실패를 모두 보존)

| Evidence | SHA / 범위 | 관측 결과 |
|---|---|---|
| [#41593156279](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41593156279) | K1/K2 archived DEV2, SHA `4f8d302b9cf3cce4e68ac3455212414d8419fece` | R5 common precision 10/10 각각 PASS, K1 근접 시작점 0, K2 5. 운영 과학 결론은 별도 |
| [#41597420058](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41597420058) | 원본 SHA `8511a3196a95408e3f8379bc13af6614ef707190`의 저장 CSV | 새 검증기로 10행/100 terminal 재검증 PASS, 40개 결함 fixture 거부. source SHA mismatch 게이트는 우회하지 않음 |
| [#41596817031](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41596817031) | 수정 운영 코드 SHA `de8b1f6c10a996afbf29d77daab97cc40f409a86` | 2/2 CI jobs SUCCESS, 통합 포함 92/92, fast 66/66 PASS |
| [#41596880906](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41596880906) | 동일 운영 코드 + CSV 음성 시험 추가, SHA `0d840d12ab3c508d2fe3b5ce6a0a505f2d1e6ca2` | fast 80/80 PASS, 통합 결과는 Actions 원본 기준으로 확인할 것 |
| [#41593803226](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41593803226) | 수정 전 | R5 terminal end_state CSV 역직렬화 실패 (`ERR_R5_TERMINAL_ROW_VERDICT_MISMATCH`) 보존; 결과 삭제/소급 변경 금지 |

## 4. 직접 저장 아티팩트 검사

- 성공한 통합 아티팩트 [#41596817031 / artifact 13212989547](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41596817031/artifacts/13212989547) outer ZIP SHA256 `3771457daaaf98dd56d0a79545a86f023b5bf7f47b66710082c2258615e84bc5`.
- 별도 stdlib 코드로 `.csv`, `S1V5_QA.json`, `C3V5_STATUS.json`, `A010_R5_COMMON_PRECISION.json`, `A010_R5_FIELD_PAIRED_CONCLUSION_STABILITY.json`을 직접 읽어 교차 검사.
- S1V5 44/132행; C3V5 10/72행, 등록키 62개 누락; 총 100 terminal = 10개 관측키 × 10 starts; duplicate 0, cap 0, 최악 common dmin `−0.000548198223810914 χ²`, max F2 2 steps, R5_PRECISION PASS, 미인증 0.
- `G5_NUMERIC_REPLAY=FAIL` 및 `C3V5_STATUS=FAIL`을 보존. H/CAL `NOT_EVALUATED_INCOMPLETE`, `science_release_allowed=false` — 이 상태가 **정상**.
- 로컬 검증 JSON SHA256: `82aa85ed7f57157ed7bd30383bda05122f89bb019a83c3f2d44f7bad262a1c93`; 독립 감사인 서명을 의미하지 않음.

## 5. R5 기술 종결과 과학 동결을 분리

- **기술 범위 완수:** 제안자 R5 계약의 terminal cap/probe 검증, field-block H/CAL alternative sensitivity 게이트 구현 및 synthetic positive/negative fixtures, archived K1/K2와 reduced SMOKE 실행 근거 확보.
- **미완료 과학 단계:** 전체 DEV3 표본의 field-level 결론은 독립 사전 동결 전 접근 불가. 비선형 solver/Hessian 전수 별도 구현, 타 actor의 독립 원본 재계산·감사 서명은 미완료.
- **실행 권한:** 지금 이 PR을 merge/FROZEN하지 않는다. DEV3 20–29·HOLDOUT2·reserve·RT 절대 실행 금지.

`R5_IMPLEMENTATION_TECHNICAL_VALIDATED=true`; `R5_INDEPENDENT_AUDIT_SIGNED=false`; `A010_SCIENCE_FROZEN=false`; `DEV3/HOLDOUT2/RT=NO-GO`.
