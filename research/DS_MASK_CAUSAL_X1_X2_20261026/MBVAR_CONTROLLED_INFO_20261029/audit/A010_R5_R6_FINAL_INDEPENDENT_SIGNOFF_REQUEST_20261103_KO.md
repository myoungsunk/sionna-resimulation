# A010 R5 결정 완료 / R6 독립 최종 승인 요청 (별도 AUDITOR)

**본 문서는 구현자/제안자 제출자료이며 감사자 서명 아님.**

### 고정 소스 및 증거

- 대상 GitHub: `myoungsunk/sionna-resimulation`, proposer branch `proposer/mbvar-a010-r5-decision-r6-arithmetic-20261103`.
- R5 제안자 최종 결정문 및 JSON 수치 계약: `contracts/AMENDMENT-010-R5-PROPOSER-DECISION-FINAL-PREFREEZE-20261103.md`, `contracts/AMENDMENT-010-R5-PROPOSER-SPEC-V1.json`.
- R6 standalone source/test `audit/a010_r6_standalone_artifact_audit.py`, Actions #41586097494, code SHA `9658ab900c128777a7ba938f6027572647d29d89`.
- 원본 SMOKE #41560555661 (tested SHA `6733fb5…`), 최신 DEV2 K1/K2 2-runner #41562234223 (tested SHA `ecb6d58…`).
- 결과 artifact https://github.com/myoungsunk/sionna-resimulation/actions/runs/41586097494/artifacts/13207593389

### Auditor must independently verify

1. R5 계약의 9 starts 및 E′ 기존 불변성, F2 1e−3/30 cap, common-probe terminal certificate 구현 여부. 만약 아직 미구현이면 R5 implementation alignment = NOT_CERTIFIED. 제안자 결정과 과학적 실행 허가를 구분.
2. A010 R6 standalone 재계산 원본 저장소 파일/CI 환경에 주입 없이 48+256 배열 SHA와 dtype/shape를 독립 재산출. Artifact ZIP digest를 GitHub와 직접 대조.
3. 10개 row 각각의 `z,x0,ds_m,gy_m,Sigma_model,dts,taps` 별도 원본 digest 재계산, 실제 C3 `FL.batch_map_v2_ms` 인수 경계 검사 코드 경로 검토.
4. 4×4 C10 10개 upper triangle, 고유값/SPD/조건, rotation, K1/K2/SMOKE full NEES4를 독립 math calculator로 재계산하고 구현자 결과/문서 불일치 조사.
5. K2 근접 5개 start의 terminal precision, 중복 최소점 미해석, 대안해에 의한 field-paired MSE/P/NEES 영향과 science conclusion stability 계획 검토.
6. 기존 C3/C3V4 `STATE_STABILITY_FIXED FAIL`, historical FROZEN A008/A009/A010-P0/RUN_REQUEST/contract_lock 변조 여부 직접 비교. DEV3/HOLDOUT2/RT 접근 여부 조사.
7. 독립 actor/session·기여 helper 재사용을 기록하고 `ACCEPT_WITH_BOUNDARIES/REVISION_REQUIRED/REDESIGN_REQUIRED/BLOCKED_EVIDENCE` 중 한 가지로 서명.

**STOP:** 과거 two-runner·SMOKE PASS를 DEV3 전체 science PASS로 승격 금지. R5 공통 precision 진단이 미실행이면 unique-MAP claim 금지. 정식 별도 감사자 서명 전 `A010=SCIENCE_DRAFT`, `DEV3/HOLDOUT2/RT=NO-GO`.
