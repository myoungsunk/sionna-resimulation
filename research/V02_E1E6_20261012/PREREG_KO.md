# V02 E1–E6 사전등록 (실행 전 작성)

날짜 2026-10-12. 상태: **사전등록, 확증 seed 실행 전.** Stage A 진단·탐색 단계이며 production 코드 변경 없음. V02 Gate는 이 실험의 결과와 무관하게 **OPEN**이다(아래 §8).

## 0. 권한과 한계 (투명성)
사용자 메시지에 “통합 실행 프롬프트” 본문이 빠져 있었다(제목 한 줄만 도착). 그래서 근거는 (a) 사용자가 앞서 보낸 V02 권고(E1–E6 정의), (b) 같은 메시지의 표(“V02 E1–E6: 사전등록 후 실행, 독립 seed 512개, PF·GSF 기준 posterior 검증”)이다. 아래 기본값(PF 입자 수, GSF 성분 수, seed 범위, 판정 규칙)은 **내가 정한 값**이며 실행 전에 여기 고정한다. 사용자가 다른 값을 원하면 새 버전으로 다시 등록한다.
Stage B/C는 이 문서의 범위가 아니다.

## 1. 데이터와 seed
- 확증 seed **3000–3511 (512개)**. 지금까지 사용한 0–127, 256–383, 512–527, 640–767, 1000–1255, 2000–2511과 겹치지 않는다.
- 개발(디버깅·PF 수렴 점검) seed **2900–2931 (32개)**. 확증 결과에는 포함하지 않는다.
- 궤적·DT·N·체크포인트·range σ(0.08, 게이트 없음)·Q/R 법칙·원본 EKF는 `V02_DECOMP_20261011/run.py`와 같다. 체크포인트 0/12/24/48 s. **주 평가점 48 s.**
- 평균 pose NEES(3자유도)의 95% 구간: χ²(3n)/n, n=512 → [lo,hi]를 실행 전에 계산해 쓴다(코드가 같은 식으로 계산).

## 2. 세계 (truth/입력 생성)
- **CONS**: 필터 자신의 `transition()`/`odometry_model()`/Q 법칙으로 생성한 model-consistent 세계(V02_DECOMP와 동일). prior ∈ {SMALL, LARGE}.
- **HIGH**: 생성기 `V.generate(level=2)`의 이산(±값) 보정 파라미터. 보정 3개(gyro bias, gyro scale, wheel asymmetry)만 켜고 wheelbase 오차 0, slip off(= 기존 `HIGH_*_NO_WHEELBASE_NO_SLIP`). 위치·yaw prior는 LARGE(`Config().p0_std`). 필터 prior 평균은 공칭값, 위치·yaw 시작 오차는 기존 HIGH 모드와 같은 방식.

## 3. 실험
| ID | 세계 | 추정기 | 비고 |
|---|---|---|---|
| E1 | CONS(SMALL,LARGE), HIGH | 원본 6상태 EKF (HIGH는 기존 legacy prior) | 기준선. HIGH_LEGACY는 prior 불일치 대조군으로 보존 |
| E2 | CONS(SMALL,LARGE) | JointCubatureFilter (GH9 range) | 후보, 통과로 간주하지 않음 |
| E3 | CONS(SMALL,LARGE), HIGH | Particle Filter, N=20,000 | 오프라인 기준 posterior |
| E4 | CONS(SMALL,LARGE) | GSF, 초기 prior를 xy 평면에서 분할: M∈{1,4,9,16} (+보조: xy·yaw 분할 M=8, 27) | EKF 성분 |
| E5 | HIGH | EKF, 보정 prior 표준편차를 생성 분포에 맞춤(bias 0.003491 rad/s, scale 0.015, asym 0.010; 평균 0) | 분산 정합 Gaussian |
| E6 | HIGH | GSF, 8성분 부호 혼합 prior (성분 평균 = (±bias,±scale,±asym), 성분 표준편차 = 수준값의 5 %, 가중치 1/8) | 이산 분포 정합 |

규칙: 필터에 **숨겨진 부호를 알려주지 않는다**(모든 부호 조합의 확률만 사용). 기존 Q/R 임의 확대 금지. 실패한 arm 삭제 금지.

### 3.1 PF 명세 (E3)
부트스트랩 PF. 입자 상태 6차원, prior = 필터 prior. 단계마다 입자별로 (nd, ng) ~ N(0, Q_dd, Q_gg) (Q는 필터 법칙, 측정값 |d|,|o| 사용)을 뽑아 d_true=d−nd, g_true=g−ng로 전이하고, 오도메트리 우도 N(o; odometry_model(x_prev,d_true,g_true), Q_oo)와 range 우도 N(r; h(x), 0.08²)로 가중. ESS<N/2에서 systematic resampling. 정적 보정 상태(x[3:6])에는 Liu–West 축소 지터(a=0.98, 평균·분산 보존)를 resampling 직후 적용(근사임을 밝힌다). 가중 평균·가중 공분산(yaw는 평균 기준 wrap)으로 NEES 계산.
**PF 유효성(기준 posterior로서 쓸 자격)**: (V1) CONS-SMALL에서 48 s NEES가 구간 안, (V2) cov95 ≥ 0.92, (V3) 개발 seed 32개에서 N=5k/20k/80k의 48 s 위치 RMSE 차이가 3 % 이내. 하나라도 실패하면 **E3는 INVALID로 보고하고 E3에 근거한 어떤 귀속 결론도 내리지 않는다.**

### 3.2 GSF 명세 (E4, E6)
성분마다 독립 `SensorV2Filter`. 성분 가중치는 각 적용된 odometry 갱신과 range 갱신의 예측 우도 N(innovation; 0, S)로 곱하고 정규화(거절된 갱신은 가중치 불변). 혼합 평균·공분산은 moment matching, yaw는 wrap. 분할: 확률론자 Gauss–Hermite 노드 t_i(가중 w_i)를 쓰되 성분 평균 = m + h·t_i·σ, 성분 분산 = (1−h²)σ², **h²=0.5 고정**(혼합의 평균·분산 보존). 차원별 노드 수 n∈{2,3,4} → xy 텐서곱 M=4,9,16; xy·yaw M=8(2³), 27(3³). M=1은 EKF와 동일해야 한다(검증).

## 4. 평가 지표 (모두 사전 고정)
- **주 지표**: 48 s 평균 pose NEES가 χ² 95% 구간 안인지.
- 보조: 12/24 s NEES, pose 95% 포함률(χ²₃(0.95)), heading MSE/P, 위치 RMSE·평균 위치 P-RMS, 실행 시간(seed당), (PF) 위치 공분산 trace 대비 EKF trace 비.
- “mode 수”는 입자 20k로 신뢰성 있게 확정할 수 없어 **측정하지 않는다**(범위 밖). 비가우시안성은 PF 가중 샘플의 주변 왜도·첨도와 EKF/PF 공분산 비로만 기술한다.
- 다중비교: arm 수가 많으므로 각 arm은 독립 95 % 구간으로 보고하며 가족별 보정 판정은 하지 않는다. 결론은 효과 크기(NEES 비)와 함께 기술.

## 5. 해석 규칙 (실행 전 고정)
- **R1 재현**: CONS-LARGE E1 48 s NEES가 상한 초과 → 이전 결과(7.85)가 독립 seed에서 재현됨.
- **R2 귀속**: PF가 유효(§3.1)하고 CONS-LARGE에서 PF NEES가 구간 안인데 E1은 밖이면, “모델 일치 세계에서의 Gaussian 근사(비선형 range 갱신)가 원인”이라고 기술한다. PF 자신이 CONS-LARGE에서 상한을 초과하면 **PF 구현 또는 우도 가정(Q를 |d_m|로 계산하는 필터 법칙 vs 세계는 |d_true|) 문제로 보고 귀속하지 않는다.**
- **R3 GSF 후보**: M∈{4,9,16} 중 CONS-SMALL과 CONS-LARGE에서 모두 48 s NEES가 구간 안이고 cov95 ≥ 0.92이며 위치 RMSE가 PF 대비 10 % 이내인(PF 유효 시) 가장 작은 M을 “후보”로 부른다. 없으면 “후보 없음”.
- **R4 HIGH**: E5·E6가 E1(legacy prior)보다 NEES를 구간 쪽으로 이동시키는지, 구간 안에 들어오는지를 각각 보고. E6 ≠ E5이면 이산 분포 형태 효과로 기술.
- 관측 NEES가 구간 밖이면 “실패”로 쓰며 사후에 구간·임계값을 바꾸지 않는다.

## 6. 실행 순서와 고정
1. 이 문서 커밋.
2. 코드 작성(`run_e1e6.py` 등), 개발 seed 2900–2931로만 디버깅·PF 수렴 점검(§3.1 V3). 개발 결과는 확증 결과와 섞지 않는다.
3. 코드·설정 해시를 `FREEZE.json`에 기록하고 커밋, 그 뒤에 확증 seed 3000–3511 실행. 실행 후 코드 수정 금지(수정하면 새 버전으로 재등록).
4. 보고서에는 세부 숫자와 함께 실패·INVALID 항목을 그대로 적는다.

## 7. 산출물
`PREREG_KO.md`, 코드, `FREEZE.json`, `RESULTS_E1E6.csv`, `STATUS.json`, `REPORT_KO.md`. 무거운 텐서(npz)는 저장하지 않는다.

## 8. V02 Gate와 단계 상태
어떤 결과가 나와도 이번 실험만으로 V02를 PASS로 바꾸지 않는다: 모델을 바꾸는 경우 사용자가 정한 대로 새 명세서·버전과 독립 검증이 필요하며, 기존 V02 FAIL은 소급 변경하지 않는다. `stage_B_allowed=false`, `scientific_PASS=false` 유지. Stage B/C 결과는 필수 Gate 통과 전에는 탐색 결과로만 보존한다.
