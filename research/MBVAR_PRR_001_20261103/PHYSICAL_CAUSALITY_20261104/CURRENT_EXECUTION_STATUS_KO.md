# 순차 실행 현황

사용자 「순서대로 실행」 및 「이미 진행한건 패스」를 적용한다. 완료된14pose/C0-B는 원본 시각·GO·원시·감사 이력을 보존하고 재실행하지 않는다.

| 관문 | 현황 | 증거 |
|---|---|---|
| 개정 producer/입력/runtime 신규 잠금·독립 GO | 완료 | NEW_RT_DATA/SM0/FRESH_CANARY_AMENDED_001/audit/PREAUDIT_KO.md |
| R4 pose194 신규257bin Native RT | 종료코드0 | 같은폴더 RUN_RESULT.json |
| 신규 canary DATA 독립감사·게시 검증 | ACCEPT | 같은폴더 audit/DATA_AUDIT_KO.md 및 PUBLICATION_AUDIT_KO.md |
| 기존14pose 확장 | 완료증거 재사용, 재실행0 | NEW_RT_DATA/SM0/BATCH_AMENDED_001/audit/DATA_RESULT_AUDIT.md |
| 기존 C0-B 물리 경로 분석 | 완료증거 재사용, 재실행0 | NEW_RT_DATA/SM0/C0B_ANALYSIS_001/audit/RESULT_AUDIT.md |
| C1a 동일prior/K/mask4arm | 실행·독립결과감사·게시검증 ACCEPT | C1/C1A_001/audit/RESULT_AUDIT_KO.md 및 PUBLICATION_AUDIT_KO.md |
| C1b 동일BASE prior의 원래joint gate 재판정 | SPEC/코드·DEV 독립수용, 전체120조건 계산·게시 완료, 최종감사 중 | C1/C1B_001/audit/DEV_AUDIT_KO.md 및 RESULTS_KO.md |
| C2 자연 재귀 인과 검증 | C1a/C1b 완료 뒤 상세 계약·SPEC/코드GO 필요, 미실행 | CAUSAL_VERIFICATION_PLAN_KO.md의C2는 초안 |

C1a: R2/R4/R5·B0/L2·공개seed10–29, 120조건·125440prior·501760단일갱신. 결과는 같은 Full prior에서 원시 관측r/s를 교체한 조건부 효과다. 장기오차 적분·NEES·새온라인정책·새RF일반화·알고리즘채택의 결과는 아니다. 기존 NO-GO/HOLD를 유지한다.

C1b: 기존 저장본에 없던 BASE shadow prior를 원래 코드/은행/controls로 재구성해 Full mask와exact대조했다. MB_VAR 기준 궤적은 기존저장본을 사용했다. seed10의6조건 DEV를 독립수용한 뒤 새GO로seed11–29의114조건을 수행했다. 전체120조건 모두exit0, 원래Full x/P/K 차이는0이다. DEV/GO 게시ef650aab16b35149782c71a75a0f0f0a813a2163, 전체raw/report 게시99674f6bae4c74046b99f2afb79781331312c944. 최종결과·보고서감사전이며 C2실행GO는없다.

기록 UTC: 2026-11-04T10:19:11.826238+00:00 (전체 C1b 최종감사 중 기록)
