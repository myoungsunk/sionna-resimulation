# G1 packet 단위 EKF 재검증 (2026-11-14)

추정기를 원래 접근(packet 단위 재귀 EKF)으로 되돌린 뒤의 두 갈래 사양이다. S2′ STOP과 Step 3 보류는 유지한다.

| 갈래 | 사양 | 데이터 | 역할 |
|---|---|---|---|
| 기존 데이터 | [G1-DIAG-003](SPEC_A_BLOCKC_KO.md) | BLOCK_C 연속 주행 RF | 원래 EKF4 회귀 재현과 integrity 실패 기전 분리(DIAGNOSTIC_ONLY) |
| 새 RT | [G1-MODEL-003](SPEC_B_NEW_RT_KO.md) | G1-RT-TB3 생산(`6242fb9`) | 관측 체인 → G-T1 특성화 → 개발 → 봉인 해제 확인 |

G1-DIAG-003 결과는 G1-MODEL-003의 arm 우선순위 해석에만 쓰고, 모수로 옮기지 않는다.

기존 데이터 갈래의 재개 조건과 판정 검토안은 [G1-DIAG-003 계획](DIAG003_PLAN_KO.md)에 기록했다.

새 RT 사양의 실행 전 검토는 [G1-MODEL-003 검토](REVIEW_B_NEW_RT_KO.md)에 기록했다.
