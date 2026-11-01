# 구현자 반환서 — DLP-PHYS-LINK-001 사후 감사

최종 제출 판정은 **REVISION_REQUIRED**이며, 첨부 재구현의 핵심 수치 결과는 **ACCEPT_WITH_BOUNDARIES**다. 기존 성능을 무효화하거나 R4를 성공시키도록 모델을 바꾸라는 요청이 아니다. 모든 수정은 새 commit과 append-only 결과물로 남긴다. 감사 상세는 [AUDIT_REPORT_KO.md](AUDIT_REPORT_KO.md), 수치 확인 범위는 [AUDIT_VERDICT.json](AUDIT_VERDICT.json)을 참조한다.

## A. 고정해야 하는 것

R2/R4/R5-aB-m0 × B0/L0/L1/L2, seed 0, 원 정수 first-path r와 signed s, 4state, source f/F/Q, mu_B/mu_M, R_B, 기존 lookup 표·조회 시점, NIS threshold와 fixed/self 분리, t≥30 평가를 유지한다. 기존 raw·control·trace·결과·실패 이력을 덮어쓰지 않는다. 보완을 위해 새 RT, ML 재학습, 5state, SUB3, sub-tap, threshold 최적화, case 제외를 하지 않는다.

## B. 수정 순서와 합격 기준

|ID|구체적 결함·부족|최소 수정|완료 기준|재계산 범위|
|---|---|---|---|---|
|R1|원격 15503350 원본 미회수, 현재 ZIP은 재구현, 원격은 일부 문서만 게시|원본과 reconstruction의 identity 분리, 신규 코드·입력·결과·ZIP manifest 게시|원본 MISSING, 재구현의 실제 commit·ZIP SHA·파일 수·원격 검증 일치|게시·해시 확인만|
|R2|CONFIG_LOCK의 execution_authorized=true/문서-only/NOT_RUN/null input lock 공존|과거 config 보존 후 RUN_ADMISSION_RECORD_V2.json append|실제 허용 phase·사용자 요청·input/config/code hash·retrospective 상태 모순 없음|문서·메타데이터만|
|R3|copied_mean_identity_pass=True가 실제 mu 동일화 시험 결과가 아님|mu_M 복사본을 mu_B로 강제 치환한 독립 호출 후 x/P/NIS/gate 비교|실제 오차·표본 수에서 PASS 산출; 의도적 mu mutation은 FAIL|저장 same-prior 자료|
|R4|Schur·prior/J/control 차이를 계산하지만 최종 PASS에 일부 미반영|필수 check_id·threshold 원장과 all(required_checks) 집계|각 필수량 오염 시 최종 FAIL; 누락은 NOT_RUN/BLOCKED|저장 자료·음성시험|
|R5|FIRST_DIVERGENCE가 첫 시점·gate 개수만 기록|첫 분기 packet의 두 arm 입력·lookup·gain·상태 원장 추가|동일해야 할 필드와 개입 필드, 첫 불일치 이유, trace hash 완비|기존 NPZ 재집계|
|R6|물리 미분·갱신 대수와 전체 재귀 개선 원인의 연결 집계는 미완성|기존 physics와 shadow 원장을 기하·tap 구간으로 정렬|signed RF/state 갱신과 n_all/n_used/n_stable가 설명 문장과 일치|기존 표 재집계; 강한 누적 인과 주장 때만 별도 V4|

## C. R3의 정확한 수정 방향

관련 코드: `code/shadow_validation.py:51,54–58,65`, `code/quality_and_comparison.py:42–43` (첨부본 기준).

같은 R에서 BB_ORIG_K와 MB_ORIG_K가 같은 것은 mu와 무관하다. 이 검사만으로 mu_M=mu_B 음성 개입을 검증했다고 말할 수 없다. 다음 두 검사를 분리한다.

1. **수학 null 검사:** 동일 x-/P-/J/z/R/lookup에서 독립적으로 만든 `mu_M_test = mu_B.copy()`로 MB code path를 호출한다. BB path와 post x/P, innovation, NIS, gate, range/polarization signed correction을 비교한다. 원본 mu_B/mu_M byte hash가 전후 동일해야 한다.
2. **mutation 검사:** 지정한 finite sample의 mu_M_test에 사전에 정한 비영 변화를 주입하여 mean-equality check가 실패하는지 확인한다. 해당 sample이 관측 갱신을 하지 않는 것만으로 실패 검출을 피하지 않도록 forced one-step와 정책 적용 결과를 분리한다.

각 검사는 `executed`, `n_compared`, `max_abs`, `atol/rtol`, `status`, `source_trace_hash`를 기록한다. `True` literal을 결과 필드에 직접 대입하지 않는다. sigma_zero도 같은 방식으로 원본·대조 경로를 명시한다.

## D. R4의 정확한 수정 방향

관련 코드: `replay_validation.py:40–41`, `shadow_validation.py:33–36,65–67`.

최종 성공은 코드가 종료됐다는 뜻이 아니라 모든 필수 검사 통과여야 한다. 기존 tolerance를 결과에 맞춰 완화하지 않는다. 최소 체크:
- exact case/pose/timestamp/finite/mask;
- motion ds/gyro/dt 및 초기 state/P;
- predicted prior/Pprior, h/J/nu/R/S/K;
- post state/P, wrap·단위;
- Schur posterior identity, innovation와 signed correction 분해;
- zero variance와 copied mean 개입;
- CSV 집계 분모·반올림 전 점수.

감사에서 현재 데이터의 해당 값은 수치 정밀도 범위였다. 수정 목적은 미래 오류가 기록만 되고 PASS하는 경로를 막는 것이다. 추가 검사와 mutation만 새 결과로 남기고 기존 결과를 다시 썼다고 주장하지 않는다.

## E. R5 첫 분기 원장 schema

비교 key: `(case,bias,reference_arm,target_arm,gate,packet_id,t_s)`.

두 arm 각각 `previous_x/P`, `rho_lookup`, `sigma_b`, `ds/gyro/dt`, `prior_x/P`, `h/J`, `mu/R`, `nu/S/K/NIS`, `accepted`, `post_x/P`, `source_trace_sha256`를 기록한다. `first_differing_field`, `must_equal_checks`, `allowed_intervention_fields`, `score_window`를 추가한다.

`SAME_PRIOR_SHADOW`와 `RECURSIVE_TRAJECTORY_DIVERGENCE`를 구분한다. 재귀에서 prior가 다르게 된 뒤의 K 변화는 단독 분산 개입의 직접 효과로 명명하지 않는다. fixed 비교는 실제 mask 배열 동등성을 포함한다. 이번 제출의 fixed masks는 감사에서 동등함이 확인됐다.

## F. 결과 문장에 대한 유지·보류

**유지:** 12조건 Heading 감소/8조건 XY 감소, R4 XY 악화, 같은 BB prior에서 mean-only 즉시 Heading MSE가 combined보다 좋은 8조건과 최종 재귀 결과의 차이, fixed/self에서 R2/R5 lookup 우세와 R4 constant 우세, SourceFFD의 signed 관측과 smooth Jacobian 수치 검증.

**보류:** 원본 15503350 복원·게시·독립 감사 완료, 사전 동결 인증, 매 packet의 개선, 전역 최적 lookup, 물리 환경 일반화, 실제 하드웨어 calibration, 원 학습 모델 fresh inference, R4의 특정 반사체 단일 원인.

V4는 선택 항목이다. V5 fresh inference가 BLOCKED인 사실을 보존하면 현재 회고적 검증을 무효화하지 않는다. 새 모델을 학습해 기존 모델이 복원됐다고 말하지 않는다.

## G. 다음 전달물

`RECONSTRUCTION_PUBLICATION_RECEIPT_V2.json`, `RUN_ADMISSION_RECORD_V2.json`, `REPAIR_DIFF.md`, `REQUIRED_CHECKS_V2.json`, `NULL_AND_MUTATION_TESTS_V2.json`, `FIRST_DIVERGENCE_DETAILS_V2.{json,csv}`, `CLAIM_LEDGER_V2.md`, 재실행 명령·환경·source/config/output hash를 제출한다. 기존 144개 점수와 비교한 score diff가 0인지 확인한다. 수학·추정 코드를 수정해 점수가 달라졌다면 별도 실행 ID로 원인을 설명하고 영향을 받은 부분만 재실행한다.

이번 반환서는 구현 수정의 지침이다. 원 모델을 바꾸는 새로운 과학 설계나 승인되지 않은 전체 연구 확장을 요청하지 않는다.
