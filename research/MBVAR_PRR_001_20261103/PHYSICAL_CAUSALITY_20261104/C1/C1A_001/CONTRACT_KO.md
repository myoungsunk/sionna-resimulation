# C1A-SAME-PRIOR-001 — 동결 Full prior의 거리·편파 단일 갱신 대조

역할: PROPOSER. 상위 CAUSAL_VERIFICATION_PLAN_KO.md의 C1a만 구체화한다. 거버넌스 RESEARCH-GOVERNANCE-v1 COMMON_CONTRACT 및 ROLE_PROPOSER/ROLE_IMPLEMENTER를 적용한다. 과학 원본 기준 Git17cbfb8bef78518729d5010dbf463df87e828c0c. 기존 S1–S3/N0B/R2/14pose/C0-B 실행과 판정은 수정하거나 재실행하지 않는다. 새로운 RT·학습·정책 설계도 하지 않는다. 이 문서만으로 과학 실행 GO를 발급하지 않는다.

## 질문과 비교 범위

Q: 이미 감사된 Full MB_VAR의 같은 prior에서 원시 거리와 편파 관측만 LoS 값으로 바꾸면, 각 성분이 그 한 번의 posterior 갱신에 어떤 영향을 주는가? 큰 RF 편파오차가 큰 Heading 영향으로 이어진다는 설명과, 실제 K 및 prior 오차에 따라 영향이 달라진다는 설명을 구별한다.

이번 단계는 C1a의 조건부 단일 갱신 계산이다. 과거부터 새 필터를 돌리거나 새로운 gate를 평가하지 않는다. 재귀 인과효과·복구 손익·온라인 guard 유효성·새 환경 일반화는 주장하지 않는다. C1b/C2는 이 결과와 별개 계약 및 GO가 필요하다.

## 표본·입력 동결

- R2/R4/R5, Anchor B, mount0, B0/L2, 기존 공개 seed10–29의 Full baseline120개. 모든 원래 pose를 포함한다(R2 979, R4 742, R5 1415개씩). 총125440 prior, 4arm=501760 posterior이다. 같은 RF를 공유한 센서 seed 반복이며 독립 RF 표본이 아니다. 신규 잠금 평가가 아니다.
- INPUT_LOCK.json의145파일 SHA/크기/기준 Git 경로를 사용한다. R4/R5의 기존 materialized packet/truth는 동일 기준 Git의 S1/MATERIALIZED_INPUTS.json과 payload hash를 대조한다. R2 packet은 inputs와 native_inputs의 별도 INPUT_LOCK registry를 대조한다. 모든 Git LFS payload는 OID·크기도 검증한다.
- Full priors는 S1 EVAL_001 W0 및 R2 FULL_002 A의 이미 감사된 trace이다. R2 FULL_001이나 역사적 MB_ORIG는 사용하지 않는다. Full/LoS packet·truth·trace의 pose_id/t는 정확히 같고 중복이 없어야 한다. 관측·평균·R·prior·H·mask의 row를 재정렬하거나 최근접 보간하지 않는다.
- Full trace에 동결된 prior/Pprior/H/h/mu/Rvar/mask/K와 packet의 z_F,z_L를 사용한다. x0/P0/Q/controls·held-route 학습 모델·변환·특징 순서의 효과는 이 trace/packet에 이미 고정되어 있다. 모델을 다시 호출하거나 재학습·mean/R 교체·새 prior 생성하지 않는다. 이를 원래 FFD 모델의 새 재현 실행으로 주장하지 않는다. trace provider 코드의 해시는 INPUT_LOCK에 포함한다.
- pinned WSL Python3.11.17/NumPy1.26.4, 1 BLAS thread를 사용한다. runtime과 실행 코드·계약·입력 lock SHA를 독립 GO에 묶는다. 원본 입력은 읽기 전용, 신규 출력은 없던 RESULTS_001이어야 한다.

## 수학과 게이트

상태 x=(X[m],Y[m],psi[rad],b_g[rad/s]), 관측 z=(r[m],s[무차원]). 각 k의 x-,P-,h,H,mu_F,Rvar_F와 기존 BASE joint mask a_F를 모든 arm에서 고정한다. 기존 BASE는 2차원 공동 NIS 기준 9.210340371976184의 전체 수용/전체 거절이다. 채널별 거절·range-only arm을 이번 단계에 추가하지 않는다.

arm FF=(rF,sF), LF=(rL,sF), FL=(rF,sL), LL=(rL,sL). LoS는 원시 z 성분만 제공한다. hybrid에도 Full mu와 Full Rvar를 유지한다. Native-LoS용 학습 mean/R를 hybrid에 넣지 않는다.

S=H P- H^T+Rvar_F, K=P- H^T S^-1; mask가 false면 K=0. 모든 arm에서 이 동일 K를 사용한다. u_a=x-+K(z_a-h-mu_F), 수용한 x_a는 u_a의 psi만 [-pi,pi)로 wrap한다. 거절한 x_a는 원본처럼 x-를 추가 wrap 없이 그대로 보존한다. P_a=(I-KH)P-(I-KH)^T+K Rvar_F K^T이며 mask false면 P_a=P-. 원본과 같이 수용 시 S/P의 수치 대칭화를 한다. 관측을 순차 두 번 갱신하지 않는다.

검사: u_FL-u_FF=K_s(sL-sF), u_LF-u_FF=K_r(rL-rF), u_LL-u_LF-u_FL+u_FF=0. wrap 이전 u로 선형 항등식을 검사하고, wrap 이후에는 원형 Heading 차이를 별도 검사한다. arm 사이 같은 P는 설계상의 항등식이며 covariance 개선 결과가 아니다. 실제 prior에 대한 H_psi는 s/rad이며 K_psi,s와 구별한다.

## 수치·실패·결과 계약

- baseline FF를 원본 trace x/P/K/mask와 대조한다. x의 Heading은 원형 차이, 다른 성분과 P/K는 np.allclose(atol=1e-10,rtol=1e-10), mask/pose/t는 정확 일치. 저장된 nu=z_F-h-mu_F 및 Rvar=trace Reff(W0) 일치도 같은 허용오차로 검사한다.
- 독립 K/Joseph 및 선형 항등식은 같은 atol/rtol1e-10. P 대칭 오차와 최소 고유값은 1e-12*max(1,||P||_2)까지 반올림 오차로 인정하며 큰 음수는 STOP. eigenvalue clipping·jitter·자동 대체를 하지 않는다. S solve 실패도 STOP.
- 행 누락/중복/키 불일치/비유한 값/잠금 위반/수치 실패가 한 건이라도 있으면 전체 STOP. 실패 위치·최대 오차·모든 완료/미완료 셀·로그를 보존한다. 실패 행 사후 제외 및 자동 재시도·출력 덮어쓰기 금지.
- core에는 truth를 전달하지 않는다. 모든 arm 계산이 끝난 후 별도 evaluator만 truth로 XY 유클리드 오차[m], Heading 원형 절대오차[degree]와 FF 대비 차이를 계산한다. 모든 시점 원장을 보존하고 t>=30s의 route/bias/seed별 평균·중앙값을 별도로 보고한다. 효과 부호에 합격 기준을 걸지 않는다. 이번 C1a는 미래10/20초 적분·NEES/coverage·재귀 공분산 과신을 평가하지 않는다(C2 계약 범위).
- 출력은 per-condition NPZ(pose/t,shared prior/H/mu/R/K/mask/P,4arm x 및 wrap전 u,RF delta), pose별 evaluator CSV, 수치검사 JSON, 실행 환경/명령/시각/exit/hash manifest와 실패 원장이다. 원본 trace에 새 결과를 써넣지 않는다.

## 관문과 허용 주장

독립 SPEC_APPROVED → 격리 구현/합성 검사 → 코드·입력·runtime SHA의 독립 GO → 신규 단일 C1a 실행 → 독립 결과감사 → 단계별 GitHub push 순서이다. 합성 검사는 무작위 선형·상관 R·거절·yaw 경계·입력 비변경을 포함하며 실제 데이터 효과 결과를 보지 않는다. independent verifier는 production core를 호출하지 않고 K/Joseph·arm identity·baseline parity·누락과 집계를 검산한다.

허용 주장: 동결된 기존 RF/Full prior에서 관측 r/s 교체의 한 번 갱신 효과 및 정확한 선형 분해. 수치 PASS는 개선/채택 PASS가 아니다. 다음 C1b에서는 동일 BASE shadow prior의 gate 재판정을 별도 정의해야 하며, MB_VAR prior의 NIS를 원래 BASE gate라고 부르지 않는다. C2의 고정 mask는 분기 후 K/P 고정을 뜻하지 않는다. C1b/C2의 source/control 재귀·R2 대조군·NEES 계약이 동결되기 전 그 단계는 실행하지 않는다.
