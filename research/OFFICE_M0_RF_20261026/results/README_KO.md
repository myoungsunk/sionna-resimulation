# Office O01/O02/O03 Mount 0도 완료 결과

**상태: OFFICE_M0_RF_QA_PASS.** 2026-10-27 01:49 KST 완료. 총 소요 약 3시간 24분.

- 저장 브랜치: `research/office-mount0-rf-20261026`
- 계산 소스: `b38a65748ae75c6678d87a6a963e8102ba392a78`
- 실행 위치: Snowball, `/home/KMS/OFFICE_M0_RF_20261026_01a17631`
- 범위: Office O01/O02/O03, Mount 0도, Full/Direct-LoS 채널 쌍, 257개 주파수.
- 검증: 파일럿 3개를 포함한 42개 배치 모두 종료 코드 0, 총 811개 RF 지점, 416854회 solver 호출.

## 결과 다운로드

[완료 결과 및 원시 검증 자료 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/office-m0-rf-20261026-complete)

| 파일 | 내용 |
|---|---|
| O01_M0.tar.gz | O01, 192개 RF 지점의 Full/Direct-LoS 채널과 시간순 pose 및 검증 기록 |
| O02_M0.tar.gz | O02, 207개 RF 지점의 Full/Direct-LoS 채널과 시간순 pose 및 검증 기록 |
| O03_M0.tar.gz | O03, 412개 RF 지점의 Full/Direct-LoS 채널과 시간순 pose 및 검증 기록 |
| OFFICE_M0_RAW_VALIDATION.tar.gz | 42개 배치 전체, raw_paths, 배치별 QA/재생 검증/해시, 전체 pose, 로그, 실행 입력 및 제어 코드 |

대용량 바이너리는 이 브랜치의 완료 커밋을 가리키는 Release에 첨부한다. 이 폴더에는 검증 기록과 파일별 SHA-256 및 다운로드 주소를 저장한다.

## 검증 자료 읽는 순서

1. `CAMPAIGN_RECEIPT.json`: 전체 및 경로별 PASS, 입력 해시, 채널 shape, LoS 유무.
2. `BATCH_QA_RECEIPTS.json`: 42개 배치의 원본 QA 기록 모음.
3. `SNOWBALL_STATUS.json`: 실행 시간, 배치별 종료 코드 및 실패 목록.
4. `FULL_PLAN.json`, `PREPARATION_RECEIPT.json`, `PREPARED_SHA256.json`, `SOURCE_SHA256.json`: 계산 계획과 입력 계보.
5. `ASSET_MANIFEST.json`, `SHA256SUMS.txt`: 다운로드 파일의 크기와 SHA-256. 모든 파일은 Snowball 원본과 로컬 전송본의 해시 일치를 확인했다.

검증 기준은 relative complex 1e-4, delay 1e-12 s, S absolute 1e-4, FP tap 일치이며 기존 기준을 유지했다.
O01/O02는 LoS 부재 0개, O03은 LoS 존재 176개 / 부재 236개이며 차폐 상태를 보존했다.

## 해석 범위와 계보 주의

이번 PASS는 RF 데이터 생성 및 정해진 검증 기준의 통과다. Sensor V2 생성, 보정 학습, 위치추정 성능 또는 일반화 성능을 검증한 결과는 아니다.
원본 실행 기록은 수정하지 않았다. 일부 원본 ARCHIVE_SHA 기록의 raw_paths 설명은 Actions 보존 방식을 가리키지만, 이번 실제 원시 자료는 `OFFICE_M0_RAW_VALIDATION.tar.gz`의 `BATCHES/<batch_id>/raw_paths`에 포함된다.
FULL_PLAN의 원본 M45 참조 필드는 입력 계보로 보존했으며, 실제 Mount 0도와 pose/계획 해시는 PREPARATION_RECEIPT 및 CAMPAIGN_RECEIPT를 함께 확인한다.
