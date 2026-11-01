# DLP-PHYS-BRIDGE-012-001 — 제안자 계약 초안 v0.1

2026-11-01 · **role=PROPOSER** · **DESIGN_ONLY / DRAFT / NOT_FROZEN**

## 1. 이번 위임과 권한

사용자 요청은 기존 검토 패키지 업로드, 물리적 관측구조와 결과를 연결할 검증의 제안자 설계, 별도 구현 객체 인계, 결과 활용 규칙, 원고 조정 계획이다. **이번 제출에서는 실험용 코드 작성·학습·필터 재생·RT·Actions dispatch를 하지 않는다.** 기존 원고도 직접 교체하지 않는다.

- contract_id: `DLP-PHYS-BRIDGE-012-001`
- role: `PROPOSER`
- base_git_sha: `1aac4d38a6fa335116bcecbebc91ba53c876ecfd`
- governance_git_sha: `1aac4d38a6fa335116bcecbebc91ba53c876ecfd`
- evidence_snapshot_git_sha: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`
- historical_RF_runtime_reference: `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13` — 실제 파일별 대응은 구현 전 입력 잠금표로 확인한다.
- document_root: `research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_BRIDGE_PROPOSER_20261101/`
- future_output_root: `research/DUAL_LP_PHYSICS_BRIDGE_20261101/runs/<run_id>/` — **현재 존재하거나 생성됐다는 뜻이 아니다.**
- independent_pre_run_auditor: `NOT_ASSIGNED`
- implementer: `SEPARATE_ACTOR_TO_BE_ASSIGNED`
- science_execution_authority: `NONE_IN_THIS_SUBMISSION`

이 계약은 기존 `DLP-EKF-GAPS-001`, `MBVAR-INFO-001`, `POL-XCORR-001`을 개정하거나 그 승인을 승계하지 않는다. 새 앵커·5상태·SUB3·신규 환경으로 연구 목표를 이동하지 않는다.

## 2. 거버넌스 적용 범위

읽은 기준: root `AGENTS.md`, `COMMON_CONTRACT.md`, `ROLE_PROPOSER.md`, `ROLE_IMPLEMENTER.md`, `ROLE_AUDITOR.md`, `PROPOSER_FREEZE_CHECKLIST.md`, 기존 원고 폴더의 `GOVERNANCE_APPLICABILITY_KO.md`, `SCIENCE_SPEC_KO.md`, `EXPERIMENT_CONTRACT_DLP-EKF-GAPS-001_DRAFT.md`.

MBVAR 전용 규정을 이 경로에 자동 강제한다고 주장하지 않는다. 원본 보호·역할 분리·불변 소스·누출 방지·실행과 과학 판정 분리·독립 감사는 본 계약이 명시적으로 채택한다. MBVAR의 GP/OU 생성기, 12×12m RT, S0/S1/R 실행 단계와 이전 canary 의무는 `NOT_APPLICABLE`이다. 해당 연구의 holdout을 열거나 재사용하지 않는다.

## 3. 변경하지 않는 연구 범위

| 항목 | 고정값 |
|---|---|
| RF case | `R2_aB_m0`, `R4_aB_m0`, `R5_aB_m0` |
| gyro 조건 | B0=0, L0=+0.01, L1=+0.05, L2=+0.20 deg/s |
| 조건 수 | 세 RF 시퀀스 × 네 센서 조건 = 12; 독립 물리 장면은 하나 |
| anchor / mount | B=(10,0,2.65)m / mount 0°; tag z=0.45m |
| 안테나·관측 | TX +45°, RX ±45°, 기존 공통 first-path tap, signed ratio `s` |
| 상태 | `[x(m),y(m),psi(rad),b_g(rad/s)]` 4-State |
| 주 결과 | `BB_ORIG/self` 대비 기존 `MB_VAR/self` |
| 진단 비교 | 같은 원본 BASE mask, 평균×분산 2×2, 동일 prior shadow |
| sensor/initial seed | 원본 seed 0; 새 난수 반복은 현재 주 범위 밖 |
| 시간 | 재귀 t=0부터; 성능 t≥30s; ACF 전체축은 별도 표기 |
| 원본 관측 | 기존 integer first-edge r, 기존 s. sub-tap·추가 tap 관측으로 바꾸지 않음 |
| 기본 모델 | 기존 μB/μM, RB, f/F/Q, 초기 x/P와 원본 control 그대로 |
| 추가분산 | rho=[0,1.5,3,6,10]m; sigma=[0.011,0.020,0.050,0.120,0.240]의 원본 보간 규칙 |
| 조회 시점 | motion prediction 이전의 직전 posterior 위치; k=0은 초기 상태. 각 재귀 arm 자신의 상태 사용 |
| 금지 | post-hoc case 제외, R4-B 제거, 실패 seed 은폐, 현재 표 재튜닝, RT, 보호 데이터 덮어쓰기 |

## 4. 질문과 검증 가능한 주장

**Q1 관측 현상→가정:** 실제 FFD가 선택한 세 경로에서 만드는 위치/Heading 민감도와 포트별 차등 왜곡이 무엇인가? 새 결과가 불명확해도 물리 관측함수의 구현 사실과 오차 통계는 분리해 남긴다.

**Q2 가정→개선:** 같은 prior에서 평균 교체와 편파 분산 증가가 각각 innovation·gain·signed 상태 갱신을 어떻게 바꾸는가? 이후 재귀 효과를 별도 보고한다. 국소 gain 축소가 최종 오차 감소를 보장한다는 단조 가설은 세우지 않는다.

**Q3 거리 조건의 가치:** 동일 평균/운동/수용정책에서 현재 lookup이 추가분산 0 및 source-route 평균에 맞춘 상수보다 다른 결과를 만드는가? 차이가 없거나 악화하면 거리 함수의 고유 우월성을 주장하지 않는다.

**Q4 재현 가능한 범위:** 12조건의 원본 표, 학습 fold→예측→μ 복원→필터 재생이 정확히 연결되는가? 저장 예측의 재생과 회귀 추론 재현은 서로 다른 완료 항목이다.

## 5. 단계와 실행 권한

- PB0: 입력/모델/분모/역할 잠금. 이번은 문서만 준비. 후속 별도 위임의 `PREFLIGHT_ONLY`에서는 source inventory와 수학 음성 시험만 허용한다.
- PB1: 물리 민감도–잔차 정렬. 새로운 물리 시험이 아니라 원본 분석이지만, 결과를 관찰하기 전 source lock과 분석 설계를 고정한다.
- PB2: 같은 prior의 2×2 shadow update + 이미 정의된 fixed/self 재귀 계열 재현.
- PB3: 추가분산 0/상수/현재 lookup의 최소 비교; 현재 성공모델을 교체하지 않는 대조 실험.
- PB4: 시공간 지속성과 Heading 전달 분석. descriptive secondary; 새 colored-state 필터 구현은 불허.
- PB5: 재현성 원장·독립 감사·원고용 claim 판정.

**PB1–PB5 실질 분석·재생은 후속 FROZEN revision과 별도 실행 위임 후 시작한다.** DRAFT를 preregistration 또는 기존 성공 결과의 독립 확인으로 부르지 않는다.

## 6. 사전 승인과 중단

필수 입력 파일별 SHA256, 정확한 extractor/SourceFFD/controls/μ/R blob, 원본 pose-time key, D2/RA4 대응, EXDS 학습·예측 계보는 PB0에서 잠금 파일로 확정한다. 현재 문서의 URL·Git blob은 `REFERENCE_PINNED`이며 전체 raw 입력의 SHA 검증 완료와 같지 않다.

누락된 소스, 모호한 lookup 시점, 부호·단위 불일치, 원본 parity 실패는 `BLOCKED_INPUT` 또는 `FAIL_QA`로 중단한다. 임계값을 결과에 맞춰 넓히지 않는다. 반면 개선 없음·상수와 동등·R4-B 악화는 실행 오류가 아니라 유효한 과학 결과다.

- PROPOSER: `DRAFT_AUTHOR_ONLY`; 설계 제출 완료, 동결 서명 아님.
- IMPLEMENTER: `NOT_ASSIGNED`; 이번 작업에서 대리 서명하지 않음.
- AUDITOR: `PENDING_DISTINCT_ACTOR`; 자기검토를 독립 감사로 표기하지 않음.
- freeze: 입력 잠금, 명세·수치설정 SHA, 구현 전 설계 감사가 준비되면 별도 immutable revision/서명 기록으로 전환. 기존 DRAFT·실패 기록은 보존.
