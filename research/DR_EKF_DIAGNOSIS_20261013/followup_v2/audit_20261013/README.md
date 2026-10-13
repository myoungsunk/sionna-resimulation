# DR EKF 감사 및 개발 실행 결과 — 2026-10-13

코드 감사와 업로드된 D6 자료에 대한 남은 감사는 완료했다. D6 최종 판정은 **UNRESOLVED**, 공식 결과 재계산은 **RECONCILED**다.

## 현재 결과부터 읽기

- [최종 D6 감사 보고서](evidence/remote_f1d6d9fc/FINAL_AUDIT_KO.md): 63/63 캐시 검증, C3/C4 FAIL, S1 4/9, 공식 JSON/CSV 재계산 불일치 0.
- [최종 실행 기록](evidence/remote_f1d6d9fc/EXECUTION_RECEIPT.json): 감사 저장 형식 오류와 수정 후 exit 0을 모두 기록.
- [코드 감사·V3/V4 pilot 보고서](evidence/AUDIT_REPORT_KO.md): 코드 수정, 19개 회귀 테스트 통과, 개발 실행 결과. 이 초기 보고서의 캐시 미수령/NOT_READY 상태는 최종 D6 보고서로 갱신되었다.
- [V3 전체 경로 pilot](evidence/v3_fullroute_pilot/V3_SECOND_ORDER_ABLATION.json), [V4 pilot](evidence/v4_pilot/V4_CALIBRATION_ABLATION.json).
- [최신 PF 보완 감사](evidence/remote_03e06b55/v2_audit/V2_PF_REFERENCE_AUDIT.json): f1d6d9fc의 PF 결과 JSON이 동일함을 최종 감사에서 확인.

## 범위 및 보존

V3/V4는 R2_d2, 개발 seed 8000–8003의 pilot이다. 전체 9셀 개발 캠페인이나 독립 300 seed 확증을 완료했다고 주장하지 않는다. V5는 후보 선택·사전등록 전이므로 NOT_RUN이다. PF 보완 검증 로그의 끝부분 잘림은 남아 있다.

코드 기준은 3032a589, 최종 D6 데이터 기준은 [f1d6d9fc](https://github.com/myoungsunk/sionna-resimulation/tree/f1d6d9fc984feb2c9a3b5fba36ca9aaa31fbe933/research/DR_EKF_DIAGNOSIS_20261013)다. D6 원본·spec·하네스·기준은 수정하지 않았다. 대용량 원본 캐시는 데이터 브랜치에 보존하며 여기에는 감사 결과/매니페스트/로그를 등록한다.

evidence는 기존 기록의 바이트를 보존하므로 당시 Windows 절대 경로와 과거 중간 상태가 포함된다. execution_scripts는 실행 당시 로컬 배치를 기록한 증거이며 이 폴더에서 바로 실행하는 CLI가 아니다. 실사용 진단 CLI는 상위 followup_v2에 있다. PACKAGE_SHA256.json은 업로드된 증거와 수정 소스의 바이트 해시다.
