# G2/G3 최소 단계 사전 감사 — 2026-10-14

## 결정
**GO_WITH_CLAIM_LIMITATION**: 아래 고정 코드로 수식·합성·보관자료의 한정 진단을 실행한다. 전체 비선형 G2/G3, 새 CIR 품질 학습, 재귀 융합, 외부 장면 일반화는 실행·채택하지 않는다.

기준 문서: 사용자 지정 9beb061f354edef18e1f977f5d462d7e0d8b1f2e / research/EKF4_RANGE_S_STAGED_20261014/PRE_RUN_AUDIT_POLICY_20261014_KO.md (Git blob df9ec6121f3f0c953e58ef8e85ce436ed9a79334).
검사 목적: '이 정확한 코드와 입력으로 계산 가능한 최소 모델을 검증할 수 있는가? 어떤 출력/주장만 차단해야 하는가?'

## 감사 방법과 독립성
작성/소스 감리: assistant. 별도 사람 또는 별도 모델 reviewer가 수행했다는 주장을 하지 않는다.
독립 계산 경로는 실행 시 다음 두 쌍을 비교한다.
1. 절단 Gaussian 곱의 해석적 evidence/평균/분산/모드 가중치 vs 정규화된 prior×likelihood 직접 적분(생산 코드의 posterior 평균·분산을 quadrature 배치에 재사용하지 않음).
2. 선형 3-state joint 정보형 해 vs 조건부 noise decorrelation 및 순차 Joseph 업데이트. 양·0·음 R_sr, full P_xy,psi 및 mixture evidence 가중치 유지.
최종 오차 승패·선택 mask는 별도 finalize.py에서 원시 거리 제곱오차로 재계산한다. 동일 helper 재호출을 독립 검산으로 세지 않는다.

## 핵심 수식 감리
r>=h=2.2 m, d∈{normal,fault}, k=RF mixture component.
Prior N(r;mu,v_d)/T_d, T_d=Phi((mu-h)/sqrt(v_d)).
Likelihood N(z;r+b_k,v_k). Signed residual는 z-r이므로 양의 b는 긴 거리, 음의 b는 과소보정이다.
v_post=(1/v_d+1/v_k)^(-1), m_post=v_post*(mu/v_d+(z-b_k)/v_k).
Z_dk=N(z;mu+b_k,v_d+v_k)*T_post/T_d.
Weights ∝ pi_d*pi_k*Z_dk. 절단 정규화 비를 생략하면 모델 선택 가중치가 잘못되므로 필수 검산 대상이다.
절단 평균 m+s*lambda, 분산 s²(1+a*lambda-lambda²), a=(h-m)/s, lambda=phi(a)/Phi(-a). log_ndtr로 tail 계산.
동일 Range factor는 1회만 적용한다. G2 linear 조건부 S는 alpha=R_sr/R_rr, H_tilde=H_s-alpha H_r, z_tilde=z_s-alpha z_r, R_tilde=R_ss-R_sr²/R_rr.

## 발견사항 및 영향 범위
| ID | 분류 | 내용 | 결정 |
|---|---|---|---|
| A01 | CLAIM_BLOCK | RF 혼합모수·2m fault spread·fault prior 0.05는 물리적으로 추정/독립 보정된 값이 아니라 고정 합성 가정 | 최소 수식/가설 진단 GO; calibrated source probability·실제 G2/G3 채택 주장 금지 |
| A02 | CLAIM_BLOCK | 이미 본 E1 반례가 synthetic 음수 component 설계에 영향을 줌 | 같은 데이터 replay는 탐색/진단만, 독립 확인으로 표현 금지 |
| A03 | HARD_EXECUTION_BLOCK 방지 | 원본 dr_pred_range_sigma_m에는 Rr가 이미 포함되어 있음 | shadow prior variance에서 0.0068578637 m²를 1회 차감. 비양수면 그 입력 실행 차단 |
| A04 | CASE_RESULT_INVALID | 특정 절단 분산/적분이 비유한이면 해당 fixture invalid | 수치 오류를 희석하지 않고 fixture 분모 기록. 독립 linear algebra는 계속 |
| A05 | DIAGNOSTIC_DEFECT_OR_WARNING | optional curvature metadata 부재와 수식 오류를 혼동할 위험 | 주입형 음성 대조로 estimator 불변 확인; 이 주입을 실제 solver 실패로 표현하지 않음 |
| A06 | CLAIM_BLOCK | 같은 observable 입력에서 DR 오류 또는 RF 오류인 두 세계가 가능 | alias 대조는 식별 가능성의 범위 제한. 실제 두 번째 현장 사례라고 하지 않음 |
| A07 | 실행기 결함 사전 방지 | 비어 있는 검산 목록을 all([])로 PASS 처리하는 위험 | 독립 finalize.py만 최종 실행. stages.py의 편의 final branch는 실행 권한에서 제외 |
| A08 | CLAIM_BLOCK | 223,236개 행은 223,236개 독립 RF 장면이 아님 | 원본 6,201 RF/방법, 7 case, 3 route 기준 유지 |

## 기존 증거 재사용
Run 38523237789, artifact 11875206058, 원본 코드 28bc2212c3bfa70f5c6d7eedec974cefbf79d516.
ZIP SHA256 56276ccb88605382b801f080cb97b58bc465bcff46c78677bcaf14fcd1b62bd5.
D0 84개 및 D4 bin parity는 이 불변 artifact에 대해서만 REUSED_VERIFIED. 다운로드 ZIP 전체 해시와 추출 파일 해시를 다시 확인. RF H/센서/LUT를 재실행하거나 이전 PASS를 새 모델에 이전하지 않는다.

## 단계별 진행·차단
- math: 해석해 vs 직접적분 및 3-state linear identity, 이중 Range 음성 대조. 필수 계산 정확성.
- controls: C1 정상, C2 DR drift, C3 RF 과소보정, C4 RF 과대측정. 가설 미지지는 claim만 보류.
- acquire/shadow: 원본 artifact 정확성 확인 후 반경 모델의 관찰용 replay. 데이터 실패는 shadow만 차단, 독립 합성은 계속.
- diagnosis: 계약에 미리 고정한 9개 prior sensitivity 및 동일입력 alias. best parameter 선택·성능 재최적화 금지.
- final: 별도 재계산 경로로 출력 확인. 누락 자료를 PASS로 대체하지 않음.

모든 단계는 gate.py를 선행하며 APPROVAL.json의 Git blob 목록과 실제 체크아웃 bytes를 비교한다. source Git blob과 실행 commit을 함께 기록하고, source SHA256도 실행 시 기록한다. 감사 문서와 실행 커밋 사이의 차이는 승인 영수증/문서뿐이어야 한다. 코드 push만으로 실행되지 않으며 승인 영수증 변경 후에만 workflow 진입한다.

## 예산·종료
단일 cloud job 15분 상한, 수식오류/진단 bug는 영향 범위 내 최대 2회 수정·재감사 가능. 과학적 모형을 결과에 맞추는 자동 재설계는 0회.
가설 미지지 시 이미 승인된 bounded diagnosis까지 완료하고, 다른 관측 특성/물리 prior/새 알고리즘으로 변경하기 전 사용자 방향 확인을 받는다. 현재 가설의 진단을 끝내는 것과 새로운 과학 가설을 실행하는 것을 구분한다.

실행 가능성·계산 유효성·가설 지지·과학적 주장 허용을 별도 영수증 필드로 기록. 기존 G3 0.387 FAIL은 해당 원본 G3 reference에 대해 그대로 유지한다.
