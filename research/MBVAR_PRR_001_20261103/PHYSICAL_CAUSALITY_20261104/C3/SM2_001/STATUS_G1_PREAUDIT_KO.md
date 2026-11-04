# C3 G0 통과 / G1 코드감사 제출

PR #35 초안의 G0 독립 SPEC 감사는 최초 REDIRECT였다. exact 입력·QA 기준·Hpsi 정의·대비 규칙을 상세 동결 계약에 추가했으며 재감사 SPEC_APPROVED를 받았다. 최초 판정과 재감사 원문을 audit/에 함께 보존했다.

G1 신규 yaw 전용 producer·QA·권한검사·launcher·음성검사를 작성했다. SM0 원본은 변경하지 않았다. pinned WSL Python3.11.17/NumPy1.26.4의 저장된 기존 SM0 ray를 이용한 오프라인 9개 검사가 통과했다. 이는 자기 검사이며 독립 CODE/DATA 감사와 다르다. 로그와 manager 종료 확인은 logs/에 보존했다.

현재 신규 RT 호출 0, G4 source-model 초기화 0. 독립 CODE 감사 및 exact SHA GO 발급 전에는 G2를 실행하지 않는다. G2 허용 범위는 R4_168 네 yaw 본캡처1028회+지정 반복 QA12회=1040회 상한이다. G3 잔여20은 G2 독립 DATA PASS 이후 별도 사용자 승인 전까지 HOLD이다. C0–C2 재실행 없음. 전체 알고리즘 NO-GO/실시간 HOLD 유지.
