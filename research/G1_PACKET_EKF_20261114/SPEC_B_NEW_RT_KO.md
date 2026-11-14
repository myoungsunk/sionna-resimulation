# G1-MODEL-003 — 새 RT(G1-RT-TB3)에서 packet 단위 EKF의 Goal 1 검증 사양서

- 작성: 2026-11-14 KST. 상태: **SPEC_DRAFT / NOT_RUN**
- 갈래: **새 RT 갈래.** 기존 데이터 갈래는 [SPEC_A_BLOCKC_KO.md](SPEC_A_BLOCKC_KO.md)(G1-DIAG-003)다.
- 대체 관계:
  - 이 사양은 G1-MODEL-002 초안(`MODEL_002/SPEC_DRAFT_KO.md`)을 대체한다. 002는 sweep 맞춤 추정기를 전제로 했다.
  - G1-RT-TB3-002의 §5(특성화 C1–C10), §6(구조 결정 규칙), §7은 이 사양의 S2·S3로 대체한다. C5의 BLOCK_C 하한 0.81은 폐기한다.
  - 002의 pose 집합(P-D/P-E/P-F), 경로 export, G7–G9, 특성화·확인 분리와 봉인은 그대로 유지한다.
- 근거: 2026-11-14 연구자·Claude·Fable 논의. Fable 골격(G1-MODEL-003)에 연구자 결정을 반영했다.

## 0. 연구 질문과 결정 사항

**질문.** mount 0 tag에서, 원래 접근인 packet 단위 재귀 EKF가 dual-LP 편파를 multipath 완화 없이 정직하게 모델링했을 때 DR 대비 integrity와 정확도를 확보할 수 있는가?

| 결정 | 내용 |
|---|---|
| 추정기 | packet 단위 재귀 EKF. sweep은 데이터 축적 프로토콜이며, sweep 중 각 packet이 개별 관측이다 |
| mount | **0°만.** 두 포트가 로봇 진행축 기준 ±45°다. 직진(heading 0°/180°) 구간에서 ∂s/∂ψ가 작은 작동점이라는 점을 결과 해석에 명시한다 |
| integrity | 공분산 일관성(NEES, 명목 95% 포함률). 항법 분야의 protection level·integrity risk 정의는 쓰지 않으며, 논문에서 이 구분을 명시한다 |
| integrity 판정 방식 | **B: 계층(pooled) 판정 + case 심각 실패 규칙.** P-C 경로를 확인 평가에 포함해 site 수를 늘린다 |
| 거리 의존 편파 분산 | Goal 1 arm(J-V)으로 넣는다. 값은 G-T1에서 맞춘다 |
| ranging 첫 경로 규칙 | Goal 1로 허용한다. 단, **거리 오차만으로** 고르고 s는 그 tap에서 읽는다 |
| DR 시나리오 | Sensor-v2 B0/L0/L1/L2가 주 축이다. TB3 실측(r1.3.1, r2.1.0)은 그 축 위의 점이다 |

### 0.1 Goal 1 경계

| 허용 | 제외 (Goal 2) |
|---|---|
| ranging 완화(첫 경로 규칙, range 평균 보정) | s 평균 편향 보정(μ_s 학습·차감) |
| 불확도 표현: 상관 상태, Schmidt/consider, 분산 스케일, 거리 의존 분산, 꼬리 | 반사 경로를 명시한 편파 관측 모델 |
| DR 오차 모델링(b_g, k_r) | 오염 감지 기반 s 가중·기각. heading/s 오차로 규칙·모수 선택 |

## 1. 데이터

| 항목 | 값 |
|---|---|
| 생산 | `evidence/Production/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa` (`6242fb9`). 11 조합, 61,992 pose. G4 PASS, G7 PASS, G8 재검증 PASS |
| 특성화·개발 | **G-T1 × A/B/C** (P-A, P-A′, P-B, P-C, P-D, P-E, P-F) |
| 확인 (봉인) | **G-T2 × A/B/C, G-V × A/B/C** (P-A, P-A′, P-B, P-C, P-E) |
| RF | 257 bin, 6.2504–6.7496 GHz, TX +45°, RX ±45°, mount 0, SNR 30 dB(민감도 20 dB) |
| 운동 | 직진 0.08 m/s, 회전 0.3 rad/s, RF 주기 0.2 s |

### 1.1 packet timeline (S0b에서 생성·동결)

- 경로별로 시간축을 만든다: TEACH → REPEAT(같은 18 station 재방문), P-B, P-C C1–C4 각각.
- 0.2 s마다 packet 하나를 둔다. 그 시각의 참 자세에 가장 가까운 RF pose를 쓴다.
  - 이동 구간: P-A′ 0.02 m 격자
  - sweep 회전: 조밀 49점(2.5°) 격자
  - P-C: 0.02 m·2.5° 격자
  - 허용 오차: 위치 ≤ 0.01 m, yaw ≤ 1.25°
- sweep 정지점(TB3 5점)은 TEACH 실측 체류 시간 동안 packet을 반복한다. 체류 시간 기록이 없으면 2 s(10 packet)로 둔다.
- 열잡음은 packet마다 독립 seed로 샘플링한다. 같은 pose의 반복 packet은 같은 clean H를 공유하므로, 독립 공간 표본으로 세지 않는다.
- REPEAT 자세는 `repeat.json` 정렬값과 P-E 재배치 표본을 쓴다.

## 2. 추정기와 arm

### 2.1 상태

| 상태 | 쓰는 곳 |
|---|---|
| 4-state [x, y, ψ, b_g] | B0/L0/L1/L2 시나리오, 원래 접근과의 연결 |
| 5-state [x, y, ψ, b_g, k_r] | TB3 점 시나리오. k_r은 회전량 비례 heading scale 오차 |
| 확장: c_s, c_r (유색 잡음) | J-C, J-CS |
| Schmidt site 기억 b_site(station 또는 site cell) | J-CS. 추정하지 않고 교차공분산만 유지 |

관측은 packet마다 [range, s]이고, LUT/M1-R 관측함수를 쓴다. gate는 J: χ²₂ 99%, S: χ²₁ 99%다. 초기 P0는 원래 EKF4 값이다. 초기 heading 미지 조건은 이 사양에서 다루지 않는다.

### 2.2 arm

| arm | 내용 | 역할 |
|---|---|---|
| DR4 / DR5 | 같은 motion stream, RF 없음 | 비교 기준 |
| R4 | range만 갱신 | 편파 기여 분리(J − R4) |
| J4 | range+s, 백색 R | 원래 접근, 기준선 |
| J-V | J4 + 거리 의존 편파 분산 σ_b(ρ)² | 분산 크기만 다루는 Goal 1 대조 |
| J-C | J4 + 유색 잡음 상태(거리·yaw kernel) | 이동·sweep 상관 |
| J-CS | J-C + Schmidt site 기억 | 재방문 상관까지 처리 |
| J-CI | covariance-intersection형 보수 갱신 | integrity 하한 대조 |
| +K (선택) | 위 arm에 consider bias(장거리 평균 성분의 분산만) 추가 | 지속 평균 성분 표현 |

관측 체인은 arm과 직교하는 요인으로 둔다.
- **O30:** 기존 30% leading-edge
- **OR:** S1에서 거리 오차로 고른 ranging 규칙

모든 arm을 두 체인 모두에서 실행한다.

### 2.3 DR 시나리오

| 축 | 값 |
|---|---|
| gyro bias | B0, L0 = 0.01, L1 = 0.05, L2 = 0.20 °/s, 부호 ± |
| sensor seed | 20 |
| TB3 점 | 회전 scale k: r1.3.1 = 0.0085 °/°, r2.1.0 = 0.0020 °/° (0.482°/station ÷ 약 240°), 정지 drift는 TB3 보고서 값 |
| 등가 bias | 경로별 b_eq = k · Σ\|dθ\| / T 를 계산해 L 축 위에 표시 |

TB3 r2.1.0 값은 단일 run이므로 `PRELIMINARY`로 표시한다. §8의 반복 측정이 들어오면 갱신한다.

## 3. 단계

### S0. 회귀와 timeline

- **S0a:** G1-DIAG-003 S0(BLOCK_C 원래 EKF4 결과 재현)이 PASS여야 같은 코드로 진행한다.
- **S0b:** §1.1 packet timeline을 생성하고 동결한다(`TIMELINE_PACKETS.csv`, SHA 기록). 검사 항목은 다음과 같다.
  - 최근접 pose 허용 오차 위반 0건
  - sequence 단조 증가
  - 경로별 총 이동거리·총 회전량이 pose 표와 일치(상대 1e-6)

### S1. 관측 체인 (G-T1만)

1. **지연 원점 보정.** 명목 위치에서 합성한 LoS의 leading-edge index가 RT `H_LoS`의 index와 일치하는 비율이 99% 이상이어야 한다. G-T1 P-A 전 pose를 대상으로 한다. 미달이면 중단한다(PRIOR_DIRECT의 0.2% 문제 해소 확인).
2. **ranging 규칙 선택(OR).**
   - 후보를 미리 열거한다: 임계 30/20/10%, 30% − 0.5 tap, 30% − 1 tap, sub-tap 보간.
   - 선택 지표: G-T1 range bias·RMSE와 검출 실패율. SNR 20·30 dB에서 각각 낸다.
   - 규칙: 검출 실패율 ≤ 1%인 후보 중 두 SNR 평균 range RMSE 최소. 차이가 1 cm 미만이면 30%를 유지한다.
   - **heading과 s 오차는 계산하지 않는다.**
3. 선택한 규칙으로 LUT/M1-R 예측과 range offset을 다시 만든다. G-T1 noise-free LoS에서 p90 |Δs| ≤ 0.005여야 한다(G4와 같은 기준).

### S2. 특성화 (G-T1, 한 번만, 계획 선커밋)

`CHARACTERIZATION_PLAN_003.json`에 추정식, seed, bootstrap을 먼저 커밋한 뒤 한 번 실행한다. 결과는 `CHARACTERIZATION_003.json`으로 동결한다. 체인 O30·OR 각각, anchor 3개 각각과 leave-one-anchor-out(LOAO) 조합으로 낸다.

| ID | 추정량 | 데이터 |
|---|---|---|
| C1 | 열잡음 σ_s, σ_r (seed 간) | P-A 5점 정지 |
| C2 | e_MP = s_full − s_LoS, range 오차 e_r의 거리별 분산 → J-V의 σ_b(ρ)(절점 0, 1.5, 3, 6, 10 m, 구간 선형, 최소제곱) | P-A, P-A′, P-C |
| C3 | 이동거리 상관 kernel(지수, 상관길이 ℓ_d), yaw 상관 kernel(sweep 내, ℓ_ψ) | P-A′, P-C / 조밀 49점 |
| C4 | 재방문 상관 ρ(d) (d = 0.005–0.10 m), TEACH↔REPEAT 상관 ρ_TR | P-D, P-E |
| C5 | 장거리 평균 성분: 창 5 m 이동평균의 분산 비 V_long, heading 바닥 σ_ψ,floor = √var(ē_5m) / median \|∂s/∂ψ\| | P-A′, P-C |
| C6 | range 잔차 모형(tap 계단, 거리 의존) | 전체 |
| C7 | 꼬리: e_MP 표준화 잔차의 초과첨도, Student-t ν | 전체 |
| C8 | 직진 구간과 sweep 구간의 \|∂s/∂ψ\| 분포(mount 0 작동점 기록) | P-A, P-C |

### S2-F. 사전 무용성 검사 (봉인 해제 전, 필수)

- 각 bias 수준과 TB3 점에 대해, DR heading RMSE를 TEACH+REPEAT 끝 시점과 P-C 각 경로 끝 시점에서 계산한다.
- σ_ψ,floor(C5)와 비교한다.

| 결과 | 조치 |
|---|---|
| 모든 수준에서 σ_ψ,floor > DR RMSE | 정확도 우위 불가로 기록. 확인 단계는 integrity만 판정하고 정확도는 판정하지 않는다 |
| 일부 수준에서만 | 정확도 주장을 σ_ψ,floor < DR RMSE인 수준으로 사전 한정 |
| 모든 수준에서 σ_ψ,floor < DR RMSE | 제한 없이 진행 |

### S3. 개발과 1차 arm 선택 (G-T1, LOAO)

- 모수는 두 anchor로 맞추고 나머지 anchor에서 평가한다(3회). §4의 integrity 규칙을 G-T1의 3 조합에 그대로 적용한다.
- **1차 arm 선택 규칙(사전 고정):**
  1. LOAO에서 §4 integrity를 모든 bias 수준에서 통과한 arm만 후보로 둔다.
  2. 그중 L1에서 pooled heading RMSE가 가장 낮은 arm을 고른다.
  3. 차이가 0.1° 미만이면 더 단순한 arm을 고른다. 단순한 순서: J-V < J-C < J-CS < J-CI, +K는 없는 쪽이 단순.
  4. 체인(O30/OR)도 같은 규칙으로 고른다.
- 후보가 없으면 **봉인을 풀지 않는다.** 결과를 `G1-MODEL-003 DEV_FAIL`로 기록하고 구조를 재검토한다.
- 1차 arm과 모수를 G-T1 전체로 다시 맞춰 동결한다(코드·모수·timeline SHA 커밋).

### S4. 확인 (봉인 해제, 한 번)

- `UNSEAL.json`에 S3 동결 커밋, `CHARACTERIZATION_003.json` SHA, 해제 시각을 기록한다.
- 6 조합 × 경로(TEACH+REPEAT, P-B, P-C C1–C4) × bias 수준 × 부호 × seed로 1차 arm과 대조 arm(DR, R4, J4)을 실행한다.
- 판정은 §4·§5를 따르고, 결과를 본 뒤 모수·arm·규칙을 바꾸지 않는다.

## 4. Integrity 판정 (B 방식, integrity 먼저)

### 4.1 평가 단위

- checkpoint:
  - TEACH/REPEAT: 각 station의 sweep 종료 시점과 각 이동 구간의 중간
  - P-B, P-C: 이동거리 L_seg마다. L_seg = max(1 m, 2ℓ_d), ℓ_d는 C3 값
- 독립 단위(site):
  - TEACH/REPEAT: station(REPEAT 재방문은 같은 site)
  - P-B, P-C: L_seg 구간
- CI: 2단계 bootstrap(조합 안의 site 재표집 × seed 재표집, B = 2,000)

### 4.2 규칙 (각 bias 수준과 TB3 점에서 모두 충족)

| 항목 | 기준 |
|---|---|
| pooled heading 포함률 | 점추정 ≥ 0.92 **그리고** 95% CI 상한 ≥ 0.95 |
| pooled 평균 NEES | heading, XY(2 dof로 나눈 값), b_g 각각 ∈ [0.5, 2.0] |
| case 심각 실패 | 6 조합 중 heading 또는 XY 포함률의 95% CI 상한 < 0.80인 조합이 없음 |
| gate 기각률 | s packet 기각 ≤ 20% (pooled). 조합별 값 보고 |
| B0 비열등 | B0에서 heading RMSE(1차 arm) ≤ 1.10 × DR RMSE (paired CI 상한 기준) |
| 이질성 보고 | 조합 간 logit 포함률의 random-effect SD (판정 아님, 보고) |

### 4.3 함께 보고할 것 (판정 아님)

- 조합별·경로별 포함률과 NEES
- 직진 구간과 sweep 구간의 갱신 기여
- 오차가 구간의 위·아래 어느 쪽으로 벗어났는지
- 연속 miss 길이

## 5. 정확도 (integrity 통과 arm만)

- 방문·이동거리·시간 축의 heading·XY RMSE 곡선. bias 수준 × 부호 × 경로별.
- **지속 교차점 N†:** 그 시점 이후 최대 horizon까지 모든 checkpoint에서 1차 arm RMSE < DR RMSE이고, paired CI가 0을 배제하는 가장 이른 시점.
- **편파 기여:** J − R4 차이와 그 CI.
- **TB3 점:** 경로별 b_eq 위치에 표시한다.
- **주장 문장 형식:** "mount 0, [형상] 조건에서 DR 등가 bias가 b* 이상이고 horizon이 N† 이상이면 1차 arm이 DR보다 heading RMSE가 낮으며, integrity 기준을 충족한다."
- S2-F에서 한정된 수준 밖으로 주장을 넓히지 않는다.

## 6. 모수 출처 규칙

| 모수 | 허용 출처 |
|---|---|
| 관측 체인, 열잡음, 분산·상관 kernel, σ_b(ρ), consider 분산, 꼬리 | G-T1(S1·S2)만 |
| DR 모수 | Sensor-v2 정의, TB3 실측 |
| BLOCK_C·K 진단·G1-DIAG-003 수치 | 사용 금지. arm 우선순위 해석에만 참고 |
| 확인 데이터 | 판정에만 사용. 모수·선택에 사용 금지 |

## 7. 실행 순서와 중단 조건

| 단계 | 중단 조건 |
|---|---|
| S0 | 회귀 불일치, timeline 검사 실패 |
| S1 | 지연 원점 일치율 < 99%, parity 실패 |
| S2 | 계획 미커밋 상태에서 실행 |
| S2-F | 결과에 따라 정확도 판정 범위만 조정(중단 아님) |
| S3 | LOAO integrity 후보 없음 → 봉인 유지, DEV_FAIL |
| S4 | 해제 순서 위반, 동결 SHA 불일치 |

## 8. 외부 의존 (TB3 측정)

- r2.1.0으로 trackA REPEAT 5회 이상, 3일 이상에 걸쳐 bag 포함 측정. σ_β와 k를 run별로 얻는다.
- 같은 날 r1.3.1과 r2.1.0 연속 실행.
- station 체류 시간 기록(b_eq 환산과 packet timeline용).
- 미측정 시 TB3 점은 `PRELIMINARY`로만 표시하고, TB3 수준에서의 우위 주장은 하지 않는다.

## 9. 이 구조로도 integrity가 성립하지 않을 가장 강한 이유

s 오차에 경로 길이만큼 지속되는 0이 아닌 평균 성분이 있으면, 평균 0의 상관 모형(J-C, J-CS)은 그 성분을 표현하지 못한다. +K(consider bias)로 덮으려면 분산을 그만큼 키워야 한다. 그러면 s의 heading 정보가 줄어 필터가 DR에 수렴하고, integrity와 정확도를 함께 얻으려면 평균 보정(Goal 2)이 필요해진다. S2의 C5와 S2-F가 이것을 봉인 해제 전에 판정한다.

## 10. 출력 위치

`research/G1_PACKET_EKF_20261114/MODEL_003/` 아래:

```text
S0/TIMELINE_PACKETS.csv(LFS), S0/TIMELINE_CHECK.json
S1/DELAY_ORIGIN.json, S1/RANGING_RULE_SELECTION.json, S1/PARITY.json
S2/CHARACTERIZATION_PLAN_003.json, S2/CHARACTERIZATION_003.json, S2/FUTILITY.json
S3/LOAO_RESULTS.json, S3/PRIMARY_ARM.json, S3/FROZEN_MANIFEST.json
S4/UNSEAL.json, S4/INTEGRITY.json, S4/ACCURACY.json, S4/checkpoint_rows.csv(LFS)
REPORT_KO.md, MANIFEST.json
```

## 11. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-14 | 초판. 추정기를 packet 단위 재귀 EKF로 복귀, mount 0, integrity B 방식(+P-C), J-V arm, ranging 규칙(거리 오차 기준) 허용, L0/L1/L2 + TB3 점, Fable 골격과 사전 무용성 검사 반영 | Claude |
