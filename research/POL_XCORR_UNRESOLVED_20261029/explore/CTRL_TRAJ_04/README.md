# CTRL-TRAJ-04 — d0(전력만) vs 신호 상관(Stokes) 직접 비교, 실제 heading prior 오차 (EXPLORATORY)

- 실행: Actions run [41003294951](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41003294951) → `results_run_41003294951/`
- 조건은 CTRL-TRAJ-03과 같다.
  - 실제 FFD bank, slab Fresnel, 직선 y = 0.3.
  - 원거리 ρ > 6 m, 1 m 창.
  - run 39376076166 EKF heading prior 오차 2,556구간(9 arm × B0/L2).
  - mount 0/45° × yaw_body 0/180°.
- 바꾼 것은 통계뿐이다. label은 쓰지 않았다.

## 비교한 통계

| 통계 | 사용 정보 | 정의 (창 평균) |
|---|---|---|
| d0_fp | 전력만 (FP tap) | \|s_fp(obs) − s_fp(pred ψ+e)\|: EKF 관측과 같은 이전 d0 |
| d0_W | 전력만 (7-tap 창) | \|(J11−J22)/(J11+J22) 편차\| |
| d0_*_fit | 전력만 | 창마다 heading 오차 1개를 ds/dψ 방향으로 LS 적합한 뒤 남는 rms. 전력만 쓰는 통계가 heading 오차를 뺄 수 있는 유일한 방법이다. |
| Dvec | S1 + S2/S3 | \|S(obs) − S(pred)\| |
| **Dperp** | S1 + **S2/S3** | heading 곡선 접선 ∂S/∂ψ에 직교하는 성분 |
| Dvec_fit | S1 + S2/S3 | 창 단위 LS 적합 후 남는 rms (d0_*_fit와 같은 방식) |

## 결과: 원거리 ceiling (NULL = LoS vs LOS+C), 4조합 pooled

| 통계 | AUC | TPR @ FPR 5% | TPR @ FPR 10% | alt/NULL 중앙값 비 |
|---|---|---|---|---|
| d0_fp | 0.726 | 0.115 | 0.296 | 3.3 |
| d0_W | 0.757 | 0.129 | 0.295 | 3.4 |
| d0_fp_fit | 0.670 | 0.057 | 0.107 | 2.3 |
| d0_W_fit | 0.654 | 0.050 | 0.101 | 2.0 |
| Dvec | 0.854 | 0.080 | 0.294 | 3.6 |
| **Dperp** | **0.930** | **0.546** | **0.800** | **29** |
| Dvec_fit | 0.869 | 0.411 | 0.518 | 8.2 |

mount·yaw별 TPR @ FPR 5%:

| 통계 | (0, 0) | (0, 180) | (45, 0) | (45, 180) |
|---|---|---|---|---|
| d0_fp | 0.025 | 0.375 | 0.030 | 0.347 |
| d0_W | 0.030 | 0.393 | 0.031 | 0.209 |
| Dperp | 0.695 | 0.570 | 0.346 | 0.710 |

arm별 AUC (18 arm × cond): Dperp 0.86–0.95, d0_fp 0.61–0.80. **18개 모두 Dperp가 높다.**

### 오차가 작은 구간만 판별할 때 (참값 rms 기준, oracle 상한)

| 구간 오차 rms | d0_fp TPR | d0_W TPR | Dvec TPR | Dperp TPR |
|---|---|---|---|---|
| ≤ 2° | 0.54 | 0.54 | 0.98 | 0.95 |
| ≤ 4° | 0.29 | 0.31 | 0.62 | 0.88 |
| ≤ 8° | 0.20 | 0.23 | 0.34 | 0.82 |
| 전체 | 0.12 | 0.13 | 0.08 | 0.55 |

### 참고: 다중 반사 포함 (ALL = ceiling + floor + wall)

- d0_W_fit은 AUC 0.967, TPR 0.75로 높다.
- Dperp는 AUC 0.985, TPR 0.93이다.
- floor·wall은 1–2 m 주기로 진동해 heading 오차와 모양이 다르다. 그래서 전력만으로도 잡힌다.

## 해석

1. **원거리 ceiling에서 신호 상관(S2/S3)은 d0보다 분명히 높은 판별력을 준다.** 같은 오차와 같은 창에서 비교했다.
   - TPR @ FPR 5%: d0 0.12–0.13 → Dperp 0.55 (약 4배).
   - AUC: 0.73–0.76 → 0.93.
2. **전력만 쓰는 통계는 heading 오차를 분리할 수 없다.**
   - 이유: s는 스칼라라서 heading 방향에 직교하는 방향이 없다.
   - 창 단위로 heading 오차를 적합하면 오히려 나빠진다(AUC 0.65–0.67). ceiling이 만드는 s 편차는 천천히 변하는 offset이고, heading bias와 같은 모양이라 적합에 흡수되기 때문이다.
3. **S2/S3를 넣기만 해서는 부족하다.**
   - Dvec(3성분 단순 편차)는 TPR 0.08로 d0와 비슷하다.
   - 이득은 heading 곡선 방향을 빼는 단계(Dperp)에서 나온다.
   - 즉 신호 상관의 가치는 heading 오차와 반사 오염을 기하학적으로 분리한다는 데 있다.
4. **heading prior가 매우 정확하면(rms ≤ 2°, 구간 34%) Dvec이 Dperp만큼 된다(0.98).** 이때도 d0는 0.54다.
5. **floor·wall처럼 빨리 변하는 반사는 전력만으로도 잡힌다.** 신호 상관이 추가로 기여하는 것은 정적인 ceiling 반사다.
6. **mount 45° / yaw 0°는 여전히 약하다**(Dperp TPR 0.35).

## 한계

통제 환경이다.
- 1회 반사, 직선 1개.
- 오차 시계열은 다른 주행에서 가져와 입혔다.
- gating은 참값 rms(oracle)로 했다.
- 장착 오차(roll/pitch)는 넣지 않았다.
- 2포트 위상 coherence가 이상적이라고 가정했다. 실제 하드웨어에서 S2/S3를 쓰려면 패킷 내 두 포트의 위상 안정도를 먼저 확인해야 한다.
