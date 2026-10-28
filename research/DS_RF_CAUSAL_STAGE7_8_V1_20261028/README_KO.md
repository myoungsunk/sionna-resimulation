# RF causal Stage 7–8 V1 실행 결과

기준 커밋: `4d2414a7238176b6e116cae2d10546e724b66b8d`.
2026-10-28 실제 RF 입력으로 7개 경로 × B0/L2 실행. Stage 1–6 재실행 없음.

최종 판정: **TECHNICAL_QA_PASS_NOT_SCIENTIFIC_CAUSAL_PROOF**. 종료 코드 0.
Stage 7: 210개 Arm/NPZ, 644개 검사, 215개 산출물 해시 통과.
Stage 8: 336개 Arm/NPZ, 952개 검사, 341개 산출물 해시 통과.

- `code/`: 실행한 전체 코드와 코드 잠금 기록
- `package/` 및 ZIP: 원본 배포 패키지
- `results/CAUSAL_FINAL_QA.json`: 최종 검증
- `results/07_rf_pol_factorial/`: 상호작용 표, 절대 성능, 상세 NPZ
- `results/08_post60_handoff/`: 상태·공분산 분리, 성능, gain ledger, 상세 NPZ
- `execution/EXECUTION_RECEIPT.json`, `logs/`: 실행 출처와 로그
- `UPLOAD_SHA256.json`: 이 파일 자체를 제외한 업로드 파일 SHA-256

원본 기록의 절대 경로는 실제 실행 당시 경로를 보존한다. 실행 입력 RF·SourceFFD bank는 기존 외부 입력을 참조하며 새로 복제하지 않았다.
GT와 미래 표본을 사용하는 오프라인 모델 개입 결과이며, 물리적 인과 기전의 독립적 입증 또는 배포 가능한 개선 알고리즘의 검증으로 해석하지 않는다.
기존 연구 폴더와 결과는 보존하고 이 폴더만 추가했다.
