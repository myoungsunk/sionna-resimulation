# G1-INT-DIAG-001

동결 Stage 2 입력에서 D0 → D5 → D1을 실행했다. 범위는 앵커 A/B, B0/L2, R2/R4/R5, Full seed 10, mount 0°다. D1은 동일성 대조 12회 및 잔차 순열 4,800회를 포함한다. [검증 계획](../INTEGRITY_VALIDATION_PLAN_KO.md) · [M1–M3 계약 개정](CONTRACT_AMENDMENT_KO.md)

| 파일 | 내용 |
|---|---|
| [RUN_CONTRACT.json](RUN_CONTRACT.json) | 실행 전 동결 원본. `attempt_02`의 사본과 바이트 단위로 일치한다. |
| [실행 보고서](attempt_02/REPORT_KO.md) · [전체 집계](attempt_02/RESULTS.json) · [검증 기록](attempt_02/VERIFICATION.json) | D0, D5, D1 판정 및 파일 해시. |
| [D0](attempt_02/d0) · [D5](attempt_02/d5) | 12개 셀의 재생 trace, 점수, 실행 기록, D5의 σ_b fold 표. |
| [D1](attempt_02/d1) | 12개 셀별 반복 점수, 적격 판정, 순열 배열. |
| [d0_d5.py](d0_d5.py) · [d1_shuffle.py](d1_shuffle.py) · [e0_batch.py](e0_batch.py) | D0·D5 실행, D1 순열과 점수 계산, E0 배치 재생. |
| [freeze_contract.py](freeze_contract.py) · [summarize_run.py](summarize_run.py) | 입력 결합과 계약 동결, 결과 검증과 집계. |

[첫 D0 시도 기록](d0/EXECUTION.json)과 [당시 드라이버](d0_d5_attempt_01.py)를 보존했다. 거리 조회값 기록 오류를 수정한 드라이버의 해시와 재시도 근거는 [재실행 기록](attempt_02/RETRY_RECEIPT.json)에 있다. 이후 집계는 `attempt_02`의 결과에 근거한다.

trace와 순열의 NPZ 파일은 Git LFS로 제공한다.

동결 계약은 실행 환경의 절대 입력 경로와 SHA-256을 담는다. 원본 online/evaluator 입력과 SourceFFD 자산은 계약이 가리키는 Stage 2 묶음에서 확보한다. A·L2에서 사용한 새 online 패킷은 동결 A·B0 패킷과 B·L2 자이로의 결합이며, [결합 기록](bound_a_l2/BINDING.json)에 원본과 파생 해시가 있다. 이 디렉터리에는 파생 패킷의 결합 기록을 포함한다. [Stage 2 실행 자료](../run_20261115_a) · [동결 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/fp-sc-original-npz-20261108)
