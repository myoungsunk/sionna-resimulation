# G1-INT-001 C1–C8 추가 검증

앵커 B·B0, mount 0°, Full RF seed 10의 R2/R4/R5에 대한 자료다. [결과 보고서](REPORT_KO.md)와 [70개 점수 행](SUMMARY_SCORES.csv)을 함께 제공한다. KS 재시험 진입 판정은 이전 계약의 `STOP_NOT_ADMITTED`를 유지한다.

| 항목 | 파일 |
|---|---|
| C1·C2·C3·C5·C6 | [결과·trace](run_01), [실행 코드](run_followup.py), [동결 계약](RUN_CONTRACT_C1_C6.json) |
| C4 | [최종 결과·trace](run_c4_retry_03), [실행 코드](run_c4_retry_03.py), [최종 계약](RUN_CONTRACT_C4_RETRY_03.json) |
| C7 | [TEACH/REPEAT 결과·코드·계약](c7) |
| C8 | [별도 재생 코드](c8/run_c8.py), [실행 기록](c8/EXECUTION_C8.json), [재생 결과](c8/replay) |
| 재집계 | [검증 코드](verify_followup.py), [검증 결과](VERIFICATION.json), [파일 SHA-256 목록](PUBLICATION_MANIFEST.json) |

NPZ는 Git LFS로 받는다. 원본 실행 증거와 계약의 SHA-256 보존을 위해 실행 당시 경로를 유지했다. 재현에 필요한 KS 동결 입력의 출처 및 경로는 [기존 공개 매핑](../continuation_ks/PUBLICATION_MANIFEST.json)에 있다. C8의 임시 입력 디렉터리는 [재생 코드](c8/run_c8.py)가 공개 기준 커밋 및 동결 입력에서 구성한다.
