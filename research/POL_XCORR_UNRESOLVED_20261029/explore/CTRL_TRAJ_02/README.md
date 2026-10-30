# CTRL-TRAJ-02 — 실제 SourceFFD 안테나 통제 궤적 실험 (EXPLORATORY)

- 성격: 탐색 실험, label 미사용. POL-XCORR-001 estimand와 무관하다.
- 실행: Actions run [40998613717](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40998613717) → `results_run_40998613717/`
- 안테나: sha 검증된 FFD bank(LP_plus45 `b29ae471…`, LP_minus45 `39729fe9…`), corridor ANCHOR_ROTATION, robot rot_z(yaw + mount)
- 반사: ceiling·floor(concrete 0.2 m slab), wall ±1.2(plasterboard 12.5 mm slab), ITU-R P.2040, 1회
- 경로: y = 0.3, z = 0.45, x 4.2 → 19.8 m(4 cm), yaw_body 0/180°, mount 0/45°

## V0 — 채널 구성 검증

이 실험의 LoS 채널식을 저장 corpus의 Sionna H_LoS(7 case × 64 pose)와 비교했다.

| 지표 | 결과 |
|---|---|
| 상대오차 중앙값 | 3.6e-5 – 5.5e-5 |
| 상대오차 최대 | ≤ 2.4e-4 |
| 편파 상태 각도 차 | ≤ 1.7e-4° |
| s_fp 차 | ≤ 6.4e-6 |

→ 안테나 모델링이 corpus와 일치한다.

## 결과 (원거리 ρ > 6 m, 4개 mount·yaw 조합 범위, 단위 °)

| 항목 | LOS | LOS+C | LOS+F | LOS+W |
|---|---|---|---|---|
| prior 없는 궤적 진동 (2 m rms) | 0.29–0.60 | **0.24–0.65** | 3.4–15 | 14–33 |
| 예측 LoS 대비 편차 (prior/모델 기반) | 0 | **6.9–8.9** | 6–23 | 14–38 |

heading prior 오차가 만드는 예측 LoS 상태 오차(LoS 채널, 원거리):

| prior 오차 | 상태 오차 |
|---|---|
| 1° | 1.0–2.5 |
| 2° | 2.1–5.1 |
| 5° | 5.2–13.5 |

## 해석

1. **원거리 ceiling은 prior 없는 궤적 진동으로는 보이지 않는다.** 진동 0.24–0.65°로 LoS 기준선 0.29–0.60°와 같다. 이상 안테나 실험(CTRL-TRAJ-01)과 같은 결론이다.
2. **예측 LoS 상태와 비교하면 보인다.** 편차는 6.9–8.9°로, 이상 안테나(2–5°)보다 크다. 실제 패턴은 grazing 방향에서도 TM 성분을 가지기 때문이다.
3. **분리 조건은 heading prior 정확도다.**
   - 오차 1°: 신호/오차 비 약 3–8.
   - 오차 2°: 약 1.5–4.
   - 오차 5°: 분리되지 않는다(prior 오차가 ceiling 편차와 같거나 크다).
   - 기존 P1 설정의 σψ = 3°는 경계 수준이다.
4. **floor·wall은 원거리에서도 prior 없는 진동으로 보인다**(3–33°). ALL 시나리오에서는 wall이 편차를 지배한다.
5. LoS q_W는 0.001–0.007로 corpus LoS floor와 같은 범위다(안테나 분산 floor 재현).

## 한계

- 오차 항목으로 heading만 넣었다. tag roll/pitch, anchor 장착각, FFD 보정 오차는 정적 편차를 만들어 ceiling 편차와 혼동될 수 있으나 포함하지 않았다.
- 1회 반사와 직선 경로 1개만 다뤘다. 다중 반사와 끝 벽은 제외했다.
- 고정 offset 오차만 다뤘다. 실제 prior 오차 분포(시간 상관, bias)는 다루지 않았다.
