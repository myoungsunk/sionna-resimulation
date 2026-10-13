# I0 RF 자료 위치 재감사와 정정

이 문서는 최초 I0 보고서의 자료 미확보 설명을 갱신한다. 원래 run_01의 재현 결과와 manifest는 유지한다. I1은 실행하지 않았다.

## 직접 확인한 내용

- 데이터 브랜치 `claude/pensive-johnson-kxx6t6`의 `f1d6d9fc984feb2c9a3b5fba36ca9aaa31fbe933`에는 r23_run.py, r23_gm_unit_test.py, gm_ekf.py, p3_common.py가 있다. 최초 조사 대상인 후속 코드 브랜치의 source snapshot에 없다는 사실을 전체 저장소의 미확보 사유로 사용한 것은 불완전했다. 실행기 소스는 확보했다.
- 별도 RF 브랜치 `research/ekf3-independent-p0-20261013`의 `ce38566d2183f6a76c349b4e39a2a000f27e542a`와 위 데이터 브랜치에서 Full H 12개, tracked LoS H 7개, 주파수 파일의 Git object 위치를 확인했다. H 19개의 P0 SHA 일치는 사용자가 확인한 결과이며, 이번 위치 감사에서는 이 19개의 bytes를 재해시하지 않았다.
- freqs_hz.npy는 실제 bytes를 읽어 SHA256 `fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8`를 확인했다. 이것은 현재 확보한 파일의 동결 해시이다. P0에 당시 해시가 없으므로 과거 실행 당시 동일 bytes를 사용했다는 직접 증명은 아니다.
- E1 모델 SHA가 P3_FREEZE_ADDENDUM의 값과 일치한다. p3_detector_candidates.py 및 현재 p3_common.py도 addendum의 SHA와 일치한다. 모델에는 R2/R4/R5 LORO fold 계수와 특징 스키마가 실제로 있다.
- GitHub Release `v01b-r-los-h-m45-20261012`에는 LoS m45 5개가 있다. 실제 다운로드 결과와 P0 비교는 `rf_location_addendum/LOS_RELEASE_VERIFICATION.json`에 기록한다. 다운로드한 원본은 별도 로컬 cache에 보존하며 Git에 중복 업로드하지 않는다.

## 남는 한계

1. R23_RESULTS.json의 과거 command/인자/input SHA 부재는 사후 소스 확보만으로 복구되지 않는다. 향후 재실행은 현재 확인한 입력·코드를 새 manifest에 동결해야 한다.
2. 적합 당시 p3_common.py의 SHA `54af036b...`와 현재 `79fa104a...`는 다르다. addendum의 적합 함수 불변 설명은 문서 증거이고, 적합 당시 파일의 바이트 동일성 검증은 아니다.
3. LoS 원본은 E1 재적합 계보 검증에 필요하다. 저장된 E1 계수로 R2-3 추론을 실행할 때는 Full H와 주파수를 사용하므로 LoS 및 과거 적합 코드의 부재를 현재 추론의 필수 차단 사유로 삼지 않는다.
4. 현재 위치 감사는 RF 통합 재생이나 R2-3 실험의 재실행이 아니다. 전체 I0는 INCONCLUSIVE, RF 통합 재현과 I1은 NOT_RUN이다. 신규 seed의 전역 미사용 확인도 별도로 남아 있다.

R23 소스에서 CIR RNG는 `[20261013, case_idx, tag, snr]`로 확인됐다. 초기 계보 조사에서 SNR 항을 생략한 설명은 이 정확한 구성으로 대체한다.

출처·Git blob ID·소스 SHA·Release URL은 `rf_location_addendum/AUDIT.json`을 따른다. 복사한 소스는 감사용 reference이며 기존 동결 실행기를 덮어쓰지 않았다.
