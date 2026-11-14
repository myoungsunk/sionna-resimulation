# G1-MODEL-003 새 RT 사양 검토

- 검토일 2026-11-14 KST
- 대상은 `research/g1-sweep-heading-floor-spec-20261113`의 `8f7fdd75ea3ac5ffa9e3284cd1f5470977cf41d1`에 있는 [새 RT 사양서](SPEC_B_NEW_RT_KO.md)다.
- 판정은 **REDIRECT**다. 아래 두 항목은 관련 단계의 실행 계약을 동결하기 전에 해소해야 한다. 사양 문서 대조만 수행했다.

## 확인한 연구자 결정

- mount 0°, P-C를 포함한 B 방식, J-V arm, 거리 오차 기반 ranging 규칙, Sensor-v2 B0/L0/L1/L2와 TB3 점이 문서에 반영돼 있다.
- G1-DIAG-003의 회귀 PASS가 S0의 선행 조건이다. 0.2 s timeline을 동결하고, S1의 합성 LoS와 RT tap 일치율은 99% 이상이어야 한다. G-T1 특성화는 계획 선커밋 후 한 번 실행한다. LOAO 통과 arm이 있어야 확인용 6조합의 봉인을 풀 수 있다.
- B 방식은 pooled heading 포함률 점추정 ≥ 0.92 및 95% CI 상한 ≥ 0.95, heading·XY·gyro bias의 평균 NEES 각각 0.5–2.0, pooled s packet 기각률 ≤ 20%를 요구한다. 어느 조합에서든 heading 또는 XY 포함률 CI 상한 < 0.80이면 실패다. B0 비열등은 DR 대비 heading RMSE 1.10배를 paired CI 상한으로 판정한다. 정확도는 integrity를 통과하고 S2-F에서 허용된 수준에서 지속 교차점 N†, J − R4, TB3 등가 bias 위치로 평가한다.

## 1. S1과 S3의 ranging 체인 선택 기준

**근거.** §0과 S1은 거리 오차로 ranging 규칙을 고르도록 정한다. S1의 OR 후보에는 기존 O30 규칙이 포함되며, 검출 실패율과 range RMSE로 선택한다. S3의 1차 arm 선택 규칙 4번은 같은 규칙으로 O30/OR 체인도 선택하도록 정한다. 이 규칙에는 LOAO integrity와 L1 heading RMSE가 들어 있다. O30과 OR이 다른 경우 최종 tap 규칙이 heading 성능에 따라 바뀔 수 있다.

**영향.** 최종 확인 실행에서 쓰인 ranging 규칙이 거리 오차로만 선택됐다는 주장의 근거가 불명확해진다.

**동결 전 해소안.** 거리 오차 기준이 최종 적용까지 이어지는 의도라면, S1이 고른 체인을 S3·S4의 1차 체인으로 고정한다. S3의 LOAO는 그 체인에서 arm을 선택하며 O30은 사전에 정한 대조로 보고한다. 사양의 S1·S3·S4가 같은 체인 선택 규칙을 가리키는지 확인한다.

## 2. C5와 S2-F의 지속 편향 검출

**근거.** S2 C5의 heading 바닥은 5 m 이동평균 오차의 표준편차를 대표 heading 감도 `median |∂s/∂ψ|`로 나눈 값이다. 경로 내 모든 5 m 창에서 오차 평균이 같은 비영 값이고 대표 감도가 유한한 양수라면, 이동평균 분산은 0이라 계산된 heading 바닥도 0이다.

**영향.** S2-F가 일정하게 지속되는 편향을 놓쳐, 해당 bias 수준을 정확도 판정 범위에 포함할 수 있다.

**동결 전 해소안.** 5 m 이동평균의 평균과 분산을 함께 보고한다. 두 성분을 함께 반영하는 후보로 중심화하지 않은 RMS `sqrt(mean(ē²))`를 명시하고, heading 환산에 사용할 감도와 작은 감도 처리, DR 비교의 경로·시점 대응, 동률 처리를 S2 계획에 고정한다. 일정한 비영 오차·평균 0의 변동·오차 0인 입력을 각각 검산한다. 이 계산은 S2-F의 사전 선별에 사용한다.

## 검토 이력

역할은 AUDITOR이며 검토 범위는 제안 사양의 문서와 수식이다. 연구 거버넌스는 로컬 RESEARCH-GOVERNANCE-v1을 참조했다.

| 지침 | SHA-256 |
|---|---|
| `COMMON_CONTRACT.md` | `a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb` |
| `ROLE_AUDITOR.md` | `e1bdc2f231c71cdc27201c688e041b078576a6adf6c0290acc16ce4d8218291a` |
