# Signed a_i a_j 공분산 검증

- 계획: commit `bd28eac6a0e235412bdced9f08505148191e39d2`, question `G1-INT-SIGNED-COV-001`.
- 과학 판정: **INCONCLUSIVE**. signed 모형이 unsigned보다 우세하다는 주 기준을 충족하지 못했다.
- [최종 보고서](attempt_02/p5/REPORT_KO.md) · [판정 JSON](attempt_02/p5/DECISION.json) · [궤적별 CSV](attempt_02/p5/HOLDOUT_COMPARISON.csv) · [부호 대조 CSV](attempt_02/p5/SIGN_CONTRAST.csv).
- 독립 감사 기록: [AUDIT_KO.md](attempt_02/p5/AUDIT_KO.md). 감사 수용은 signed 가설 지지·H3 채택과 별개다.

주 분석은 BLOCK_C × 앵커 B × mount 0의 기존 noise-free RF다. LORO·재방문 제거·부호 공동 지지를 통과한 R2/R4의 수평거리 6–10 m만 주 예측 점수에 들어간다. R5는 NO_SUPPORTED_FOLD이며 n=0으로 명시했다. R4 근거리에 대한 signed 구조의 입증으로 해석하지 않는다.

| 단계 | 최종 코드 | 동결·증거 |
|---|---|---|
| P0 입력·관측·signed 미분 | p0_inputs_v2.py | attempt_02/RUN_CONTRACT.json, P0_CHECKS.json, P0_R*.npz |
| P1 지지·분할 | p1_design_v2.py | attempt_02/p1_revision_02/PRE_REGISTERED_CONTRACT.json, SPLITS.json, PAIR_INDEX.csv |
| P2 합성·정보 차단 | test_covariance_v2.py, test_runner_boundary.py, covariance_core_v2.py | attempt_02/p2_synthetic_revision_02/, p2_runner_barrier/, AUDIT_PRE_FIT.json |
| P3 실제 donor 적합·미사용 예측 | run_covariance.py | attempt_02/p3/; 승인 source/design/input SHA를 실행 전 검증 |
| 보조 대조 | run_supplemental.py | attempt_02/AUXILIARY_PLAN.json(실제 점수 전 동결), supplemental/ |
| P4 앵커 A·비봉인 G-T1_B | retrieve_external.py, run_external.py | attempt_02/p4/; 기존 RF만 사용, 새 RT 없음 |
| P5 집계·판정 | finalize.py | attempt_02/p5/ |

`reference_d3.py`는 기준 계획 commit의 원본 D3 소스 blob 그대로다. 기존 D3의 EKF truth 잔차와 원시 Full−LoS 잔차는 섞지 않았다. 원본 입력 위치·SHA는 단계별 SOURCE_HASHES/INPUT_INDEX와 실행 계약에 기록되어 있다. 비봉인 G-T1_B 원본은 `D:/SLAM_bot/artifacts/G1_SIGNED_AA_COV_20261117_GT1B`에 별도 보관한다. G-T1에는 검증된 elapsed-time grid가 없어 시계열 점수를 만들지 않았다.

초기 입력 정의 실패(`attempt_01`), 초기 P1 donor 간 매칭 오류, 초기 P2의 과도한 작은 고유값 제거 구현은 삭제하지 않았다. 이 폴더의 `p0_inputs.py`, `p1_design.py`, `covariance_core.py`, `test_covariance.py`와 해당 초기 결과는 최종 구현이 아닌 보존 증거다. 실제 점수를 확인하기 전에 감사·수정·재동결한 `_v2` 코드만 본 적합에 사용했다.

실행 환경은 기존 `D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/test_env/Scripts/python.exe`이며 새 설치는 하지 않았다. 긴 실행은 검증된 대화 ID·새 run ID의 관리 절차를 사용했고, [PROCESS_RECEIPT.json](attempt_02/p5/PROCESS_RECEIPT.json)에 종료 코드·로그·작업 종료 확인이 있다. foreground 합성 검사도 단계별 명령·코드 SHA를 남겼다. 각 runner는 기존 출력 디렉터리를 거부하므로 재현은 새 attempt·새 관리 run에서 수행해야 한다. 본 적합에는 그 attempt의 독립 감사 승인과 일치하는 SHA가 필요하다.

Git 기준은 계획 commit이며 이번 실행 구현은 새 파일의 SHA로 고정했다. M7·기존 연구 브랜치의 결과를 수정하지 않았고, G-T2/G-V 봉인·S2′ STOP·Step3 HOLD를 유지했다.
