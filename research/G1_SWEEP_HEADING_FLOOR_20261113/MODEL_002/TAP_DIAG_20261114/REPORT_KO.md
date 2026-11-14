# Goal 1 · G1-MODEL-002 tap 추출 진단 결과

**DIAGNOSTIC_ONLY · S2′ STOP (FULL_6) · Step 3 HELD**

세 추출법을 BLOCK_C 6개 mount-0 case, 물리 station 122개, N30 sweep 2,440개에 적용했다. 각 (case, seed)에서 기존 검출 tap, LoS 기준 oracle tap, PRIOR_FRAC를 **같은 full H와 같은 복소 잡음**으로 계산했다. PRIOR_FRAC는 위치 prior로 정한 거리 창에서 에너지 점수를 최대화하는 분수 지연 구현이다. oracle이 읽은 값도 잡음이 있는 full H에서 나왔다. LoS H는 oracle 인덱스를 정하는 데 사용했다. [사양](SPEC_KO.md) · [실행 요약·입력 해시](out/SUMMARY.json) · [sweep 원시 결과](out/SWEEP_ROWS.csv) · [station별 결과](out/STATION_ROWS.csv)

## 전체 case

모든 2,440개 sweep에 세 추출법의 heading이 있다. RMSE 단위는 °다. Δ는 같은 sweep의 RMSE 차이이며, 구간은 물리 station 단위 짝 bootstrap 95% 구간이다.

| case | station / sweep | 기존 검출 | LoS 기준 oracle | PRIOR_FRAC | oracle−기존 [95% CI] | PRIOR_FRAC−기존 [95% CI] |
|---|---:|---:|---:|---:|---:|---:|
| R2_aA_m0 | 21 / 420 | 4.96 | 3.61 | 7.49 | −1.34 [−2.39, −0.37] | +2.53 [+1.56, +3.63] |
| R2_aB_m0 | 21 / 420 | 3.86 | 3.33 | 7.23 | −0.53 [−1.41, +0.18] | +3.37 [+2.21, +4.71] |
| R4_aA_m0 | 10 / 200 | 5.21 | 4.13 | 6.71 | −1.08 [−2.65, +0.39] | +1.51 [+0.31, +3.49] |
| R4_aB_m0 | 10 / 200 | 3.24 | 2.65 | 6.01 | −0.60 [−1.97, +0.58] | +2.77 [+0.80, +4.21] |
| R5_aA_m0 | 30 / 600 | 4.42 | 3.85 | 6.76 | −0.57 [−1.00, −0.22] | +2.34 [+1.10, +3.65] |
| R5_aB_m0 | 30 / 600 | 3.59 | 3.09 | 6.65 | −0.50 [−1.25, +0.19] | +3.05 [+2.12, +4.08] |

oracle tap을 쓰면 6개 case 모두 RMSE 점추정치가 낮아졌다. 개선 구간이 0을 제외한 case는 R2_aA와 R5_aA다. 이번 PRIOR_FRAC 구현의 RMSE는 6개 case 모두 기존 검출보다 높았고 각 차이 구간도 0보다 높았다. **위치 prior가 예측한 tap에서 직접 읽는 가설은 이 실행에서 검정하지 않았다.** case별 구간에는 다중비교 보정을 적용하지 않았다.

## R4_aB

- station 평균 오차 RMS는 기존 **3.21°**, oracle **2.60°**, PRIOR_FRAC **5.99°**였다. sweep의 |e|>5°는 **10.5% / 9.5% / 38.0%**였다. oracle 대조는 개선 방향이지만 10개 station의 차이 구간은 0을 포함한다.
- PRIOR_FRAC는 200 sweep 중 68개에서 거리 창의 늦은 쪽 끝을 택했다. 선택한 경로 길이의 참 기하 거리 대비 차이 중앙값은 +0.199 m였다. heading 창 경계 후보는 기존·oracle 각 0개, PRIOR_FRAC 60개였다.
- 재방문 공분산과 첫 방문 분산 스케일의 효과는 별도 가설로 남는다.

## R2_aA

| 복도 x 층 | station / sweep | 기존 bias / RMSE | oracle bias / RMSE | PRIOR_FRAC bias / RMSE |
|---|---:|---:|---:|---:|
| 전체 | 21 / 420 | −2.44° / 4.96° | −1.31° / 3.61° | −4.84° / 7.49° |
| x ≤ 6 m | 5 / 100 | −0.53° / 1.82° | −0.50° / 1.57° | −0.50° / 4.90° |
| x ≥ 8 m | 14 / 280 | −3.55° / 5.96° | −1.90° / 4.30° | −7.00° / 8.52° |

x는 복도 좌표다. 두 층 사이의 2개 station은 전체 행에 포함된다. x ≥ 8 m에서 oracle−기존 RMSE 차이는 **−1.66° [−2.89, −0.57]**였고, oracle에서도 |e|>5°가 **23.6%**였다. 복도 위치에 따라 남은 방향성 오차는 거리·고각을 포함한 조건부 검증 대상으로 남는다. PRIOR_FRAC는 420 sweep 중 174개에서 늦은 쪽 창 경계에 닿았다.

## 지연 선택과 주장 범위

PRIOR_FRAC는 모의 사전 위치로 계산한 거리 d_geo를 중심으로 ±3σ_d 창을 잡는다. 같은 sweep에서 공통 지연 하나를 고를 때 잡음 분산으로 정규화한 에너지 합에서 prior 벌점 (d−d_geo)²/(2σ_d²)를 뺀 점수를 최대화한다. 2,440개 sweep에서 **선택된 지연**의 에너지 항은 **4.18×10⁵–1.91×10⁹**였고 창 안의 벌점은 최대 **4.5**였다. **961개(39.4%)**가 지연 창 끝을 골랐고, 그중 **960개**가 늦은 쪽이었다. 선택 지연의 참 기하 거리 대비 차이 중앙값은 **+0.213 m**였다. 이 분포는 창 안의 강한 후행 성분을 고르는 동작에 부합한다. 후보 간 순위에 대한 벌점의 효과나 어떤 반사가 영향을 줬는지는 별도로 측정하지 않았다. [점수식](tap_diagnostic.py#L29-L48) · [sweep 원시 결과](out/SWEEP_ROWS.csv)

oracle은 LoS 기준의 정수 tap leading edge에서 읽고 PRIOR_FRAC는 선택된 분수 지연의 템플릿 중심에서 읽는다. 두 arm의 차이에는 지연 선택과 읽기 위치 정의가 함께 들어간다.

heading은 세 arm 모두 동일한 **참 heading ±10° 오프라인 창**에서 평가했다. 선택 후보가 heading 창 경계로 표시된 sweep은 기존 검출 **160개**, oracle **112개**, PRIOR_FRAC **850개**였다. 창 밖 최소의 오차가 집계에 들어오지 않으므로 기존 검출과 oracle의 RMSE 차이는 이 창에 한정된다. 기존 검출이 창에 더 자주 제한되어 관측된 개선 폭이 작아졌을 가능성은 있으나, 경계 횟수만으로 잘림이 RMSE 차이에 미친 영향의 방향과 크기를 확정할 수 없다.

이 결과로 운용 heading, DR 대비 성능, integrity 또는 새 형상의 일반화를 판정할 수 없다. R2_aA의 조건부 편향, R4_aB의 초기 분산·재방문 공분산 가설에 이 진단의 수치를 모수로 옮기지 않는다.

## 실행 및 검증 기록

- Snowball KMS 실행 G1_MODEL_002_TAP_20261114T091605Z_qXXTzb. 2026-11-14 09:16:06–09:18:57 UTC, 종료 0. [실행 명령](COMMAND.txt) · [로그](run.log) · [SHA-256 목록](SHA256SUMS.txt)
- 동결 Q1 기준선 2,440행의 오차·분산·XY·flat을 검사했다. 수치 필드 최대 절대차는 5.69e−14였다. Fourier 정수 표본 대 IFFT 최대 절대차는 5.01e−13이었다. 단일 경로 검사에서 지연 차이는 2.32 mm, 편파비 차이는 3.34e−16 이하였다. case별 LoS 예측의 선형 연산 대조는 모두 2.00e−15 이하였다.
- 첫 실행은 동결 기준선을 통과한 뒤 공통 분수 지연을 yaw에 배정하는 검사에서 인덱싱 오류로 종료했다. 수정 후 사양 SHA와 입력을 그대로 사용해 새 실행 ID에서 재실행했다. [첫 실행 로그](FIRST_ATTEMPT.log)
- 내려받은 파일의 해시, 122개 station과 2,440개 고유 sweep 키, 각 case 및 R2_aA 층의 RMSE·bias·절대오차·station 평균을 sweep CSV로 재계산해 대조했다. [재집계 스크립트](verify_outputs.py) · [재집계 결과](VERIFIED.json)

## 실행 후 해석 정정

이 개정은 저장된 sweep과 점수식을 대조해 주장 범위를 바로잡았다. 실행 당시 매니페스트의 보고서 해시는 최초 게시본에 대응한다. [최초 게시 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/2449d55d8b7358ae9a95b369a82cfc3094c032d0/research/G1_SWEEP_HEADING_FLOOR_20261113/MODEL_002/TAP_DIAG_20261114/REPORT_KO.md) · [실행 매니페스트](https://github.com/myoungsunk/sionna-resimulation/blob/2449d55d8b7358ae9a95b369a82cfc3094c032d0/research/G1_SWEEP_HEADING_FLOOR_20261113/MODEL_002/TAP_DIAG_20261114/RUN_MANIFEST.json)
