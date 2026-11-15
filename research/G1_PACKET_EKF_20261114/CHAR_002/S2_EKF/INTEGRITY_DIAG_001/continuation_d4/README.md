# G1-INT-DIAG-001 · D4 공개 자료

[검증 보고서](REPORT_KO.md)는 A/B, B0/L2, R2/R4/R5의 평균 모형 진단과 동결 거리 보정 HGB의 특징 범위 비교를 정리한다. [전체 D4 결과](run_02/RESULTS.json)와 [거리 구간별 잔차 표](run_02/RESIDUAL_BINS.csv)에 수평거리와 3차원 거리 집계를 함께 담았다.

- [HGB 특징별 이탈률 표](HGB_FEATURE_RATES.csv)는 [실행에서 생성한 원본 JSON](run_02/HGB_FEATURE_SUPPORT.json)을 CSV로 펼친 것이다. 이탈률 열은 0–1 비율이다. JSON에는 학습 fold와 특징별 분위수도 들어 있다.
- [실행 코드](run_d4.py), [잔차 집계](residual_d4.py), [HGB 특징 복원](feature_d4.py), [결과 재검증](verify_d4.py)과 [실행 기록](run_02/EXECUTION.json), [구현 검사](run_02/CHECKS.json), [재집계 기록](VERIFICATION.json)을 포함한다.
- 성공한 실행의 [동결 계약](RUN_CONTRACT_RETRY_02.json) SHA-256은 `4610582a9e858878bfbd205a544e631099125f83736c6a6dc3c8459ebc0d9e2e`다. 첫 시도의 [계약](RUN_CONTRACT.json), [실행 기록](run_01/EXECUTION.json), [변경 전 소스 사본](executed_source_attempt_01), [수정 기록](RETRY_RECEIPT.json)도 보존했다. 첫 시도의 부분 출력은 실행 호스트에 보관했다.

동결 계약은 기존 실행 호스트의 입력 경로와 해시를 기록한다. 재실행에는 [D0/D5 자료](../attempt_02), [D2/D3 자료](../continuation_d2_d3), [SC/KI 동결 기록](../structure_sc_ki), Stage 2 입력과 잠금된 X1 원본 특징 자료가 필요하다. 환경을 준비한 뒤 `python -B run_d4.py run --contract RUN_CONTRACT_RETRY_02.json --out run_reproduced`와 `python -B verify_d4.py --contract RUN_CONTRACT_RETRY_02.json --out run_reproduced`로 실행하고 점수를 재집계한다.
