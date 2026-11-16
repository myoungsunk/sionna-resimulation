# Mount +45° 검증 체크리스트 결과

Full RF, seed 10, R2·R4·R5 총 3,136개 패킷. +45° 패킷과 최초 E0 parity는 `5b044c43b0c5a3a201e80ecb957bbee5addc8cdd`에 고정했다. +45° parity는 같은 SourceFFD를 사용하는 별도 재귀 두 개의 일치 검사다. 예전 +45° 기준 trace는 없다.

## 1. RF·패킷·관측식

0° 동결 입력과 패킷 ID·시간·초기값·주행 입력·body 참궤적이 일치했다. Full과 LoS는 각각 인증된 RF 배열과 일치했다. SourceFFD의 `body yaw + 45°`와 `mount 0°에서 body yaw에 45° 추가`는 같은 관측값을 냈다. LoS 첫 경로 tap 불일치는 0건이었고, 편파 절대 오차의 궤적별 p90 최댓값은 `3.89e-7`이었다. 같은 분기 내부의 Jacobian 최대 정규화 차이는 `1.91e-8`이었다. R5 pose 1288의 heading은 검사한 간격에서 분기 경계에 걸려 유한차분 판정에서 제외했다. [관측식 동결 계약](OBSERVER_CONTRACT.json) · [관측식 검사 결과](OBSERVER_RESULTS.json)

평가 RF는 동일한 원래 RT 경로에서 mount를 달리 적용한 이전 BLOCK_C/V01B 자료다. 학습은 유한 반사면 필터를 적용한 G-T1 +45° 생산본을 사용했다. 아래 성적은 이 +45° 실행의 결과이며, 유한 반사면 조건으로 통제한 0°–+45° 효과를 추정하지 않는다.

## 2. TEACH·REPEAT 적합

각 앵커의 TEACH 990개와 REPEAT 1,014개, 합계 6,012개로 R1/R2·S1/S2/S3를 적합했다. E4는 TEACH dense49 회전 54개에서 63,504쌍을 사용했다. 적합한 yaw 길이는 11.43°이고 상관 성분 비율은 100% 상한에 근접했다. 본래 CHAR-001에서 기록한 SHA-256을 기준으로 원본 소스 4개를 바이트 단위로 확인했다. [학습 계약](training/RUN_CONTRACT.json) · [거리·편파](training/FIT.json) · [E4 yaw](training/FIT_S2.json) · [학습 검증](training/FIT_RECEIPT.json)

## 3. 동일 주행 입력의 DR과 E0–E5

모든 EKF arm은 E0의 동결된 수용 마스크를 공유한다. 괄호 안은 R2 / R4 / R5 순서다. NEES3와 최종 위치·heading 오차, 5 s·10 s 짝 블록 구간은 결과 JSON에 있다. [결과 전체](comparison/execution/RESULTS.json) · [비교 계약](comparison/RUN_CONTRACT.json)

| Arm | Pose95 R2 / R4 / R5 | Heading95 R2 / R4 / R5 | XY95 R2 / R4 / R5 | Pooled heading RMSE | Pooled XY RMSE |
|---|---|---|---|---:|---:|
| DR | 100.0 / 100.0 / 100.0% | 100.0 / 100.0 / 100.0% | 100.0 / 100.0 / 100.0% | 2.56° | 46.03 cm |
| E0 | 12.6 / 95.1 / 5.2% | 10.9 / 92.6 / 23.2% | 24.7 / 100.0 / 6.9% | 3.52° | 71.97 cm |
| E1 | 11.6 / 82.1 / 12.9% | 20.4 / 88.7 / 30.0% | 9.8 / 83.0 / 18.9% | 3.27° | 69.16 cm |
| E2 | 12.4 / 51.9 / 54.8% | 30.4 / 55.5 / 84.1% | 9.8 / 61.2 / 48.8% | 3.05° | 51.32 cm |
| E3 | 4.0 / 5.5 / 2.9% | 9.9 / 5.0 / 2.9% | 9.5 / 44.2 / 4.8% | 4.87° | 69.53 cm |
| E4 | 9.5 / 11.7 / 26.4% | 25.3 / 46.4 / 75.4% | 11.0 / 43.5 / 44.1% | 2.44° | 41.58 cm |
| E5 진단 | 8.4 / 7.1 / 5.9% | 25.0 / 5.3 / 8.3% | 7.3 / 41.1 / 12.1% | 3.77° | 74.28 cm |

사전 지정 1차 arm E3는 pooled Pose95 3.86%, pooled heading95 5.58%로 무결성 실패다. E0의 주요 실패 궤적은 R2·R5였다. R4에서 E0는 DR 대비 XY RMSE를 46.97 cm에서 5.37 cm로 줄였다. E4는 pooled 정확도를 DR보다 개선했으나 pooled Pose95가 17.6%이고 mean NEES3가 165.72였다. DR의 mean NEES3는 0.54였다.

0° → +45° E0 Heading95는 R2 94.1% → 10.9%, R4 55.4% → 92.6%, R5 99.0% → 23.2%였다. 같은 궤적의 0°–+45°와 +45° 기준선 대비 차이를 모든 E0–E5 지표에 집계했다. [짝비교 표](MOUNT_0_VS_45_S2.csv)

## 4. D0 → D5 → D1 → D2 → D3·M3

D0에서 3개 궤적의 E0 trace와 마스크를 재현했다. D5에서 pooled Pose95는 28.76% → 23.92%로 하락했다. 차이는 −4.85%p였고 10 s 블록 95% 구간은 [−9.22, −1.40]%p였다. 동결 H4 기준인 10%p 하락에 미달했다. R4 heading95는 92.6% → 70.5%로 하락했다. D1의 3개 동일성 대조가 통과했다. [진단 계약](diagnostics/RUN_CONTRACT.json) · [D0](diagnostics/d0/RESULTS.json) · [D5](diagnostics/d5/RESULTS.json)

D1은 동일성 대조 3회와 4개 조건 × 100회 × 3개 궤적을 완료했다. R4 편파 순열의 heading95 중앙값은 74.7%로 원본 92.6%보다 17.9%p 낮았다. H1의 90% 기준에 미달했다. H6의 R4 거리 순열 XY95 절대 기준은 통과했고, R4 XY95 변화는 100.0% → 100.0%였다. R5의 같은 개입은 6.9% → 10.95%였다. D1의 편파→XY 진단은 동결 H7 문턱에 미달했다. [D1 조건별 결과](diagnostics/RESULTS.json) · [실행 기록](diagnostics/d1/EXECUTION.json)

D2에서 R4의 편파 heading 정보 몫은 79.6%였다. B·B0의 유효 20 s 구간 30개에서 H2의 예측과 실측 z²의 Spearman 상관은 0.037이었다. 동결 H2 예측식은 기각됐다. R4의 편파 잔차를 중심화해 1차 전파한 XY 응답 RMS는 8.43 cm였다. 편파 순열 뒤 R4 XY95 증가가 0%p여서 H7의 공동 판정은 지지를 얻지 못했다. [D2 구간별 결과](diagnostics/d2/RESULTS.json)

M3의 5 cm·10° 재방문 기준을 충족한 쌍은 R5 donor의 10 s 초과 쌍에서만 나타났다. R2 holdout에 대해 23쌍, R4 holdout에 대해 24쌍이었다. 두 fold에서 편파의 표준화 잔차 교차곱 평균은 −0.0004, −0.0026이었고 누적거리 kernel 예측은 거의 0이었다. 위치 kernel 전환 조건에 해당한 fold는 없었다. R2·R4 donor의 해당 근접 쌍 수는 0이다. [M3 위치·yaw 구간표와 상관 적합](diagnostics/d2/M3_FITS_AND_PAIR_TABLES.json)

| 궤적 | E0 heading95 | 느린 편파 제거 | 빠른 편파 제거 | 상수 편파 제거 | E0 XY RMSE → 느린 편파 제거 |
|---|---:|---:|---:|---:|---:|
| R2 | 10.9% | 11.7% | 13.8% | 41.6% | 82.5 → 41.0 cm |
| R4 | 92.6% | 48.8% | 82.5% | 54.2% | 5.37 → 11.99 cm |
| R5 | 23.2% | 49.2% | 29.0% | 27.8% | 82.2 → 10.1 cm |

R4에서 두 편파 제거 결과 모두 90% 회복 기준에 미달해 SC·KI의 진단 우선순위가 미결이었다. R2의 느린 거리·편파 동시 제거는 XY RMSE를 21.5 cm로 줄였다. R5에서는 느린 편파 단독 제거 시 XY95 78.2%, heading95 49.2%였다. 제거는 참값을 쓴 진단이다. [D3 전체 격자·지지집합 결과](diagnostics/d3/RESULTS.json) · [M1 kernel과 D3 분산 비교](diagnostics/d3/M3_SLOW_SCALE_COMPARISON.json)

## 5. SC → KI → D4

| 궤적 | Arm | Pose95 | Heading95 | XY95 | Heading RMSE | XY RMSE | 평균 NEES3 |
|---|---|---:|---:|---:|---:|---:|---:|
| R2 | E0-LORO | 6.7% | 6.1% | 19.2% | 4.69° | 83.2 cm | 475.82 |
| R2 | SC | 11.0% | 14.8% | 27.1% | 4.64° | 80.5 cm | 299.35 |
| R2 | KI | 16.0% | 13.9% | 17.8% | 5.54° | 84.1 cm | 260.34 |
| R4 | E0-LORO | 86.8% | 70.5% | 93.0% | 1.30° | 7.35 cm | 4.48 |
| R4 | SC | 95.1% | 96.1% | 94.6% | 1.49° | 6.81 cm | 2.51 |
| R4 | KI | 96.1% | 100.0% | 95.1% | 0.90° | 5.53 cm | 1.53 |
| R5 | E0-LORO | 2.8% | 20.4% | 6.4% | 3.49° | 80.0 cm | 442.43 |
| R5 | SC | 9.1% | 56.0% | 12.9% | 3.42° | 76.7 cm | 133.54 |
| R5 | KI | 10.2% | 12.6% | 26.6% | 4.70° | 81.8 cm | 181.61 |
| Pooled | E0-LORO | 23.9% | 27.8% | 30.9% | 3.57° | 71.1 cm | 349.23 |
| Pooled | SC | 30.1% | 52.6% | 36.6% | 3.54° | 68.5 cm | 154.30 |
| Pooled | KI | 32.3% | 33.7% | 40.1% | 4.44° | 72.3 cm | 163.58 |

R4 heading95의 기준선 대비 회복폭은 SC +25.6%p, KI +29.5%p였다. SC는 두 RMSE 한도를 충족했다. KI는 heading RMSE가 pooled +24.4%, R5 +34.8%로 각각 +10%, +25% 한도를 초과했다. 두 arm 모두 R2·R5의 75% 포함률 하한과 pooled 무결성 기준을 충족하지 못했다. [SC·KI 결과](structure/execution/RESULTS.json) · [동결 계약](structure/RUN_CONTRACT.json) · [0°·+45° 및 기준선 차이 표](MOUNT_0_VS_45_STRUCTURE.csv)

5% 백색 하한 활성률은 편파에서 SC R2/R4/R5 63.0%/34.9%/40.2%, KI 62.9%/34.8%/40.2%였다. 거리 채널은 양쪽 모두 0%였다. [공분산·하한 검사](structure/execution/IMPLEMENTATION_CHECKS.json)

D4에서 B·B0의 9개 유효 구간 중 거리 0개, 편파 2개가 `|잔차 평균| > 0.5√R`을 충족했다. 편파 2개는 R2·R5의 3–6 m였고 평균은 각각 −0.0974, −0.0905였다. 편파 초과율 22.2%는 H3 문턱 25%에 미달했다. 기존 HGB의 holdout 학습 범위 p05–p95를 가장 자주 벗어난 특징은 세 궤적 모두 `ds_+8`이었다. 이탈률은 R2 25.7%, R4 28.4%, R5 17.8%였다. [D4 잔차·판정](d4/execution/RESULTS.json) · [HGB 특징별 이탈률](d4/execution/HGB_FEATURE_RATES.csv) · [동결 계약](d4/RUN_CONTRACT.json)

## 6. KS 진입 진단

V8 → V1 → V2 → V4 → V3 → V9 → V5·V6 → D4·V7 → D6 순서로 기록했다. 비평탄 +45° σ_b에서 `R_ref`는 동결 계약의 직전 posterior 거리 조회를 유지했다. kernel과 감도 조회는 현재 prior를 썼다.

| V8 예측 / 실측 | 1.5–3 m | 3–6 m | 6–10 m | 판정 |
|---|---:|---:|---:|---|
| R2 | 0.96 | 0.70 | 0.28 | 실패 |
| R4 | 1.91 | 11.31 | 5.09 | 실패 |
| R5 | 0.83 | 0.80 | 1.79 | 통과 |

R4에서 donor 감도 최댓값 초과율은 0%였다. R4의 분산 이전 실패는 이 기준에서 외삽과 일치하지 않았다. V1은 실패했고 V2는 미결이다. V4에서 원본 E0 gain으로 전파한 R4의 원잔차 응답 상관은 0.959, 느린 성분 응답 상관은 0.712로 사전 기준 0.80에 미달했다. [V8 분산 이전](ks/execution/V8.json) · [V1](ks/execution/V1.json) · [V2](ks/execution/V2.json) · [V4](ks/execution/V4.json)

| V3 R4 | Pose95 | Heading95 | XY95 | Heading RMSE | XY RMSE | 평균 NEES3 |
|---|---:|---:|---:|---:|---:|---:|
| E0-LORO | 86.8% | 70.5% | 93.0% | 1.30° | 7.35 cm | 4.48 |
| (a) R4 oracle | 100.0% | 100.0% | 98.9% | 1.18° | 5.88 cm | 2.07 |
| (b) 거리 donor | 99.5% | 100.0% | 98.0% | 0.94° | 5.39 cm | 1.91 |
| (c) 감도 donor | 99.5% | 100.0% | 98.0% | 0.94° | 5.39 cm | 1.91 |

(a)와 (c)의 10 s heading95 95% 구간은 모두 [100%, 100%]였다. (a)의 느린 분산 절단은 지지된 수용 패킷 590개 중 0건이었다. 동결 10% 트리거에 따라 (a′)는 해당 진단에서 생략됐다. R4의 V3 통과에도 V8·V1·V2의 진입 요건이 충족되지 않아 KS 후보 재시험은 `STOP_NOT_ADMITTED`다. [V3](ks/execution/V3.json) · [KS 진입 판정](ks/execution/KS.json)

V5의 R4 0.5 m 공통 지지 heading95는 47.1%였다. V6에서 느린 거리 성분 제거가 R4의 XY95에 준 효과는 5%p 기준 이내였다. V7은 R4·R5 앵커 A의 +45° 동결 보정 부재로 비교가 막혔다. D6에서 R4 원본 E0의 gate를 13.8로 올리면 heading95는 −0.13%p, 유효 패킷을 전부 수용하면 −29.78%p 변했다. 동결 H5 제외 조건은 충족되지 않았다. [V9 SC/GM 대조](ks/execution/V9.json) · [V5](ks/execution/V5.json) · [V6](ks/execution/V6.json) · [V7](ks/execution/V7.json) · [D6](ks/execution/D6.json) · [동결 계약](ks/RUN_CONTRACT.json)

V9의 동일 모수표 GM에서 R2/R5 heading RMSE는 5.42°/3.77°이고 heading95는 1.7%/4.7%였다. 현재 prior 조회를 통제한 SC에서는 4.65°/3.44°와 14.8%/55.6%였다. E0-LORO gain을 강제한 SC는 기준선 상태를 유지했고, 공분산 변화로 heading95가 25.1%/75.5%였다. 이 행은 gain을 고정한 원인 진단이다. [V9 궤적별 지표](ks/execution/V9.json)

## 7. C1–C8 및 R2·R5 원인 대조

- C1에서 R4의 같은 적용 oracle 분산을 쓴 KS·인과적 KI·단순 백색의 heading95는 100.0%, 99.7%, 88.9%였다. `R_ref + V_l`만 적용한 보조 백색 대조는 71.6%였다. [C1](followup/execution/C1.json)
- C2에서 0.25–4배의 7점 모두 동결 heading95 및 RMSE 기준을 충족했다. 상한 적용·해제 조건의 판정이 같았다. [C2](followup/execution/C2.json)
- C3의 모든 길이·크기·배분 교차 대조에서 R4 heading95는 98.7–100.0%였다. [C3](followup/execution/C3.json)
- C6의 자체 gate에서 두 arm의 수용 수는 726 → 741이었다. 새 수용 15건, 새 거절 0건이었다. [C6](followup/execution/C6.json)
- C5의 거리 단독 크기에서 R5 Pose95 89.9%, heading95 99.9%, XY95 86.4%, XY RMSE 8.4 cm를 얻었다. R5의 donor 상한 배수 11.72를 적용하자 각각 10.5%, 35.7%, 9.3%, 95.3 cm로 악화됐다. R2는 거리 단독과 상한 배수 양쪽에서 포함률 하한에 미달했다. C5 판정은 실패다. [C5](followup/execution/C5.json) · [동결 계약](followup/RUN_CONTRACT.json)
- C4의 세 배분 변수 모두 R2의 포함률 하한에 미달했다. C7의 +45° TEACH/REPEAT dense49 5,292개로 감도 지지가 넓어졌다. R4의 모든 구간에서 감도 최댓값 초과율은 0%였으나 TEACH의 예측/실측 느린 분산 비는 11.89–19.88이었다. C7은 같은 복도의 시뮬레이션 yaw sweep 진단이다. [C4](followup/execution/C4.json) · [C7 모형·이전 결과](c7/execution/C7_RESULTS.json) · [C7 입력 행](c7/execution/C7_DONOR_ROWS.csv)
- C8은 격리된 새 Python 프로세스에서 V3 적합과 (a)·(b)·(c)를 재생했다. 모든 arm에서 36개 필드가 정확히 일치했고, 별도 점수 계산과 블록 구간도 일치했다. 같은 호스트의 동결 입력과 SourceFFD를 사용했다. [C8 재현 확인](c8/execution/TRACE_AND_SCORE_CHECKS.json) · [C8 계약](c8/RUN_CONTRACT.json)

R2에서 거리 단독 크기의 heading95는 느린 성분만 26.9%, 빠른 성분만 9.6%, 둘 다 32.2%였다. 배수를 3–6 m에서만 쓰면 38.4%로 가장 높았고 Pose95는 20.7%에 그쳤다. R5는 거리 단독 크기에서 느린 성분만 쓰면 heading95 99.6%, XY RMSE 7.7 cm였고 빠른 성분만 쓰면 25.7%, 79.2 cm였다. 배수를 3–6 m에서만 올리면 XY RMSE가 89.8 cm였고 3–6 m를 제외하고 올리면 9.0 cm였다. 두 궤적의 차이는 배수와 적용 거리 구간에 민감했다. 느린·빠른 성분을 모두 끈 대조는 E0-LORO를 재현했다. [R2/R5 재생·거리별 점수](r2_r5/execution/RESULT.json) · [동결 계약](r2_r5/RUN_CONTRACT.json)

## B·L2 paired controls 민감도

세 궤적에서 기존 0° L2 archive와 +45° 두 재귀 구현의 parity를 확인했다. 이 실행의 L2는 B0와 RF·보정이 동일하다. 고정 gate는 +45° L2에서 E0로 새로 재현했고 모든 L2 arm이 이를 공유했다. SC·KI는 B·B0에서 동결한 모수표를 그대로 적용했다. [패킷·parity](l2/PACKET_PARITY.json) · [동결 계약](l2/RUN_CONTRACT.json)

| B·L2 | E0 Heading95 | E0-LORO Heading95 | SC Heading95 | KI Heading95 | E0 Pose95 |
|---|---:|---:|---:|---:|---:|
| R2 | 14.2% | 13.1% | 22.2% | 17.9% | 13.9% |
| R4 | 90.8% | 67.3% | 86.7% | 100.0% | 98.1% |
| R5 | 28.0% | 23.2% | 57.7% | 25.0% | 6.9% |

L2에서도 R2·R5가 무결성 판정을 제한했다. SC의 R4 heading RMSE는 1.40° → 1.96°로 궤적별 허용 증가율 25%를 넘었고, KI의 pooled heading RMSE는 3.32° → 3.92°로 허용 증가율 10%를 넘었다. [DR·E0–E5 결과](l2/comparison/execution/RESULTS.json) · [SC·KI 결과](l2/structure/RESULTS.json) · [0°·+45° L2 차이 표](MOUNT_0_VS_45_L2.csv)

## 앵커 A·B0 및 A·L2

R2는 앵커 A의 +45° 동결 MB_VAR·주행 입력을 X1에서 확인해 재생했다. B0·L2 모두 979개 중 941개를 수용했다. X1 대비 관측값의 최대 절대 차이는 `5.33e-15`였고, 두 E0 재귀의 prior·posterior·공분산·관측 Jacobian과 gain은 정확히 일치했다. gate 불일치는 0건이었다. SC·KI는 B·B0에서 동결한 R2 holdout 모수를 적용했다. [A 계약](anchor_a_final/RUN_CONTRACT.json) · [실행·점수](anchor_a_final/execution/RESULTS.json) · [실행 기록](anchor_a_final/execution/EXECUTION.json) · [재생 코드](run_a_mount45_final.py)

| A·R2 | Arm | Pose95 | Heading95 | XY95 | Heading RMSE | XY RMSE | 평균 NEES3 |
|---|---|---:|---:|---:|---:|---:|---:|
| B0 | E0 | 27.0% | 30.0% | 44.2% | 2.18° | 19.02 cm | 13.51 |
| B0 | E0-LORO | 25.1% | 40.9% | 52.8% | 1.55° | 12.86 cm | 14.42 |
| B0 | SC | 87.4% | 86.7% | 78.7% | 1.03° | 11.82 cm | 5.13 |
| B0 | KI | 84.0% | 82.1% | 81.6% | 0.91° | 11.21 cm | 5.14 |
| L2 | E0 | 28.7% | 27.7% | 47.7% | 2.12° | 18.15 cm | 13.04 |
| L2 | E0-LORO | 25.9% | 38.4% | 55.6% | 1.52° | 12.34 cm | 14.12 |
| L2 | SC | 76.9% | 85.1% | 72.1% | 1.06° | 11.70 cm | 5.82 |
| L2 | KI | 79.2% | 81.9% | 81.7% | 0.96° | 10.53 cm | 5.44 |

B0에서는 SC·KI 모두 R2의 75% 궤적별 하한을 넘겼다. L2에서는 SC의 XY95가 72.1%였고 KI는 세 하한을 모두 넘겼다. 앵커 A의 EKF 점수는 R2 한 궤적의 이전 진단이다. 앵커 A의 pooled 판정은 산출하지 않았다.

A·R4/R5는 동결 보정이 확인되지 않아 O30 관측 패킷과 evaluator까지 만들었다. R2/R4/R5의 LoS tap 차이는 0건이었고 편파 오차 p90은 각각 `1.41e-6`, `1.91e-7`, `4.20e-7`였다. A·R4/R5의 E0 및 공통 gate를 확정할 수 있어야 V7을 평가할 수 있다. [패킷별 상태와 LoS 검사](anchor_a_final/execution/RESULTS.json)

A의 첫 두 시도는 검사 코드에서 중단됐다. DR에는 RF gate가 없으므로 gate 비교를 RF arm에만 적용했다. E4의 공분산 검사를 기존 S2의 양의 준정부호 허용오차로 맞췄고, 점수 계산에서는 pose 3축의 Cholesky 조건을 확인했다. 같은 동결 입력과 95% 판정 기준으로 재실행해 종료 코드 0을 확인했다. [첫 실행 계약](anchor_a/RUN_CONTRACT.json) · [두 번째 실행 계약](anchor_a_retry/RUN_CONTRACT.json) · [최종 실행 기록](anchor_a_final/execution/EXECUTION.json)

## 검증 기록

실행 기록 16개의 출력 270개에서 SHA-256을 확인했다. 관측식과 학습 확인 자료는 각각 1·2절에 연결했다. C8의 V3 재생은 같은 호스트에서 수행한 구현자 검증이다. 이번 실행 기록과 소스는 이 로컬 폴더에 있다.

