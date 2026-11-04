# C3 G2 canary 독립 DATA·보고서·기게시 원자료 감사

판정: **ACCEPT — R4_168 고정 좌표의 4개 yaw 원시 canary 범위**.

이 판정은 raw 데이터의 수치·무결성과 실행 보고서 및 기게시 원자료의 연결을 수용한다. yaw에 따른 편파·검출 tap의 물리적 효과나 source-model Hpsi를 검증한 결과는 아니다. 전체 24조건 완료, 알고리즘 채택 또는 실시간 성능 통과를 뜻하지 않는다.

## 확인한 증거

독립 검산기 `INDEPENDENT_CANARY_VERIFIER.py`는 생산 producer·QA·native_math 함수를 import하지 않았다. pinned WSL Python 3.11.17 / NumPy 1.26.4에서 원본 4조건을 한 번 검산했다. 새 PathSolver 호출·FFT·source-model 초기화는 0회다.

- 본 호출 1,028회(4×257 bins), 반복 QA 12회, 총 1,040회.
- raw rays 총 64,320개. 조건별 16,080개, bin당 62–63개, semantic groups 조건별 63개.
- 실제 complex64 per-ray phase·C-contiguous reduction과 저장 배열 exact replay.
- 별도 F64 vector replay 및 독립 scalar trig·compensated sum의 joint/각 RX closure.
- 원시 object/interaction에서 semantic chain·count·missing mask 재구성.
- 모든 RAW–bin 연결, 12개 반복 원시 배열 exact equality와 채널 검산.
- 수동 bilinear FFD 보간과 Cartesian contraction으로 1,028개 직접파 2×2 행렬, 총 4,112개 복소 coefficient와 geometry delay 확인.
- 원자료 index 1,079개 항목의 해시, 9개 코드 바인딩·새 GO·SPEC receipt·게시 revision·런타임·종료 기록 확인.

|yaw (deg)|bins|raw rays|groups|F64 closure relative L2|직접파 최대 bin 상대오차|
|---:|---:|---:|---:|---:|---:|
|0|257|16080|63|3.194e-16|8.086e-7|
|180|257|16080|63|3.546e-16|1.164e-6|
|35.7|257|16080|63|2.661e-16|7.877e-7|
|-35.7|257|16080|63|2.780e-16|1.031e-6|

F64 closure 최대 joint relative L2는 3.5459560153116525e-16, legacy closure relative L2는 0이었다. 독립 직접파 최대 bin 상대오차는 1.1644774819475287e-6으로 고정 기준 1e-4 이하다. 직접파 delay 최대 절대오차는 2.665871757977135e-16 s로 기준 1e-12 s 이하다. F64와 legacy closure는 각각 joint/각 RX의 relative L2·max-normalized 1e-8 기준을 통과했다. 원래 tolerance를 바꾸지 않았다.

실행 보고서 `G2_EXECUTION_SUMMARY.json`의 4개 행·RAW SHA·ray 수·group 수·delay·반복 판정과 `G2_EXECUTION_REPORT_KO.md`의 표시 수치 및 주장 범위를 대조했다. 직접파 수동 보간과 생산 보간의 차이는 약 1.1e-17의 relative-error 표시 차이이며 기존 판정 기준을 바꾸거나 재실행할 사유가 아니다.

## 실패 증거와 실행 횟수

첫 CANARY_001은 native frequency의 자료형 읽기 오류로 본/반복 solver 호출 0회에서 STOP했다. 기존 GO·MANIFEST·FAILURES·index와 9개 indexed artifact를 보존했다. 수정은 scalar 읽기와 새 출력·GO 연결에 한정됐고 과학 조건·threshold·예산은 변하지 않았다.

테스트003의 모듈 import명 충돌은 별도 실패 로그로 보존됐으며 테스트004 11건이 통과했다. 독립 검산기의 선행 host launch는 스크립트 파일 미존재로 exit 2였고 검산기 본체는 실행되지 않았다. 이후 동일 SHA 소스의 실제 독립 검산은 한 번 수행돼 exit 0으로 끝났다. 해당 실행과 RF 실행·게시 helper는 natural exit, ref 0, process/supervisor/job 부재 증거를 확인했다.

## GitHub 게시 연결과 한계

기게시 커밋은 `398793f7897387fdc6a6dff82fd742f50ac82aaf`, 부모는 실행 코드·GO 게시 커밋 `907af979a8827772a60e9835b2bc8b39c325c924`이다. 원격 `proposal/sm2-c3-yaw-only-audit-20261104` 브랜치의 head가 해당 커밋임을 읽기 확인했다.

새 1,089개 경로는 모두 C3/SM2_001 범위이며, 일반 Git blob 45개와 LFS pointer 1,044개의 OID·size가 검증된 로컬 payload와 일치했다. LFS payload 합계는 21,007,047 bytes다. 코드·GO·SPEC 및 기존 STOP 관련 15개 추가 경로의 게시 바이트도 확인했다. 게시 helper의 성공·원격 ref 확인 기록을 대조했다.

**원격 LFS payload를 다시 다운로드한 검증은 수행하지 않았다.** 이번 게시 판정은 Git bytes / LFS pointer OID·size, 검산된 로컬 payload, 성공한 업로드·push 기록과 원격 ref 확인에 한정된다.

이 독립 감사 receipt·검산기·검산 로그·감사 보고서는 후속 커밋 게시 대상이다. 기게시 raw 커밋에 이 신규 감사 묶음까지 들어 있다고 주장하지 않는다.

## 주장 경계

G2 원시 canary DATA를 수용한다. 기존 CANARY_001 STOP과 C0–C2 및 SM0 결과는 유지한다. G3 나머지 20조건은 별도 승인 전 HOLD이며, G4 편파·tap 분해와 Hpsi 모델 계산은 미실행이다. 이번 감사는 G3/G4 GO를 발급하지 않는다. 전체 채택 NO-GO / 실시간 HOLD를 유지한다.

필수 수정: 없음.
