# N0–N3 Full RF Heading 연구 — 순차 실행 보고 (2026-10-15)

**진행 상태:** N0·N1·N2 실제 실험/감사 완료. N3 통합 물리 특징량의 held-route 실험 실행 중이며 최종 결과가 확인되기 전까지 임의 수치를 기입하지 않는다.

## 공통 물리·추정기 계약

- `[x,y,ψ,b_g]` 4-state, `z=[range_raw,s]` (s=(P1−P2)/(P1+P2)); LoS FFD 2° LUT, original R0, 99% joint gate 유지.
- DR4는 RF 없는 동작 대조군이지만 B0에서 4-state 효용을 부정하는 주 평가 기준이 아니다. 연구의 주 평가 조건은 L0(+0.01°/s), L1(+0.05°/s), L2(+0.20°/s), B0는 거짓 Gyro Bias 오염 원인 통제.
- 모든 source/data/policy는 원본에서 변경 없이 복사한 별도 branch `research/r5-n0n3-audited-20261015`, 연구 로그는 기존 보고 위에 덮어쓰지 않음.
- Train/held-out = R4+R5 학습, R2 평가(같은 corridor). Eval `t>=30s`, seed 0, 829 frame/case.
- Signed Mean 및 G5 R_s는 원본 PHY 연구 물리 특징량(G0~G5); Range/전력/s/CIR 및 Dual LP 기초 지표와 분리하지 않음.

## N0 — 기준선 해시·정합 / 범위 한정 GO

- [Run 38694200212](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38694200212), [artifact 11953640791](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38694200212/artifacts/11953640791), ZIP SHA256 `aade786b83357086c9e645fa9b87467a869289aa93040e3b48410f44af2d08fb`.
- 원 RF 14 trace, R2 점수 256행, B0 Hard/Soft 60행 확인. 대응 8개 B0 DR4/J4 기준 수치 비교.
- **strict parity 예외는 보존:** B0 Full Mount0 J4 Pose NEES 차이 `0.008063471336754446`; 기존 state 최댓값 약 `7.58e−8`, covariance `6.06e−10`, Gate 차이 0. **전체 exact-equivalence PASS로 소급 불가.**
- `N0_SCOPED_GO_POSE_NEES_NOT_NUMERICALLY_IDENTICAL`, 이번 실험 내 같은 코드/입력을 사용한 paired 비교만 범위 한정 수용.

## N1 — L0/L1/L2 물리 신뢰도 정책 확장 / 계산 PASS

- [Run 38694638851](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38694638851), [artifact 11954136512](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38694638851/artifacts/11954136512), source `e189b444977ac9050e04320c8ee703fa2a5f4337`.
- 감사·원본 해시, 7개 핵심 수학·품질 테스트 PASS, 원본 R2 recursive 12개 트레이스와 gate/parity 검사. 204개 성능행(15개 새 정책 + 원 S4/SR4), raw posterior x/P/quality 12 세트 보존.
- 모든 G0/G2/G3/G4/G5 모델·`p>0.5/0.75` 임계값은 기존 B0 사전 고정. L0/L1/L2 결과를 보고 사후 튜닝하지 않음.

### Heading RMSE Full RF (deg)

| Mount | Bias | J4 R0 | G5 R_s | Signed Mean | Signed Mean+R_s | Hard full p50 | Hard s-only p50 |
|---|---|---:|---:|---:|---:|---:|---:|
| 0° | L0 | 7.4991 | 4.3047 | 4.6006 | **3.3622** | 5.8162 | 5.0191 |
| 0° | L1 | 7.5399 | 4.3257 | 4.6016 | **3.3676** | 5.8472 | 5.0420 |
| 0° | L2 | 7.5209 | 4.3776 | 4.5556 | **3.3884** | 5.8995 | 5.0590 |
| 45° | L0 | **0.8444** | 1.3487 | 1.1840 | 1.3490 | 4.0071 | 3.5896 |
| 45° | L1 | **0.8436** | 1.3511 | 1.1772 | 1.3493 | 3.9904 | 3.5827 |
| 45° | L2 | **0.8481** | 1.3610 | 1.1603 | 1.3526 | 3.9658 | 3.5597 |

**L2 Mount0 signed mean+Rs:** Heading NEES `12.8104`, Pose NEES `5957.58`, Gyro Bias RMSE `0.05943°/s`. Original J4 Pose NEES `297.85`. 즉 Heading point estimate가 좋아도 Pose covariance가 훨씬 더 과신됨. Mount45는 J4보다 성능 악화. 전역 채택 보류.

## N2 — LoS/Full Range×s 2×2 분리 / 계산 PASS

- [Run 38695060389](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38695060389), [artifact 11953388822](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38695060389/artifacts/11953388822).
- 동일 원본 R2 wheel+gyro, B0/L0/L1/L2, AnchorA mount0/45, **J4·SR4**, One-step·Recursive, natural & fixed/common E11 gate: **256개 평가행 및 64개 2×2 효과 분해행**, 원 E11 재귀/one-step source parity 검사.
- E00=[r_LoS,s_LoS], E10=[r_Full,s_LoS], E01=[r_LoS,s_Full], E11=[r_Full,s_Full].
- E10/E01은 실제 하나의 공동 RF 패킷이 아니고 원인 구분용 반사실적 측정 믹스. Gaussian cross-covariance 독립성을 주장하지 않음.

### L2 Recursive J4, E11 원본 수용 시간 마스크 공통 (Heading RMSE deg)

| Mount | E00 | E10 | E01 | E11 |
|---|---:|---:|---:|---:|
| 0° | 0.26793 | 0.77144 | **7.74424** | 7.52091 |
| 45° | 0.16738 | 0.48712 | 0.72776 | 0.84809 |

Mount0의 큰 Heading 오차는 s 오염 영향이 주도: E01 한 개만으로 E11과 비슷하게 악화. 그러나 Range 오염은 Pose 신뢰도에 큰 영향을 줌: Mount45 Pose NEES E00=5.34, E10=83.76, E01=11.12, E11=86.84. MSE 차이/interaction은 비선형 필터·시간누적/Gate 영향을 포함하여 전체 오차의 유일한 인과 기여율이 아님.

## N3 — 전체 물리 특징량 재평가

**평가 항목:** 원 PHY G0~G5와 이전 전력 P1/P2·총전력·s·CIR first-path/peak·early8 포트별 비율·dual-port JSD/shape L1. 실제 archive `z_r,z_s` 14,502시점 전수 parity, route-heldout 동일 fixed RandomForest 회귀+분류, 1.5m x block 재표본화 신뢰구간.

중요 구분:
- `e_total^2=(s-h_LoS(true))^2` 조건부 예측과 `|s_Full-s_directLoS|>0.1` 오염프록시는 **Heading 위해성 label이 아님**.
- `s`, `P1/P2`, `log(P1/P2)`는 서로 결정적으로 관련되어 독립 RF 정보라고 해석하지 않는다.
- Complex frequency Jones G3/G5는 DWM1000에서 구현된 실제 측정 특징으로 볼 수 없으므로 research-only.
- 외부 독립 Scene/기구 회전/Active Gradient 정보는 이 N3 실행 범위 밖.

## 다음 결과를 위한 연구 게이트

N3 통과 뒤 N4: 실제 RF observation-conditioned Heading harm, Range signed bias 및 `R_r,R_{rs},R_s`의 centered covariance와 temporal correlation을 검증. N5: 기존 169개 Full yaw sweep에 PHY feature+Gradient를 결합하고, nuisance 제거 Heading 정보량 및 multi-modal likelihood 평가. 별도 수치 경계 MAP solver 문제는 독립 트랙으로 유지.
