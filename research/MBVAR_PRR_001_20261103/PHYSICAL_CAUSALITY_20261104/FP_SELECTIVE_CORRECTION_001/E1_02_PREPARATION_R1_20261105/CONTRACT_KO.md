# FP-SC-E1-02-PREP-R1 — 실행 전 준비 계약

역할 IMPLEMENTER 및 동일 작업자 자체검사. 독립 감사 아님.
기준 ba8d978acce3a41d113a2021b0e26e911d21ba71, VAB 주안 유지.
E1-02/E2 실행, 동적 mapping 수치 실험, 새 RF, EKF replay, 학습은 이번 범위 밖이다.
원본 E1 실패, 후보 R1, bridge R1, reach R2는 별도 증거이며 덮어쓰지 않는다.

## 검출 경로

`VAB_DETECTION_ONLY_R1`은 `RevisionEvidenceAdapter(VAB)`를 명시 주입한다.
`detection.detect`는 실제 선택기와 동일한 `prepare_candidate_set`을 사용한다.
raw 후보의 기존 점수식 `0.7*(-log(max(q,1e-12))) + max(p,m)^2`를 검출 점수로 내보낸다.
q는 bridge R1의 비보정 점수이며 확률/신뢰도가 아니다. 후보가 최저점이어도 selected_tap=raw_tap,
action=KEEP_ORIGINAL이다. 일반 select, SyntheticSelectionProbe, EKF update를 호출하지 않는다.
unsupported raw에도 점수 바닥이 적용되는 특성은 유지하며, 보정된 검출 성능이라고 주장하지 않는다.
C는 native mapping/시간 이력을 사용하지 않는다. P/M/PM은 보관된 측정 전 prior/Pprior를 사용한다.

M/PM의 `RAW_ONLY_LEGACY_SUPPORT_GATE_R1`은 원래 tap만 bootstrap한다.
raw supported, polarization_valid, legacy_support>=0.15, prior 폭<=1.5m, residual<=1,
연속 2 packet 및 기존 elapsed-motion/age 조건을 유지한다. 개정 q를 신뢰도로 대입하지 않는다.
VAB 지원 기록에서 계산한 legacy_support이므로 원래 V0 이력과 완전 동일하다는 주장은 하지 않는다.
새 이력 의미는 제안된 검출 전용 정책이며 아직 실제 데이터에서 검증/채택되지 않았다.
일반 VAB select와 TrustedHistory.observe의 차단은 유지한다.

## 입력과 모델

개발 입력은 기존 R2/R4/R5, B0, Full/Native_LoS의 동일 RF를 사용한다.
6개 동적 case의 합계 6,272 packet을 준비한다. 후보 개정의 50,560행을 재실행하지 않는다.
기존 48개 static waveform은 별도 CIR-only control이다. 이를 동적 시간열/가짜 prior로 만들지 않는다.
static canonical 준비 여부는 사전 검사 보고서에 별도로 표시한다.
온라인 입력과 evaluator 전용 LoS/truth는 분리한다. 원본 t/pose_id로 exact join하며 결측을 추정하지 않는다.
controls/replay는 기존 E0 A2 archive를 재사용한다. A2 rematerialization은 역사적 byte identity와 다르다.
FFD bank와 원본 SourceFFD를 SHA로 검증하고 로딩까지만 확인한다. model.batch/replay 호출은 금지한다.
F00/F01/F11 모델 학습은 E1-02 준비의 필수조건이 아니다.

## 권한과 환경

Snowball KMS, Docker fp-sc-e1:20261105, affinity 0,1,2 및 CPU quota 3.
OPENBLAS/OMP/MKL/NUMEXPR 스레드는 각 1. 목표 Python 3.12.14, NumPy 2.3.5.
준비 manifest는 mapping_reviewed=false, 승인 문서는 execute_science=false, stages=[]다.
미래 실행 시 정확한 manifest/code/input 해시와 stages=[E1-02]만 허용한다.
동적 mapping 검토 receipt는 policy/candidate mode/bridge/selector/history/code lock과 근거 파일 해시에 결속된다.
boolean만 바꿔서는 통과하지 않는다. 기존 선행 HOLD를 자동 PASS로 바꾸지 않는다.

## 주장 한계

이번 PASS는 파일·스키마·합성 검사·모델 로딩에 한정한다.
동적 mapping, 검출 정확도, FP 정정, EKF 개선, 일반화, VAB 전체 정책 채택은 입증하지 않는다.
E1-02는 남은 mapping 검토·선행 결과 검토·명시적 실행 승인 뒤 단일단계로만 진행한다.
