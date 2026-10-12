# traces_R4_aB 원자료 전달

2026-10-12. 요청 기준 커밋 `4d19561ce5449e78848685c19851b1bb2e0b3477`의 `TRACE_REQUEST_MANIFEST.json`과 두 tag 목록을 사용했다.

## 제공한 자료

`traces_R4_aB/`에 전체 Tier 2의 547개 위치에 대한 원본 NPZ 547개와 원본 JSON 영수증 547개를 보존했다. Tier 1의 40개 위치도 포함한다. 원자료 합계는 102,279,311 bytes, 가장 큰 개별 파일은 185,813 bytes이다. 선택 자료인 scene_shard 메시 PLY는 포함하지 않았다.

원격 출처는 Snowball KMS의 `/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2/traces_R4_aB`이다. 요청된 파일 이름만 읽기 전용 tar 스트림으로 받아 원본 바이트를 그대로 추출했다. 신규 RF 실행, trace 재생성 또는 원본 수정은 하지 않았다.

## 전달 검증

- 변경하지 않은 요청 검증기: Tier 1 `CHECKED 40 PASS 40 NOT_PASS 0`, Tier 2 `CHECKED 547 PASS 547 NOT_PASS 0`, 모두 exit code 0.
- 원격·로컬 파일별 SHA256 및 바이트: 1,094/1,094 일치. 전체 목록은 `SOURCE_FILE_MANIFEST.json`, 내려받은 데이터 검사는 `SHA256SUMS.txt`를 사용한다.
- 추가 읽기 전용 검사: receipt의 versions/solver/materials/runner_sha256/command/dropped_audit 키, tau/node_bins/node_freq_hz shape, node frequency finite, 요청 tag와 NPZ 좌표의 대응을 확인했다. 추가 이상 0개. 상세 내용과 과거 생성 환경 버전은 `ADDITIONAL_AUDIT.json`에 있다. 이는 영수증에 기록된 버전 확인이며 현재 환경에서 해당 solver를 실행한 증거가 아니다.
- 요청 매니페스트·tag 목록·검증기 SHA, 전송 출처, 실행 상태는 `DELIVERY_MANIFEST.json`; 원 검증기 출력은 `VERIFY_TIER1.log`, `VERIFY_TIER2.log`에 보존했다.

```bash
python research/V01B_TRACE_REQUEST_20261012/verify_traces.py research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB --tier 1
python research/V01B_TRACE_REQUEST_20261012/verify_traces.py research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB --tier 2
cd research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012
sha256sum -c SHA256SUMS.txt
```

## 저장 방식과 판정 범위

전용 디렉터리 `.gitattributes`에서 NPZ의 LFS 및 텍스트 변환을 끄고 JSON 영수증도 원본 바이트를 보존한다. 루트 `.gitattributes`, 요청서, 기존 결과, 원격 원본은 변경하지 않는다.

이번 작업은 자료 제공과 형식·전송 무결성 검증이다. 사양서의 B 기준인 `rf_b_apply.py` m0/m45 재생성 SHA 대조와 C 기준인 Native 경로별 비교는 수행하지 않았다. 따라서 Tier 2 형식 PASS를 재생성 자가 검증 완료 또는 원인 가설 지지로 해석해서는 안 된다. 모든 자료를 제공하여 후속 비교를 수행할 입력은 갖추었지만 V01b FAIL, `stage_B_allowed=false`를 변경하지 않았다.
