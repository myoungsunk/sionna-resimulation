# M6 GM-θ 실행·검증 묶음

mount 0°, 앵커 B, B0, Full RF, R2/R4/R5, seed 10–14의 완료된 검증 자료다. 계획은 같은 브랜치의 PLAN_M6_GM_THETA_STAGED_KO.md, 커밋 ff6f42144c78aa7805fd04abe6963aa55dc5d9b9에 있다.

## 결과

G1 단독은 NO_BAND이며 LORO pooled 통과는 0/5 seed다. G1+KI의 pooled 통과는 3/5 seed다. 두 후보 모두 동결한 채택 기준은 미충족이다. 후보 54개와 G0 15개를 모두 실행했다. 69개 trace의 점수 독립 재계산 최대 차이는 3.55e−15이고 기준 판정 96개가 일치했다.

- [전체 궤적별·seed별 표](attempt_02/results/REPORT_KO.md)
- [최종 판정과 실패 위치](DECISION_KO.md)
- [특성화·지원 표](characterization_tables/attempt_02/REPORT_KO.md)
- [K4·K5·K3 및 국소 구간 표](diagnostics_tables/attempt_02/REPORT_KO.md)
- [최종 독립 검토](FINAL_REVIEW_KO.md)
- [특성화 동결 계약](characterization/RUN_CONTRACT.json)
- [재생 동결 계약](attempt_02/RUN_CONTRACT.json)
- [구현 검사](attempt_02/implementation/CHECKS.json)
- [추가 온라인 정보 차단 검사](online_barrier/CHECKS.json)
- [점수 독립 재검산](attempt_02/VERIFICATION.json)

## 파일과 재현

재생 trace는 attempt_02/implementation/seed10–14, attempt_02/seed10/seed10, attempt_02/seed11_14/seed11–14에 있다. 각 실행의 계약·명령·환경·종료 상태·출력 SHA-256은 해당 폴더의 RUN_CONTRACT.json과 EXECUTION.json에 기록했다.

실행 코드는 run_characterization.py, characterize.py, gm_replay.py, gm_checks.py, run_replay.py다. aggregate.py와 verify_results.py는 재집계·기준 판정을 검증한다. 동결한 기존 M5·D3·S2·SourceFFD 의존 경로는 계약에 남겼다. 원래 실행 경로와 소스 해시를 보존했다.

Python과 numpy가 있는 새 checkout에서는 이 폴더의 verify_archive.py를 실행하면 된다. 먼저 Git LFS의 NPZ 원본을 받아야 한다. 검증기는 SHA256SUMS, 실행 영수증, 고정 mask·격자·R_ref와 69개 trace의 점수를 다시 확인한다. evaluator 세 파일과 실행 지침·계획 사본을 inputs에 함께 넣었다. 입력 위치는 INPUT_LOCATIONS.json에 기록했다.

첫 구현 검사는 trace 메타데이터 누락으로 중단됐고 attempt_02에서 수정·재검증했다. 처음 표시용 표의 열 제목 정정 이력도 보존했다. 현재 유효한 두 표 보고서는 각각의 attempt_02다.

seed 반복은 같은 RF 실현에서 wheel·gyro 잡음만 바꾼 것이다. K2는 공통 지원 부족으로 약 2° 규모를 진단값으로 사용했고, K1′ 공통 지수에서 R4의 기여는 약 1.09%다. 추가 범위는 이번 실행에 포함되지 않았다.
