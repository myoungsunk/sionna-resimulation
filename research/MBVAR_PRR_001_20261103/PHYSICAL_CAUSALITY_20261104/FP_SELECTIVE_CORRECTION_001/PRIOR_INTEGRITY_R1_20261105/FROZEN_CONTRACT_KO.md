# FP-SC-PRIOR-INTEGRITY-R1 — 결과 전 동결 계약

Base b8cc7ee731d61ac747cc99d7203ddcce28de962c; branch implement/fp-sc-001-e1-run-20261105.
PROPOSER → IMPLEMENTER → 동일 작업자 자체검사. 독립 감사 아님.
기존 E1 실패, VAB 주안, mapping R1의 NUMERICAL_PASS_REVIEW_HOLD와 11,095 배제 기록 보존.

## 질문·범위
잘못되었거나 신뢰 근거가 없는 prior가 P/M 오류 점수와 trusted history를 오염시키는 경로를 차단하는가?
이번 실행은 구성요소 재검증이다. 실제 RF의 detect/select/detection_loop/E1-02/E2/EKF 실행 금지.
기존 6,320 RF의 후보 재생성과 prepare_candidate_set 및 보호 구성요소 호출은 허용한다.
새 RT/SourceFFD mapping/보정/정책 튜닝 없음. 기존 nominal/stress mapping 구간을 해시 확인 후 재사용한다.
논리 CPU 최대3개, BLAS/OMP 1 thread. static48 C-only, 가짜 prior/history 없음.

## 변경 계약
상태 VALID/UNKNOWN/INVALID를 수치 Support와 분리한다. 이 버전에는 검증된 외부 integrity provider가 없으므로
실제 prior에서 VALID를 생성하지 않는다. VALID 문자열/좁은 폭/작은 PSD covariance로 우회할 수 없다.
UNKNOWN은 근거 부재, INVALID는 비유한/시간 또는 covariance 등 구조 이상이다. UNKNOWN을 INVALID 오류로 숨기지 않는다.
VALID 활성화는 향후 별도 증거·provider·계약 개정 대상이다. 이 보수적 제한은 P/M availability를 입증하지 않는다.

C는 종전 동작 유지. P/M/PM은 UNKNOWN/INVALID일 때 RF-only 후보 집합을 유지하되 effective_mode=HOLD,
active wrong_score=None, P/M 영향0. prior/motion residual과 종전 비용은 diagnostic_only로 별도 보존한다.
단순 C fallback을 P/M 성공으로 집계하지 않는다. 후보 삭제0; selected_tap=raw_tap.
UNKNOWN/INVALID 및 prior conflict/만료 시 기존 trusted state를 reset하고 bootstrap/refresh를 금지한다.
M native offset도 보호 범위에 포함한다. 온라인 경로에 evaluator/LoS/GT를 넣지 않는다.
새 recipe를 authorization receipt/code lock에 연결한다. 기존 approval=false 유지, E2 차단 유지.

## 동결 검사
G0: 기존 NOMINAL 6,272 / STRESS43,904 exact keys/hash, exclusion11,095 및 nominal G0-G3 재집계 일치.
G1: 6,320 RF × 2 candidate modes ×4arms=50,560행 후보 재생성/기존 후보·eligibility exact 재현.
G2: VAB TWO_PORT_UNION dynamic6,272 × (nominal+7stress)=50,176 packet-scenario,
각 C/P/M/PM=200,704 component rows. 이 전체를 UNKNOWN/INVALID 각각 검사한다(401,408 state-mode checks).
UNKNOWN/INVALID의 P/M/PM active score·history refresh/reuse0, 후보 집합 변화0. 분모·HOLD 전수 공개.
G3: static48을 C-only 구성요소로 검증, 동일 후보 집합/입력 SHA; P/M/PM/시간·prior 생성0.
G4: 합성 반례 — VALID spoof 거부, nonfinite/비PSD/시간 이상 거부 또는 INVALID,
UNKNOWN/INVALID seeded-history reset, stale/gap/역전·복구, C invariance,
wrong prior diagnostic와 active score 분리, GT 독립, 실제 stage 금지 sentinel. 기존 legacy1,000 Decision 정확 일치.
G5: 새 manifest/code/recipe/input lock 및 부정 승인으로 실제 실행 차단 확인. VAB/실패 기록 변경0.
모든 구조 검사를 통과하면 PASS_COMPONENT_GUARDS_ONLY / E1_02_HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING.
P/M usable coverage는 0%라도 그대로 공개하며 scientific safety/adoption PASS로 승격하지 않는다.

## 재검증 한계
이미 노출된 동일 RF 및 기존 stress 구간의 구성요소 재검증이다. 신규 분포/운용 오류율/정정 성공률을 주장하지 않는다.
VALID prior의 실용성, 새 radial/tangential stress mapping, 실데이터 detect 성능은 이번에 실행하지 않는다.
원래 P와 축소 P의 paired 신규 mapping 검사는 후속 별도 계약이며 이번 보호 수정의 통과 근거로 쓰지 않는다.
결과·실패 실행은 새로운 경로에 보존한다. 이번 계약은 구현 및 본 재검증 전에 커밋한다.
