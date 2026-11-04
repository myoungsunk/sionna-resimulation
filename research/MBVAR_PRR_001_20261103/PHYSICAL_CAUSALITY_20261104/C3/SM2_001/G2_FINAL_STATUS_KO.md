# C3 G2 완료 — 독립 DATA ACCEPT

R4_168 고정 좌표의 yaw 0°, 180°, +35.7°, −35.7° 네 조건을 실행하고 독립 DATA·보고서·기게시 원자료 감사를 통과했다. 본 PathSolver 1,028회, 지정 반복 QA 12회, 원시 ray 64,320개, 직접파 복소 계수 4,112개를 검증했다. 첫 실패 시도는 실제 추적 0회에서 중단했으며 해당 자료와 이전 GO를 보존했다. 총 실제 추적은 1,040회이고 자동 과학 재실행은 없었다.

|관문|현재 판정|증거|
|---|---|---|
|G0 상세 동결 계약|SPEC_APPROVED|audit/C3_SPEC_REAUDIT_RESULT.json|
|G1 코드·native CFR 수정|ACCEPT|audit/C3_CODE_REAUDIT_RESULT.json|
|운영 자료형 수정·새 GO|ACCEPT|audit/C3_SPEC_EXECUTION_FIX_RESULT.json, audit/C3_CODE_EXECUTION_FIX_RESULT.json, GO_CANARY_002.json|
|G2 4yaw 원시자료·독립 수치검산|DATA ACCEPT|audit/C3_DATA_RESULT_AUDIT_RESULT.json, audit/INDEPENDENT_CANARY_VERIFIER_001.json|
|G2 보고서·기게시 raw 연결|ACCEPT|audit/RESULT_FINDINGS_G2_KO.md|
|G3 잔여20조건|HOLD — 별도 사용자 승인 필요|CONTRACT_KO.md, PLAN.json|
|G4 물리분해·source-model Hpsi|미실행|G2 GO 범위 밖|
|전체24조건 C3 및 G5 최종물리주장|미완료|G3·G4 선행 필요|

최종 독립 receipt SHA256: `07894ecebf001388f76c7420ad4cfaee96f1627659fe18260178487803ee4996`.
독립 한글 감사 보고서 SHA256: `c66069202d2d37e0ffff84515487c00c7c89d2fd7bc104d868c13da91ac25255`.

실행 코드/GO 게시 기준은 `907af979a8827772a60e9835b2bc8b39c325c924`, 원시자료·실행 보고서 게시 기준은 `398793f7897387fdc6a6dff82fd742f50ac82aaf`이다. 원자료 게시 1,089개 신규 경로(Git 45, LFS 1,044)의 바이트 또는 OID·size/로컬 payload와 성공 업로드 기록을 독립 확인했다. LFS payload 21,007,047 bytes의 원격 재다운로드 검증은 하지 않았다. 이 문서와 최종 감사 bundle은 해당 원자료 커밋 이후 별도 후속 커밋으로 게시한다.

기존 G1_PREAUDIT 및 G2_EXECUTION 문서의 pending 표시는 각 당시의 제출 상태로 보존한다. 최신 판정은 위 독립 receipt와 본 상태 문서이다. C0–C2 및 기존 actual-yaw 원본을 재실행하지 않았다. 이 통과는 선택된 한 좌표의 네 yaw 원시자료에 대한 수치·출처 검증이다. 복구 정책, EKF 성능, 전체24조건 완료 또는 알고리즘 채택을 뜻하지 않는다. 기존 전체 채택 NO-GO·실시간 HOLD 유지.
