# 독립 감사 기록

**독립 감사 판정: ACCEPT. 과학 판정: INCONCLUSIVE.**

감사자: 이 검증에 한해 사용자가 허용한 독립 `/root/signed_cov_audit` 에이전트. 감사자는 읽기·독립 검산을 수행했고 구현 변경이나 실제 RF 적합을 맡지 않았다. 아래는 감사자가 이 대화에 반환한 최종 판단을 구현자가 기록한 것이다. 구현자 자체 검사를 독립 감사로 표시하지 않는다.

## 최종 감사 판단

- 검증 실행과 최종 INCONCLUSIVE 판정을 수용한다. signed 가설이 지지됐다는 뜻은 아니다.
- R4의 s-only(S0) 대비 개선, unsigned 대비 미확인, R2의 반대 방향 contrast가 정확히 구분됐다.
- R5·시간 holdout·N2/N3의 지원 부족과 G-T1의 시간정보 부재를 성공으로 처리하지 않았다.
- 이전 실패·수정 증거와 원 P3 파일을 보존했다. 불필요한 범위 확장은 확인되지 않았다.
- 현재 판정에 필요한 누락 증거와 필수 수정 사항은 없다.

감사자는 단계별 manifest 50개 항목의 해시 일치, 주 bootstrap CI·contrast의 독립 재계산 일치, 주 적합 전 보조 계획 동결·승인 해시 포함, 보조 대조·앵커 A·R5 명시적 집계와 보고서의 일치를 확인했다.

**감사한 REPORT_KO.md SHA256:** `cab7838dd7cc9893b90302914f27c56cfbe79874a9733534e279fb35c3c6e3f1`

## 실행 전 감사와 수정 이력

1. attempt01의 TRUTH_MISMATCH는 STOP 처리했다. 실제 RF 생성 입력의 6자리 직렬화와 evaluator 원정밀도 차이를 확인한 뒤, 실제 RF 생성 pose를 primary로 삼고 round6 exact provenance를 검사하는 수정안을 수용했다. 초기 실패는 보존했다.
2. attempt02 P0의 입력·관측·SourceFFD·미분 검사를 독립 확인해 해당 범위 ACCEPT를 발급했다.
3. 초기 P1의 donor 궤적 간 매칭을 REDIRECT했다. donor별 선매칭으로 수정한 p1_revision_02의 수치·분할·해시를 확인해 ACCEPT했다.
4. 초기 P2의 작은 고유값 제거가 정확한 중복 이외에도 적용되는 결함을 REDIRECT했다. exact duplicate 축약, 불일치·near-singular 비중복 중단 및 추가 fitter 검산을 독립 재실행해 revision02의 T00–T09 모두 PASS를 확인했다.
5. 실제 P3 runner의 합성 holdout 교란이 donor mean/p99/blocks/fit에 영향을 주지 않고, HOLDOUT_IN_DONORS를 중단하는지 독립 확인한 뒤 해시를 지정해 ACCEPT_PRE_FIT를 발급했다. 해당 기록은 `../AUDIT_PRE_FIT.json`이다.
6. P3 CI·contrast를 독립 재계산했다. 최종 보고서·보조 대조·외부 지지·R5 명시적 집계를 확인하고 최종 ACCEPT를 발급했다.

## 주장 경계

단일 RF 실현, 제한된 원거리 공동 지지, 검증 불가 대조 때문에 물리 yaw 편향·보편적 이전·M6의 σθ≈2°를 입증할 수 없다. 실행·감사 수용은 H3의 채택이나 기존 M7 결과 변경을 허용하지 않는다. G-T2/G-V 봉인, S2′ STOP, Step3 HOLD는 유지한다.
