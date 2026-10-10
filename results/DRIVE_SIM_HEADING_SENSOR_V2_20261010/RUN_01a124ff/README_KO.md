# Sensor-v2 CIR·RF heading 실행 결과

[한국어 최종 보고서](FINAL_REPORT_KO.md)를 먼저 읽으십시오. A–E 5,250회와 별도 대조/검증까지 총 5,697회 실행했습니다. 본 비교 실패는 0건입니다. 신뢰도 정책 E는 평균 NEES를 낮췄지만 heading/위치 RMSE를 악화시켜 채택 보류입니다. F01/F02 OPEN, scientific_PASS=false를 유지합니다.

## 읽는 순서

- `PLAN.json`, `SOURCE_MANIFEST.json`, `OUTPUT/00_INPUT_AUDIT.json`: 실행 전 동결·출처·입력 parity.
- `ANALYSIS/ALL_RUN_METRICS.csv`, `CASE_DRIFT_ARM.csv`, `PAIRED_SEED_BOOTSTRAP.csv`: seed 단위 정확도/일관성 비교.
- `RELIABILITY/`: leave-one-route-out 모델과 held-out 예측·calibration 지표.
- `ASSOCIATION/`: station 단위 상관과 CI, 선형 예측, false accept.
- `PROBES/`: 대각 공분산 가정의 오프라인 진단. 확률·운용 F 검증은 차단됨.
- `EXECUTION_CONTAINERS.json`, `LOGS/`, `VERIFICATION.json`: 실제 명령·exit code와 보존 검증.
- `PUBLISH_MANIFEST.json`: 게시한 파일의 SHA256. `OUTPUT_MANIFEST.json`: 원격 전체 출력의 SHA256.

`ANALYSIS_ATTEMPT1/`의 실패 수 5,250은 빈 오류 문자열을 잘못 센 폐기된 분석입니다. 유효한 수정 결과는 `ANALYSIS/`이고 실제 run 실패는 0입니다. `FEATURES_INITIAL_PRESERVED/`는 수정 전 특징 계산의 보존용이며 학습에는 사용하지 않았습니다. `LOGS/`에는 초기 입력/저장 형식 실패도 포함합니다. 모델 pickle은 이 실행의 보존용입니다.

## 원자료 보존

전체 raw는 Git에 포함하지 않고 Snowball의 `/home/KMS/DRIVE_SIM_HEADING_SENSOR_V2_20261010_01a124ff/`에 보존했습니다. `TRACES/`, `LABELS/`, `OBS/`, `FEATURES_V2/`와 이를 묶은 `RAW_ARCHIVE.tar`가 있습니다.

- RAW_ARCHIVE.tar SHA256: `96398a070d12e4613c29e2bcd40df5088a49ecb806556971ecf3790703116b75`
- 접속 계정: case-sensitive `KMS` (`ssh Snowball`). 필요시 `scp Snowball:/home/KMS/DRIVE_SIM_HEADING_SENSOR_V2_20261010_01a124ff/RAW_ARCHIVE.tar .`로 회수하십시오.
- `DELIVERY_RECEIPT.json`에 요약 241파일 해시 일치와 전체 raw 로컬 전송 미완료를 구분했습니다. 불완전한 로컬 archive는 게시하지 않았습니다.

기존 연구 브랜치의 최신 내용을 보존하고 새 디렉터리에만 추가했습니다. 실행 사양서 c2d829e와 sensor-v2 16d22fc의 기준을 게시 브랜치 최신 revision으로 바꾸지 않았습니다. 이번 게시에서는 시뮬레이션을 재실행하지 않았습니다.
