# M1 후속 원인 분리 실험 결과


기준 commit `7d65f387a2e4c461cbca65014f3975d452e00f93`. 기존 코드·데이터·결과를 변경하지 않고 별도 runner와 결과를 추가했다. 임계값·학습 모델·초기조건은 사후 조정하지 않았다. `scientific_PASS=false`.


## 실행·재현성


- 단위·회귀 테스트: **83 PASS**. 합성 smoke 144셀, RF smoke 72셀 성공 후 full 실행.

- 합성 full: **4,848셀**, 정확한 SE(2)와 합성 `s=0.8 sin(ψ)` 관측. 각 경로/Bias별 noisy 100개 독립 trial, 별도 noiseless 1개. 실제 FFD/RF 검증과 구별한다.

- 동결 RF full: **6모델 × 252셀 = 1,512셀**. `noise_pair`, level1, 기존7조건 × seed0/1/2, LoS B_OLD 및 Full B_OLD/E1, D0/A/B/C. 기존 FP와 Range 유지. 평가 시작은 기존대로 30초.

- M0 및 M1B_REPRO: 각각 252/252셀 parity PASS, 최대 차이 0.0, 허용치 `1e-8`.

- RF trace 1,339,416행 전부 재계산. 1,512셀 지표 최대 차이 3.64e-12, 저장 공분산으로 NEES 재계산 최대 차이 4.66e-10.

- 합성 대표 trace 96셀 재계산, 지표 최대 차이 3.55e-15. 전체 noisy trial의 원시 trace를 저장했다고 주장하지 않는다. Bias gain×innovation과 실제 보정 차이 최대 1.82e-17deg/s.


## 1. M1-A 합성 대조


무잡음·실제 Bias0에서는 pose 및 Bias 불변성 PASS(허용치 `1e-10`). 불필요한 Bias가 생기지 않았다. 아래는 **잡음이 있는 100 trial**, 60초 전체 구간의 Joint C 결과다. RMSE는 제곱오차를 모아서 계산하며, 포함률은 고정 실제 Bias에 조건부인 반복 평가다.

| 경로 | 실제 Bias °/s | 모델 | Heading RMSE ° | 위치 RMSE m | Pose NEES | Pose95 % | 최종 Bias 오차 평균 °/s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| return | 0.00 | M0 | 0.8319 | 0.0572 | 2.99 | 95.04 | — |
| return | 0.00 | M1-A | 1.0013 | 0.0590 | 2.76 | 96.88 | -0.00090 |
| return | 0.05 | M0 | 1.2781 | 0.0654 | 23.98 | 40.18 | — |
| return | 0.05 | M1-A | 1.0353 | 0.0595 | 2.82 | 96.57 | -0.00135 |
| straight | 0.00 | M0 | 0.9143 | 0.0635 | 3.20 | 92.88 | — |
| straight | 0.00 | M1-A | 1.0411 | 0.0646 | 3.04 | 95.25 | -0.00031 |
| straight | 0.05 | M0 | 1.3161 | 0.0722 | 51.38 | 38.57 | — |
| straight | 0.05 | M1-A | 1.0572 | 0.0648 | 3.08 | 95.13 | -0.00148 |
| turn | 0.00 | M0 | 0.8671 | 0.0830 | 2.76 | 95.92 | — |
| turn | 0.00 | M1-A | 1.0866 | 0.0852 | 2.64 | 95.67 | -0.00103 |
| turn | 0.05 | M0 | 1.3245 | 0.0914 | 29.29 | 38.63 | — |
| turn | 0.05 | M1-A | 1.1471 | 0.0863 | 2.70 | 95.47 | -0.00163 |


Bias0에서는 추가 상태를 허용한 M1-A의 Heading RMSE가 증가하지만, 실제 Bias +0.05deg/s에서는 세 경로 모두 M0 대비 Heading·위치 RMSE와 포함률이 개선된다. 이 결과는 Bias 추정이 정합한 모델에서도 항상 실패한다는 설명을 지지하지 않는다. 반대로 실제 FFD의 식별성·RF 잔차 흡수·운동모델 불일치 중 어느 것이 주원인인지는 이 합성 실험만으로 결정하지 못한다.


D0는 Bias를 관측할 수 없으므로 수렴을 요구하지 않는다. 다른 A/B 및 trial별 결과, paired 차이와 표준오차는 `BIAS_SUMMARY.csv`, `BIAS_PAIRED_CONTRASTS.csv`, `BIAS_FULL_CASE_METRICS.csv`에 있다. 각 시점은 독립 반복이 아니다.


## 2. RF 요소를 하나씩 변경한 결과


모든 모델은 true3-state다. MEAN_ONLY, VAR_ONLY, HUBER_ONLY, GATE_OFF는 각각 M0의 평균, 분산, 손실, gate 정책 하나만 변경한다. HUBER_ONLY의 gate는 보정 전 R0의 NIS로 검사한다. M1B_REPRO는 기존 평균+분산+Huber+gateOFF 조합이다. 각 요소 효과를 단순 합으로 해석하지 않는다.


### los / B_OLD / Joint C

| 모델 | Heading RMSE ° | 위치 RMSE m | Pose NEES | Pose95 % |
| --- | --- | --- | --- | --- |
| M0 | 0.2586 | 0.0538 | 16.06 | 74.68 |
| RF_MEAN_ONLY | 0.2677 | 0.0671 | 8.97 | 72.16 |
| RF_VAR_ONLY | 0.2523 | 0.0568 | 976.46 | 25.64 |
| RF_HUBER_ONLY | 0.2588 | 0.0538 | 17.22 | 74.86 |
| RF_GATE_OFF | 0.2585 | 0.0538 | 17.06 | 73.65 |
| M1B_REPRO | 0.2868 | 0.0605 | 1195.73 | 20.70 |


### full / B_OLD / Joint C

| 모델 | Heading RMSE ° | 위치 RMSE m | Pose NEES | Pose95 % |
| --- | --- | --- | --- | --- |
| M0 | 1.2744 | 0.2302 | 49.75 | 18.06 |
| RF_MEAN_ONLY | 0.9780 | 0.1602 | 43.21 | 16.18 |
| RF_VAR_ONLY | 0.8871 | 0.1840 | 38.06 | 22.30 |
| RF_HUBER_ONLY | 0.9755 | 0.1799 | 34.81 | 23.06 |
| RF_GATE_OFF | 4.6412 | 0.8531 | 914.29 | 12.26 |
| M1B_REPRO | 0.9628 | 0.1603 | 64.43 | 31.50 |


### full / E1_FULL_LORO / Joint C

| 모델 | Heading RMSE ° | 위치 RMSE m | Pose NEES | Pose95 % |
| --- | --- | --- | --- | --- |
| M0 | 0.9414 | 0.1531 | 24.24 | 33.14 |
| RF_MEAN_ONLY | 0.7442 | 0.1105 | 46.07 | 32.62 |
| RF_VAR_ONLY | 0.8400 | 0.1412 | 28.78 | 32.33 |
| RF_HUBER_ONLY | 0.8114 | 0.1313 | 21.55 | 38.85 |
| RF_GATE_OFF | 4.2159 | 0.7641 | 594.53 | 18.34 |
| M1B_REPRO | 0.8179 | 0.1388 | 23.70 | 37.70 |


### 경로 조건별 변화

| 채널 | Range | 모델 | Heading 악화 /7 | 위치 악화 /7 |
| --- | --- | --- | --- | --- |
| full | B_OLD | M1B_REPRO | 4 | 3 |
| full | B_OLD | RF_GATE_OFF | 6 | 6 |
| full | B_OLD | RF_HUBER_ONLY | 0 | 0 |
| full | B_OLD | RF_MEAN_ONLY | 5 | 2 |
| full | B_OLD | RF_VAR_ONLY | 5 | 5 |
| full | E1_FULL_LORO | M1B_REPRO | 4 | 4 |
| full | E1_FULL_LORO | RF_GATE_OFF | 6 | 7 |
| full | E1_FULL_LORO | RF_HUBER_ONLY | 0 | 0 |
| full | E1_FULL_LORO | RF_MEAN_ONLY | 2 | 3 |
| full | E1_FULL_LORO | RF_VAR_ONLY | 3 | 3 |
| los | B_OLD | M1B_REPRO | 4 | 4 |
| los | B_OLD | RF_GATE_OFF | 수치동등6·개선1 | 수치동등6·악화1 |
| los | B_OLD | RF_HUBER_ONLY | 4 | 4 |
| los | B_OLD | RF_MEAN_ONLY | 4 | 4 |
| los | B_OLD | RF_VAR_ONLY | 2 | 2 |


7개 RF 조건은 독립 scene 7개가 아니다. 일부는 같은 기본 경로·장면을 공유한다. 위 악화 횟수는 seed3개를 합친 조건별 기술 통계다. LoS gate-off의 6개 조건 차이는 약1e-15 수준의 수치오차이고, R5_aB_m0만 Heading -0.00027735°, 위치 +0.00033153m 변화가 있다. 이 행은 기계 정밀도 차이를 악화로 세지 않고 명시적으로 표시했다. RF_WORSE_CASE_COUNTS.csv의 strict 부호 횟수는 이 수치오차도 포함하며 통계적 유의성이나 실질적 악화를 뜻하지 않는다. 실험 gate와 parity 허용치는 변경하지 않았다.


## 해석

1. **LoS 과신은 학습 분산 교체만으로도 재현됐다.** M0 대비 VAR_ONLY의 Pose NEES는 16.06→976.46, Pose95는 74.68%→25.64%다. 평균 보정·Huber·gate 제거 없이 발생했다. 이 대조는 s와 Range의 두 분산을 함께 바꾸므로 s 분산만의 기여와 Range 분산만의 기여까지 분리한 결과는 아니다. 학습 LoS R_s/R0_s는 0.001409–0.108687이며, 지나치게 작은 측정 오차 척도가 과신에 기여한다는 해석을 지지한다. 단일 요소 교체에 따른 재귀 궤적·실제 gate 판정 변화도 이 효과에 포함된다.

2. **기존 RF 모델에서 gate 제거는 큰 악화를 만든다.** Full B_OLD Joint의 Heading RMSE는 1.2744→4.6412°, 위치 RMSE는 0.2302→0.8531m, Pose NEES는 49.75→914.29다. E1에서도 Heading 0.9414→4.2159°, 위치 0.1531→0.7641m로 악화됐다. 이것은 M0의 평균·분산·Gaussian 손실에 조건부인 gate 제거 효과이며, 다른 요소와 결합한 M1-B 실패 전체를 gate 하나로 설명한다는 뜻은 아니다.

3. **원본 R0와 gate를 유지한 Huber-only가 가장 일관된 조건별 정확도 개선을 보였다.** Full B_OLD에서 Heading 1.2744→0.9755°, 위치 0.2302→0.1799m, NEES 49.75→34.81, Pose95 18.06%→23.06%다. E1도 Heading 0.9414→0.8114°, 위치 0.1531→0.1313m로 개선됐다. 두 Range 방식 모두 seed3개를 합친 7/7 RF 조건에서 Heading·위치 RMSE가 감소했다. 그러나 95% 포함률은 여전히 매우 낮고 LoS의 NEES도 16.06→17.22이므로 채택 또는 통계적 일관성 PASS로 승격하지 않는다.

4. **집계 평균 개선과 모든 조건 개선은 다르다.** Full B_OLD의 MEAN_ONLY와 VAR_ONLY는 pooled Heading RMSE가 개선되지만 각각 5/7 조건에서 악화했다. 기존 M1-B 조합은 4/7 조건에서 악화하는 결과를 그대로 재현했다. 단일 RF 장면에서 가장 잘 나온 대조군을 고른 결과를 독립 확증으로 해석하지 않는다.

5. **M1-A의 실제 RF 악화 원인은 아직 일부만 분리됐다.** 정합한 무잡음 조건에서 가짜 Bias가 없고 알려진 비영 Bias에서 추정이 개선되는 점은 보편적인 구현 실패 설명을 약화한다. 실제 RF의 편향 흡수, FFD 관측 민감도/식별성, 운동모델 불일치, 재귀 gate 변화의 상대 기여는 이번 합성 대조만으로 확정하지 않는다.



## 한계와 상태


원본 FP/Range/학습 모델을 유지한 단일 요소 개입이다. 여기서는 경로 홀드아웃 모델을 재학습하거나 variance floor·gate·Huber·Bias prior를 조정하지 않았다. E1은 기존 전체경로 평가의 공간 중복 및 모델 선택 이력이 남아 있으며 독립 확증이 아니다. 강건 필터의 NEES는 근사 공분산에 대한 진단이며 Gaussian 확률 보장을 자동으로 뜻하지 않는다.


이번 결과만으로 M1-A/B/C를 채택하지 않는다. M1-A는 정합한 합성 환경에서 작동 가능함을 확인했고, 실제 RF 악화의 전체 원인은 미확정이다. M1-B는 요소별 실패를 더 좁혔으나 독립 환경 검증이 남는다. M2-T0 주변화 수정 및 M2-T1은 **이번 범위에서 실행하지 않았다**. `scientific_PASS=false`.


실행 명령·시간·종료코드·소스/입출력 SHA는 각 receipt와 manifest에 있다. 원시 RF trace·합성 대표 trace·실행 로그·정확한 소스·캐시 및 기존 학습 모델은 분할 `EVIDENCE.zip.part*`에 포함한다. `RESTORE_EVIDENCE.py`로 무결성 검증 후 복원한다.
