# G1-DIAG-003 D7.1 결과와 재현 기록

**DIAGNOSTIC_ONLY · S2′ STOP (FULL_6) · Step 3 보류**

사양은 커밋 [f3c2717](https://github.com/myoungsunk/sionna-resimulation/blob/f3c2717d45326f4226c4e548c0f25db116c51026/research/G1_PACKET_EKF_20261114/SPEC_A_BLOCKC_KO.md)의 D7 및 D7.1이다. D7.1의 전체 case를 합친 무결성 기준을 충족한 조건은 없다. [결과 보고서](REPORT_KO.md) · [완료와 재현 기록](COMPLETION_KO.md)

| 파일 | 내용 |
|---|---|
| [out/D7_JC.json](out/D7_JC.json) | 네 case, 7개 bias·부호 조건, 조건별 seed 20개의 집계 |
| [out/checkpoint_rows.csv.gz](out/checkpoint_rows.csv.gz) | checkpoint 오차, 공분산과 포함 지표 71,120행 |
| [attempt_02/](attempt_02/) | 네 case의 정확 일치 J4·J‑V 재현 검산 및 FFD bank 검증 |
| [main/](main/) | 모형 설정, seed·case별 결과, worker 로그, 실행 증빙, 매니페스트 |
| [launcher/](launcher/) | 두 검산 시도와 본 계산의 컨테이너 로그·종료 상태 |
| [FINAL_PROVENANCE.json](FINAL_PROVENANCE.json) | D4 상한 재확인 및 기존 D5·D6 비교 파일 해시 |
| [ARTIFACT_MANIFEST.json](ARTIFACT_MANIFEST.json) | 원본 본 계산 결과·요약 파일 SHA-256 |
| [PUBLISH_MANIFEST.json](PUBLISH_MANIFEST.json) | 이 디렉터리에 게시한 파일의 SHA-256 |

## 재현 진입점

격리된 실행 폴더를 컨테이너의 /d7에 연결한다. 루트 Python·셸 코드와 S0 판정 기록을 복사한다. 검산 결과 폴더와 본 계산 결과 폴더는 실행 중 만들어진다. 기존 결과는 증거로 보존한다.

- 실행 이미지 SHA-256은 [main/MANIFEST.json](main/MANIFEST.json)에 있다. 실행 인자와 마운트는 [main_command.txt](main_command.txt)를 참조한다.
- /diag는 기존 DIAG-003 동결 작업 폴더다. S0 trace, 원 RF ZIP과 추출 관측 자료, D4 및 D5·D6 checkpoint 파일을 포함해야 한다. 파일 해시와 고정 소스 커밋은 [기존 DIAG-003 매니페스트](frozen_inputs/DIAG003_MANIFEST.json)에 있다. 재사용하는 초기 runner 모듈의 보관본은 [frozen_code/](frozen_code/)에 있다. /diag와 FFD bank가 들어 있는 /banks는 읽기 전용으로 연결한다.
- PYTHONPATH=/d7:/diag/diag003_work/code에서 [gate.sh](gate.sh)로 네 case를 재현 검산한다. [check_d7_range_inputs.py](check_d7_range_inputs.py)가 동결 거리 관측과 무잡음 추출을 대조한다.
- 두 검증이 끝나면 [d7_dispatch.py](d7_dispatch.py)로 실행한다. [d7_export.py](d7_export.py)는 출력을 검사하고 보고서와 집계 파일을 만든다.
- cohort별 NPZ에는 Git LFS를 적용했다. 체크아웃한 뒤 Git LFS로 원본을 받을 수 있다.

첫 검산의 로그는 루트 GATE 파일과 [attempt_01_sources/](attempt_01_sources/)에 보존했다. 본 계산에 진입한 검산은 attempt_02다. 기준 재현 검산의 거리 상태 비활성화는 D7.1 본 계산에 적용하지 않았다.
