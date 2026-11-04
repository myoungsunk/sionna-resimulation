# MBVAR-PRR-001 — SM0 이후 Sionna RT 물리–관측–EKF 인과 검증 설계서

**계약:** PRR-RT-POST-SM0-001  
**기준:** 2026-11-04 KST · 사용자 직접 계산 / USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY  
**기준 코드:** PR #33, e69fcdd6123d3d056cd95ea210ac8eb732f17628  
**기존 계약의 연속:** CAUSAL_VERIFICATION_PLAN_KO.md, SIMULATION_DATA_REQUEST_KO.md, DATA_READINESS_AUDIT_KO.md  
**현재 판정:** SM0_TECHNICAL_ACCEPT_WITH_BOUNDARIES / NEXT_RT_NOT_RUN / HOLDOUT2_SEALED.

## 0. 먼저 확정된 사실

기존 R4-B 원본 pose 194/234/500/525, 같은 anchor와 LP±45 FFD bank, 257-bin, C00 DIRECT/C01 FLOOR/C10 PARALLEL CONCRETE PLATE/C11 OBLIQUE CONCRETE PLATE 각 2회 재현. 실제 Native Sionna PathSolver 8,224 호출, 14분55초, C00 엄격 parity 8/8, 다른 arm 기술 QA 24/24 통과. 이전 실패 19개 원본 파일과 성공 151개 파일을 별도로 보존.

원본 SHA와 다른 경로를 사용하는 Python 구현의 GitHub 읽기 전용 검산 #41815490532: 과거 실패 19/19, 성공 출력 151/151 바이트 SHA256 일치, 원시 복소 H와 저장 ray coefficient/tau 32개 key 재합, 최대 상대 residual 9.29e-8; 동일 설정 반복 H 16/16 동일. 새 물리 solver 호출은 없었다.

**중요한 과학적 차이:** 이번 통제 실험은 바닥/콘크리트 판의 새 geometry다. 기존 R2/R4/R5의 6면 corridor 및 기존 전체 Full archive와 동등한 장면이 아니다. 따라서 네 pose의 기술적 재현성 성공은 원래 corridor 벽별 인과 기여나 EKF 과신의 설명을 입증하지 않는다.

| 원본 R4 pose | C01−C00 signed s | C10−C00 signed s | C11−C00 signed s | C10 FP tap 변화 | 반사판 증거 |
|---:|---:|---:|---:|---:|---|
| 194 | −0.009565 | +0.184534 | −0.009565 | +1 (0.149552 m) | C10 변화 큼, C11의 복소 H는 C01과 동일 |
| 234 | +0.006333 | +0.333093 | +0.186553 | 0 | 편파오차 크지만 FP 이동 없음 |
| 500 | −0.005482 | −0.005482 | −0.005482 | 0 | C10/C11 모두 C01과 복소 H 해시 동일 |
| 525 | +0.012516 | +0.012516 | +0.012516 | 0 | C10/C11 모두 C01과 복소 H 해시 동일 |

표의 signed s는 **C00 대비**이다. 반사판만의 추가 효과는 반드시 C10−C01 / C11−C01로 계산한다.

| 원본 R4 pose | **C10−C01 평행판만의 Δs** | **C11−C01 경사판만의 Δs** |
|---:|---:|---:|
| 194 | +0.194099180 | 0 |
| 234 | +0.326759704 | +0.180219798 |
| 500 | 0 | 0 |
| 525 | 0 | 0 |

이 값은 Snowball의 paired CSV에서 **C00 대비 두 편파비 차이를 빼서** 직접 계산한 incremental signed polarization effect다. 모든 포트의 복소 경로 차이로 추후 독립적으로 재검산해야 하며, 이 Δs 자체를 경로별 가산적 물리 인과 기여율이라 부르지 않는다.

 비응답 pose 500/525는 버릴 outlier가 아니라 이미 정해진 **반례 및 음성대조**이다. 2회의 동일 H는 하나의 deterministic 장면 반복일 뿐 독립 장면 표본 2개가 아니다.

## 1. 연구 질문과 정의

Q0-P — 어떤 원래 corridor 반사면과 경로가 두 LP 포트의 복소 진폭·위상·지연을 바꿨는가?  
Q0-FP — 그 변화가 Hann + 4N IFFT + peak의 30% leading edge를 거쳐 first-path tap 이동 또는 동일 tap에서의 포트 전력 변화를 일으켰는가?  
Q1-K — 동일 EKF prior, mask 및 K에서 range와 편파 관측오차가 Heading/XY 갱신에 어떻게 별도로 작용하는가?  
Q2-R — 연속된 위치/heading의 다른 RF 반사와 이전 state error가 갱신을 반복하면서 posterior P/NEES 과신을 유지·증폭하는가?  
Q3-Y — **같은 위치**에서 yaw만 다르게 할 때 간섭·편파 반응·Hψ(per rad)가 달라지는가?

원본 복소 채널:
\[
H_{uv}(f,q)=\sum_p a_{uv,p}(f,q)e^{-j2\pi f\tau_p(f,q)},\qquad
|\sum_p H_p|^2 = \sum_p |H_p|^2 + 2\sum_{i<j}\Re(H_iH_j^*).
\]

RX±45 × TX±45 2×2의 포트 순서·단위·원본 archive phase32 연산을 그대로 잠근다. 위상 소스 재현과 F64 독립 수치 정밀도 진단을 혼합하지 않는다. 반사 경로별 전력은 결코 단순 가산하지 않는다.

\[
s(H,k)=\frac{P_+(H,k)-P_-(H,k)}{P_+(H,k)+P_-(H,k)},\qquad
s_F(k_F)-s_L(k_L)=[s_F(k_L)-s_L(k_L)]+[s_F(k_F)-s_F(k_L)].
\]

첫 항은 동일 tap의 복소장 효과, 둘째는 FP 선택 효과이다. **대수적 분해이며 독립적인 물리적 인과 기여율이 아니다.** 분모가 미세하거나 FP 부재면 INVALID/STOP. 1 tap 간격은 현재 257-bin/1028-IFFT에서 약 0.149552 m이고 calibration 적용 전 raw 거리다.

## 2. 실행 우선순위 — 네 개의 연구 트랙

### R0 — 기존 8,224회 raw의 경로 분석 (신규 RT 0회)

**가장 우선.** Snowball 성공 tar 안의 32개 RAW_COMPLEX_H_AND_PATHS.npz를 소비하고 원본 SM0 입력은 수정하지 않는다.

1. 각 bin의 직접파/바닥/콘크리트 판 interaction chain, path objects, τ, 복소 coefficient, valid flag, path count/offsets를 재구성한다. 원본 SM0의 2×2 H와 ray sum 및 원본 H SHA 일치.
2. C01−C00(바닥), **C10−C01(평행판 추가)**, **C11−C01(경사판 추가)**의 complex H, per-port amplitude/phase, coherent interference, FFD 투영 및 raw s 차이를 구한다.
3. FP detector 원래대로 재실행한 값과 **tap을 C01 또는 C00 값으로 고정**한 대조를 나누어 기록한다. Detector 개입과 물리적 경로 추가를 혼동하지 않는다.
4. Pose 194/234은 양성, 500/525는 음성 대조를 **전부** 포함한다. 효과가 없는 이유는 path chain과 geometry ray incidence 증거가 없으면 단정하지 않는다.

산출물: R0_PATH_LEDGER.csv / R0_PLATE_MINUS_FLOOR_COMPLEX_FIELD.csv / R0_FP_FIXED_VS_REDIRECT.csv / R0_COHERENT_INTERFERENCE.csv / R0_POSITIVE_NEGATIVE_CONTROLS.json / R0_MECHANISM_REPORT_KO.md.

### SM0-B — 원래 R2/R4/R5 6면 corridor의 15개 ray-resolved 원본 재현 (신규 Native RT)

이전 SIMULATION_DATA_REQUEST_KO.md에 **이미 고정된 사후 진단 pose**를 바꾸지 않는다:

| Route | pose_id | 수 |
|---|---|---:|
| R4-B | 168, 172, 173, 194, 234, 500, 525, 729 | 8 |
| R5-B | 401, 465, 979, 980, 982, 983 | 6 |
| R2-B | 525 | 1 |
| 총계 | | 15 |

원본 BLOCK_C의 Full/Native-LoS 257-bin archive, 동일 원본 6면 mesh·materials, Anchor B=(10,0,2.65)m, robot z=.45m/mount=0° (원본 pose/scene 매니페스트 확인 필수), 기존 source bank LP_plus45 및 LP_minus45 SHA, 원본 solver max_depth=3 및 seed=20260924를 고정한다. 새 C00~C11의 바닥판은 **원본 6면 corridor로 치환하면 안 된다**.

- **SM0-B0:** R4-B 194/234 두 pose를 LoS/Full 257 bin으로 원본 재생(2×2×257=1,028 solver calls). 사전 numeric parity는 원래 archive LoS relative L2≤1e−5, Full relative L2≤1e−3 제안(재실행 전에 최종 기록), native raw ray sum residual≤1e−8. source mesh/FFD/port/phase SHA mismatch 또는 gate FAIL면 STOP.
- **SM0-B1:** B0 전부 PASS 시 나머지 13 pose의 LoS/Full 257 bin ray-level 생성(13×2×257=6,682 calls). 총 15개는 **7,710 calls** (반복 없음). 이 15개는 개발용 posthoc hotspot이고 독립 holdout이 아니다.
- **SM0-B2(선택):** 재현성 확인에 실제 필요가 있을 때만 4개 미리 고정 pose의 반복 4×2×257=2,056 calls를 별도로 승인. Solver retry를 묵시적으로 허용하지 않는다.

각 ray: frequency별 complex a/tau, theta/phi arrival/departure, valid, objects/interaction/primitives, path count/offsets, LoS/reflected labels, direct path source index, 2×2 full complex H, original archive Full/LoS parity, receiver complex CIR/FP/r/s. 주파수마다 ray 인덱스가 변할 수 있으므로 interaction chain과 기하 위치·지연을 사용한 **frequency path ID association 및 불확실성**을 기록한다.

반사면 영향은 반드시 두 종류로 구분:
- **POSTHOC_PATH_DELETE:** 고정된 기존 경로에서 특정 ray group의 H를 빼고 FFT/FP 재계산. 관측구성의 algebraic ablation이며 재광선추적 아님.
- **GEOMETRY_REMOVE_RETRACE:** 해당 면을 원래 scene에서 실제로 제거하고 새 ray tracing. 경로 생성/소실/가림/반사 경로 변경까지 달라짐. 새 비용 승인과 재질·장면잠금 없이는 시행 불가.

원본 R4 168/172/173의 편파 및 tap, R5 465/982의 extreme, R2 525의 큰 eMP이지만 tap 변화 없는 반례와 R4 234의 작은 eMP 통제 집합을 **선택 실패에도 포함**.

### SM1 — 원래 이동경로의 시간·공간 집중 구간

원본 causal plan의 연구개발 hotspot은 이미 알려진 사후 선택임을 항상 표시. **SM0-B native archive parity PASS 뒤에만** 새 ray tracing 확대.

최소 첫 구간: R4-B **33.0–35.2 s** (168/172/173 포함), R5-B **195–198 s** (979/980/982/983 포함). 필요 시 R4 0–15, 59–61, 99–105.4s; R5 79–81, 92–94, 132–135s 순서로 확대. R2는 기존 C0A에서 고정한 large-error/no-tap-shift와 정상 대조.

원래 Tnone timeline에서 (route, t, pose_id, x,y,ψ)를 **실제 key join**하여 고유 pose 집합을 잠근다. t×5 반올림만으로 pose_id를 만들지 않는다. 필요한 신규 calls는 **N_new_unique_pose × 2(Full/LoS) ×257**; SM0-B와 중복 pose는 원본 ray 데이터 재사용. 5Hz/0.2m/s 직진 시 **5초≈1m**, 현재 위치를 5초 평균으로 대신하면 물리적 원인/시각을 흐릴 수 있으므로 time window 0.2/1/5s와 spatial separation 0.1/0.25/0.5/1m를 별도 분석.

물리 eMP_s/r, ε_s/r, Hψ per rad, delta_h=h(x_GT)−h(x_prior), ν=ε+delta_h, NIS/BASE gate, K/P와의 연계를 구분한다. 한 위치의 큰 eMP가 미래 posterior 과신의 **직접 인과증거**라는 식의 시간상관 해석을 금지한다.

### SM2 — 같은 (x,y)에서 yaw만 변경한 물리 반증

원본 R4 pose168 (x,y)에서 yaw {−35.7°,0°, +35.7°, 180°, 해당 원본 GT yaw}를 **동일 x/y/z·anchor·mount·material·solver**로 계산. 동일 yaw 값이 중복이면 정확히 한 번만 실행하고 중복 receipt를 남긴다. 한 위치에서 최대 5 yaw×2 mode×257=**2,570 calls**. R5 pose982를 두 번째 위치로 추가할 경우 최대 2,570 calls. 기존 제안 좌표 (10,±0.35)/(13.9,±0.35)m는 mesh collision 검사 및 별도 승인 전 포함 금지.

위상/포트 projection/complex H/first-path/r/s 및 ∂h_s/∂ψ(per rad)를 기록하고, 기존 R4와 R5 경로의 서로 다른 (x,y,yaw)를 같은 위치 yaw 개입처럼 취급하지 않는다. SM2 신규 physical counterfactual은 **원래 주행 실측이 아님**.

### C1/C2 — 기존 저장된 Full/LoS를 이용한 EKF 메커니즘 (신규 RT 0회)

C1: 동일 prior (x−,P−), 고정 K/H, 고정 BASE gate·원래 mean/R에서 네 관측 arm (rF,sF), (rL,sF), (rF,sL), (rL,sL)을 비교. 고정 K의 Δx=KΔz와 같은 Joseph P는 정의상 발생함을 명시. 고정 gain과 gate 재선택은 별도 실험.

C2: 동일 x0/P0/gyro/odom/5Hz RF timebase에서 오염 구간만 교체한 뒤 **각 arm 자연 재귀**. H(prior), ε, δh, innovation, K, posterior full 4×4 P, NEES4/NIS, Heading/XY 95%, gate-mask 전후, 0–2/2–5/5–10/10–20s 효과. 원래 calibration mean/R 및 seed/controls 유지, GT oracle은 후처리만. C1/C2의 새 필터/성능 주장 및 recovery policy 변경은 이 RT 데이터 생성 요청서의 범위 밖이다.

## 3. 실험–주장 매핑 / fail-closed

| 검증 게이트 | 지원 주장 | FAIL 및 금지 |
|---|---|---|
| R0 raw/reconstruction | 통제 plate가 complex H·FP·signed s에 영향을 주는 구체 경로 | source/ray metadata mismatch, 500/525 무효과 삭제 금지 |
| SM0-B 원본 6면 archive parity | original corridor hotspot 반사면 원인 귀속 분석 시작 가능 | 기존 Full/LoS와 H mismatch면 attribution STOP |
| SM1 sequential matched RF | 이동 중 RF 오염 발생·시공간적 구조 설명 | 다른 pose/time mean, pose_id 추정 join, time OU 일반화 |
| SM2 fixed XY yaw | yaw 자체가 port/간섭/FP에 주는 물리 효과 | pose shift/geometry 변경과 혼합 금지 |
| C1 fixed-prior | 거리 vs 편파 innovation이 K를 통해 state에 주는 직접효과 | gate/R/mean 변경 후 순수 r/s 개입이라고 주장 금지 |
| C2 natural recurrence | 관측오염 history→state/P 과신의 특정 구간 내 paired 효과 | deterministic H 반복 2개를 2 independent scenes로 세지 않음 |

모든 실패/NaN/충돌/누락/부호/시드/포트/scene material 불일치를 denominator에 남긴다. 실제 원본 LoS/Full source replay, 2×2 port, material/mesh SHA, archive phase32, ray grouping, FFT FP chain 중 하나라도 불명확하면 해당 단계 **BLOCKED**. Independent auditor signature 없는 사용자 직접 계산은 **non-independent exploratory**로만 표시한다.

## 4. 다음 직접 실행의 순서

**권장:** (1) 신규 RT 0회로 R0 전체 path + coherent s 분석 → (2) original corridor B0 2 poses/1,028 calls → (3) B1 13 poses/6,682 calls → (4) SM1 최소 창 → (5) SM2 한 XY yaw set/2,570 calls. C1/C2의 기존 데이터 분석은 병렬 가능.

본 문서는 실행 승인·생성 결과가 아니다. 정확한 pose key·원본 source SHA·계산 시간/자원 상한은 [별도 시뮬레이션 요청서](SIMULATION_REQUEST_SM0B_SM1_SM2_KO.md)의 계산 계약으로 먼저 잠근다.

**최종 현재 상태:** SM0=TECHNICAL_PASS / R0_MECHANISM=NOT_EVALUATED / ORIGINAL_CORRIDOR_RAY=NOT_RUN / SM1=NOT_RUN / SM2=NOT_RUN / EKF_CAUSAL_EFFECT=NOT_EVALUATED / HOLDOUT2=SEALED.
