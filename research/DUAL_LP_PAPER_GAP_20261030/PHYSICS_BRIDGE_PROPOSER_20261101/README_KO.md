# Dual-LP 12조건 물리 주장 강화 — 제안자 패키지

**역할: PROPOSER · 상태: DRAFT / DESIGN_ONLY · 구현·실험: NOT_RUN**

사용자 요청의 다섯 항목을 위해, 기존 검토자료를 읽기 가능한 형태로 게시하고, 별도 구현 객체가 수행할 검증 설계·결과 활용 규칙·원고 조정 계획을 준비했다. 이번 변경은 이 새 폴더 안의 문서·설정·역사적 검토자료 복사에 한정된다. 원고 v4, 원본 H, filter code, 기존 계약, `.github` workflow는 수정하지 않았다.

## 먼저 읽을 문서

| 읽는 순서 | 문서 | 목적 |
|---|---|---|
| 1 | [제안자 계약](01_PROPOSER_CONTRACT_KO.md) | 질문·범위·개입·보존 대상과 실행 권한 |
| 2 | [과학·검증 명세](02_SCIENCE_SPEC_AND_VERIFICATION_KO.md) | 물리 민감도→갱신→성능의 PB0–PB5 절차 |
| 3 | [별도 구현자 인계서](03_IMPLEMENTER_HANDOFF_KO.md) | 구현 모듈 경계, 입력·출력·negative tests·수치 parity |
| 4 | [실행 결과 활용·주장 규칙](04_RESULT_USE_AND_CLAIM_RULES_KO.md) | 성공·혼합·불지지 결과마다 허용되는 논문 표현 |
| 5 | [원고 v5 조정 계획](05_MANUSCRIPT_REVISION_PLAN_KO.md) | §1–4, 주요 그림·표와 문단 수정 계획; 현재 v4는 보존 |
| 6 | [구현 전 독립 검토·동결](06_PREIMPLEMENTATION_REVIEW_AND_FREEZE_KO.md) | missing source locks, 독립 reviewer 질문, FROZEN 전환 절차 |
| 기계 설정 | [CONFIG_PROPOSED.json](CONFIG_PROPOSED.json) | 12조건·상수 비교산식·FD·분모·수치검사·RT0 예산 |
| source refs | [SOURCE_REFERENCE_LOCK.json](SOURCE_REFERENCE_LOCK.json) | 원고/거버넌스/기존 분석의 exact commit/blob 및 미확정 입력 |
| 기존 자료 | [reference_review/](reference_review/README_KO.md) | 이전 평가문서·12조건표·factorial표·QA·역사적 재집계 스크립트 |
| 무결성 | [PACKAGE_MANIFEST.json](PACKAGE_MANIFEST.json) | 패키지 콘텐츠 Git blob와 업로드 범위 확인 |

## 이번 패키지가 유지하는 연구 목표

`R2_aB_m0, R4_aB_m0, R5_aB_m0 × B0/L0/L1/L2`, mount0°, single-anchor B, 원래 4-State Joint EKF와 `MB_VAR/self`의 관측된 결과를 더 명확히 설명한다. 모든 case에서 XY를 개선해야 하는 새 목표를 추가하지 않는다. 다른 성공 case·5상태 GM·SUB3로 주모델을 바꾸지 않는다.

논문 강화의 중심은 **실제 복소 FFD 관측함수와 Jacobian의 물리성**이다. 기존 거리별 추가분산은 정확한 물리 covariance 복원이 아니라 경험적 신뢰도 조절이며, 그 효과와 한계를 통제된 비교로 설명한다.

검증해야 할 핵심:

1. **PB1 물리 민감도–잔차 정렬:** Full/Direct/SourceFFD, 포트별 power, signed s, Hsx/Hsy/Hsψ와 detector branch를 같은 packet 원장에 연결한다.
2. **PB2 같은 prior의 2×2 개입:** mean-only·variance-only·combined와 기존 기준을 같은 prior 및 pre-predict lookup 상태에서 비교하고, signed update와 fixed/self 전체 재귀 효과를 구분한다.
3. **PB3 상수 대 거리 조건:** 추가분산 0 / train-only 상수 / 현재 lookup. 상수는 다른 두 selected route의 sigma² 평균으로 미리 정하며 test 성능으로 튜닝하지 않는다.
4. **PB4 보조 상관 분석:** raw·기하 mean 제거·Heading 투영 잔차를 구분한다. 공간 field를 읽은 시계열을 독립 시간 drift로 재명명하지 않는다.
5. **PB5 재현/claim 판정:** 학습→예측→μ→관측→재귀→score 계보와 전체12조건을 보존한다.

## 별도 구현 객체의 실행 범위와 예상 계산량

- 새 RT: **0회**.
- 기존 4-arm×2gate×12 = **96개** factorial 궤적은 정확한 trace가 있으면 재사용한다.
- 상수분산 대조는 **48개** 신규 재생이 최소 추가분이다. 전체 protocol 144개는 기존96개 포함이며 이미 실행됐다는 뜻이 아니다.
- 두 reference prior의 shadow updates는 reference 재귀를 바꾸지 않는다.
- 입력 source lock과 pre-run 독립 review 전에는 science comparisons를 실행하지 않는다. 새 원본 H를 만들거나 다른 실험의 holdout을 열지 않는다.

## 결과를 본 뒤 바꾸지 않을 해석 규칙

- 현재 분산-only도 Heading12/12 개선한다. 결합의 필요성은 성공 건수만으로 말하지 않고 R2-B/R5-B에서 두 단독보다 좋은 결과와 R4-B의 역전을 함께 설명한다.
- 거리 lookup이 상수와 동등하거나 열등하면, 기존 Heading 개선은 유지하되 거리 함수의 고유 우월성은 주장하지 않는다.
- local gain 축소가 확인돼도 최종 재귀 RMSE 감소의 단조 증명으로 확대하지 않는다.
- R4-B의 small Heading gain/XY loss는 삭제하지 않는다. mean 부호만으로 원인을 단정하지 않는다.
- 평가 GT는 offline analysis/scoring용이다. 온라인 feature와 variance lookup은 실제 filter prior/기존 lookup 상태를 사용한다.
- source/수학 QA PASS와 과학 가설 SUPPORTED, 독립 AUDITOR 승인을 분리한다.

## 보존한 것과 아직 완료하지 않은 것

- 기준 원고 v4: [immutable manuscript](https://github.com/myoungsunk/sionna-resimulation/blob/1aac4d38a6fa335116bcecbebc91ba53c876ecfd/research/DUAL_LP_PAPER_GAP_20261030/PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md).
- base/governance commit: `1aac4d38a6fa335116bcecbebc91ba53c876ecfd`.
- 과거 분석 snapshot: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`.
- 원고 v4 직접 수정: 없음. 새 실험 코드/필터 실행/RT/Actions dispatch: 없음.
- 기존 검토 ZIP의 보고서·표·QA·스크립트 등8개 파일은 원바이트로 게시했다. 원본 `RA4_336_ARMS.csv`는 [기존 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594/artifacts/12890904334)와 SHA로 연결했다. 원본 ZIP 바이너리 자체는 이 tree에 포함하지 않았고 대화 첨부 원본으로 남긴다. 따라서 이 폴더가 전체 raw를 중복 수록한 완전자급 ZIP이라고 부르지 않는다.
- 원본 검토 QA는 역사적 기록이다. 이번 게시의 Git writes나 새 분석 성과가 아니다.
- 실제 raw 입력 모두의 SHA 검산, 별도 IMPLEMENTER와 독립 AUDITOR 지정, FROZEN 서명: **후속 preflight/승인 항목**.

## 별도 구현자에게 전달할 첫 문장

> `03_IMPLEMENTER_HANDOFF_KO.md`를 따라 IMPLEMENTER 역할로 source inventory와 설계 수신 검토부터 하라. 제안자의 관찰과 가설을 구분하고, R2-B/R4-B/R5-B 12조건·기존 h/J·pre-predict lookup·4-State·평균/분산 설정을 보존하라. 현재 DRAFT 문서 업로드를 실험 실행 승인이나 독립 감사 완료로 해석하지 마라. 입력 잠금과 candidate review 후 승인된 PB 단계만 실행하고, 결과는 `04_RESULT_USE_AND_CLAIM_RULES_KO.md`로 원고에 연결하라.
