# R4 QA V3 — 재현 명령

## 입력

- 보존된 원 재구현 ZIP `DualLP_Physics_Link_Validation_RERUN_20261101.zip`, SHA-256 `d2c9ab428ae676579a79907451a7523615876d3075f24f6abe7ee279ba75f7b2`.
- V2 감사·보완 ZIP `DLP_PHYS_LINK_REPAIR_V2_20261102.zip`, SHA-256 `18a99461a245be53b46bcfa0c4ac1596383f74459b4f17dc981e5bb62e51d70d`.
- 별도 ±45° FFD 은행 `LP_plus45_bank.npz` / `LP_minus45_bank.npz`: `b29ae471…` / `39729fe9…`. V3 새 FFD 계산 없음. **108개 원 input lock**은 source-root의 `recovered/`에 원 FFD 파일까지 갖춰져 있어야 통과.
- V2 원 구현은 GitHub의 `repair_v2.py`, Git blob `5566bcb53b32075af0f72ad83e2565138d8bc6c3`.

## 실행

Python 3.13, numpy, pandas, pytest 설치 후 위 source-root를 압축 해제하고 은행을 `/recovered/inputs/banks/`에 놓는다.

```bash
export SOURCE_ROOT=/absolute/path/DualLP_Physics_Link_Validation_RERUN_20261101
export QA_V3_ROOT=/absolute/path/DLP_PHYS_LINK_R4_QA_V3_20261102
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

pytest -q "$QA_V3_ROOT/tests/test_r4_guard_v3.py"
python -u "$QA_V3_ROOT/code/repair_v3.py" --source-root "$SOURCE_ROOT" --out "$QA_V3_ROOT"
PYTHONOPTIMIZE=1 python -u "$QA_V3_ROOT/code/repair_v3.py" --source-root "$SOURCE_ROOT" --out "$QA_V3_ROOT"
```

각 실행은 별도 폴더에 `--out`을 주면 덮어쓰지 않는다. 원 데이터·기존 result ZIP 변경 금지. 이 보완은 저장된 132 trace와 shadow 데이터를 읽어 QA를 다시 계산하는 작업이다. 원 132회 EKF 전체 재귀 실행, RT, ML 학습을 새로 수행하지 않는다.

`results/REQUIRED_CHECKS_V3.json`의 **5,729 필수 검사**와 `results/NULL_AND_MUTATION_TESTS_V3_SUPPLEMENT.json`의 **76개 음성시험** 및 `results/PARITY_V2_TO_V3.json`의 V2 5,290행 불변 확인을 검토한다. `results/REPAIR_VERDICT_V3.json`의 PASS는 **구현자 자체검증** 범위에 한정한다.
