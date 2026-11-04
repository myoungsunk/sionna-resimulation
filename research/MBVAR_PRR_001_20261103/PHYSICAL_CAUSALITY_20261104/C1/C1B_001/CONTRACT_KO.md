# C1B-BASE-GATE-001 — 같은 Full 이력의 BASE gate 재판정

역할 PROPOSER. C1a 독립 수용 이후의 C1b 세부 계약이다. RESEARCH-GOVERNANCE-v1 COMMON_CONTRACT/ROLE_PROPOSER/ROLE_IMPLEMENTER를 적용한다. C1a·기존14pose·C0-B·S1–S3·N0B·R2의 계산은 재실행하거나 수정하지 않는다. 새 학습·RT·온라인 정책 채택을 하지 않는다. SPEC/코드 감사 및 별도 GO 전 과학 실행 금지.

## 질문·고정 표본

관측 성분을 바꾼 뒤 기존 BASE의 같은 prior에서 공동 NIS를 다시 계산하면, C1a의 고정 mask 대조와 한 번의 MB_VAR 갱신 결과가 어떻게 달라지는가? RF 오차 감소 자체와 현재 패킷 수용 여부 변경을 분리한다. MB_VAR prior의 NIS를 BASE gate라고 바꾸어 부르지 않는다.

R2/R4/R5·AnchorB·mount0·B0/L2·공개 seed10–29, 원래 모든 pose(979/742/1415)를 고정한다. 총120조건/125440 prior/4arm501760행. seed10의6조건 DEV_001을 먼저 실행·감사하고, 통과하면 같은 코드의 seed11–29 114조건 REMAINING_001에 새 GO를 받는다. seed10은 재실행하지 않는다. 두 출력 합계가120조건이어야 한다. 이는 개발/계산 관문 분할이며 비노출 holdout이 아니다.

INPUT_LOCK.json은 기존 C1a 입력 lock/수용 판정과120개 원래 control stream, 원본 관측·predict 모듈, bank2개를 SHA·크기로 묶는다. 외부 모델 소스는 원본 p2의 상대 트리를 cache/legacy에 정확한 bytes로 복사한 것이다. 물리·관측 수식은 바꾸지 않는다. core.py는 원래7e2855314de867e0481f8eb5ed1a07c48710f364, online.py/check_base.py/ENV_LOCK은17cbfb8 기준이다.

실제 필터의 원래 Windows Python3.13.15/NumPy2.2.4/SciPy1.15.2/pandas2.2.3/joblib1.6.0/threadpoolctl3.6.0와 BLAS1thread를 사용한다(ENV_LOCK의 실제값 재확인). C1a의 별도 행렬검산 Linux runtime과 혼동하지 않는다. 고정 Full/LoS packet의 수치 예측 mean만 재사용하며, held-route 학습 모델·특징 변환·순서를 다시 학습하거나 호출하지 않는다. SourceFFD의 원본 source-bank polar-cap 초기화는 동일 고정 bank·코드로 수행하는 관측모델 초기화이며 새로운 RF/GT 학습을 추가하지 않는다.

## BASE shadow prior와 공동 gate

BASE shadow는 Full 패킷만 사용하여 t=0부터 한 번 진행한다. 초기 상태는 기존 control.x0에 b_g=0을 붙인4상태, 초기 P는 Full packet.P0다. 이후 원래 online.predict/core.predict와 동결 ds/gy/dt/Q를 그대로 사용한다. 각 시점의 BASE predicted state/covariance b-,C-에서 원래 SourceFFD.batch의 hB,HB를 구한다.

SB=HB C- HB^T+RBASE_F. arm a의 vB_a=z_a-hB-muBASE_F, NIS_a=vB_a^T SB^-1 vB_a. a_a=(NIS_a <= 9.210340371976184). FF/LF/FL/LL의 z 조합은 C1a와 같다. Full BASE mean과 RBASE를 네 arm에 공통 유지한다. 기존 BASE는2차원 전체 수용/전체 거절이며, per-channel gate·range-only 갱신을 새로 추가하지 않는다. 행렬 연산/대칭화/Heading wrap 순서는 원본 online.replay의 shadow 구간과 같다.

다음 시점 BASE shadow로 넘어갈 때는 **FF 관측과 FF gate만** 사용해 원본 Joseph update를 한다. 다른3개 arm의 현재 gate 판정은 이 Full shadow 이력에 영향을 주지 않는다. 따라서 네 arm의 BASE prior도 같은 현재 시점의 것이라는 조건을 유지한다. 이는 새로운 네 개 재귀 필터가 아니다. 원래 결과에는 shadow prior/H/S가 없고 mask만 있어 이 gate 전용 재구성은 필요하다. 원래 MB_VAR 기준 궤적을 다시 생성하는 작업과 구분하여 재구성 횟수를 명시한다.

FF gate는 모든 시점 기존 Full trace.mask와 정확히 같아야 한다. 차이가 있으면 다음 조건/확장으로 진행하지 않는다. DEV에서 SourceFFD h/H를 저장된 MB_VAR prior에 평가하여 기존 h/H와도 atol/rtol1e-10으로 대조한다. 이는 원본 소스·bank·runtime의 연결 검사이며 prior/H 자체를 바꾸는 것이 아니다.

## 동일 MB_VAR prior에서 조건부 갱신

MB_VAR의 x-/P-/h/H/mu_F/Rvar_F는 기존 C1a와 같은 Full trace에서 고정한다. `K_star = P_prior @ H.T @ inv(H @ P_prior @ H.T + Rvar_F)`를 **기존 FF mask와 무관하게** 계산한다. arm별 K_a는 새 BASE gate가 true면K_star, false면0이다. FF가 거절됐던 시점에도 hybrid가 새로 수용되면 K_star가 필요하므로 C1a의 이미0으로 마스킹된 K를 그대로 쓰면 안 된다.

u_a=x-+K_a(z_a-h-mu_F). 수용 시 psi를[-pi,pi)로 wrap, 거절 시 x-를 그대로 반환한다. P_a는 해당 K_a의 Joseph 식(수치 대칭화), 거절 시 P-다. hybrid에도 Full mean/Rvar를 유지한다. 채널을 두 번 순차 갱신하지 않는다. arm별 gate 차이 때문에 P가 다를 수 있지만 이를 covariance calibration 개선이라고 해석하지 않는다.

FF의 x/P/K/mask는 원래 Full trace 및 C1a FF와 재현돼야 한다. 각 hybrid에 대해 C1b 결과와 C1a 같은 arm의 차이는 같은 관측·MB_VAR prior에서 현재 gate만 달라진 조건부 효과다. 개입 후 미래 prior는 갱신하지 않는다. C2에서처럼 재귀 후 K/P가 변한 결과와 혼합하지 않는다.

## 수치·제외·기록·주장

기존 C1a와 같은 pose/time exact join, 중복·누락0, 모든 행 유한, baseline/독립 K/Joseph/선택 갱신 atol/rtol1e-10을 사용한다. Heading은 원형 차이와 wrap전 u를 구분한다. 공분산 대칭/음의 고유값 허용치는1e-12*max(1,||P||_2); jitter/clipping 금지. solve 실패·소스/환경/키/mask/parity 불일치는 최초 STOP, 로그·완료/미완료 조건·실패 위치를 보존한다. 실패 행 사후 제외, 자동 재시도/덮어쓰기, DEV 실패 후 잔여 확장 금지.

core/gate에는 GT를 전달하지 않는다. 사후 evaluator가 모든 시점 XY[m]·Heading 절대오차[degree], FF 및 C1a 같은 arm 대비 차이와 gate 변화(true→false/false→true) 수를 계산한다. t>=30s의 조건별 평균·중앙값을 별도로 보고한다. 미래10/20초 적분/NEES/coverage는 C2에서 평가하며 이 단계의 결과로 대체하지 않는다. 효과 부호에 수치 PASS 기준을 걸지 않는다.

출력에는 pose/t, BASE b-/C-/hB/HB/SB/muBASE/RBASE/NIS4/mask4, frozen MB_VAR prior/H/mu/R, unmasked K*, 4arm x/u/P/K, RF delta, evaluator CSV, 원본/C1a parity·분모·실패 원장, runtime/명령/코드·입출력 SHA/시각/exit를 포함한다. 모든 결과는 신규 DEV_001 또는 REMAINING_001에만 기록한다.

독립 SPEC_APPROVED → 합성 gate/선택 갱신/거절·상관 R·경계 검사 → 코드·입력·runtime SHA 독립 GO_DEV → DEV 결과감사 → 새 GO_REMAINING → 잔여114조건 실행·결과감사 → 전체120조건 누락/중복 검증·게시 순서다. 전체 결과는 같은 RF/공개 seed의 사후 기전 분석이며, 새 online gate의 채택·일반화·긴 시간 Heading 과신 인과효과를 입증하지 않는다. C2는 C1a/C1b 완료 뒤 별도 상세 계약·SPEC/코드 GO가 필요하다.
