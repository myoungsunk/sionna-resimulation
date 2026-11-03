VERDICT: REDIRECT — **GO_S2_LOCKED_EVAL: HOLD**.

FINDINGS:

- **S2-R1-001 / P1 — 20초 snapshot 경계 누락.** 고정 코드 `4eeb7f5`의 `run_stage.py`가 `3.2+20`과 `23.200000000000003`을 다르게 비교하여 마지막 packet을 제외합니다. R4 Full B0/L2의 snapshot0, 총 **8개 trace**가 101개 대신 100개 packet·19.8초로 저장되고 잘못 censoring됩니다.
- **S2-R1-002 / P1 — 처치 후 상태로 모집단 분류.** `endpoints.py`의 `already_accurate`가 첫 갱신 후 `x[0]`에서 계산됩니다. R4 L2 Full snapshot0의 공통 처치 전 오류는 Heading **0.742706°**, XY **0.071713m**로 이미 정확하지만, A/C_P는 갱신 후 Heading **1.430294°**가 되어 `false`, B/D_P는 `true`로 분류됩니다. 동일 시작점 비교에서 arm별 회복 모집단이 달라집니다.

EVIDENCE:

- 원본 `DEV_001` manifest SHA256: `e2018ff24694173136fdc44442c16959294722813256321e843edd274ce61824`.
- **528 traces / 444,320 packet 갱신 / 2,000 점수행** 독립 검산 통과. 91,360개 검사, 최대 차이 `2.28e-13`.
- 960개 paired summary·bootstrap, factorial/ablation 각 1,600행, endpoint 255건 및 geometry 323건 재계산 통과. 추가 22,067개 검사.
- 32개 snapshot 그룹의 초기 x/P·입력·공통 schedule 동일성, A/B의 S1 parity, 196개 주입과 이벤트 일치 확인.
- 개발 결과의 전체 개선·채택은 미지지입니다. D_P의 R4 Full Heading 비율은 **0.914131/0.904056**으로 목표에 미달합니다. R5 Full은 Heading **1.101443/1.080044**, XY **1.135930/1.172889**로 보호 기준에 실패합니다.
- R4 XY의 실제 오차 감소는 관측되므로 단순 P 확대 효과로만 표현할 필요는 없지만, 전체 복구·결합 효과로 확대하면 안 됩니다.

MISSING_EVIDENCE:

수정 SHA 및 수정된 snapshot/endpoint 증거의 재감사가 필요합니다. 현재 작업 파일의 수정은 이 원본 실행 감사에 포함하지 않았습니다.

REQUIRED_CORRECTION:

처치 전 공통 상태로 회복 모집단을 고정하고 첫 출력 오류는 별도 기록하십시오. 등록된 20초 경계를 허용오차와 일관되게 포함하십시오. 원본을 보존하고 영향받은 snapshot·endpoint 증거를 새 revision/receipt로 제출해야 합니다. 현재 토큰은 발급하지 않습니다.