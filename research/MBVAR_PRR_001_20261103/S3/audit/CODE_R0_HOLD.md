VERDICT: REDIRECT — 동결 SHA `f0877cfc5b852158ef5a5712f97021d91a98670a`는 HOLD. `GO_S3_DEV`를 발급하지 않습니다.

FINDINGS:

1. **P1 — 원본 packet 식별자 검증 누락.** `History`와 foreground는 연속 index·timestamp를 검사하지만 `pose_id` 중복을 차단하지 않습니다. 10개 합성 packet에서 `pose_id[5]=pose_id[4]`로 바꿔도 replay가 완료됐습니다. 요구된 원본 likelihood ledger와 중복 packet 음성시험을 충족하지 못합니다.
2. **P1 — S2 최종 감사 기록의 불변 연결 누락.** S3 grant는 현재 head의 `FINAL_RESULTS.json`에서 상태·코드·manifest를 확인하지만, 승인된 `dfd90f4`의 기록 자체를 고정하지 않습니다. 해당 기록의 `published_commit`을 영값으로, C4/C6/adoption을 SUPPORTED/GO로 바꾼 음성시험에서도 `GO_S3_DEV` 분기가 통과했습니다. 잘못된 manifest는 거부됐습니다.

EVIDENCE:

- 합성 다중 episode: 두 arm × 3회 재처리의 독립 cold 검산 통과.
- 실제 R4 Full 310 packet 및 R5 Full 700 packet의 제한된 QA 통과. identity의 x/P·shadow·risk machine·geometry를 대조했습니다.
- 독립 계산 총 4,486개 검사, 최대 차이 `1.80e-14`.
- history 누락·중복 index·순서 오류·오염 config·stale 후보·PSD·변화량 경계·R precision/correlation·timestamp drift·짧은 buffer 음성시험 통과.
- 실제 clock을 이용한 5Hz 합성 timing 확인. 과학적 점수·성능 결과는 생성하지 않았습니다.
- 소스와 실행 로그는 도구 transcript에 있습니다. 파일은 수정하지 않았습니다.

MISSING_EVIDENCE:

- Linux runner에 `psutil`이 없어 RSS/HWM 계측만 `/proc` 기반 대체 모듈을 사용했습니다. Windows 성능·메모리 측정의 독립 인증은 아닙니다.
- 수정본은 이번 동결 SHA 감사 대상이 아닙니다.

REQUIRED_CORRECTION:

- canonical pose-ID 순서를 history·checkpoint·candidate에 연결하고, 중복·누락·순서 불일치·후보의 마지막 식별자 불일치를 거부하십시오.
- S3 grant가 승인된 S2 최종 기록의 불변 commit 및 digest를 검증하도록 연결하십시오.
- 새 동결 SHA에서 두 결함과 관련 회귀시험을 재검증해야 합니다.