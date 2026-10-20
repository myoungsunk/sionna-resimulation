# S1 N1 이벤트 검증 — 입력 차단 보고

S1은 **BLOCKED_INPUT / NOT_ESTABLISHED**다. 77개 원본 이벤트 명단을 확정하지 못하여 사전등록 lock과 재귀 실행을 시작하지 않았다. 아래 PASS는 입력 감사 자체에 한정한다. 필터·N1·D7 검증 PASS를 뜻하지 않는다.

| 항목 | 확인 결과 |
|---|---|
| 요청 모집단 | 기존30 + 신규47 = 77; 원본 행 단위 명단 미확보 |
| 고정 물리 결과의 신규 이벤트 | 61 = C01 14 + C02 14 + C03 18 + O01 1 + O02 5 + O03 9 |
| SPEC / aggregate 대조군 | 선택12개; 전체77개가 아님 |
| 엔진 | 034e57a7209a3bd1bb8857b24fd85c64942e1258 원본과 로컬 bytes 동일 |
| 엔진 SHA256 | e725f92bd74e6a845b07418d6f3b7a2974a518b2cd03b16969518bf879ee11b8 |
| T2 센서 lock SHA256 | b05e7ead6cf658d20a4830094cec56332ffcc839e7dccf04fd4ce3a1f86ccef0 일치 |
| 기존 주로 실제 los_exists | 원본 플래그·producer 근거 미인증; true로 채우지 않음 |
| 신규 LoS 대응 | 기존 T2 소스·성공 receipt 확인; S1 원본 전체 재다운로드·재인증은 미실행 |
| 새 재귀 / Actions / artifact | 0 / 없음 / 없음 |

## 명단 불일치와 검색 범위

`fcf072599ed92382284e1549804621c2663b997a`의 crosscase 보고서는 기존30/신규47을 명시하나, 78행에서 재귀 코드·결과 위치를 `/mnt/data/POWERJOINT_CROSSCASE_HEADING_CAUSES_20261020`으로 제시한다. 해당 git 디렉터리의 9개 파일에는 원본 열거 CSV·재귀 실행 코드가 없다. CHAIN_VALIDATED external_evidence의10개 요약 파일과 artifact12188722472의41개 멤버 목록에서도 찾지 못했다. 이는 확인한 범위의 미확보이며 모든 가능한 저장소에 원본이 없다고 주장하지 않는다.

고정 `physical_event_contrast.py`와 run39349484700의 물리 출력에는 신규61개가 있다. `aggregate_best_worst.py`는 historical skip reference가 있는 선택 대조군을 취한다. 온라인 SPEC12나 물리61개를 원본77개로 대체하지 않았다. 행 수, horizon, 과거 skip 효과를 보고61개에서47개를 고르지 않았다.

`EVENT_PROVENANCE_DRAFT.json`은 고정 소스 원본 bytes·Git blob/SHA256, 물리 출력 멤버·원래 CSV 행, 과거 T2 입력 receipt와 검색 결과를 보존한다. `PHYSICAL_61_CANDIDATES_NOT_S1_ROSTER.csv`는 그61개를 열람하기 위한 표이며 **S1 EVENT_TABLE이나 신규47개 인증 결과가 아니다**. `T2_full_post30_horizon_available`도 과거 T2 clock에 대한 참고값이며 이 표에서 행을 제외하거나 새 모집단을 정의하지 않는다.

## 필요한 입력

1. 원래 legacy30 및 new47 열거표: case / bin / visit / RF 행 i0·i1 / t_start·t_end / 원본 clock·pose ID 대응.
2. 위 명단을 생성한 원래 재귀 이벤트 enumerator와 입력 매핑 코드. 보고서의 `/mnt/data/POWERJOINT_CROSSCASE_HEADING_CAUSES_20261020` 원본 폴더 또는 보존 asset이 적합하다.
3. 기존7조건의 실제 per-pose LoS existence/validity 원본 metadata 또는 frozen H/SAMPLES와 불변 ID·hash로 연결되는 producer 근거. H_LoS 파일명이나 detector 동작만으로 존재를 인증하지 않는다.

명단을 복원한 뒤 고정 POST30 RF-run 규칙과 행 단위 비교를 먼저 완료해야 한다. 이후77개 roster와 D7·gate·분모·제외 규칙을 포함한 `PROTOCOL_LOCK.json`을 **새 재귀 실행 전에** 커밋한다. 아직 원본 명단이 없으므로 lock을 확정했다고 표시하지 않았다.

## 실제 검사와 보존

`audit_inputs.py`를 로컬 Python으로 실행했다(exit0). 고정 commit의 엔진을 GitHub API로 읽어 로컬과 byte identity를 확인하고, 센서 lock SHA, embedded source bytes의 SHA256·Git blob SHA1, 물리 이벤트61개 unique key·route별 개수를 검증했다. 이 코드는 RF 관측 추출·학습·filter 실행을 하지 않는다. `INPUT_AUDIT.json`에 실행 시각과 관측 branch head를 기록했다.

새 재귀가 없으므로 POWER1 재현, gate mismatch, 독립 scorer, D7 arm parity는 **NOT_RUN**이다. 새 runtime 오류는 없으며 미충족 입력은 `ERRORS.json`에 차단 항목으로 남긴다. 원래 S0 수치·판정·보존 receipt·trace는 변경하지 않았다. S0는 ACCEPT_FOR_S1이지만 잔차 평균 조건은 여전히 OPEN / NOT_ESTABLISHED다. S2/S3와 새 RF 실행은 하지 않았다.

## 주장하지 않는 것

N1의 지지·반증, D7 회복, 필터 구조 변경의 인과적 필요성, 원래77개 복원, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 입력 감사의 PASS를 과학 판정으로 승격하지 않는다.
