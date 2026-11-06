# FP-SC-C-ONLY-OFFLINE-R1 — 별도 탐지 계약

사용자의 '모두실행'에 포함된 별도 C-only 시험. dynamic6272 + static48=6320 원본 파형, VAB/TWO_PORT_UNION.
기존 E1-02 승인/차단 파일을 변경하지 않으며 결과를 E1-02/P/M 성능으로 집계하지 않는다.
online 함수는 Hrf, 원래 noise variance만 받는다. prior/M/trusted history/model/GT 입력 없음.
생산 RevisionEvidenceAdapter → detect(mode=C)를 재사용한다. select()/history/native/필터는 금지 sentinel로 보호한다.
selected_tap=raw_tap 정확 일치. 모든 온라인 출력을 먼저 저장한 뒤 evaluator clean_H의 raw_detection으로 정답을 결합한다.
policy는 현 Policy 기본값/manifest와 SHA 일치, wrong_cut=2.0 고정. 결과를 보고 threshold 튜닝하지 않는다.
기본 정답은 유효 raw/reference tap 불일치; error size 0/1/2+tap도 별도 보고. 모사 clean reference이며 실측GT가 아니다.
TP/FP/FN/TN, 유효정답분모, score가 없는 hold, 정상전체FP율, 오류전체TP율 및 활성표본조건부율, 전체파형활성률 공개.
reference/raw invalid는 제외 이유와 전체분모를 보존. 수정 0건은 정정안전성 증거가 아니다.
경로/채널/corpus별, 연속20초 dynamic block별 기술 결과. static은 실제시각/이력 조작 없이 별도집계.
새 정책 채택/모집단 안전성 기준 없음: DESCRIPTIVE_ONLY. provider 안전성/HOLD와 무관하게 독립 결과로 남긴다.
허용위험 수치가 미정이어도 이 고정정책 기술 평가만 가능. E1-02·E2는 실행하지 않는다.
