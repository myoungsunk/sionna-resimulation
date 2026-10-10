# 10 — 요구사항 정정: 주행 중 상시 EKF + 신뢰도 저하 시 제자리 프로브 + first-cluster 이중 LP 분석

작성 2026-10-10, 상태: **설계/검증 사양서 (closed-loop simulation 미실행)**.
상위 입력/기존 결과: 06 (full P6, noisy probe, 교차공분산), 08 (mount 0/45 12케이스, first-arrival 편파비), 기존 09 통합 문서. 본 문서의 **event-driven 지속 EKF 제어 정책**이 그 이전의 오프라인 일회성 프로브 검증 설계를 대체한다. 데이터 요건은 계속 적용한다.

## 0. 사용자가 원하는 시스템 — MUST

정상 운전에서는 **매 센서 시점 EKF**로 IMU+wheel prediction/correction 및 single-anchor UWB range를 갱신하고, **고신뢰 RF s도 매 시점** 함께 업데이트한다. 주행 중 현재 상태에서 RF 측정이 저신뢰라는 신호가 감지될 때만:
1. RF 업데이트 이전의 prior와 RF/CIR 특징을 검사하고 low-confidence trigger 결정. 이 관측은 먼저 EKF를 오염시키지 않는다.
2. 로봇을 **현 위치에 정지** (속도 0, 물리적 stop/settle and any xy deviation recorded).
3. 같은 위치에서 몸체 yaw(혹은 검증된 독립 head)만 회전해 **추가 1–2개 각도**에서 RF 측정. 최초 triggering s 1개를 포함해 **총 2–3개 yaw 관측**이다. "2–3회 프로브"가 최초 관측 외 2–3회 추가라는 별도 정책이면 그 시나리오를 명시적으로 구분. 여기서는 total 2/3 points를 default로 고정.
4. 해당 위치 및 각도의 LoS FFD-LUT와 두 포트 first-path/first-cluster 전력비, IMU/odom/회전 불확실성을 이용하여 site-level 및 각 측정점 별 오염확률(q_site/q_i)과 **공동 pose/heading posterior**를 산출. 오염 포인트는 낮은 가중치로 유지, 가장 residual 작은 포인트 하나만 고르지 않는다.
5. **동일 관측을 두 번 업데이트하지 않고** 한번의 correlated batch or posterior-to-EKF fusion으로 x6/P6를 갱신. Low confidence이면 적절한 공분산을 유지한 채 propagation을 우선하고, 근거 없이 정확한 heading을 강제하지 않는다.
6. 실측 회전 엔코더/IMU로 원래 주행 heading(경로 기준)을 복원하고 주행을 재개; 갱신된 heading과 공분산은 이후 **모든 EKF 시점에 계속 전파**된다.

이것은 이전의 "RF-off 전체 주행 → 일부 지점에서 offline one-shot probe" 연구가 아니다. 그 이전 연구의 7.03°는 대조군으로만 보존하며 신규 closed-loop endpoint와 비교 불가.

## 1. 상태 기계와 필터 호출 순서

기본 filter: 6-state sensor-v2 [x,y,psi,bias_g,gyro_scale,eps_wheel], 5 Hz dt nominal 0.2s, 주행 0.2m/s, 동일 단일 anchor (A 또는 B). 추적 state/control:
- DRIVE_NORMAL: 매 tick gyro+wheel predict/odom correction → UWB range correction (available, gated) → pre-s quality (LUT, s, P1/P2, optionally first-cluster amplitude) → quality good인 경우만 일반 scalar s update; low로 판별되면 s를 **보류**, trigger 생성.
- BRAKE_SETTLE: commanded v=0; 실제 stopping distance/latency/gyro+wheel noise propagation 기록. Range는 계속, RF s는 optional diagnostic/low-weight policy로 사전 고정. Trigger 이전 s를 EKF에 넣고 나서 stop 판단하지 않는다.
- PROBE_TURN_1 / PROBE_TURN_2: 실제 body 또는 독립 head를 상대 목표 offset으로 이동. 경과시간과 실제 각도/위치 이동 기록, 매 0.2초 sensor-v2 계속 예측, 범위 측정도 동일 계약으로 갱신. 로봇이 헤딩을 물리적으로 회전 중이면 이를 **로봇의 실제 psi 변화**로 처리해야 한다.
- PROBE_MEASURE: 각 각도에서 P1/P2 및 first-cluster power, range, detection, measured yaw offset, pre-measurement x6/P6를 취득; 위치 이동은 stationarity tolerance 0.02m 이하일 때만 same-location 가정(시나리오 제안값).
- PROBE_JOINT_UPDATE: initial withheld s + 1 or 2 additional s를 correlated update로 **한번만** 반영. Range과 s의 cross covariance가 증명되지 않았다면 별도 승인된 근사 arm으로 분리. Measurement model h(p,psi, mount+delta), Jacobian wrt x,y,psi and relative-angle noise; no true xy/yaw to choose root.
- RETURN_HEADING: 실제 방향/회전 센서 기반으로 원래 route heading에 복귀, EKF 계속. body orientation이 물리적으로 이미 바뀐 것이므로 x6/P6로 같은 자세변화를 중복 적용하지 않는다.
- DRIVE_RESUME, COOLDOWN: 일정 이동거리/시간 안에는 신규 probe를 반복 발동하지 않음(초기 사전등록 후보 2m 또는 10s; 둘 중 어떤 기준을 적용하는지 실행 전 고정). 만성 multipath stretch에는 MAX_PROBES_PER_ROUTE와 fallback/no-probe 악화방지 가드.
- FAILED/UNAVAILABLE: RF missing, ambiguity, bad all points, unable to stop/turn, no RF H at current pose. 추가 관측이 없으면 없는 것으로 기록; 하드코딩한 clean RF or true angle 사용 금지.

각 틱의 정확한 호출 순서:
t_k gyrowheel sample → odom correction → range update → calculate q_preRF → [if good: standard s update] OR [if low: withhold s, request stop]. 이때 x_after_range,P_after_range가 현재 RF prior이다. 한 시점에 stop으로 넘어가도 EKF time step을 정지시키지 않는다.

### Trigger 설계: 하나 이상의 지표를 합성하되 ground truth 금지

CIR/HW가 가능한 경우의 후보: s_FP, |s_FP|, Psum, first-cluster ratio s_W, shared-window difference |s_W−s_FP|, port-gain-normalized early power, LUT sensitivity |dh/dpsi|, preRF innovation r = s_FP-h_FP(p_preRF), normalized NIS with true predicted covariance, gyro-wheel discrepancy, recent s motion-consistency. Distance feature is optional baseline and may dominate, so ablation mandatory.

Trigger score q_bad5 calibrated using **training geometry/routes**: P(RF heading error>5deg | online features). Threshold not selected on test route. Hysteresis proposal enter q_bad5>=0.6 for 2 consecutive informative samples or severe large discrepancy; exit q_bad5<=0.3 over 3 samples / valid fresh probe posterior. These numbers are exploratory simulation candidates, not demonstrated optimal or physical. Register full exact rule, cooldown, no_match and s slope constraints before evaluation. Compare thresholds 0.4/0.6/0.8 in explicitly named sensitivity arms, not cherry-pick.

RF feature model inputs from actual runtime measurements only; without physical CIR accessibility, no CIR-dependent trigger arm may claim hardware feasibility. Range only remains single-anchor and may itself have correlated multipath bias.

### Performance must use same stopped-probed-recovered trajectory

Run **closed-loop actual trajectories**, not fixed Tnone path by inserting free static observations. Every stop/turn/return changes elapsed time and sensor drift. Compare full-route endpoints with identical underlying route goal and conservative time/cost accounting. Provide no-probe counterfactual with same noise stream and explicitly account for differing time indices; path-length and arrival clock may differ. An RF-trigger at an arbitrary XY cannot be replaced by closest preexisting station RF; compute new Sionna path for actual pose/yaw or label RF_MISSING and abort/inhibit feedback. The 74 stored full yaw-sweep physical stations and 16 with v2 RF-off prior are insufficient to verify arbitrary-time online triggering.

## 2. Mount + actual single-anchor RF configuration

Use 08's fully paired 12-cell matrix R2/R4/R5 × anchor A/B × mount 0/45. Existing cases 7, new required H pairs for 5. RX nominal ports +45 and −45, TX **+45 only**, anchor rotation diag(1,-1,-1), robot antenna up, robot body yaw+mount. Co/cross label cannot be assigned by port name because TX is flipped in world frame. Compare 0/45 under same geometry, route, seed, RF call budget. Existing R2-A mount45 alone is NOT all 45 degrees.

## 3. 핵심 RF 지표: 첫 도착 peak/tap/공통 뭉치에서 LP 비의 변화

기존 observer contract **그대로**:
Hann window → 4N zero-padding → complex IFFT (simulation only) → strongest RX branch 30%-peak leading edge shared tap k_FP → P1_FP, P2_FP at the SAME k_FP → s_FP=(P1−P2)/(P1+P2). Receiver-only instrument sees no cross-port coherent phase.

NEW amplitude-only early-gate feature at common tap relative window W_L:
E_{j,L}=sum_{n=k_FP}^{k_FP+L-1} max(|CIR_j[n]|²−noise_j[n],0),
s_L=(E_{1,L}−E_{2,L})/(E_{1,L}+E_{2,L}).
L ∈ {4,8,16} *zero-padded CIR taps* (roughly first ~2ns/~4ns/~8ns at bandwidth 500MHz), as **separate exploratory features**; ~2ns resolution does not improve by padding. Original s_FP remains h_FP target. Same window for BOTH RX ports, never separately peak-lock the two ports, avoid leaking oracle gating. Store k_FP and k_peak separately. Constrain windows to valid CIR length and log clipping/detection.

Because zero-padding makes adjacent samples correlated and leading-edge gate can include a pulse mainlobe not a path, the name **first-arrival power-ratio in common early gate** is more faithful than "separating reflection and LOS". This cannot resolve coherent overlapped paths, but their effect on effective receive polarization can show in FP/early ratio.

**Compare three different quantities separately:**
- measured s_FP and measured s_L for each L; f_L=|s_L−s_FP| and gain-normalized port contrast. These are online-available only if device exports amplitude-CIR; H-derived first-cluster is research surrogate until verified.
- oracle e_MP,FP=s_full_FP−s_LoS_FP and e_MP,L=s_full_L−s_LoS_L, where clean LoS uses **same observation chain** and own aligned first tap; these are offline labels ONLY.
- online r_FP=s_meas_FP−h_FP(p_hat,psi_hat,mount). To calculate online r_L=s_meas_L−h_L, first build/validate **separate cluster-LUT h_L** with exactly the same gating; NEVER subtract original single-tap h_FP from cluster measurement s_L and call it a multipath residual.

You can evaluate whether f_L, cluster P1/P2, s_L etc predict heading error despite not having h_L, but no *cluster measurement EKF update* with an FP-only LUT.

## 4. Analysis of measured P1/P2 versus physically "depolarized" signal

- TX nominal +45 has world flip from ceiling orientation; in ideal vertical LOS at robot yaw 0,mount0, RX −45 can be co-like. At mount45, clean LOS can produce P1≈P2. |s| high/low is NOT evidence of reflection nor depolarization. All anomaly targets must be differences from **geometry/FFD-matched LoS response**, and that truth is offline.
- s and 10log10(P1/P2) are deterministic transforms, not two independent features.
- Same radio-frequency coherent LOS + reflected field in each RX yields |L1+R1|², |L2+R2|²; without relative phase no unique decomposition of actual reflection powers or physical total DoP. Angular modulation of 2ψ across 3 points may diagnose polarization response, but a common effective polarization rotation may remain indistinguishable from true heading.
- Evaluate FP and early gate ratio against **operational RF heading correct5 label** from sensor-v2 *at the same pose* (branch selected from preRF prior), plus oracle multipath s mismatch label separately. Compare learned q against distance+Psum+s base and CIR shape groups; report actual added value, held-out Brier, AUROC, calibration and station-level confidence.
- When all points share a coherent polarization rotation bias, additional yaw points may not reveal it; correctly enlarge uncertainty instead of false confidence.

## 5. For next executable simulation — needed snapshots

Emit for every T sensor step: physical time and phase, reference route progress, physical/control yaw and XY truth (evaluation-only), measured gyro and wheels, current anchor, 0/45 mount, P1/P2 and s from full H+noise, first path/candidate window/CIR amplitude (if supported), H and Jacobian, q_preRF, is_trigger, trigger_reason, withhold_s flag; x6 and P6 BEFORE and AFTER odom/range/s and correlated joint update (6×6), residual/NIS pre gate, effective covariance and covariance eigenvalue/PSD check. For probe: station original/actual XY, actual yaw offset vs sensor inferred, stop/rotate/return time, RF first cluster ratio per point, s_FP and f_L per point, q_site and q_i plus heading posterior/multimodal flags, difference to prior, noRF fallback, total failed/success triggers and longest RF outage. Preserve thermal cross-port and across-yaw covariance if calibrated, and range–s coupling, not diagonal IID unless labeled reference arm.

Required scripts and outputs:
- CONTROLLER_CONFIG_FROZEN.json (threshold, consecutive samples, cooldown, max stops, duration/turn rate, exact sensor seeds, validation split)
- EVENT_TRACE.parquet/csv: one row per **every** time step; trigger logs linking action to measurements and state.
- PROBE_PACKET_<station>.npz (M=2/3 FP P1/P2, first-cluster energy per both ports, recorded body yaw and time, quality and full covariance).
- GLOBAL_FILTER_TRACE_<run>.npz and ORACLE_EVAL_ONLY_<run>.npz; logged separately with matching hashes.
- DISTANCE/INCIDENCE/MOUNT_STRATIFIED_FP_CLUSTER.csv, TRIGGER_CALIBRATION.csv, STATION_AND_POINT_RELIABILITY.csv.
- FULL_ROUTE_RESULTS.csv (per arm/case/drift/seed: heading/position RMSE, P95, NEES, coverage, distance walked, elapsed seconds, number probes, first low-confidence moment, wall-outage length).
- MATCHED_STATION_RESULTS.csv distinct one-shot postprior comparisons (ONLY secondary).
- RF_CHANNEL_COVERAGE.json (each low-quality trigger: actual H available? required new channel? masked?).
- independent held-out geometry, code/manifest checksum, plot, status. Scientific_PASS remains false until audited.

## 6. Fair baseline arms and STOP

Baseline A: 5Hz odom+IMU, range as fixed arm where specified, **NO RF s**.
D: full-route 5Hz default EKF with EVERY RF s (old style), no probing.
E: full-route 5Hz EKF with **passive reliability-only weighted s** at every tick, no probing.
F2/F3: continuous EKF plus trigger-based 2/3-point **same-site stop/turn/joint-update/resume**, with first-path-only quality.
H2/H3: same F2/F3 but with first-cluster LP ratio and multi-angle quality. To isolate features, do not change movement schedule after seeing outcomes; report differing triggered trajectories/cost.
Oracle LoS-only C and oracle multipath-identity are offline controls, NOT actual inference.

Primary outcome is FULL_ROUTE_RESULTS, not isolated probe error at a few positions. Compare identical mount, route, anchor/seed and checkpoint progress, with elapsed-time and nearest-station coverage. Need initial noRF and full LoS references on same timeline or explicitly time/trajectory-normalized analysis. Any improvement requires heading and position accuracy **AND** NEES/coverage without nuisance inflation or unrealistic free turns. All abnormal/outage episodes counted, not only evaluated probe sites.

STOP: if missing new RF at triggered pose, actual noisy motion, sample timestamps, P6, h_L full early cluster for cluster measurement update, independent Sigma_probe, hardware amplitude capability proof for claimed hardware, then mark that particular component BLOCKED; preserve partial FP-only experiments when valid. Never backfill with truth or sweep best-3 oracle. Existing full H 7 cases & 74 yaw stations can support partial offline FP/early feature **association** but do NOT establish closed-loop behavior at arbitrary trigger poses.

## 7. Rule on interpretation of past runs

Entire-route EKF A~E from sensor-v2 performed every update on Tnone routes; old MIX_3 offline took RF-off sensor-v2 preRF prior **only at locations with existing saved yaw sweeps** and combined 3 values. MIX_3 was not reinjected into future EKF states, ignored probe duration, noisy yaw motion and full pose crosscov. It is NOT the user's desired architecture. Future reports must distinguish \`OFFLINE_DIAGNOSTIC\`, \`CLOSED_LOOP_DYNAMIC\` and \`NEW_RF_ORACLE\` explicitly.
