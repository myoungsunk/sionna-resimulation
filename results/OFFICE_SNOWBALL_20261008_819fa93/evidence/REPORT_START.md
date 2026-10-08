# 사무실 Snowball 검증 및 전체 실행 시작

- 기준 커밋: `819fa93b152ca3cdf66297af09ff073880bd9d9b`, `claude/office-e-layout`.
- 최신 대응서와 R1–R3 수정 확인. 관련 오프라인 검사: 62 passed, 1 skipped, 3 deselected. 생략한 3개는 로컬 셸 검사이며 실제 Snowball 실행기로 추가 확인했다. 저장소 전체 테스트 통과를 주장하지 않는다. 대응서의 과거 계약 파일 부재에 따른 전체 테스트 3개 실패는 이번 검사 범위 밖이다.
- Snowball 접속 계정 KMS. 실행 원본 90개 파일 SHA-256 모두 Git blob과 일치. 두 LP 뱅크 해시는 BANK_MANIFEST와 일치.
- 환경: `rt-dual-engine:s2-deps-r2-20260928`, image ID `sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f`; Sionna RT 2.0.1, Mitsuba 3.8.0, Dr.Jit 1.3.1, NumPy 2.4.6, SciPy 1.17.1.

## 실제 검증 결과

1. 슬랩 검증: PASSED, 단일 판 상대오차 최대 약 1.3e-5, 기준 1e-4. `slab_check/SLAB_CHECK.json`.
2. 기하 LoS: 35곳, 열림 25 / 막힘 10, 불일치 0. `geom_check/GEOM_LOS_CHECK.json`.
3. 시험: 6곳 × bin 3개 × yaw 19개, 호출 총 342회. 종료 0, 유효 6 / 무효 0, 누락·중복·예상 밖 출력 없음. `pilot_stride128_lf/VERIFY.json`, `RUN_STATUS.json`, 위치별 receipt.
4. 전체: 35곳 × bin 257개 × yaw 19개, 4코어. `office-full35-819fa93` 컨테이너 RUNNING 확인. 2026-10-08 02:56:50 UTC 시작(11:56:50 KST). 위치 계산 로그에서 첫 bin 진행 확인. **전체 결과 PASS나 완료는 아직 성립하지 않는다.**

시험 호출 평균시간의 위치별 중앙값은 약 0.648초. 단순 외삽은 약 7.7시간이며 초기화·마지막 묶음·부하에 따라 달라진다.

## 실행 경로와 보존

원격 루트: `/home/KMS/OFFICE_SNOWBALL_20261008_819fa93`.
전체 출력: `full35_stride1`; 시험 출력: `pilot_stride128_lf`.
전체는 BIN_STRIDE=1, CORES=4, PYTHON=/opt/rt-env/bin/python, 기본 전체 위치 목록으로 실행.
완료 판정은 전체 검증 종료 0 및 `full35_stride1/logs/SWEEP_COMPLETE`로만 한다.

Windows의 Git archive 전송 묶음에 CRLF가 적용되어 첫 셸 실행은 127, 다음 시험은 위치 이름의 숨은 CR로 검증 종료 1이었다. 원본 Git 파일은 LF였다. 배포 텍스트를 LF로 복원하고 전체 90개 SHA를 Git blob과 대조한 뒤, 새 시험 경로에서 통과했다. 이전 `pilot_stride128`, 컨테이너 로그, 전송 tar와 실패 증거는 원격에 보존했다. 저장소 소스 변경이나 커밋·푸시는 하지 않았다.

책상은 윗판 한 장, 재질은 기존 가정이며 분석 코드는 이번 실행 범위에 포함되지 않는다. NPZ 원시 출력은 원격에 보존하고, 통과 단계의 작은 증거 파일만 로컬로 회수했다.
