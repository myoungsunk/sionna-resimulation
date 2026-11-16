# RX mount +45° 유한 반사면 적용 재생성 및 G4

2026-11-15 22:39:14부터 2026-11-16 00:02:10까지 Snowball에서 실행했다. 시각은 KST다. 질문 ID는 G1-RT-TB3-001과 G1-RT-TB3-002다. F1의 형상·pose·솔버 설정과 17개 노드·257개 bin을 유지하고 수신 안테나 회전에 body yaw + 45°를 적용했다. 전계 계산 전 유한 반사면 검사는 [G6를 통과한 구현](../../G6/G1_RT_TB3_G6_FINITE_FACE_REVALIDATION_20261115T111337Z_a465Ta/RESULT_KO.md)을 사용했다. 기본 코드는 커밋 a2dff24f603c2460fcf7cabf5597cbf0da7ad551이며 적용한 스크립트와 해시는 [실행 manifest](results/RUN_MANIFEST.json)에 기록했다.

| 검증 | 판정 | 결과 |
|---|---|---|
| LoS·G8 파일럿 | PASS | G-T1 × 앵커 A의 P-A 앞 3개 station, 332 pose × 257 bin의 LoS 복소 계수 341,296개와 지연이 기존의 독립 +45° 기준과 정확히 일치했다. PATHS_NEAR로 재합성한 LoS의 최대 상대 오차는 0이었다. [파일럿 기록](canary01/CANARY.json) |
| F1 재생성 | PASS | 기본 9개와 G-T1의 P-F 2개 조합에서 61,992 pose를 생성했다. 본 52,218 pose에 P-D·P-E·P-F 9,774 pose를 더했다. 26,460개 XY × 17개 노드에 솔버를 449,820회 호출했고, 27,810 pose의 PATHS_NEAR와 H를 같은 trace에서 저장했다. 경로 내보내기용 솔버 호출은 0회였다. [생성 기록](results/GENERATION_RESULT.json) |
| 유한 반사면 및 0° 대조 | PASS | 기존 +45° 결과와 비교해 G-T2의 문제 경로 4개를 각각 17개 노드에서 제외했음을 확인했다. 필터를 적용한 0° 결과와 26,460개 XY의 pose ID, 노드, 경로 개수와 제거 기록이 모두 일치했다. 11개 조합 각각에서 H_full과 H_LoS의 해시는 0°와 달랐다. [필터 검증](post_generation/GENERATION_CHECK.json) · [0° 대조](post_generation/CROSS_MOUNT_CHECK.json) |
| G4 | PASS | 전체 11개 조합·71,136관측에서 조합·arm별 P90 절대 편차의 최댓값은 G-T2 × C 본 데이터의 1.11683 × 10⁻⁶이었다. 기준은 0.005다. [G4 판정](results/gates/G4.json) |
| 봉인 | PASS | G-T2·G-V의 새 봉인 6개 조합·18개 파일의 SHA-256과 쓰기 금지 상태를 검증했다. 기존 실행의 봉인 명세와 접근 로그 해시도 확인했다. [봉인 검사](results/gates/SEAL_STORAGE_CHECK.json) · [실행 전후 확인](recovery/INPUTS_VERIFY.log) |

첫 실행은 Dr.Jit의 메모리 매핑 실패로 샤드 8개가 중단됐고, G-T1 × A의 병합에서도 `MemoryError`가 발생했다. 완료된 156개 샤드를 재사용하고 실패한 8개 샤드만 낮은 동시성으로 다시 추적했다. 이어서 G-T1 × A·B·C를 병합하고 G4를 실행했다. 첫 시도의 종료 코드 1과 `INCOMPLETE` 판정, 복구의 종료 코드 0을 각각 보관했다. [첫 시도](recovery/initial_attempt/GENERATION_RESULT.json) · [복구 기록](recovery/retry.log) · [최종 종료 코드](recovery/EXIT_CODE.txt).

최종 산출물은 3,953,822,126 B다. 조합별 원본 배열·경로 파일의 위치와 해시는 [산출물 목록](results/CASES.json)에 기록했다. 원본은 Snowball의 +45° 실행 폴더 `/home/KMS/G1_RT_TB3_FINITE_FACE_MOUNT45_20261115T133901Z_gMgSBo`에 보관한다. Git에 올라간 실행·검증 기록의 원본 바이트는 [전송 파일 SHA-256](SNOWBALL_FILES.sha256)에서 대조할 수 있다.
