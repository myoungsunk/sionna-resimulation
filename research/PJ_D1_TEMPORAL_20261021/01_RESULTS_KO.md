# D1 결과 — 잔차 시간구조와 재귀 Heading 과잉확신 (2026-10-21)

실행: [run 39534654820](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39534654820), 7 case × {Full B0, Full L2, LoS B0} = 21조건 × 9 arms. 기계 판정은 `results/D1_JUDGEMENT.json`, 표는 `results/D1_*.csv`. 새 학습/튜닝 없음. 하나의 복도, 63 arm-case는 독립 표본 아님.

## QA
- QA0: 21/21 조건에서 trace prior로 재계산한 K,H가 posterior를 재현(max|Δx| ≤1.8e-15, max|ΔP| ≤2.8e-17). 분해 closure ≤1.4e-14 rad.
- trace heading95 재계산 차이 ≤1.1e-16.
- QA1: LIN 성분 >30%인 행 65개(Full B0 13, Full L2 18, LoS B0 34). Full에서는 R2 A M0(JOINT4/POWER1/POWER_DIAG/PWR_MU_SEP_COV), R2 A M45 대부분 arm, R5 B L2 다수. 이 행들은 선형 귀속을 부분적으로만 주장한다. LoS는 절반 이상이 비선형 지배라 LoS 해석은 보류.

## 사전등록 판정
| 항목 | 결과 | 판정 |
|--|--|--|
| H1 whitened u_s lag-1 >0.5 | POWER1 7/7, SEP_BIN 7/7. lag-1 0.63–0.92, τ_int(s) 1.5–11.6 s (Δ=0.2 s) | **PASS** |
| H2 SHUF∈[0.5,2] & ACT>3 과반 | 25/63 | **FAIL** |
| H2b PHASE/ACT | 위 25행 중 PHASE<0.5·ACT 16행 | "위치 정렬된 결정적 성분 필요" |
| H3 R5 A coverage 변화 중 σ효과 ≥70% | σ효과 +0.062, δ효과 −0.326 (σ 비중 −23%) | **FAIL** |
| H4 R2 B MSE 증가 중 U_S ≥50% | 61% | **PASS** |
| 보조: 스칼라 γ vs 경험 ACT/SHUF | Spearman −0.30 | 스칼라 AR(1) 식은 예측력 없음 |

## 해석 (수치 근거 → 추론 구분)
1. **Heading 오차는 저주파 편파 잔차의 선형 응답이다.** Full에서 U_S_LF/U_ALL heading RMS 비 중앙값 B0 0.99, L2 1.02. 예: R5 A POWER1 전체 4.56° 중 U_S_LF 3.64°; R2 B SEP_BIN 3.47° 중 2.65°. L2 gyro-bias 오차에서도 U_S_LF가 63/63 arm-case에서 최대 성분.
2. **시간상관은 측정기인 NEES를 키운다.** Full B0 ACT/SHUF 중앙값 4.6, 63행 중 65%가 >3. SHUFFLE(동일 marginal, 시간상관 제거) NEES^u 중앙값은 POWER1 1.34, SEP_BIN 1.73 — 패킷 수준에서는 대체로 calibrated. 그러나 H2는 FAIL: 30/63 행에서 SHUFFLE 자체가 >2(JOINT4 전부, R4 A·R5 A 다수)라 marginal/전역 평균 오지정도 동시에 존재한다. 시간상관 단독 설명은 기각.
3. **공분산 모델이 이득과 잔차의 위치 정렬을 바꾼다 (새 발견).** ACT/PHASE 중앙값: POWER 공분산 계열 0.61–0.81(실제 정렬이 같은 spectrum의 무작위 정렬보다 유리), SEP 공분산 계열 1.54–1.68(불리). 평균이 동일한 POWER1 대 PWR_MU_SEP_COV에서도 같은 차이 → 원인은 R(q). 추론: SEP V(q)가 저주파 s 잔차가 큰 구간에서 V_s를 작게(이득 크게) 준다. 식으로는 \(m=\sum\Phi K_k d_k\)의 \(\mathrm{Cov}(K,d)\) 항. 직접 측정(D1b)은 아직 안 함.
4. **이전 예측 ③ 기각.** R5 A에서 RMSE는 같지만(4.556/4.554) 시점별 heading 오차는 1.22° RMS 다르고, coverage 하락은 δ효과(−0.33)가 지배한다. Full 전 arm에서 σ효과는 |0.17| 이하(JOINT4 제외 시 |0.10| 이하); coverage 변화는 σ 축소가 아니라 오차가 어디서 생기는가로 결정된다. σ 평균 0.942→0.749는 평균 σ의 비교이며 시점별 비 평균은 0.96이다.
5. LoS: ACT ≈ SHUF(POWER1 2.94/2.35)로 시간구조 효과는 작지만 LIN 비중이 커 해석 보류.

## 다음 단계 함의
- 분산 inflation(N_eff)은 coverage를 개선할 수 있으나, DC gain이 1이므로 저주파 편향에 의한 RMSE는 줄이지 못한다.
- s 편향 상태(Gauss-Markov, τ≈1.5–12 s) 추가는 저주파 잔차를 직접 겨냥하지만, s 단독으로는 s 편향과 ψ가 구별되지 않는다. 구별은 range+운동 기하 또는 시간척도 분리로만 가능하므로 observability 분석이 먼저다.
- D1b: 이득과 잔차의 공분산 \(\mathrm{Cov}(K_{\psi s}g, d_s)\)를 구간별로 직접 측정(trace 재실행 시 K, u 저장).
