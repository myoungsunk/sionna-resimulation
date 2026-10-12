# R4_aA 원 trace 전달

요청 기준: `16388d300dc6b64ef592569c159aef4ba9cbe6b5`, `research/V01B_TRACE_REQUEST2_20261012/`.

전체 547개 위치의 원본 NPZ와 영수증 1094개를 포함한다. 실제 원자료 용량 83,891,485 bytes이다. Tier 1을 먼저 확보·검사하고 나머지 위치를 이어받았다. 선택 메시 PLY는 제공하지 않는다. 출처는 `DELIVERY_MANIFEST.json`의 Snowball KMS 기존 S2 보관본이다. 원본에 쓰거나 RF를 재실행하지 않았다.

파일별 원격/로컬 SHA256 및 크기를 전수 대조했다. 목록은 `SOURCE_FILE_MANIFEST.json`, 내려받기 후 검사는 `SHA256SUMS.txt`를 사용한다. 이 세트의 `.gitattributes`에서만 NPZ LFS·텍스트 변환을 끄고 영수증 JSON 원본 바이트를 보존한다. 루트 `.gitattributes`와 다른 checkout의 변경은 건드리지 않았다.

## 요청 검증기의 판정은 그대로 보존

Tier 1: SET R4_aA TIER 1 CHECKED 55 PASS 1 NOT_PASS 54, RESULT NOT_ALL_PASS.

Tier 2: SET R4_aA TIER 2 CHECKED 547 PASS 1 NOT_PASS 546, RESULT NOT_ALL_PASS, exit code 1.

실패 사유별 건수: `{'tag_xy': 546}`. 세부 실패 행은 `VERIFY_TIER1.log`, `VERIFY_TIER2.log`에 있다. 검증기나 요청 수용 기준을 변경하지 않았다. 원자료 전달 완료를 `ALL_PASS`로 표시하지 않는다.

파일명 tag는 요청대로 소수점 네 자리이며, NPZ와 영수증 좌표는 더 높은 정밀도로 저장되어 있다. 검증기는 반올림된 파일명 숫자를 원 좌표와 1e-9로 직접 비교하므로 `tag_xy` 실패를 발생시킨다. 별도 진단에서 지정 형식으로 좌표를 다시 쓴 tag가 파일명과 일치한 위치는 547/547, 영수증과 NPZ의 좌표가 일치한 위치는 547/547이다. 최대 반올림 차이는 5e-05 m이다. 이 진단은 실패 원인을 설명하며 원 검증기 판정을 대체하지 않는다. 형식에 맞춘 비교 방법의 correction은 요청자 판단 대상으로 남긴다.

영수증의 경로 task·앵커·nodes17·solver·재질 검사는 원 검증기에서 수행했다. 버전·runner 경고는 `{}`, 별도 shape·node frequency·receipt 키 검사 이상은 0개이다. 과거 버전과 runner 해시 분포는 `ADDITIONAL_AUDIT.json`에 보존했다. 이를 현재 solver 실행 증거로 해석하지 않는다.

```bash
python research/V01B_TRACE_REQUEST2_20261012/verify_traces_multi.py research/V01B_TRACE_REQUEST2_20261012/DELIVERY_TRACES_20261012/R4_aA/traces_R4_aA --set R4_aA --tier 2
# 위 명령의 NOT_ALL_PASS를 보존한다.
cd research/V01B_TRACE_REQUEST2_20261012/DELIVERY_TRACES_20261012/R4_aA
sha256sum -c SHA256SUMS.txt
```

G3 전 위치 경로 완전성 판정, G5 m0/m45 재생성, LoS H 복구 및 Native 비교는 수행하지 않았다. 데이터 업로드 범위만 완료했으며 `V01b FAIL`, `stage_B_allowed=false`는 유지한다.
