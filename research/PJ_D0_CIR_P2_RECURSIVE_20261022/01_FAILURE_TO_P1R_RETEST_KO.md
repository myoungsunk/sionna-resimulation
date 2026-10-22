# P2 실패 시 P1R 복귀 실험 — 사전 고정된 원인 분석 및 수정 범위

P1R의 원전 run 39752301964, frozen HGB 설정, P2 source ref를 보존한다. P2 결과를 보고 당일 임의로 held route H에 맞춰 hyperparameter를 변경하지 않는다. **먼저 조건을 분리하는 반사실 실험**, 다음 train-only 변경, 마지막 독립 route 확인 순서.

| P2 관측 | 우선 가설 | P1R 수정 실험 (다른 조건 고정) | 다음 단계 진입 기준 |
|---|---|---|---|
| GT-fixed P1R에서는 개선, P2에서는 heading 개선 없음 | GT position을 사용한 P1R prior가 과도하게 유리 | P1R-XY: 동일 실제 full CIR/heading prior에서 x,y prior만 실제 재귀 prediction 값으로 대체; heading prior는 GT+δ 고정, XY prior error bin 측정 | WIDE vs CIR_ONLY heading RMSE 차이 원인으로 XY LUT 왜곡 확인 |
| heading 추정 오차가 크거나 초기 ±20°에서 수렴하지 않음 | offline δ~Uniform(±20°) 와 online heading prior distribution mismatch | P1R-PR: inner replay의 true prior error histogram을 train T에서만 수집해 WIDE prior 증강 분포 설정; δ=±20 경계 초과율 점검; 중간 P 상승 제한. H 평가 route의 δ histogram 사용 금지 | case/route별 OOD bin에서 signed bias 감소, heading correction 유지 |
| LoS 복원 RMSE 감소하면서 누적 heading drift 증가 | residual pseudo-observation이 prior를 따라 움직이며 heading 오차를 bias로 흡수 | P1R-IN: 같은 Full packet에 실제 recursive prior 오차 주입 vs GT center ±δ 대조; ν_clean/ν_oracle signed slope, Kε, residual bias 추적; same-path temporal correlations | prior-error bin 별 ν sign·scale 재현 및 ψ bias 상쇄 관계 파악 |
| heading RMSE 개선, NEES 과신·포함률 악화 | 보정 ehat와 prior 오차의 상관, residual R 과소 추정 | P1R-R: **held route 제외** inner recursions로 residual conditional R_s(q), crosscov(P,e), time-lag whitening vs scalar R 비교; covariance Joseph & correlated nuisance 유지 | 재귀 95% 포함률 개선, RMSE 큰 악화 없음 |
| gate로 큰 오염 재수용, mean 개선 무효 | combined NIS range-pol coupling | P1R-GATE: 같은 prior·같은 range innovations에 gate corrected vs gate raw vs separate χ²_1, same accept-mask counterfactual; q99 over time | 어느 gate가 heading 악화에 기여하는지 분해 |
| CIR_ONLY와 WIDE 차이 없어지거나 부호가 뒤집힘 | d0가 아닌 augmentation/learners 효과 또는 R 차이 | P1R-AUG: CIR_ONLY×3 반복 학습 / WIDE에서 d0 셔플 / 데이터 복제 대조; 모든 arm에 identical R/gate 고정 | held-route WIDE 이득 유지 여부; 아닌 경우 d0 독립 기여 주장을 철회 |
| ±20°에서 WIDE 오차 증가, FP shift·다중해 집중 | LUT 비단조, gradient sign flip, multiple roots | P1R-ROOT: training route 기준 각도별 h_s(ψ) 다중근 수, g sign, FP tap 전환, IEKF 초기점·line search 비용 분해; prior orientation 대칭 | failure mode 라벨링 및 안전한 gating/active scan 후보 |
| LoS/B0 negative control에서도 오류 | 구현 또는 보정값 중복 사용 | P1R-CORE: ehat target의 μ_s 중복, units(rad/deg), R² sign, D0_DIRECT ν=0, GT injection, SHA, manifest, interpolation 확인 후 재실행 | 원본 P1R QA parity 및 reference BASE parity 통과 |

## 단일 입력 비교로 구분할 것
1. 같은 Full RF 샘플을 사용하고 평가용 x,y 좌표만 변경(Δx,Δy one-factor).
2. 같은 Full RF 샘플을 사용하고 heading prior만 변경(Δψ one-factor).
3. Δx,Δy,Δψ 동시변경(원래 P2).
4. 위의 각 조건에서 R과 H와 gate를 각각 고정/변경. 동일 RF의 rank/LoS/Δs 라벨은 평가 전용.

## 교육받은 prior와 online prior의 차이
P1R에서는 3회 uniform ±20° 증강이 학습 route GT 위치·heading 중심이었음. P2에서는 자이로·바퀴 입력의 누적오차, anchor range state coupling, x-y-ψ의 비독립 오차가 모두 present. 따라서 분포 변화의 분해가 실패 원인을 구별한다. 새로운 train 분포는 outer held H의 결과를 보고 맞추지 않는다.

## 결과 보고
각 수정안의 효과를 다른 수정안과 동시에 적용하지 않고, frozen BASE/CIR_ONLY/WIDE/ORACLE 비교 및 failure case별 delta RMSE, NEES·95%·q99·XY, route-level paired bootstrap CI를 함께 보고한다. 실행 이전 명시하지 않은 모델 수정이 발생하면 separate experiment ID를 부여하여 exploratory임을 선언한다.
