# DualLP Physics Link Validation — 재구현본

**제안자 패키지가 아니라 실제 실행 결과를 담은 재구현 패키지입니다.** 원래 사라진 ZIP과 byte-identical 복원본은 아닙니다.

|핵심 확인|결과|
|---|---|
|실제 재귀 / 논리 비교|132회 / 144개|
|원 CSV 결과 대조|864/864, 6유효숫자 일치|
|이전 대화 RMSE 대조|48/48, 소수 넷째 자리 일치|
|원 CONTROL 상태·공분산|B0/L2 × 3경로 × 2평균 = 12건 통과|
|물리 미분|안정 9,356 통과, 전환 52 별도 보존|
|동일 prior 후보 갱신|50,176개|
|원 저장 평균 계보|6,272행 통과|
|독립 감사|미실행 — SELF_REVIEW_ONLY|

[한국어 상세 보고서](REPORT.md) → [최종 QA](QA.json) → [이전 보고 대조표](results/tables/PREVIOUS_REPORT_CLAIM_COMPARISON.csv) → [12조건 결과](results/tables/LEGACY_PRESERVATION_12.csv)

기존 Heading 12/12 개선, XY 8/12 개선이 재현됐습니다. lookup 대 사전 지정 상수는 R2/R5 8조건에서 lookup 우세, R4 4조건에서 상수 우세로 이전과 같습니다. 과학적 해석은 MIXED입니다.

메인 ZIP에는 코드, 원 RF/CONTROL, 원 예측 CSV, 132개 전체 trace, shadow ledger, 검사표와 그림을 포함합니다. 큰 입력인 FFD bank 두 개만 외부 companion ZIP입니다. 필터 전체 재실행에는 [REPRODUCE.md](REPRODUCE.md)에 따라 두 bank를 추가하세요. 원 결과는 덮어쓰지 않고 새 출력 폴더에서 실행합니다.

V4는 선택 항목으로 미실행. V5 fresh inference는 원 모델/scaler/fold 미회수로 BLOCKED입니다. 원 아카이브·동결 서명·감사 파일이 복구되었다고 주장하지 않습니다.
