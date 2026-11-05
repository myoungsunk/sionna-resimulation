# 구현자 인계 — 먼저 E0, 그다음 단계별 승인

현재는 제안 초안이다. 이 문서를 받은 즉시 RT·전체 EKF·새 정책 sweep을 실행하지 않는다.

## 첫 요청

`01_EXECUTION_PLAN_KO.md`와 `04_RUN_CONTRACT_DRAFT.json`을 읽고 H0/E0만의 구현 사양을 작성한다. 원본 detector/SourceFFD range convention·μ/R·FP 선택과 noise recipe를 정확히 재현할 수 있는지 자료를 준비한다. 공개 seed10·clean RF를 이용한 사전 canary와 noisy replay를 같은 결과로 혼합하지 않는다.

E0 사양에는 원시 H/CIR, timeline/pose, gyro/odom, original prior/P, means/R, FFD bank, environment를 실제로 받을 수 있는지 항목별로 표시한다. LFS 파일 목록 또는 OID만 있으면 PAYLOAD_UNVERIFIED이다. 없으면 그 파일과 정확 schema·shape·dtype·hash·필요 실험을 지정해 데이터 요청서를 낸다.

## 지금 바꾸면 안 되는 것

원본 S1–S3·C0–C3 결과/계약, baseline MB_VAR, original FP definition, 학습 mean/R, 기존 승인 기준을 수정하지 않는다. old GO를 새 selector 실행에 재사용하지 않는다. 변환된 측정이 원래 분포와 같다고 가정하여 성공을 선언하지 않는다.

## 각 단계 완료 보고 형식

“계약/코드/입력 SHA → 실행한 정확 범위와 counts → 자체 QA → 독립 감사의 실제 범위 → 가설별 지지·반례 → 다음 단계 승인 여부” 순서로 보고한다.

실데이터 계산 없이 synthetic unit tests만 통과했다면 그렇게 표현한다. 원 raw payload를 읽지 않고 summary만 재계산했다면 그 한계를 명시한다. 감사 template의 빈칸을 PASS로 채우지 않는다.

## 향후 감사자 인계

구현자와 분리된 checker/runner가 `03_AUDIT_AND_CLAIM_REVIEW_KO.md`의 단계별 항목을 검증한다. 작성자·구현자와 같은 agent/session에서 점수를 재집계했으면 SELF_CHECK이며 INDEPENDENT_ACCEPT가 아니다.

정상 FP 보호와 wrong→correct rescue가 동시에 성립하지 않으면 E2의 선택적 정정 주장은 보류한다. FP정정이 편파오차를 줄여도 E4에서 R2/R5·LoS 또는 공분산 보호에 실패하면 전체 채택 NO-GO를 유지한다.
