# 논문 및 완료 주장 경계 — DLP-PHYS-LINK-001 R1–R5 후속

|주장|허용 여부|근거/한계|
|--|--|--|
|원 12조건 Heading 12/12 개선, XY 8/12 개선|유지|원 144 score·재현 대조, 132 trace 재사용. 같은 실험장면 3경로×4 bias이며 독립 RF 환경 12개 아님|
|R4 XY 손실과 상수 추가분산 우위|유지|R2/R5 8조건 lookup 우세, R4 4조건 상수 우세. 수정에 의한 성능 향상 없음|
|SourceFFD signed 관측과 branch-stable Jacobian 수치 정합|유지|과거 V1 9,356 stable 통과 및 52 transition 분리; 새로운 하드웨어 검증 아님|
|같은 BB prior에서 mean-only/combined 즉시 Heading 손실 역전|유지(한정)|R2/R5의 8조건 **조건별 평균**. 모든 packet/다른 prior에 일반화 금지|
|신규 R3 mu_M=mu_B null 개입과 negative 검출|이번 실행 범위에서 유효|24개 배치·25,088 호출 비교, 24개 실제 mean mutation 전부 FAIL 감지|
|기존 15503350... 원본 실행의 재게시·원본 ZIP 바이트 동일성|불허/BLOCKED_EVIDENCE|원본 Git object와 original ZIP 미확보; 새 package는 회고적 재구현의 audit repair임|
|사전 독립 감사·pre-registration 서명 복구|불허|사후 사용자 승인과 별도 기술 감사는 과거 실행 전 독립 서명으로 소급 안 됨|
|실시간 Full multipath likelihood / 완전한 시공간 상관 모델|불허|현재 경험적 분산 lookup와 국소 선형 EKF, V4 미실행|
|R4 특정 반사체가 실패의 유일 원인|불허|기하/표본 구간 집계는 설명 후보, 누적 인과 경로 분해 아님|
|V5 새 학습 모델 fresh inference|BLOCKED|모델·scaler·fold 산출물 미회수. 저장 예측값 재생/계보 검사만 인정|
|이번 R1–R5 구현의 외부 독립 감사 완료|불허|SELF_REVIEW_ONLY; 기술 검사 PASS ≠ 외부 감사 완료|