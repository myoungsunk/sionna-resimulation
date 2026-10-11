# V01b 옵션 A 원자료 전달

2026-10-12, 요청 기준 `58c09c2318752829fed4d04efee71590c36ccb49`.

Snowball의 기존 S2 보관본에서 요청한 레거시 Method-B mount45 H 5개를 읽기 전용으로 복사했다. 새 RF 계산이나 trace 재생성은 수행하지 않았다. 요청서의 전체 SHA256·바이트·complex128 dtype·shape·finite 검사 5/5 PASS, 검증기 exit code 0이다. 총 113,705,664 bytes이다.

원본 파일 이름과 바이트를 그대로 보존해 Git 일반 blob으로 제공한다. 이 디렉터리의 `.gitattributes`만으로 LFS와 텍스트 변환을 비활성화한다. 저장소 루트 `.gitattributes`, 요청 사양서 및 기존 결과는 변경하지 않았다.

파일별 결과는 `VERIFY_DELIVERY.log`, 출처·검증 명령·입력 해시는 `DELIVERY_MANIFEST.json`, 전송 검사용 전체 해시는 `SHA256SUMS.txt`에 있다.

```bash
python research/V01B_DATA_REQUEST_20261011/verify_delivery.py research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012
```

요청한 trace 디렉터리 5개도 원격에 존재하지만 내용 검증은 하지 않았다. 옵션 A가 성공하여 옵션 B·C는 불필요하므로 실행·업로드하지 않았다.

이는 입력 복구 및 전달 완료이며 V01b 통과 판정이 아니다. 다음 작업은 이미 보유한 Native 5개와 동일 조건의 모든 저장 pose에서 원 사양대로 복소 채널·s·first-path tap을 비교하는 것이다. 이번 작업에서는 비교, HIGH_* prior 결정, V02 인정, Stage B 활성화를 수행하지 않았다. F01/F02 및 scientific_PASS 상태는 변경하지 않는다.
