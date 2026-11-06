# FP-SC S1 — 6개 동적 case 가상 선택

## 범위
기준 구현 9cc34f0675a79ee94e2af39f93bf84bb3e45d587, 실행 당시 준비/승인 커밋 482d62823ea71333f7b713553de2d6736663ada5. FINAL_002의 동결 manifest 6개와 사용자 명시 S1 승인만 사용했다. 과학 코드·Policy·VAB 주안·기존 실패 기록은 변경하지 않았다. 실행은 로컬 Windows, 논리 코어 3개 affinity, BLAS/OMP/MKL 1스레드다.

## 실행 결과
동적 6,272개 × C/P/M/PM = 25,088행을 저장했다. 각 case 영수증의 COMPLETE_TECHNICAL_ONLY는 실행 완료이며 성능 승인이나 다음 단계 승인이 아니다. 전체 실행 시간은 BATCH_RECEIPT.json의 start/end에 기록된다.

| case | 파형 | S1 행 | C 교체 | P 교체 | M 교체 | PM 교체 |
|---|---:|---:|---:|---:|---:|---:|
| R2 Full | 979 | 3,916 | 0 | 0 | 0 | 1 |
| R2 Native_LoS | 979 | 3,916 | 0 | 0 | 0 | 0 |
| R4 Full | 742 | 2,968 | 0 | 0 | 0 | 1 |
| R4 Native_LoS | 742 | 2,968 | 0 | 0 | 0 | 0 |
| R5 Full | 1,415 | 5,660 | 0 | 0 | 0 | 4 |
| R5 Native_LoS | 1,415 | 5,660 | 0 | 0 | 0 | 0 |

Full PM 6/3,136시점(약 0.19%)에서만 가상 교체를 제안했다. 이것은 교체 제안 빈도이며 정정 성공률이 아니다. 나머지 보류·유지 사유별 집계는 CHECK_001.json에 저장한다. M은 직전 raw FP의 비신뢰 가설이며 VALID나 TrustedHistory를 만들지 않는다. 제안 tap을 다음 시점에 피드백하지 않는다.

## 검산
check_s1_only.py는 입력/코드/모델 잠금, manifest·승인·결과 해시, 정확한 packet-mode 키와 행 수, 시간/pose/raw 검출 일치, 원본 CIR에서 재생성한 VAB pool/후보집합 해시, 선택 후보 자격, 후보 점수식, 교체 gain/margin/conflict 조건, 모든 F00/F10/F01/F11 관측 배열을 검산한다. 원본 evaluator나 GT 참조 라벨은 열지 않는다. CHECK_001.json의 최종 상태·오차 수치가 검산 결과의 근거다. 같은 작업자의 재계산 자기검사이며 독립 감사가 아니다.

## 주장 경계와 중단 상태
실제 VAB 후보에 기존 정책을 적용한 가상 선택과 저장이 완료됐다. 현재 결과만으로 PM 6건이 정상→오류인지 오류→정상인지 말할 수 없다. C/P/M에서 교체가 없다는 사실도 해당 모드의 모든 탐지 점수가 0이라는 뜻은 아니다. S2 참조 평가·S3 단일 갱신·폐루프·운영 FP/EKF 반영은 하지 않았다. 평가용 참조와의 오차 비교는 이번에 실행하지 않았다.
S2/S3 및 E1-02/E2는 미실행. 다음 단계 ACCEPT_TO_NEXT_STAGE 검토 문서나 승인 파일을 만들지 않았다. 원래 E1 실패, VAB 개발 데이터 범위와 과거 11,095건 기록을 유지한다.

## 산출물
APPROVALS는 사용자 S1 승인 범위를 case별 manifest/code hash에 묶는다. RESULTS/{case}/ROWS.json.gz는 전 행 데이터, RUN_RECEIPT.json은 공통 잠금과 파일 hash를 포함한다. BATCH_RECEIPT.json, CHECK_001.json, 관리 프로세스 종료 기록과 로그 및 FILE_HASHES.json으로 실행·검산·게시 파일을 추적한다. 재실행은 기존 폴더를 덮어쓰지 않는다.

최종 검산: PASS_S1_SELF_CHECK, 25,088/25,088행, 후보 점수 재계산 최대 절대오차 0. 원본 CIR 재생성 후보집합 hash와 4종 관측 배열 일치. 첫 검산은 NPZ 반복 압축해제 비용으로 중단하고 입력 캐시만 수정한 검산기로 재검산했다. 이 중단은 CHECK_ATTEMPT_01과 로그에 보존하며 S1 실행은 반복하지 않았다. 실행·최종 검산 exit code 0, 관리 프로세스 전부 종료 및 참조 해제 확인.
