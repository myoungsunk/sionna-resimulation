# G1-INT-001 · KS 이전 진단 실행 자료

B·B0, mount 0°, Full RF seed 10의 R2/R4/R5에서 개정 계획 순서대로 V8부터 D6까지 진단했다. KS 후보 재시험의 진입 판정은 `STOP_NOT_ADMITTED`다. [결과 보고서](REPORT_KO.md) · [동결 계획](PLAN_FROZEN.md) · [진입 판정](run_03/KS.json)

| 항목 | 파일 |
|---|---|
| 실행과 재집계 | [run_ks.py](run_ks.py), [ks_fit.py](ks_fit.py), [ks_replay.py](ks_replay.py), [ks_diagnostics.py](ks_diagnostics.py), [verify_ks.py](verify_ks.py) |
| 계약 | [원본](RUN_CONTRACT.json), [첫 재시도](RUN_CONTRACT_RETRY_02.json), [최종 실행](RUN_CONTRACT_RETRY_03.json) |
| 최종 결과 | [run_03](run_03), [실행 기록](run_03/EXECUTION.json), [재집계 검증](VERIFICATION.json) |
| 초기 시도 | [run_01](run_01), [run_02](run_02), [첫 시도 코드 사본](executed_source_attempt_01), [두 번째 시도 코드 사본](executed_source_attempt_02) |
| 소스와 입력 | [공개 자료 매핑 및 SHA-256](PUBLICATION_MANIFEST.json), [추가 입력](replay_inputs), [기존 입력 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/fp-sc-original-npz-20261108) |

`run_03`에는 V9까지 재사용한 21개를 포함해 최종 실행 기록이 열거한 37개 산출물이 있다. NPZ는 Git LFS로 내려받는다. `run_02`에 남아 있는 재사용 전 파일도 보존했다.

공개 자료 매핑에는 동결 계약의 입력 104개와 SC 재확인에 쓰인 M3 표, SourceFFD의 출처 기록이 있다. 기존 커밋과 Release에 동일 SHA-256의 파일이 있는 경우 해당 위치를 기록했다. 추가 입력에는 SourceFFD 소스 12개와 출처 기록, B·L2, A·B0, A·L2에 쓰인 패킷 15개가 들어 있다. A·L2 evaluator는 A·B0와 공유하므로 매핑에도 같은 파일을 가리킨다.

원본 계약의 SHA-256을 보존하기 위해 실행 당시 절대 경로를 유지했다. 재실행 환경에는 매핑에 적힌 경로의 입력, [이전 진단 코드와 계약](..), [Stage 2 소스](../..), 동결 계약에 명시한 거버넌스 문서가 필요하다. Python 3.13.15, NumPy 2.2.4, SciPy 1.15.2를 사용했다. 환경을 구성한 뒤 원래 실행 위치에서 다음 명령으로 별도 디렉터리에 재생하고 재집계한다.

```powershell
python -B run_ks.py run --contract RUN_CONTRACT_RETRY_03.json --out run_reproduced
python -B verify_ks.py --contract RUN_CONTRACT_RETRY_03.json --run run_reproduced --out VERIFICATION_REPRODUCED.json
```
