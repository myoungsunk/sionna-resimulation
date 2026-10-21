# 부호 있는 Δs의 사용 지도 확장 — 탐색 계획 (실행 전 고정, 2026-10-21)

Step 1에서 부호 있는 \(\Delta s_o=s(fp+o)-s(fp)\)가 편파 편향을 route-heldout으로 27–46% 설명함을 확인했다. 이번에는 Δs가 **무엇과 관련되어 필터의 어느 부분에 쓸 수 있는지**를 넓게 조사한다. 탐색 분석이므로 판정 기준은 두지 않고, 목표·지표·모델을 미리 고정해 결과를 크기로 보고한다. 필터 replay 없음.

## 물리적 출발점
단일 경로면 두 포트가 같은 pulse를 공유해 s가 tap에 무관(합성 검증 4e-15). 따라서 Δs≠0은 해상도 안에 겹친 경로의 증거이고, 겹친 경로는 (i) 편파 편향, (ii) first-path 검출 시점(range 편향), (iii) 두 오차의 공동 부호에 동시에 영향을 줄 수 있다.

## 입력 (pose 단위, 7 case)
- 부호 Δs: o∈{−8,−4,−2,−1,+1,+2,+4,+8}, 각 tap 진폭/peak 비.
- 기존 특징(EXIST): features.py의 G0–G4 중 range_m 제외 16개(log_fp_power, abs_s_fp, early4/8/16, delay_rms_ns, peak_diff_ns, eta_fp_win80, s_diff4/8/16, tap_pol_var80, jones_diversity, freq_s_var, detector_s_span, detector_delay_span_ns).
- 라벨: \(e_s, e_r\) (필터가 보는 오차), \(d^{mp}_s=s^{Full}-s^{LoS}\), \(d^{mp}_r=r^{Full}-r^{LoS}\), POWER1 \(\mu_r,\mu_s,V_r,V_s\) (OOF), \(g=\partial h_s/\partial\psi\) (SourceFFD, GT pose).

## 목표와 필터 슬롯
| ID | 목표 | 필터 슬롯 | 지표 (held route) |
|--|--|--|--|
| A1 | \(e_s\), \(e_s^{LF}\) | 편파 평균 μ_s / 편향 상태 관측 | R²_nc |
| A2 | \(e_r\), \(d^{mp}_r\), \(e_r^{LF}\) | range 평균 μ_r / range 편향 | R²_nc |
| B1 | \(|e_s|\) | 편파 분산 V_s | Spearman(예측, |e_s|), POWER V_s와 비교 |
| B2 | \(|e_r|\) | range 분산 V_r | 동일 |
| C1 | \(|d^{mp}_s|>0.05\) (다중경로 오염 패킷) | 품질 플래그 / LoS·NLoS | AUC: 학습 없는 \(|\Delta s_{+1}|\), held-out logistic |
| C2 | \(|e_s|>2\sqrt{V_s}\) (분산모델 밖 이상치) | gate 보조 | AUC (동일) |
| C3 | \(\mathrm{sign}(e_re_s)\) | 교차공분산 \(C_{rs}\)의 국소 부호 | held-out logistic AUC |
| D | \(\Delta s_{+1}\) ~ [\(h_s\), g, g²] | ψ 독립성(상태 관측으로서의 분리성) | case별 R² (낮을수록 ψ와 독립) |
| E | Δs와 \(e_s\)의 시간 상관시간 | GM 상태 구동/시간모델 | τ_int (D1 정의) |
| F | LoS에서 Δs 크기 | 물리 전제 확인 | median \(|\Delta s_{+1}|\) LoS vs Full |

## 모델 (고정)
- EXIST, DS(부호 Δs 8개), EXIST+DS 세 집합 × 표준화 Ridge(α=1). 절댓값 목표(B)는 log|target|에 적합.
- 비선형 상한 탐색: EXIST+DS에 HistGradientBoosting(max_iter=200, lr=0.05, max_leaf_nodes=15, l2=1.0) — 탐색용으로만 표기.
- 분류: logistic(C=1, 표준화). train = 다른 두 route의 Full, test = held route.
- 저주파: timeline 순서 2 s 이동평균(예측도 동일 처리).

## 해석 규칙
EXIST 대비 EXIST+DS의 증분으로 Δs의 고유 가치를 판단한다. DS 단독이 높아도 EXIST로 이미 설명되면 고유 가치는 낮다. 결과는 표로 모두 남긴다.
