# G1-INT-001 | SC·KI 실행 자료

[궤적별 검증 보고서](REPORT_KO.md)와 [전체 점수 및 5초·10초 블록 구간](run_01/RESULTS.json)은 B·B0, mount 0°, seed 10의 R2·R4·R5를 다룬다. [D0·D5 고정 gate 및 LORO 기준선](../attempt_02)과 [D2·D3 동결 모수 근거](../continuation_d2_d3)를 사용했다.

- [동결 실행 계약](RUN_CONTRACT.json)의 SHA-256은 `c056347b9d8a20685442235d250415058c85073ec93535c947723c685d2d684b`다.
- [실행 진입점](run_structure.py), [SC·KI 재생](structure.py), [검사와 점수 집계](score_structure.py), [저장 trace 재집계](verify_structure.py)를 포함한다.
- [실행 영수증](run_01/EXECUTION.json), [구현 검사](run_01/IMPLEMENTATION_CHECKS.json), [재집계 기록](VERIFICATION.json)이 입력·코드·출력 해시 및 검사 결과를 연결한다. [실행 폴더](run_01)의 SC·KI 궤적 trace 6개는 Git LFS로 제공한다.

원본 계약과 코드는 실행 호스트의 디렉터리 배치를 기준으로 동결했다. 분석을 재현할 때는 계약에 적힌 경로·SHA-256에 맞춰 상위 실행 자료와 [Stage 2 Release 입력](https://github.com/myoungsunk/sionna-resimulation/releases/tag/fp-sc-original-npz-20261108), SourceFFD 자산을 준비한다. 재생 진입점은 `python -B run_structure.py run --contract RUN_CONTRACT.json --out <새-출력-폴더>`이고, 검증 진입점은 `python -B verify_structure.py <출력-폴더>`다.
