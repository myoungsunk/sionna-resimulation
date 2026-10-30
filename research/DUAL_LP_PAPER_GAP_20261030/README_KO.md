# Dual-LP Heading–EKF 논문 데이터 공백: 제안자 준비 패키지

**상태: PROPOSER_DRAFT_ONLY / DOCUMENTATION_ONLY / NOT_FROZEN / NO_RUN.**

- 역할: `PROPOSER` (구현자·감사자 역할 수행 아님)
- 계약: `DLP-EKF-GAPS-001` (신규 논문 데이터 정합·비교군 확보 전용)
- 기준 저장소: `myoungsunk/sionna-resimulation`
- 기준 브랜치: `research/pol-xcorr-audit01-20261030`
- 기준 base Git SHA: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`
- 읽은 governance 기준 스냅샷 SHA: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`
- 문서 작성 브랜치: `research/dual-lp-paper-gap-proposal-20261030`
- 대상 논문: 단일 Anchor Dual-LP Heading 관측 및 특성 반영 EKF
- 목적: 기존 데이터가 부족한지 **입증**한 다음 필요한 최소 재계산·시뮬레이션 범위를 결정
- 실행·재학습·원본 변경·독립 감사: **모두 NOT_RUN**
- 계약 해시·기술적 허용오차·새 Anchor 기하·추가 RF 예산·독립 감사: **P0_TO_RESOLVE**

## 고정된 논문 구성

1. 고정 시뮬레이션 설정
2. Dual-LP의 Heading 관측 개념 (축 A)
3. 특성 분석 (축 B): 3-A 오차 형성, 3-B signed bias, 3-C 이분산·공분산, **3-D spatiotemporal correlation and information redundancy (RESERVED / 이 문서에서 미설계)**, 3-E 상태 의존 관측 효용 및 재귀 전달
4. Characteristic-Aware EKF 모델
5. DR vs Conventional single-anchor EKF vs Conventional ≥3-anchor EKF vs Characteristic-Aware EKF
6. Limitations

3-D와 최종 M2는 현재 **결정하지 않는다**. 해당 영역의 기존 `MBVAR-INFO-001` 및 `POL-XCORR-001` 계약과 충돌·중복하는 새 실험을 허가하지 않는다.

## 문서 목록

1. `EVIDENCE_GAP_MATRIX_KO.md`: 실제 존재 증거, 매칭 장애, 필요한 최소 작업, 우선순위
2. `EXPERIMENT_CONTRACT_DLP-EKF-GAPS-001_DRAFT.md`: 제안자 계약 초안; 연구 질문·estimand·공정성·입력 잠금·중단 조건
3. `SCIENCE_SPEC_KO.md`: 물리·필터·추정량의 수학적 정의와 데이터 계열의 동치 조건
4. `PROPOSER_HANDOFF_KO.md`: 향후 구현자/독립 감사자에게 넘길 단계·QA·출력 계약
5. `FREEZE_READINESS_KO.md`: 아직 동결하지 못하는 필드·증거·승인 체크리스트
6. `GOVERNANCE_APPLICABILITY_KO.md`: 기존 MBVAR 전용 역할 규정의 이번 계약 적용 경계

## 사용자 지시를 반영한 금지사항

- 원본 Corridor C0와 Office·CP Paper 2·새 장면의 수치를 같은 데이터셋의 직접 비교 결과로 합치지 않는다.
- CP Paper 2의 3-anchor WLS·2D EKF **코드가 존재한다는 사실**을, Dual-LP Corridor용 ≥3-anchor 4-State RF 데이터/성능이 확보되었다는 증거로 바꾸지 않는다.
- 기존 `EKF3`의 '3'을 3-anchor로 오독하지 않는다.
- SourceFFD와 구 LoS LUT 결과를 같은 관측모델로 포장하지 않는다.
- `DRAFT` 문서를 `FROZEN`/사전등록/과학적 검증으로 호칭하지 않는다.
- 사후 선택된 prior·gate·oracle 진단을 deployable 방식으로 제시하지 않는다.
- 이 문서의 작성·커밋은 신규 실험이나 기존 연구의 CLAIM 승격을 의미하지 않는다.

## 다음 단계 (허가 전에는 실행 금지)

구현자에게 넘기기 전, 제안자·독립 감사자가 입력/계열 정의와 비교군을 검토하고 `FREEZE_READINESS_KO.md`의 블로커를 해소한다. 사용자 지시 없이는 코드 구현, RT canary, 데이터 생성, 재귀 replay, 계약 동결 서명을 진행하지 않는다.

## 원본 핵심 자료

- `research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json` (C0 Original RF·시계열)
- `research/FFD_P0P3_20261016/RESULTS_KO.md`, `SOURCE_BANK_RECEIPT.json`
- `research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py`
- `research/POWERJOINT_FINAL_20261016/05_PAPER_STORY_KO.md`
- `rt_cp_uwb_py/localization.py` (비동치 CP Paper 2 multi-anchor 코드)
- `docs/research-governance/{COMMON_CONTRACT,ROLE_PROPOSER,ROLE_IMPLEMENTER,ROLE_AUDITOR}.md`
