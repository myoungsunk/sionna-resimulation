# CLAIMS — POL-XCORR-001 (draft ledger, append-only)

전역 `docs/research-governance/CLAIM_REGISTER.md`는 MBVAR 범위이므로 수정하지 않는다. 승격은 독립 auditor 서명 필요.

| ID | 질문 | 상태 | 허용 표현 | 금지 표현 | 필요한 새 증거 |
|---|---|---|---|---|---|
| PX-001 | 단일 경로는 타원이어도 창 coherency rank-1인가 | NOT_RUN (수학적으로 자명, 수치 미확인) | 유도상 단일 경로에서 det J = 0 | φ≠0·S3≠0이 다중경로 증거 | P0 LoS 채널, S0 |
| PX-002 | 감지량 ∝ δ²·\|a∧b\|² | NOT_RUN | 2-path 소 δ 전개에서 유도된 예측 | 실제 채널에서 확인됨 | S0, T4(R-01 PASS 시) |
| PX-003 | M1이 \|ds1\| 이상의 정보를 준다 | NOT_RUN | 가설 | 감지됨/성능 향상 | P1 E1 |
| PX-004 | 교차상관 lag·비대칭(M2)이 M1 이상의 정보를 준다 | NOT_RUN | 부호 미정 가설 | — | P1 E2 |
| PX-005 | 이동 중 differential fading·breathing이 prior 없이 분리 가능 | NOT_RUN | 기하상 Λ ≈ 1–2 m 예측 | LoS면 두 편파 비율 일정 | P2a E3 |
| PX-006 | ceiling(anchor 5 cm 아래) 경로는 이 계열로 감지 불가 | PREDICTED_FROM_GEOMETRY | δ≈0.05–0.3 ns, Λ≈10–22 m 예측 | 감지 실패 = 방법 실패 | T4 분해 |
| PX-007 | route A/B(포트별 별도 패킷)에서 M1/M2 사용 가능 | NOT_RUN | ε_ρ는 포트 이득·위상 오프셋에 불변(수학) | 실장 가능 확정 | P3 E5 + R-07 실측 jitter |
| PX-008 | 일반화/실측 | BLOCKED | 단일 corridor scene retrospective | 일반화, 실측 검증, EKF 방어 | 신규 scene variant(R-11), P4 |
