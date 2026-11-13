# G1 사양서 2 v3.2 검증 실행

실행 ID는 `RUN2_20261113T072631Z`입니다. [동결 사양서 v3.2](https://github.com/myoungsunk/sionna-resimulation/blob/ebd55913519e852364a07fb33ec3188c9cbe7bca/research/G1_SWEEP_HEADING_FLOOR_20261113/SPEC2_KO.md)의 R0 재현과 S1′ 검증까지 진행했습니다. G-OBS-1/2는 mount 0의 6개 case에서 모두 통과했습니다. G-INT-a는 보간 격자 세분화 후에도 기준을 충족하지 못해 S2′ 본 계산과 §8 판정을 보류했습니다. 상위 폴더의 v3.2 실행 코드에는 이번 실행에서 도달하지 않은 본 계산 경로도 포함됩니다.

- [실행 보고서](outputs/REPORT_KO.md)
- [R0 재현과 비교 해시](outputs/R0.json)
- [6개 case의 관측 검증](outputs/S1P_OBS_PREFLIGHT.json)
- [G-INT-a 구간별 집계](outputs/S1P_G_INT_SUMMARY.csv)
- [실행 명령, 입력과 출력의 SHA-256](outputs/MANIFEST.json)

매니페스트의 `output_sha256` 경로는 이 폴더 기준입니다. `code_sha256`의 Python과 JSON 파일은 상위 폴더에 있습니다. `preflight.sh`와 `server_stage.sh`는 [launch](launch/)에 있고, 실행 시 `SPEC2_V32_FROZEN.md`로 복사한 문서는 위 링크의 `SPEC2_KO.md`와 바이트가 같습니다.

입력 묶음과 R0의 대용량 재생 배열은 기존 입력 및 [이전 실행 기록](../RUN_20261113T052908Z/)을 참조합니다. 재생 배열 비교 결과와 해시는 `outputs/R0.json`에 기록했습니다.
