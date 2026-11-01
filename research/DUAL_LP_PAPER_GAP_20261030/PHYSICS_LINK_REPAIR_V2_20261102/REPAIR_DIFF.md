# R1–R5 변경 명세 (append-only)

|ID|기존 상태|신규 파일·실제 검증|영향을 받는 수치|
|--|--|--|--|
|R1|원본 커밋 `15503350…` 회수 실패, 문서만 GitHub 게시|기존 원본 MISSING 명시, 보관 중인 재구현 ZIP의 SHA와 새 코드/검증 결과의 GitHub 원격 파일 SHA 대조를 `RECONSTRUCTION_PUBLICATION_RECEIPT_V2.json`에 기록|EKF/성능/trace 불변|
|R2|CONFIG_LOCK의 승인 상태 모순|원 파일을 보존하고 `RUN_ADMISSION_RECORD_V2.json` 신설: 당회 사용자 R1–R5 지시, code/source/input/config 해시, 사후 실행 권한, 독립 사전 승인 부재를 별도 명시|EKF/성능/trace 불변|
|R3|`copied_mean_identity_pass=True`가 미실행이었음|실제로 `mu_M_test=mu_B.copy()`를 MB 호출 경로에 대입, BB 호출과 혁신·gain·Knu·post x/P·NIS·gate·signed term 비교. 각 조건의 수치·표본 수 기록. 수용된 packet의 mu를 고의 변경하면 검사 실패|기존 loss/trace 불변|
|R4|Schur/prior/J/control 등이 PASS 논리와 분리|원 기록된 state/P를 재계산하고 full trace의 prediction, h/J/R/nu/S/K/NIS/accepted/post x/P, 원 CONTROL/legacy score, shadow Schur, null test의 필수 check_id 5,288개 **사전 선언**. 모든 필수 ID가 존재·유일하고 전부 PASS해야 통과. 고의 주입 67종 검출, 누락 ID는 BLOCKED|기존 성능 불변|
|R5|FIRST_DIVERGENCE에 최초 시점·gate 수만 기록|144개 두-arm 스냅샷의 k−1 state/P→rho/sigma→u→prior x/P→h/J/mu/R→innovation/S/K/NIS/mask→post x/P. 같은 prior shadow 48개 별도 원장. 실제 trace SHA 포함|기존 성능 불변|
|R6(선택)|물리–갱신 도표의 case별 설명 부족|기존 physics × shadow를 exact case/pose/time으로 join. 기하별 n_all/n_used/n_stable 및 signed Kε/Kδh 출력. 누적 원인 및 특정 반사체의 단일 인과 주장 금지|EKF 재실행 없음|

## 방어적 코드 변경 기록

- 새 코드만 작성하고 과거 `code/shadow_validation.py`, `code/replay_validation.py`, `code/quality_and_comparison.py`를 **수정하지 않았다.** R3의 과거 literal PASS는 새 V2 실계산에 의해 교체된 것이 아니라 V2에서 별도 판정으로 명시적으로 정정됨.
- R4 첫 개발 실행에서 고의 pose/time 오염 2건을 검출하지 못해 FAIL로 종료했다. 검사값을 PASS 집계에 포함하도록 보완하여 67/67 PASS. FAIL 이력 `logs/repair_run_02.log` 보존.
- full 144 trace의 scalar motion predictor는 원 `core.transition/predict` 수식과 같은 sinc_half(F,G,Q) 구조를 벡터화해 검사 시간을 단축했다. 본래 원 상태 예측기를 교체하지 않았음.
- R1 원격 인증은 GitHub branch/commit/blob 조회에 근거하여 별도 게시 영수증으로 완료. 패키지와 GitHub에 공개한 아티팩트 범위를 구분.