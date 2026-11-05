# FP-SC-001 E1-01 Snowball 실행·검산 결과

**실행 완료 / 별도 구현 checker 재계산 통과 / 관측 기준: `OBSERVED_THRESHOLD_NOT_MET` / E2 미실행.**

## 범위와 출처
- GitHub 게시 기준 커밋: `b05fb4c8e20666b2c839bb350657b0734cee8628`.
- 고정 과학 구현 커밋: `ce4ac73cae7debe3754c7b7b0b0008ca66fdbf5d`. 후보 생성·검산 코드와 threshold 변경 없음.
- 입력 35개, 141,841,815 bytes: 로컬 34개와 GitHub의 기존 주파수 파일 1개를 고정 SHA256으로 검증 후 전송. 전송 archive의 양쪽 해시 일치.
- 실행: Snowball `KMS`, 전용 Docker, Python 3.12.14와 고정 scientific package 버전, 수치 연산 1 thread.
- 원 환경의 Python 빌드·CPU/BLAS 차이는 실행 전 `AMENDMENT.json`과 새 환경/실행 lock에 기록. **원 동결 환경과 완전히 같은 실행이라는 주장은 하지 않음.**
- 사전 61개 시험 통과, 원 코드 commit 바이트·입력·H0 근거·단계 범위 검증 통과.

## 실행 결과
- 동적 6,272 + 정적 G4 48 = **6,320 waveform**, 두 후보 모드 **12,640행**, 누락 없는 범위 검사.
- production: 164.4초, exit 0; 별도 checker: 143.4초, exit 0.
- checker 판정: `PASS_CANDIDATE_AVAILABILITY_REPRODUCTION`. 6,320 waveform과 12,640 packet-mode 행 및 후보/lobe/집계 증거를 재계산.
- 유효 원 tap 보존: `True`.

주 판정은 동적 Full의 ≥2tap 오류에서 TWO_PORT_UNION 후보의 usable 참조 recall이며, 전체와 분모가 있는 각 경로가 모두 95% 이상이어야 한다.

| 범위 | usable 참조 후보 포함 |
|---|---:|
| 전체 | 79/87 (90.80%) |
| R2 | 18/19 (94.74%) |
| R4 | 13/14 (92.86%) |
| R5 | 48/54 (88.89%) |

참조 후보 미포함 8건은 `MISSING_REFERENCE_CASES.json`에 보존했다. 실패를 보고 파라미터를 바꾸거나 재실행하지 않았다.

## 검산과 주장 경계
별도로 구현된 기존 checker를 동일 담당자가 실행한 **SELF_REVIEW_WITH_SEPARATE_CHECKER_CODE**이다. 외부 독립 감사/승인은 아니며 `external_independent_accept=false`를 유지한다. 기술적 재계산 일치와 95% 후보 가용성 기준 충족 여부는 별개이다.

이 결과는 이미 노출된 동일 RF의 후보 가용성 시험이다. FP 교체, 오선택 탐지 성능, 거리·편파 개선, EKF 개선, noisy RF 강건성, 새 환경 일반화, 실시간 성능을 입증하지 않는다.

**E1-02 이후 및 E2–E5는 실행하지 않았으며 GO=false이다.** 기존 E0 제한과 취소된 GitHub Actions 증거는 그대로 보존했다. 본 실행은 그 실패/취소 결과를 덮어쓰지 않는다.

## 근거
- `RUN_001/RUN_MANIFEST.json`, `SUMMARY.json`, 상세 CSV와 gzip 후보/lobe 로그
- `REVIEW_001/E1_RESULT_REVIEW.json`, `NUMERICAL_COMPARISONS.json`, 재계산 CSV
- `PRODUCTION.log`, `CHECKER.log`, 각 명령·시각·종료코드 receipt
- `PUBLICATION_VERIFICATION.json`, `PACKAGE_SHA256.json`, `REMOTE_EXECUTION_METADATA.json`
