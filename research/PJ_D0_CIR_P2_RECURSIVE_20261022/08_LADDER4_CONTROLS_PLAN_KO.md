# 사다리 4 — 증강·d0 정보·early stopping·갱신/gate R 분리 (실행 전 고정, 2026-10-23)

## 검토 반영 (검증 1·2 해석 정정)
- c1은 "참 상태에서도 남는 보정기 잔차"(미제거 다중경로, 과보정, 잘못된 bias 예측 포함). 결론: 주된 요인은 현재 상태 오차의 오인보다 참 상태에서도 남는 편파 보정기 잔차.
- `V1_STRATA`의 FP 이동 층별 값은 전 시간·전 패킷 기준이었다. t ≥ 30 s·accept 기준 재집계에서 R2 세 case 모두 FP 이동 0 층에서 WIDE가 평균 편향을 키운다. FP 이동량은 오프라인 진단 라벨이며 FP 이동 0이 깨끗한 패킷을 뜻하지 않는다.
- 사다리 3의 PWIDE→PWIDE_KV는 갱신 R과 gate R을 함께 바꿨다.
- PCIR→PWIDE(그리고 사다리 1 S3→S4, P1R WIDE vs CIR_ONLY)는 d0 추가와 학습 행 3× 복제가 함께 바뀌었다. 추가로, HGB `early_stopping='auto'`가 학습 행 > 10,000에서 켜져 1× 모델(5,610–7,675행)은 꺼지고 3× 모델(16,830–23,025행)과 NARROW 2×(11,220–15,350행)는 켜져 있었다(무작위 10% 내부 검증, 복제 행이 양쪽에 섞임).
- 학습 route 내부 LORO 지표(R², 잔차 평균, κ)는 inner μ가 상대 학습 route의 라벨로 적합되어 순수한 미래 예측력이 아니다. held route 격리는 유지된다.

## 설계
모든 신규 모델은 P1R HGB 하이퍼파라미터 + `early_stopping=False`, n_iter_ 기록. 학습 route만 사용.

| 모델 | 행 | d0 | 비고 |
|---|---|---|---|
| X1 | 패킷당 1 | 없음 | = 기존 CIR_ONLY / PCIR (원래 ES off였으므로 parity) |
| X3 | 같은 행 ×3 | 없음 | 행 수만 3× |
| SHUF | ×3, X와 같은 δ 추출 | 행 사이에서 섞음 | d0 분포는 같고 정보 없음 |
| D0 | ×3, 기존 WIDE/PWIDE와 같은 δ 추출 | 참 d0 | 기존 모델과 ES 설정만 다름 |

W 계열(목표 e, μ_s = 0)과 P 계열(목표 Δ = e − μ_inner, μ_s = POWER) 각각.

사다리(NOM, Full B0/L2, R = POWER V_s):
- W: CIR → CIR3(행 ×3) → WIDE_SHUF(정보 없는 d0 열) → WIDE_NOES(d0 정보). WIDE_PREV → WIDE_NOES(early stopping만).
- P: PCIR → PCIR3 → PWIDE_SHUF → PWIDE_NOES → PWIDE_NOES_KU(갱신 R = κV_s) → PWIDE_NOES_KV(gate R도). PWIDE_PREV → PWIDE_NOES.
- κ = P_D0의 학습 route LORO mean(ε²/V_s).

QA (1e-7): L_BASE = P2-A, L_CIR·L_WIDE_PREV·L_ORACLE = 사다리 1, L_PCIR·L_PWIDE_PREV = 사다리 3.

판정: 임계값 없이 route × 조건 × case별 크기와 방향. d0의 독립 기여는 SHUF → D0 단계에서만 주장한다.
