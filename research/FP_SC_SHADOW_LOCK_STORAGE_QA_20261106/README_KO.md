# 단계 공통 잠금 및 S3 저장 보완

질문: S1 결과가 다른 입력·코드·모델의 S2/S3에 연결되는 것을 차단하고, 단일 갱신 결과를 사후 검산할 수 있는가?
기준 커밋 c1afde831deffd42f811cf59c9ecd1dd954e44d1. IMPLEMENTER 자기검사이며 독립 감사 아님.

## 계약 변경
공통 identity recipe는 SHADOW_COMMON_LOCK_V2이다. 기존 case/policy/arm/mode/source 식별에 canonical online/evaluator payload SHA256, code_files 전체, baseline_sources 전체, model_files 전체를 추가했다. 단계별 결과·영수증·검토 파일은 공통 identity에서 제외하지만 기존 input_files 해시 검증과 선행 검토 연결은 유지한다. 이전 recipe의 결과 영수증은 새 단계와 연결되지 않는다. 기존 증거를 재작성하지 않는다.

새 manifest에는 model_files를 추가해야 하며 LP_plus45_bank.npz 및 LP_minus45_bank.npz가 필수다. baseline_sources에는 원래 모델 코드와 pilot 코드가 필요하다. 후보 생성기와 원본 로더·관측 코드도 필수 code_files에 추가했다. 각 단계는 동일한 공통 lock을 유지해야 한다. 이는 실행 승인을 만들지 않으며 기존 승인/선행 검토 조건을 대체하지 않는다.

## S3 결과
기존 산술·선택·임계값·mask는 변경하지 않았다. 각 행에 t/pose_id, prior/Pprior, h/H, mu/R, 고정 accepted mask, 관측 F00/F10/F01/F11 및 각 arm의 기존 update 반환 전체를 저장한다. 반환 전체에는 x/P/K/pre_gate_K/S/innovation/unwrapped_delta/nis/accepted가 포함된다. 유효하지 않은 관측은 reason과 updates=null을 보존한다. GT 또는 추정한 gyro bias를 추가하지 않는다. 결과는 JSON 왕복 후 고정 입력으로 재계산 검산했다. 폐루프나 성능 향상 증거가 아니다.

## 검증 및 경계
7개 기존 합성 묶음과 추가 검사: 입력/평가/코드/모델/원본 모델 변경 시 공통 identity 변경, 단계 산출물 추가 시 identity 유지, 실제 S2 선행 연결에서 payload 교체 거부, 모델 잠금 누락 거부, S3 저장값 재계산 및 기각 mask 보존. 기존 선택기 200×5 Decision 재현 검사를 포함한다. QA.json에 실행 환경·결과·변경 파일 해시를 기록한다.
기존 연구 브랜치·알고리즘·임계값·실패 기록 유지. S1–S3 과학 실험 및 E1-02/E2 미실행. 원본 RF나 모델 payload를 로드하지 않는 합성 검사만 실행했다.
