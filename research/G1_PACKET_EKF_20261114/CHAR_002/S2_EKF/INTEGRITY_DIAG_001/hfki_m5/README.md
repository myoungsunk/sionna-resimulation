# M5 HF-KI 검증 결과

mount 0°, 앵커 B, B0, Full RF. [검증 계획서](../PLAN_M5_HFKI_STAGED_KO.md)는 커밋 033abcc7f2940bd8437ccbebd145d2f9f229730b에서 동결했다. 연구 질문 ID는 G1-INT-001/M5다.

A2는 seed 10에서 **NO_BAND**였다. R4는 다섯 설정, R2는 6°·8°에서 궤적별 기준을 충족했고, R5와 pooled는 통과 설정이 없었다. Stage 3은 R5의 X2 진단 분기로 실행했다. seed 10–14 전부에서 A0의 R5 거울해는 0건, X2는 2건이었다. HF-KI 채택 조건은 미충족이다.

| 단계 | 보고서와 비교표 | 상세 결과·검증 | 동결 계약 |
|---|---|---|---|
| 0 | [구현 검사](attempt_02/stage0/REPORT_KO.md) | [검사 및 seed 입력 목록](attempt_02/stage0/CHECKS.json) · [검증](attempt_02/stage0/VERIFICATION.json) | [RUN_CONTRACT.json](attempt_02/stage0/RUN_CONTRACT.json) |
| 1 | [궤적별 예측](attempt_02/stage1/REPORT_KO.md) | [PREDICT.json](attempt_02/stage1/PREDICT.json) · [검증](attempt_02/stage1/VERIFICATION.json) | [RUN_CONTRACT.json](attempt_02/stage1/RUN_CONTRACT.json) |
| 2 | [궤적별·pooled 재생 비교](attempt_02/stage2/REPORT_KO.md) | [점수](attempt_02/stage2/SCORES.json) · [대역 판정](attempt_02/stage2/BAND.json) · [검증](attempt_02/stage2/VERIFICATION.json) | [RUN_CONTRACT.json](attempt_02/stage2/RUN_CONTRACT.json) |
| 3 | [seed별 비교와 Stage 4 판정](attempt_02/stage3/REPORT_KO.md) | [점수](attempt_02/stage3/SCORES.json) · [거울해 판정](attempt_02/stage3/BAND.json) · [검증](attempt_02/stage3/VERIFICATION.json) | [RUN_CONTRACT.json](attempt_02/stage3/RUN_CONTRACT.json) |

## 자료와 코드

- [Stage 0 seed 11–14 online NPZ](attempt_02/stage0) 12개, [Stage 2 trace](attempt_02/stage2) 41개, [Stage 3 trace](attempt_02/stage3) 20개. Stage 3 trace는 seed 번호별 하위 폴더에 있다.
- [Stage 0–2 실행·재집계](run_hfki.py) · [HF-KI 재생·검산](hfki_replay.py) · [Stage 1 예측](hfki_predict.py) · [Stage 3 실행·재집계](run_stage3.py).
- [seed 자료 준비 검사](seed_readiness/SEED_DATA_READINESS.json)와 [실행 코드](seed_readiness/check_seed_data.py) · [첫 Stage 0 실패 기록](stage0/EXECUTION.json)과 [당시 코드](stage0/failed_sources).
- 단계별 검증은 구현자가 수행한 재집계와 검사다. seed 간 Full RF·복도·시간 격자·z는 공유한다. Stage 3은 seed 10의 초기값·초기 공분산·gate를 고정했다.

## 게시본 검사와 원본 재생 환경

Git LFS로 NPZ를 받은 저장소 체크아웃에서 이 폴더의 verify_archive.py를 Python 3.11+로 실행하면 원본 실행 기록에 연결된 출력 해시, 단계별 계약, NPZ 목록 및 [게시 파일의 SHA-256](SHA256SUMS)을 검사한다. 이 검사는 출력의 보존 여부를 확인한다. 재귀 실행과 점수 재집계는 각 단계의 실행·검증 코드에 있다.

동결 계약과 재생 코드는 실행 당시의 파일을 바이트 단위로 보존했다. 원본 재생에는 계약에 적힌 Windows 경로와 SHA-256으로 입력을 준비해야 한다. mount 0 seed 10 online/evaluator와 SourceFFD 자료는 기존 [동결 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/fp-sc-original-npz-20261108) 및 [Stage 2 실행 자료](../../run_20261115_a)에서 확인한다. 공통 gate·LORO trace와 D3·V3·C1·M1–M4 참조는 같은 브랜치의 [진단 결과와 코드](..)에서 찾아 계약의 해시와 대조한다. [단계별 원본 실행 기록](attempt_02)은 명령, 환경 및 산출물 해시를 담는다.
