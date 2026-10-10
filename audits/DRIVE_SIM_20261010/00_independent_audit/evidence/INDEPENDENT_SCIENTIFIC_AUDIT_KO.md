# DRIVE_SIM_20261007 독립 과학 감사

감사일: 2026-10-08 (KST). 대상: `myoungsunk/sionna-resimulation`, `claude/cool-dijkstra-hnznhm`.

고정 revision: **`155bf5a63558a4fba9ff02cd0da159c7636fb8d8`**. 아래의 코드 위치는 별도 표시가 없으면 이 revision 의 저장소 상대 경로와 1-based line 이다. 격리된 detached checkout 을 읽었으며 기존 source, 실험 결과, 사전등록, threshold 를 변경하지 않았다. 감사 산출물만 별도로 추가했다. RF production 재실행·filter tuning·commit/push·로봇 실행은 하지 않았다.

## 1. Executive verdict

**최종 결정: `BOUNDED_CORRECTION_OR_VALIDATION_REQUIRED`.**

현재 결과는 **하나의 이상화된 복도, 지정 FFD, 알려진 앵커, 좁은 초기 pose prior, 합성 sensor/noise 조건에서 RF-derived `s`를 이용한 tracking 의 유용성을 탐색하는 simulation evidence**로 사용할 수 있다. 그러나 논문의 핵심 주장인 물리적으로 검증된 single-anchor heading/localization, 신뢰할 수 있는 uncertainty, 환경 일반성 또는 hardware validity 를 확립했다고 주장할 수 없다. `scientific_PASS=false`를 유지한다.

저장 결과의 provenance, 주요 통계와 코드의 기본 Jacobian 은 상당 부분 독립 확인되었다. 작은 RMSE 가 전부 분석 오류에서 나온다는 증거는 없다. 동시에 **L1/L2 실패, covariance inconsistency, evaluation-informed mismatch calibration, 불완전한 parity 범위 및 사전 G3 공허 통과**는 유효한 연구 claim 을 제한한다. 절차 결함과 수치 결과의 오류를 같은 것으로 취급하지 않는다.

| 핵심 쟁점 | 판정 | 영향 |
|---|---|---|
| LoS LUT validation | L1/L2 FAIL | 실제 full-channel observation 을 충분히 검증한 measurement model 이라고 할 수 없음 |
| Uncertainty calibration | FAIL | P0 평균 pose NEES 약 44, 기대값 3; 낮은 RMSE 와 별개로 covariance 를 신뢰하기 어려움 |
| G3 | Original strict FAIL / authorised relaxed delay eligibility PASS | old 0-station PASS 는 무효; corrected G3 가 pre-S6 sequence 를 소급 증명하지 않음 |
| Anchor B interpolation | 제한된 parity PASS, production 전체 coverage PARTIAL | production dropped-amplitude 최대값이 parity 표본 범위를 벗어남 |
| Calibration·prior·probe | 조건부 유효 | 같은 경로로 noise 선택, 좁은 초기 prior, 추가 정지시간 때문에 일반적 성능 주장 제한 |

**Confidence:** 코드·저장 통계·hash·G3 판정에 높음; RF completeness 와 전체 A/B interpolation 에 중간 이하; hardware/generalization 은 증거 부족으로 UNKNOWN. 자료 부족을 자동 FAIL 로 처리하지 않았다.

최소 후속 검증은 claim 정정, 기존 trace 의 전체 path-change 검토, covariance/GSF 결함 확인, held-out noise calibration, 제한된 anchor-B 최악 pose parity, equal-budget probe 재평가이다. 이 감사에서는 실행하지 않는다. G3 의 약 30 μm delay residual 만으로 전체 RF campaign 재실행을 요구할 근거는 없다.

## 2. Execution evidence

### 2.1 Revision freeze 와 lineage

| 항목 | SHA | Commit time UTC | 확인 |
|---|---|---|---|
| Audited HEAD / guide 포함 commit | `155bf5a63558a4fba9ff02cd0da159c7636fb8d8` | 2026-10-08 01:59:45 | 감사 시작 시 branch HEAD; KST 10:59:45 |
| A14 | `13caea15b568b8c39a5fa5327cd9bd900899c248` | 2026-10-08 01:37:53 | amendments 문서만 변경 |
| R1 executed source | `1b9cf190244f91d0097a82106a02ec1dd5f53220` | 2026-10-07 08:20:15 | 원격 실행 source 27 개 파일 hash 가 이 revision 과 일치 |
| R1 result publication | `1592c53ef461c9403225acc1325910d342717a02` | 2026-10-07 10:21:16 | 현재 HEAD 의 ancestor; 코드와 결과 commit 을 구분 |
| R2/R4/R5 executed source | `0d4588f79116e221d874307f233d69ff0b13d99c` | 2026-10-07 12:48:40 | 원격 실행 source 33 개 파일 hash 가 이 revision 과 일치 |
| A12 G3 fix | `c92da486aa7e411ee20337b688acfdf70b007676` | 2026-10-07 13:51:49 | `drive` inclusion 및 empty guard |
| Route result publication / recheck snapshot | `8b693825` | 2026-10-07 14:07:24 | corrected recheck snapshot 에 G3 fix 포함 |
| Invalid G3 retraction/evidence | `ecd6800c` | 2026-10-08 01:24:16 | 사후 recheck 결과 공개 |

R1 결과는 현재 HEAD 로부터 새로 실행한 결과가 아니다. 원본 base `c13797a`에서의 개발·실행 결과가 merge `84094a4` 등을 통해 현재 branch 에 이어졌다. R1 과 route source 는 각각 실행 snapshot 과 비교했으며 현재 source 전체가 production 당시와 같다고 가정하지 않았다. A11 의 optional RX-power 모드와 A13 exploratory 분석이 후속 추가되었지만 기본 FP observation 동작을 바꾸어 production 결과를 재생성한 증거는 없다. A14 와 guide commit 은 H/S6 를 변경하지 않았다.

### 2.2 실제 실행 환경 및 순서

E1 receipts/environment: image `rt-dual-engine:s2-deps-r2-20260928` (image ID prefix `18a2a931b69e`), **Sionna RT 2.0.1 / Mitsuba 3.8.0 / DrJit 1.3.1**, LLVM polarized CPU. GPU production 으로 서술하면 안 된다. R1 RF 는 one-thread process 16 개 병렬, S6 는 nproc=4. Routes RF 는 초기 16 에서 32 로 재시작, 실제 S6 는 **nproc=32**. 개별 solver `threads=1`과 전체 다중 process 실행을 구분한다.

Route 원본 `EXECUTION.jsonl`의 exit=0 완료시간(UTC):

| 실행 | 완료시간 | 의미 |
|---|---|---|
| routes-parity / parity-report | 13:08:57 / 13:09:01 | A10c refined interpolation parity |
| trace | 13:35:47 | 원본 route RF trace |
| continuity | 13:35:50 | 결함 checker 의 0-station PASS; 무효 |
| apply / LUT mismatch | 13:41:47 / 13:41:50 | H assembly 와 경로 기반 mismatch 산출 |
| S6_routes | 13:58:10 | `--mismatch-sigma 0.16095229605409875 --pos-process-std .01 --seeds 50 --nproc 32` |
| analysis | 13:58:19 | 저장 CSV 분석 |
| corrected G3 | 2026-10-08 01:21:29.977474 | 기존 trace 만 사후 검사; H/S6 재실행 없음 |

A12 fix commit 이 S6 완료보다 앞선다는 사실은 실제 실행 중 checker 교체 또는 유효한 사전 G3 를 입증하지 않는다. receipt 와 old reports 는 결함 checker 사용을 보여준다. `pre_S6_valid_G3=false`를 유지한다.

### 2.3 원본 접근 및 hash 확인

E1/E2 원격 root 는 아래와 같다. KMS key-only SSH 로 읽기만 수행했다.

- R1: `/home/KMS/COOL_DIJKSTRA_20261007_01a11582/source`.
- Routes: `/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source`.
- Route raw traces: `results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2/traces_R*_a*`.
- Route H/S6: 같은 root 의 `S2`, `S6_routes`.

`UNCHANGED_H_S6_VERIFICATION.json`의 historical hashes 와 **현재 실제 원격 H 12 개 및 S6 37 개를 대조하여 12/12, 37/37 일치**를 확인했다. S6 는 canonical Git blob 과도 37/37 일치했다. `TRANSFER_MANIFEST.json`은 5,751 entry 의 transfer inventory 다. 공개 checkout subset 의 plain file 95 개 canonical hash 가 일치하고, LFS pointer 1 개의 oid 도 일치했다. 나머지 5,655 entry 가 일반 Git checkout 에 없다는 사실은 원격 원본 부재를 뜻하지 않는다. 이번 감사에서 inventory 전체 5,751 개를 모두 다운로드/hash 검사한 것은 아니다.

원본 PREREG `02009ca`와 HEAD 의 canonical byte identity 를 확인했다: SHA256 `db28d1dd0dbb5a7c5695b0bb3ed630f5abaa10eb6c1eb48545c6b14c9a1a1d01`. Windows checkout CRLF 변환 때문에 working-copy text hash 를 manifest 와 바로 비교하지 않고 `git show`의 canonical bytes 를 사용했다.

원격 실제 bank/LUT hash:

| 파일 | SHA256 |
|---|---|
| LP_plus45_bank.npz | `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b` |
| LP_minus45_bank.npz | `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9` |
| hs_lut_2deg.npy | `711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079` |
| selected H_R2_aA_m0.npy | `1c40aea5ab7af87223f942c0727c0f6aabe7bd60e55a70c68c74d2c115750a51` |

Hash equality 는 file identity 이다. RF 물리 정확성, filter 타당성 또는 올바른 gate 순서를 입증하지 않는다. old immutable transfer receipt 의 `G3_strict:true`는 공허 통과로 무효이며 새로운 검사로 해석을 정정한다.

### 2.4 Evidence hierarchy 및 locator

| ID | 계층 | 자료/이번 검사 |
|---|---|---|
| E-PROV | E1+E2 | 실제 Snowball source/environment/execution, `provenance_validation.json`, `audit_provenance.py` |
| E-R1 | E1 | `results/DRIVE_SIM_20261007/SNOWBALL_RUNS/01a11582/final_B_20261007T1017Z/B_RESTART_20261007_01a115bd/`의 gate, S6, ANALYSIS |
| E-ROUTE | E1 | `results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/results/`의 TRACE_AUDIT, PARITY_STAGE_AUDIT, S6_routes, ANALYSIS |
| E-G3 | E1+E2 | `SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/`; 원격 raw 5,630 trace 독립 decode/계산 |
| E-STAT | E2 | 원본 16 CSV, 총 72,000 run 의 독립 paired statistics/bootstrap 재계산 |
| E-CPU | E2 | 기존 85 tests, 별도 Jacobian/DFT/PSD 반례, selected H replay, actual LUT local sensitivity |
| E-DEV | E3 | `DEV_RESULTS/`, A7 calibration table, A11/A13 exploratory 결과 |
| E-DOC | E4 | `PLAN.md`, `RUN_SNOWBALL.md`, `BRANCH_AUDIT_GUIDE.md`, amendments 설명 |

E4 의 자체 PASS 를 독립 검증으로 대체하지 않았다. 대형 NPZ/NPY 는 Git LFS pointer 와 원본 파일을 구분했다. 전체 raw H 의 모든 time-series estimator 결과를 재계산하지 않았으며 full RF regeneration, 전체 native A/B paired H 재계산, 모든 FFD 각도/주파수 export provenance 는 **NOT INDEPENDENTLY VERIFIED**다. `DEV_LOCAL/` 전체와 git-ignored 중간 산출물도 blanket 검증 완료로 표현하지 않는다.

## 3. RF validation

### 3.1 Geometry / material / solver

[src/qclean_uwb/scenarios/corridor.py:45–59,82–98](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/scenarios/corridor.py:45>): corridor 20×2.4×2.7 m, robot antenna z=.45 m, lever arm=0. **실제 anchor z=2.65 m** (`height_m - .05`), A=(4,0,2.65), B=(10,0,2.65)다. 필터도 2.65 를 사용하여 실행 range geometry 는 일치한다. Anchor z=2.7 문구는 수정이 필요하다. Ceiling rotation `diag(1,-1,-1)`은 determinant+1 이고 boresight world −z, robot Rz(yaw)는 +z 이다.

[scripts/corridor_sionna_run.py:41–45,82–96](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/corridor_sionna_run.py:41>): six quad boundary, floor/ceiling/end wall concrete .2 m, side wall plasterboard .0125 m. 로봇 본체·사람·가구·문·roughness·설치물이 없다. 따라서 corridor research 의 controlled idealization 이지만 특정 실제 복도 대표성은 미검증이다.

실행 CONFIG 는 max_depth=3, samples_per_src=100000, max_num_paths_per_src=1000000, seed=20260924, synthetic_array=true, los/specular/refraction=true, diffraction/edge_diffraction/diffuse=false. `llvm_ad_mono_polarized`와 float32 field buffer 를 사용한다. complex128 저장이 solver 내부를 double 로 만들지 않는다. Sampling/pruning/depth 에 따른 path completeness 나 convergence evidence 는 확인되지 않았다. Refraction 옵션 사용은 확인했으나 실제 벽 두께·transmission physics 가 현장과 맞는지까지 검증한 것은 아니다.

[corridor_sionna_run.py:160–168](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/corridor_sionna_run.py:160>), [pattern_apply.py:79–86](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/pattern_apply.py:79>)은 `H(f)=Σ a_p(f) exp(−j2πfτ_p)` coherent channel 을 생성한다. Jones/basis/phase chain 의 구현과 저장 LOS parity 는 부합한다. Native solver 자체를 재실행하거나 상용 full-wave solver 와 대조하지 않았다.

### 3.2 FFD 와 polarization

실제 bank 를 ZIP/NPY header 와 중앙 slice 로 독립 읽었다: `(257,181,361)` complex64, 6.2504–6.7496 GHz, θ=0–180°, φ=−180–180°, 1° grid. `BankPort.update`의 sqrt(2π/Z0) scaling 후 중앙 gain sphere integral/4π는 plus .986592, minus .985520, peak gain 5.84758/5.89651 로 1 W incident-field convention 에 수치상 합리적이다. HFSS export 의 원 calibration 자체는 미검증이다.

Boresight Eφ/Eθ는 plus `1.013247−.140778j`, minus `−1.016494+.142188j`, normalized Hermitian overlap .02438 이다. Nominal ±45° LP 이며 완벽한 ideal orthogonal sensor 는 아니다. 실제 복소 FFD 를 사용하는 것은 오류가 아니지만 ideal curve 와 동일시할 수 없다. RX conjugation 을 상쇄하는 bank 처리, local/global transverse basis, port ordering 을 source 와 LOS receipt 로 확인했다. 저장 LOS 48 cases 최대 relative complex error 6.067e−7, delay error 8.882e−16 s 는 E1 validation 이다.

이상적 incident field 에 대해 `Q=(|Ex|²−|Ey|²)/I`, `U=2Re(Ex Ey*)/I`이면 `s=U cos2ψ−Q sin2ψ`다. 현재 ideal on-axis TX/frame convention 에서는 `s=−cos2ψ`, `∂s/∂ψ=2sin2ψ`. 독립 ideal-channel check 오차 6.123e−17. 0°/90°는 낮은 sensitivity, 45°는 최대; π-periodic 및 mirror ambiguity 가 남는다. 실제 `s`는 position, direction, mount, FFD, multipath 와 FP tap 에 의존하는 nonlinear measurement 다. `s`는 q_clean 또는 직접 heading angle 이 아니다.

### 3.3 A/B parity 및 anchor-B cut

Method A 는 native direct evaluation, B 는 isotropic V/H trace→Jones→FFD pattern application 이다. [pattern_apply.py:27–32,64–86](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/pattern_apply.py:27>)의 basis/Jones bilinear 적용과 coherent synthesis 는 source 상 일관된다. 두 방식이 같은 solver 가정을 공유하므로 parity 는 현실 physical truth 를 검증하지 않는다.

| 저장 E1 gate | Poses | Max pose H error | Max Δs | FP equality | Range diff |
|---|---:|---:|---:|---:|---:|
| A G2 | 817 | 9.580e−5 | 7.865e−5 | 100% | 0 |
| A G2′ | 817 | 9.575e−5 | 7.856e−5 | 100% | 0 |
| A G4 | 18 | 5.394e−5 | 9.051e−6 | 100% | 0 |
| B node/G4 | 35 | 5.902e−5 | 1.509e−5 | 100% | 0 |

G2 기준은 median H≤1e−4, max H≤1e−3, Δs≤1e−3, FP=100%, range≤1 mm 이다. G2′는 Δs≤2e−3, FP≥99.5%, range≤2 mm 이며 H threshold 는 없다. G4 원문은 same as G2 지만 node code 는 G2′를 사용한다. 위 B 수치는 더 엄격한 G2 도 만족하므로 수치 판정은 바뀌지 않는다. **표본 pose/node 에서의 관측량 동등성**만 인정하며 경로 구조 전체의 동등성으로 확대하지 않는다.

[rf_b_trace.py:70–137](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/rf_b_trace.py:70>), [pattern_apply.py:99–134](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/pattern_apply.py:99>): frequency 별 union reference, absent Jones zero, presence transition bisection(약 4 solver calls), present node 내 Jf cubic spline, absent 범위 zero. 다중 transition 은 unusable. 1e−2 dropped-amplitude screen 은 A10b 이후 gate 가 아닌 flag 다. 초기 union interpolation Δs=.0113 FAIL 을 본 뒤 cut refinement 로 통과했으며 개발 반응형 수정임을 유지한다.

최대 dropped amplitude 는 parity 5 positions 에서 .03514597, production R2/R4/R5 에서 .04806840/.04770211/.04547423 다. Screen exceeded positions 507/299/704. 기존 parity 는 유효하지만 production 최대 조건까지 덮었다는 주장은 확인되지 않는다. Hidden node-between transitions, Jones/direction continuity, drop 의 물리 원인도 전체 검증되지 않았다.

G1 은 `threads=1` 65 bin×2 yaw 에서 bit-identical E1 evidence. `threads=4` pose 3.2e−6, bin 최대 1.2e−5 로 원 기준 FAIL. 이를 전체 병렬 process pipeline 결정성으로 확대하지 않는다.

### 3.4 G3: independent raw verification

원 checker 는 `drive_out/drive_back`만 station 으로 세어 route `drive` 0 개를 PASS 시켰다. `c92da48`에서 `drive`와 `NO_STATIONS_FOUND`를 추가했고 기존 regression tests 가 실행 통과했다. old six PASS 는 무효다.

이번 감사는 프로젝트 classifier 를 재호출하지 않고 stdlib ZIP/NPY decode, timeline deduplication, depth0–3 six-plane image enumeration, delay-class tie=1e−13, nearest-delay residual 계산을 별도로 구현하여 원격 원본 5,630 trace 를 읽었다. Exit0, 약 4.89 s. Missing/status-not-OK 는 전부 0 이며 corrected JSON 과 수치가 일치했다.

| 조합 | Stations | Strict unmatched 5e−14 | Relaxed unmatched 2e−13 | Max residual s | Min distinct-class gap s | Recorded set changes |
|---|---:|---:|---:|---:|---:|---:|
| R2 A | 925 | 1 | 0 | 5.109035716e−14 | 2.577283985e−13 | 53 |
| R2 B | 925 | 1 | 0 | 5.831573750e−14 | 2.432944745e−13 | 51 |
| R4 A | 547 | 3 | 0 | 9.383682083e−14 | 1.026671568e−13 | 44 |
| R4 B | 547 | 3 | 0 | 8.187995700e−14 | 1.052943760e−13 | 33 |
| R5 A | 1343 | 9 | 0 | 1.006418859e−13 | 1.030390639e−13 | 106 |
| R5 B | 1343 | 9 | 0 | 9.678208470e−14 | 1.154111447e−13 | 103 |

**Original strict G3: 6 조합 모두 FAIL. Authorised relaxed G3: 6 조합 모두 PASS, delay-class eligibility 범위에 한정.** set-change count 는 원 JSON/source 대조이며 독립 residual 계산이 direction identity 까지 재검증한 것은 아니다.

[paths.py:15–42](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/paths.py:15>), [path_continuity.py:57–78](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/path_continuity.py:57>)은 delay class 만 비교한다. 예를 들어 TX(4,0,2.65), RX(7,0,.45)의 두 side-wall reflection 은 delay14.76751201 ns 가 같지만 direction dot=.412245 로 다른 ray 다. Equal delay 는 물리 path uniqueness 가 아니다. R4/R5 min gap 이 relaxed tolerance 보다 작아 labels 도 모호하다. PASS 조건이 set-change 원인 설명을 요구하지 않으며 `set_changes=changes[:50]`라 R2/R5 의 변화 일부가 저장 보고서에서 잘린다. Path-set 변화를 모두 물리적으로 설명했다는 결론은 부적절하다.

Labels 는 RF Jones/H 합성의 입력이 아니므로 labeling 한계가 곧 S6 숫자 오류는 아니다. 최대 residual 약 30 μm, relaxed tolerance 약 60 μm 의 equivalent distance 다. 사후 검사로 pre-S6 gate chronology 실패를 고칠 수 없으나 그 실패만으로 S6 를 수치 FAIL 로 단정하지도 않는다.

### 3.5 FP chain, ranging, noise 와 hardware

[observation.py:18–76](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/observation.py:18>): 257-bin Hann→1028 padding→ifft×N→선택 TX column 의 두 RX 중 global peak branch→30% leading edge→공통 tap P1/P2→s 및 cτ. TX+45 단일 column 과 RX port ordering 을 test/source 로 확인했다. 독립 직접 DFT vs FFT 최대 오차 3.458e−13, 40 ns single path (amplitude .3,.9)에서 index76, s=−.8, τ=37.91280056 ns 가 일치했다.

Actual bank Δf=1.95 MHz, range tap .1495523 m. Hann sum(w²)=96 이므로 per-bin complex variance ν의 tap variance=6ν는 맞다. Tap correlation 및 data-dependent tap selection 은 남는다. Noise 는 bin 별 합성 complex Gaussian 이고 SNR10/30 dB 는 unit-gain10m reference 이며 actual stronger-port median13.823/33.823 dB 다. Detector 의 power clipping/bias subtraction 은 코드에 있으나 low-SNR tap-switch distribution 이 Gaussian `s` noise 를 보장하지 않는다.

20 ns weak path amplitude.05 와 80 ns later path amplitude1 의 합성 반례에서 code 는 77.821 ns 를 고른다. 따라서 “FP”가 항상 earliest physical path 인 것은 아니다. Range 와 s 는 동일 index 를 공유하여 error correlation 이 가능하다. LoS leading-edge range bias 는 FFD chain 기준 −.5315984 m, 방향별 mean std.0182659 m 이며 필터의 constant offset 으로 보정한다. Quantization variance code 의 Δf=1.953125 MHz 상수와 actual1.95 MHz 는 작은 차이로 MINOR 다.

두 port power ratio 자체는 receiver 간 complex phase 출력이 필수는 아니다. 그러나 동일 channel state 의 동시/일관된 FP sampling, CIR 접근, port timing/gain calibration 이 필요하다. 실제 UWB 제품/보드가 이를 제공하고 detector/ranging bias 가 동일하다는 증거는 없다. 현재 기능은 simulation capability 이며 hardware validation UNKNOWN 이다.

## 4. Localization validation

### 4.1 Sensor generation 과 estimator input

[sensors.py:35–46,50–54,67–82](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/sensors.py:35>)은 gyro angular increments, run 별 constant bias/scale, wheel increments 를 합성한다. Accelerometer 또는 full inertial navigation 모델은 아니다. Gyro bias random walk 는 실제 generator 에 없고 noise/parameter random sign, slip 은 정지 회전 조건의 제한적 가정이다. Wheel diameter-ratio 와 wheelbase error 는 생성하지만 estimator 상태가 모두 표현하지 않는다. 센서 수치는 placeholder 이며 실측 hardware population 이 아니다.

Zero-noise 1,205-sample 독립 propagation 에서 max position error6.51e−14 m, yaw7.55e−15 rad 로 kinematic chain 이 일치했다. 매 step truth pose 를 다시 넣어 drift 를 지우는 오류는 확인되지 않았다. Truth 는 measurement generation, initialization 및 evaluation 에 사용한다. Inference 중 future trajectory/true error/true heading 을 직접 넣는 code 는 발견하지 못했다. 초기 mean 은 **truth 근처 .1m/5° prior**로 주어진다. 이것은 명시된 simulation initialization 조건이며 global acquisition 증거가 아니다.


실제 수치도 placeholder 로 유지한다. Sampling dt=.2 s, gyro ARW=.015°/√s, wheelbase=.287 m, nominal radius=.033 m 이다.

| Drift | Gyro bias magnitude dps | Gyro SF | Wheel diameter ratio | Wheelbase error |
|---|---:|---:|---:|---:|
| low | .01 | .005 | .002 | .005 |
| mid | .05 | .010 | .005 | .0075 |
| high | .20 | .015 | .010 | .010 |

각 systematic parameter 는 run 별 random sign 이다. Wheel distance variance=2e−5|ds|, yaw variance=1e−4|dθ|+1e−5|ds|; in-place rotating sample 의 slip probability=.01, Student-t(3) scale=.5°; 추가 range sigma=.05 m 이다. Generator gyro 식은 `(1+SF)Δθ+b dt+ARW√dt N(0,1)`이며 bias random walk 를 추가하지 않는다. Datasheet comment 와 실제 hardware noise 측정은 구분한다.

### 4.2 State/process/range/s 수식 독립 검사

[filters.py:131–150,194–238](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/filters.py:131>) 실제 state 는 `[x,y,ψ,b_g,SF_g,ε_d]` 6 차원이다. θ는 rad. Process 는

`x+=d_o cosψ`, `y+=d_o sinψ`, `ψ+=(Δψ_g−b_g dt)/(1+SF_g)`.

따라서 F(x,ψ)=−d_o sinψ, F(y,ψ)=d_o cosψ, F(ψ,b)=−dt/(1+SF), F(ψ,SF)=−(Δψ_g−b dt)/(1+SF)²이다. 독립 finite-difference max error7.67e−10 으로 일치했다.

Range 는 `h_r=sqrt(u²+v²+(z_r−z_a)²)+offset`, H=[u/d,v/d,0,0,0,0]. Lever0, actual height.45/2.65 와 일치하며 FD max8.66e−10 이다.

LoS LUT `h_s=L(θ,φ_tx,φ_rx)`, θ=atan(ρ/h), φ_tx=atan2(−v,u), φ_rx=atan2(−v,−u)−ψ−mount 이다. Degree-grid chain rule 로 `∂s/∂ψ=−(180/π)∂L/∂φ_rx`; position derivatives 에는 θ 및 두 azimuth 의 derivatives 가 들어간다. [hs_lut.py:138–162](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/hs_lut.py:138>)의 cell 내 derivative 는 독립 FD 와 일치(synthetic table4.39e−10, actual LUT selected poses≤6.24e−9)한다. FP switch·cell boundary 에서 smooth derivative 를 보장하지는 않는다.

EKF prediction/update, wrapped innovation, Joseph covariance, gain/gating 은 core source/test 에서 일관되었다. IEKF 는 s update 를 반복하는 구현이며 모든 update 가 iterative 인 별도 알고리즘은 아니다. UKF sigma-point 와 circular heading treatment 를 source/test 검토했지만 production 전조건 independent posterior replay 는 하지 않았다. GSF 는 s likelihood 로 mode weights 를 갱신하며 range/odom update 가 같은 방식으로 weights 를 갱신하지 않는 설계 제한이 있다.

**GSF PSD 반례:** [filters.py:109–128,421–422](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/filters.py:109>)가 between-mode heading variance 를 줄이면서 position–heading cross covariance 를 유지한다. 유효한 block `[[1,.8],[.8,1]]` (min eigenvalue .2)에 현재 collapse 를 적용하면 min eigenvalue **−.245244**가 된다. Code validity 결함이다. 실제 production GSF 모든 component 에 발생했는지는 UNKNOWN 이며 primary EKF 결과를 이 반례만으로 폐기하지 않는다.

### 4.3 LUT / calibration / covariance

2° θ/[0,90], φ_tx/φ_rx/[−180,180) LoS-only table 이며 fixed10m reference FP chain 이다. Full-Sionna measurement 에는 multipath, amplitude/delay/tap switching 이 있고 LUT 는 이를 포함하지 않는다. L1 max.023972>.01, median~.00053; L2 max.0104489>.005 로 **둘 다 FAIL**. 큰 σ_mismatch 는 interpolation discontinuity 를 없애거나 FAIL 을 PASS 로 만들지 않는다.

R1 mismatch RMS≈.180205→.18, routes≈.160952 를 **평가할 RF 경로 자체**에서 계산했다. Seed 별 noisy errors 를 직접 estimator 에 넣은 oracle 는 아니지만 independent held-out calibration 도 아니다. 환경·경로에 대한 evaluation-informed R 선택이며 gains, gating, posterior covariance 및 NEES 에 영향을 준다. A7 position slack calibration seeds1000–1009 와 evaluation0–49 는 분리되었으나 같은 scene/routes 다. {0,.002,.005,.01}에서 NEES3 에 가장 가까운 .01 선택 후에도 calibration P0 NEES93.3/P1 15.7 로 실패했다. 이를 기록한 점은 투명하나 consistency 를 확립하지 못한다.

[experiment.py:115–137](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/experiment.py:115>) NEES 는 wrapped [x,y,ψ(rad)] error 와 해당 3×3 marginal P 를 사용한 eᵀP⁻¹e 이다. Degrees/radians 나 state dimension 착오가 아니라 **pose NEES 기대값 3**이다. Full6-state NEES 와 구분한다.

| EKF baseline | R1 mean pose NEES | Routes mean pose NEES |
|---|---:|---:|
| odom_imu | 3.415 | 3.375 |
| gyro_only | 3.926 | 4.017 |
| range | 99.675 | 62.752 |
| range_s_P0 | 43.731 | 44.187 |
| P1 T10 | 24.238 | 29.259 |
| P1 T20 | 27.690 | 33.283 |
| P1 T60 | 27.388 | 42.562 |
| inverse_heading | 307.132 | 509.847 |

P0 mean 은 기대값의 약 14.6 배다. 모든 경우를 일괄 20–40 배라고 표현하면 부정확하지만 inconsistency 는 명백하다. Routes P0 의 per-run time-averaged NEES 최대 11871.955, route mean R2/R4/R5=73.634/13.457/45.471 이다. Temporal correlation, diagonal range–s R, unmodelled bias/wheelbase, reuse of gyro control in odom pseudo-measurement, prior·gating 등이 원인 후보다. 코드상 gyro-control 와 같은 noisy increment 를 pseudo-measurement 에서 다시 사용하므로 independent-noise assumption 이 깨진다. 단일 원인을 확정하지 않았다.

Accuracy 와 consistency 는 분리해야 한다. 낮은 heading RMSE 는 존재하지만 posterior ellipse/confidence/protection level 의 신뢰를 보여주지 않는다. 시간·seed correlation 을 고려한 consistency 검증은 후속 필요하다.

### 4.4 Observability

Odometry/IMU 만으로 absolute translation/rotation 은 정해지지 않는다. Constant-speed straight motion 에서 gyro bias 와 wheel diameter-ratio drift 를 분리하기 어렵다. Range+relative odometry/IMU 는 anchor-centered rotation gauge 를 보존한다: `p'=a+Rα(p−a), ψ'=ψ+α`가 같은 range 와 body-frame increments 를 만든다. Initial heading prior 를 제외하면 range 만으로 absolute heading 을 입증할 수 없다.

Range+s 는 순간 pose3 에 최대 2 scalar constraints 다. Motion 과 known TX polarization/angular response 가 rotation gauge 를 국소적으로 깨뜨릴 수 있으나 global roots 는 남는다. Probe 는 stationary yaw variation 으로 sensitivity 를 높일 수 있지만 이상적 s 의 π ambiguity 를 자동 제거하지 않는다. Straight/180° turnaround 는 collinear geometry 의 ambiguity 가 남고 rectangle/zigzag/serpentine 은 excitation 과 conditioning 을 개선한다. A/B geometry 와 mount 가 conditioning 을 바꾸며 두 anchor 는 독립 single-anchor 조건이지 fusion 이 아니다.

실제 production LUT 와 R2 P0 의 21-sample(4s) selected windows start index100/300/700 에서 3-pose noiseless sensitivity matrix 를 독립 계산했다. Range rank2, rotation-gauge residual≤1.81e−16; range+s rank3. Singular values 는 [1.856,.926,.742], [4.417,1.453,.03358], [4.418,2.520,.03168]. 실제 ds/dheading 은 −.004290,+.002362,−.013140 per degree 로 위치에 따라 작아진다. **Mixed units 의 unwhitened selected local LUT-model 검사**이며 full6-state observability, 모든 route/full RF, global uniqueness 를 증명하지 않는다. 작은 RMSE 도 그 증명이 아니다.

### 4.5 Route/probe/baseline fairness

R1 straight round-trip 두 lateral, R2 rectangle(실제 4 legs 사이 90° turns3 개; 문서 4 개와 차이), R4 ±35.7° zigzag, R5 three-lane serpentine 을 검토했다. R3 중복 straight 제외는 제한된 route suite 에서 합리적이며 다양한 일반 환경을 cover 하지는 않는다. .2m/s,5Hz,.04m,4° wobble/12s, three drift levels, SNR30/10,50 seeds, mount0/45, anchorA/B 를 source/timelines 와 대조했다. Truth waveform 은 seed 별 environment 가 아니라 고정 경로다. Clearance/wobble guard 는 solver 퇴화 근처를 제외하므로 그 영역으로 외삽할 수 없다.

P1 은 drive-time T10/20/60 마다 36 samples/7.2s 정지 회전이다. 같은 경로·drive time 을 비교하지만 elapsed time, observation count, stationary updates, metric weighting 은 다르다. Probe 동안 gyro/wheel/RF update 가 계속되고 period 별 noise draw 도 완전히 같은 물리 sample pair 가 아니다. R1 P0/T10/T20/T60 elapsed=183.2/305.6/240.8/197.6s. 따라서 improvement 는 maneuver+extra observations+timing 의 결합 효과이며 정보만의 독립 이득이나 동일 elapsed-budget 효율로 해석하면 안 된다.

`odom_imu`는 A5 에 명시한 weak baseline 이다. 동일 priors/noise 를 사용했지만 gyro_only 와의 별도 비교가 필요하다. range 는 range only, P0 는 range+s, noturn 은 turnaround s 사용 차이를 검사, P1 은 scheduled probes, inverse 는 estimated previous heading 과 가까운 inversion root 를 택한다. Inverse branch 에 truth oracle 를 넣는 code 는 발견되지 않았다. 그러나 informative initial prior 와 previous estimate 로 root 를 고르는 tracking 비교이므로 unknown-heading global initialization baseline 이 아니다.

## 5. Preregistration audit

원 `PREREG.json`은 그대로 보존되었다. 변경은 transparent amendment 이나 원래 criterion 의 PASS 와 동일하지 않다. 아래 시각은 **최초 공개 commit UTC**다. Commit 만으로 개발자가 비공개 결과를 언제 보았는지 증명할 수 없으므로 문서 주장과 실행 증거를 구분했다. A8 이 A7 보다 먼저 적혀 있으며 번호를 시간순으로 취급하지 않았다.

| 항목 | 변경 / 원래 기준→수정 | 실제 공개 시점 | 결과 확인 전/후 | 과학적 타당성 | 선택편향/기존 영향 |
|---|---|---|---|---|---|
| A1 | thread 미명시 G1→production threads1;1e−6 유지, threads4 FAIL 기록 | 04e002d 10-07 06:09:24 | G1 thread 결과를 본 뒤 | 실제 execution 설정 고정은 타당; 전체 결정성 아님 | 중간; 성공한 runtime 범위로 한정 |
| A2 | T drive-time, kinematic truth,17.6m legs,36-sample probe, fixed wobble | 5dfcbee 06:14:07 | RF/filter run 이전으로 기록 | 모호한 설계 고정은 타당 | 낮음; elapsed fairness 가정 명시 필요 |
| A3 | axis-clearance≥.01m 및 axis parity 제외/G4 위치 변경 | 2a4214d 06:48:12 | degeneracy observed 뒤, parity 집계 전으로 기록 | 수치 퇴화 회피지만 문제 geometry 제외 | 중간; off-axis eligible domain 한정 |
| A4 | 5°→2° LUT, L1 max.01/median.001,L2 max.005 명시 | 6e77a33 06:57:57 | ideal-bank 오류 본 뒤, real-bank build 전으로 기록 | 개발 기반 grid refinement | 낮음~중간; real-bank gate 이후 유지 |
| A5 | priors sweep RMS, gyro_only 추가, R/gating/range offset 고정 | 6e77a33 06:57:57 | synthetic weak-baseline 결과 뒤, RF filter 전으로 기록 | prior 설명 및 stronger baseline 추가 유익 | 중간; narrow prior 와 weak primary baseline 영향 |
| A6 | real-bank L1 FAIL 공개; gate threshold 유지 | 3e041ea 07:04:01 | 결과 후 | 투명한 failed validation | FAIL 을 mismatch sigma 로 면제할 수 없음 |
| A7 | SNR30/10,σmismatch.09→.18,range offset, process slack calibration | 6e3a1be 07:28:11; result1b9cf19 08:20:15 | DEV RF/calibration 후, production evaluation 전 | seed-disjoint slack 은 제한적 타당; scene/routes in-sample sigma | 높음; gains/gating/P/NEES,5dB 제외는 domain 선택 |
| A8 | delay classes tie1e−13, strict5e−14 FAIL 와 2e−13 별도보고; tag rounding; assembly unmatched decouple | 6e3a1be 07:28:11 | full-route trace 와 strict failure 후 | float32 residual 설명·tag fix 타당; equal delay≠physical same path | 중간~높음; strict gate 유지, identity 주장 제한 |
| A9 | R2/R4/R5,A/B,H5/H6/H7; σmismatch route 재측정 | 53fca06 12:16:37 | 새 route 실행 전; R1 결과 후 | 추가 route 사전 선언; H7 exploratory | 중간; R1-informed expansion, evaluation sigma |
| A10 | fixed path set→union zero-fill + amplitude≤.01 screen | 0d4588f 12:48:40 | anchor-B missing path 관찰 후 | solver output 근사 수정은 가능 | 중간; discovered failure 대응 |
| A10b | amplitude screen gate→flag, parity threshold 유지 | 같은 0d4588f | amplitude 가 screen 초과함을 본 뒤 | observable parity 로 판단하는 논리는 타당 | 높음; production max coverage 미확립 |
| A10c | Δs=.0113 FAIL 뒤 bisection/piecewise refinement | 같은 0d4588f | failed parity 후, production 전 | 코드 근사 결함 correction; gate unchanged | 중간; independent worst-case coverage 필요 |
| A11 | FP 대신 total RX power; own LUT/sigma | 9b0583f 13:40:51; resultc92da48 13:51:49 | main R1 후 exploratory | 물리 원인 탐색 유익 | 높음 if confirmatory 승격; DEV1440pairs 만 |
| A12 | zero-station defect fix + no-stations guard | c92da48 13:51:49 | old G3 후; route 결과 inspected 전이라는 문서 주장 | 필수 code defect correction | old6PASS 전부무효; pre-S6 gate 미복구 |
| A13 | LUT vs ideal angular curve ablation, own sigma | 4e9ed8b 10-08 01:31:26; resultfdde99a 01:36:27 | main results 후 exploratory | angle model 중요성 탐색 | confirmatory 아님; same-route refitted sigma |
| A14 | route2e−13 user authorisation 기록, strictFAIL 보존 | 13caea1 01:37:53 | corrected recheck 및 S6 결과 후 | 승인된 amended criterion 을 별도 기록 | 원 criterion PASS 아님; 사후 gate chronology 유지 |

**Authorization timing evidence conflict:** route `START_RECEIPT`는 10-07 12:56:01 UTC 에 “2e−13 s 적용 for new R2/R4/R5 routes” 승인 문구를 포함한다. Guide/A14 는 earlier approval 이 R1 만이었다고 기술한다. 실제 인간 승인 시점을 source receipt 와 후기 prose 만으로 확정할 수 없다. 현재 승인된 relaxed 사용과 original strict FAIL 은 구분되며 이 문서 불일치가 numerical results 를 바꾸지는 않는다. 정확한 승인 chronology 는 UNKNOWN 으로 남긴다.

A11: total-RX s 는 mismatch RMS.301(fp.180), mount0 P0 median28.3°(fp6.7°) 등 11/12cells 에서 악화. A13: ideal curve mismatch.294(LUT.180), P0 mount0/45 median18.49/8.04°(LUT6.70/1.38°). DEV10seeds 와 refitted sigma 의 exploratory 설명 자료로만 사용한다. 새로운 preregistered test 통과로 승격하지 않는다.

## 6. Statistical validation

### 6.1 독립 계산과 범위

원 16 CSV 의 R1 18,000 / route54,000 rows(그 중 EKF10,800/32,400)를 읽어 failed/missing run0, 조건당 paired seeds50 을 확인했다. Independent implementation 으로 exact signed-rank subset-sum distribution, Holm, paired median effect 와 relative≥10%, 10,000 bootstrap95% CI 를 재계산했다. 원 analysis 함수의 PASS 를 재호출하는 것에만 의존하지 않았다. Tables 의 metric max difference3.55e−15, CI7.99e−15, verdict mismatch0 이었다. H4 bootstrap bound diff≤3.55e−15, selected period mismatch0.

Seed 가 statistical unit 이며 time samples 를 독립 표본으로 센 pseudo-replication 은 발견되지 않았다. 단,50seeds 는 같은 frozen RF 환경의 sensor/noise Monte Carlo 이지 50 개 독립 corridor·antenna·material 이다. 조건 cell 성공비율은 환경 일반성의 확률이나 aggregate causal effect 가 아니다. Two-sided Wilcoxon alpha=.01, hypothesis 별 condition family 에 Holm correction 을 적용하고, significance 와 median relative improvement≥10%를 함께 요구한다. 원 primary heading metric 은 최초 30s 제외 wrapped RMSE. 다른 whole-time/max/closure metrics 와 구분하였다.

| 가설 | 등록 대상 / metric | 독립 재검산 결과 | 해석 |
|---|---|---|---|
| H1 R1 | P0 vs odom_imu, heading RMSE | 19/24 improved; gyro_only 대비 18/24,2cells worse | weak baseline 뿐 아니라 stronger sensitivity 필요 |
| H1 routes | route/anchor/mount/drift/SNR 별 P0 vs odom | 66/72 improved; gyro_only62/72,4worse | 많은 지정 조건에서 개선하나 universal 아님 |
| H2 R1 | measurement fusion vs inverse_heading | 24/24 improved | 선택 baseline/initial prior 조건에서 지지 |
| H2 routes | 같은 비교 | 40/72 improved,18/72 worse | route 일반적 우월성은 반박/혼합 |
| H3 R1 | P0 mount45 vs0 | 12/12 mount45 improved | straight-specific prediction 지지 |
| H4 | largestT∈10/20/60 satisfying bootstrap wrong-branch≤10% | 20°에서 P0 도 R124/24, routes72/72 이미 만족; T60 모두선택 | need-for-probe 또는 optimality 증거 아님 |
| H5 | route mount prediction | mount45 improved12/36, mount0better16/36 | R4 지지; R2B contradiction; R5 혼합 |
| H6 | displacement/closure error vsodom | routes69/72 improved | R2loop 와 R4/R5endpoint displacement 의 의미 구분 |
| H7 | A/B heading, no direction | Bbetter18/36, Bworse12/36 | exploratory geometry sensitivity |

H5 세부: R2A45better6/6, R2B45better0/6·0better4/6; R4A/B0better6/6 각각; R5A/B45better4/6,2/6. H2R4A3/12improved6worse, R4B0improved6worse, R5A6worse. 이 contradictions 를 삭제하거나 성공 cell 만 골라 결론을 만들 수 없다.

### 6.2 Probe benefit 의 분포

| 범위 | P1 T10 / T20 / T60 paired seeds 중 heading 악화 | Median-condition 악화 | Pooled median relative improvement |
|---|---|---|---|
| R1 | 35.00 /42.08 /18.42% | 9/24,9/24,1/24 | 38.80 /6.59 /30.96% |
| Routes | 31.86 /27.64 /41.56% | 21/72,17/72,21/72 | 18.99 /17.70 /5.17% |

Worst inspected paired worsening: R1 T20 lateral0/mount0/mid/10dB/seed16=2.236→5.936°; routes T60 R5A/mount0/high/30dB/seed49=5.741→11.627°. P0 가 나쁜 조건의 최악값은 probe 로 줄기도 한다(sampled max R1 11.541→T10 2.580°, routes13.729→5.293°). 이것은 sampled benefit 이지 항상 개선 또는 worst-case bound 는 아니다.

`wrong_branch`는 실제 inversion root identity 가 아니라 `|wrapped heading error|>20°`의 operational metric 이다. 10° sensitivity 에서는 routes P0 도 61/72 만족, T60 는 57/72. H4 는 P0 를 optimal candidate 에 넣지 않은 largest registered period 규칙이며 elapsed budget 최적화를 수행하지 않았다.

### 6.3 선택된 raw-H→EKF 독립 재실행

Actual bank frequency axis 와 selected `H_R2_aA_m0.npy`(1303×257×2×2), 원 LUT/timeline 로 low drift/30dB/seed0 의 9EKF baselines 를 CPU replay 했다. 새로운 RF 를 만들지 않았다. 별도 fulltime RMSE 계산은 replay summaries 와 roundoff 수준 일치, 9 개 pose covariance 는 SPD(min eigenvalue8.51e−5).

7baselines 저장 metric 과 약 3.6e−12 이내 일치. P0 heading replay8.739865995° vs 저장 8.739888690°(Δ2.27e−5°), NEESΔ5.08e−5; noturn headingΔ2.05e−7°, 전체 selected metric 최대차 1.96e−4. **Bit-identical reproduction 은 아니다.** 작은 차이의 정확한 원인은 확정하지 않았으며 platform/interpolation sensitivity 로 단정하지 않는다. 이는 좁은 H→observation→EKF correspondence 검증이고 전체 72,000 trajectories 또는 RF regeneration 이 아니다.

Existing selected tests85 개 PASS,38.20s(exit0). Tests 는 config/trajectory/routes/sensor/filter/LUT/observation/pattern application/single-TX/G3-regression/corridor 를 포함한다. Test PASS 가 physical scientific PASS 를 대신하지 않는다.

## 7. Trust matrix

| Domain | Verdict | Evidence / 범위 | Severity |
|---|---|---|---|
| Execution provenance | PASS | E-PROV executed source27/33, runtime receipts | INFO |
| Code/result correspondence | PARTIAL | hashes 및 selected-H replay; 전 trajectory 미검산 | UNKNOWN 전체 |
| RF geometry/materials | PARTIAL | 실제 six-plane/ITU material source; 현장대표성 미검증 | MAJOR |
| Antenna/polarization | PARTIAL | 실제 bank slice, normalization, LOS evidence; full export/hardware 미검증 | UNKNOWN |
| Method A/B parity | PARTIAL | 저장 817/35pose gates; raw paired H 전체 재계산 없음 | UNKNOWN |
| Anchor-B interpolation | PARTIAL | refinedcutsource;productionmax 미 coverage | MAJOR |
| G1 reproducibility | PARTIAL | thread1 표본 identity;thread4FAIL | INFO |
| G3 original strict | FAIL | raw 5,630, all 6 unmatched | MAJOR |
| G3 relaxed | PASS | raw 5,630, all 6 unmatched0;delay eligibility 만 | INFO |
| G3 gate chronology | FAIL | invalid pre-S6, correctedafterS6 | MAJOR |
| First-path observation | PARTIAL | 독립 DFT 일치;earliestarrival 보장없음 | MAJOR |
| UWB ranging | PARTIAL | unit/quantization/offset 일치;receiverrealism 미검증 | MAJOR |
| UWB heading/s | PARTIAL | nonlinearorientation 정보;globalambiguity | MAJOR |
| LUT L1/L2 | FAIL | storedmax.023972/.0104489 thresholds 초과 | BLOCKER |
| IMU/odometry | PARTIAL | incrementdrift source/test;placeholder/nofullIMU | MAJOR |
| Filter equations | PARTIAL | coreJacobianPASS;GSFPSDcounterexample | MAJOR |
| Observability | PARTIAL | rangegauge 및 3selectedLUTlocalrank;6state/global 미증명 | MAJOR |
| Covariance/NEES | FAIL | correctNEES3, P0mean~44 | BLOCKER |
| R1 experimental design | PARTIAL | declaredmatrix;weakbaseline/narrowprior | MAJOR |
| R2/R4/R5 design | PARTIAL | declaredroutes/A-B;R2turn 문서차이, geometry 한정 | MAJOR |
| Probe fairness | PARTIAL | 동일 경로/drive time, 다른 elapsed time/sample updates | MAJOR |
| Preregistration integrity | PARTIAL | originalimmutable;transparentchanges;gatechronologyFAIL | MAJOR |
| Statistical analysis | PASS | frozenCSV pairedseedtables independently match | INFO |
| Data leakage | PARTIAL | inferenceoracle 없음;in-sample sigma/initialprior | MAJOR |
| Reproducibility | PARTIAL | selectedCPUreplay/hash/test;fullRF 미실시 | UNKNOWN 전체 |
| Scientific claim readiness | PARTIAL | limitedtrackingevidence;scientific_PASS=false | BLOCKER 강한주장 |
| Hardware validity | UNKNOWN | dualport/CIR/calibration 실측 없음 | UNKNOWN |
| Generality | UNKNOWN | onecorridor/fixedbank/material/seededtruth | UNKNOWN |

PASS 는 표에 명시한 범위의 검사를 뜻한다. PARTIAL 은 일부 확인·한계가 섞인 상태이고 UNKNOWN 은 접근/필수자료/검사 부족이다. 구현 반례와 실제 저장 결과 영향 미확정을 구분한다.

## 8. Findings

### F01 — BLOCKER: Measurement model validation 실패

- Exact source: [src/qclean_uwb/drivesim/hs_lut.py:54–87,102–122](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/hs_lut.py:54>); `S0/PREREG_AMENDMENTS.md` A4/A6.
- Original evidence: E-R1 S4/LUT validation 및 `LUT_LIMITATIONS.json`, actual `hs_lut_meta.json`.
- Expected: L1 max≤.01/median≤.001, L2 max≤.005; validated smooth prediction.
- Observed: L1max.023972, L2max.0104489; FP tap change 의 discontinuity 를 table smoothing.
- Problem/impact: mismatch 를 scalar Gaussian R 로 추가해도 systematic/non-smooth measurement mismatch 를 제거하지 않는다. Accurate physical heading model claim 을 차단한다.
- Required: discontinuity 위치와 route residual/tap-switch 영향 분해, held-out measurement-model validation 또는 claim downgrade. Gate 를 사후완화하지 않는다.
- Affected: R1/routes 전체 s-fusion 해석; 기존 수치 RMSE 자체가 거짓이라고 입증한 것은 아니다.

### F02 — BLOCKER: Posterior uncertainty inconsistency

- Exact source: [experiment.py:115–137](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/experiment.py:115>); [filters.py:194–238,268–314](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/filters.py:194>).
- Evidence: E-R1/E-ROUTE S6 mean NEES, E-STAT independent summaries.
- Expected: validated3pose NEES consistency and empirical uncertainty coverage.
- Observed: P0means43.731/44.187 vs3;range/inverse 더큼. Metric math 는 올바름.
- Problem/impact: covariance 가 trueerror 를 과소대표; confidence/protectionlevel claims 불가. Accuracy improvement 와 별개다.
- Required: temporal/crossmeasurement noise 및 bias 모델 진단, held-out consistency/coverage evaluation. 원인 없이 sigma 만 tuning 하여 PASS 시키지 않는다.
- Affected: 모든 uncertainty 해석; accuracy evidence 는 조건부 유지.

### F03 — MAJOR: G3 empty PASS 와 gate chronology

- Source: executed `0d4588f:scripts/drive_sim/path_continuity.py`; corrected [path_continuity.py:57–78](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/path_continuity.py:57>), [tests/test_path_continuity_script.py:29–47](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/tests/test_path_continuity_script.py:29>).
- Evidence: old six stations0 JSON, EXECUTION13:35:50, correctedreceipt/postS6decision.
- Expected: nonempty station check beforeS6.
- Observed: drive phase 제외로 공허 PASS, S6 후 correctedstrictFAIL/relaxedPASS.
- Impact: original pipeline eligibility protocol 미준수. 사후 검사로 소급 PASS 불가.
- Required: oldPASSvoid 표기, future fail-closed pre-S6 check; 이번 결과는 retrospective eligibility 로만 설명.
- Affected: routesprocedure. R1 의 같은 phaseemptydefect 는 해당없음; routesnumericwrong 으로 단정하지 않음.

### F04 — MAJOR: Delay-class G3 를 physical identity 로 확대할 수 없음

- Source: [src/qclean_uwb/drivesim/paths.py:15–42](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/paths.py:15>), [scripts/drive_sim/path_continuity.py:57–78](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/path_continuity.py:57>)(특히 75).
- Evidence: E-G3 min gaps,53/51/106/103changes; equaldelay/differentdirection 반례.
- Expected: 개별 pathcontinuity 주장에는 ray/direction/reflection identity 와 모든 set-change 원인.
- Observed: nearest-delay class, tie merging, fullchanges[:50] truncation, 원인조건없음.
- Impact: relaxedPASS 는 delay eligibility 만. Physicaluniqueness/labelcontinuity 완료주장불가.
- Required: 기존 trace 로 전체 changes/rootcauseofflinecheck; identity 필요시 directiongeometry 독립판정.
- Affected: routes/R1G3claim; labels 가 H 합성입력이아니므로 S6numeric 직접오류미확인.

### F05 — MAJOR: Anchor B worst-case interpolation coverage gap

- Source: [rf_b_trace.py:58,109–137](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/rf_b_trace.py:58>), [parity_gate.py:111–124](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/parity_gate.py:111>).
- Evidence: E-ROUTE `TRACE_AUDIT.json`, `PARITY_STAGE_AUDIT.json`; .03515parity vs .04807/.04770/.04547production.
- Expected: demotedscreen 을 parity 로대체할때 production worst positions 포함.
- Observed: tested 35 poses 의 drop 범위보다큰 productionpositions 존재.
- Impact: testedparityPASS 유효, route-wide observable equivalence 는미확립.
- Required: 실제 maxpositions/minimalyaws 에 targetedA/Bparity; failure 시해당 H/S6 영향범위재평가.
- Affected: anchorB route RFapproximation 의 uncertainty; anchorA 회귀 PASS 와구분.

### F06 — MAJOR: In-sample mismatch covariance calibration

- Source: [scripts/drive_sim/run_route_experiments.py:33–47](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/run_route_experiments.py:33>), [experiment.py:103–108](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/experiment.py:103>); amendmentsA7/A9.
- Evidence: σ.18/.160952 measuredonevaluatedroutes, S6command.
- Expected: independent calibration 또는 evaluation-informedcondition 명시.
- Observed: 같은 RF 경로의 true residualRMS 를 globalR 로선택. Seed 분리만으로 RFenvironmentholdout 아님.
- Impact: gains/gating/P/NEES 와 reportedaccuracy 가해당환경에맞춰짐; externalnoise choice 라주장불가.
- Required: frozenheld-outgeometry/trajectorycalibration, fixedR 를 independentevaluation 에적용.
- Affected: R1/routes 전체 sfilters. Persteptruthoracle 와는다름.

### F07 — MAJOR: Reused gyro noise 및 unmodelled wheelbase

- Source: [sensors.py:67–82](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/sensors.py:67>), [filters.py:131–150,194–211](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/filters.py:131>).
- Expected: noisycontrol/pseudomeasurement correlation 을 model 하거나독립입력.
- Observed: gyrocontrol 재사용 odominnovation 와 crosscorrelation, generatorE_b 를 state/update 가모두설명하지않음.
- Impact: Pconsistency/gain 에영향; F02 원인후보이나전체원인확정아님.
- Required: 수식으로 crosscovariance 포함모델검증 및 matched syntheticsanitytest.
- Affected: odom-headingfusionbaseline 및 RFfusion; gyro-only 비교별도.

### F08 — MAJOR: GSF collapse can produce indefinite covariance

- Source: [filters.py:109–128,421–422](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/filters.py:109>).
- Evidence: originalcode 호출 PSDcounterexample mineigen.2→−.245244.
- Expected: posterior/momentmatchingP≥0.
- Observed: headingvariance 수축,crosscov 유지로 PSD 깨짐.
- Impact: GSF uncertainty/likelihood numericalvalidity 위협; productionincidenceUNKNOWN.
- Required: mathematicallyvalidcircularmixturemoment/crosscovjointtransform 및 PSDregression; 영향있는 GSFruns 만 targetedreplay.
- Affected: GSF, primaryEKF 에는직접해당없음.

### F09 — MAJOR: Probe effect 와 resource/time confounding

- Source: [trajectory.py:84–114](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/trajectory.py:84>), [routes.py:62–91](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/routes.py:62>), [experiment.py:121–143,163–167](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/experiment.py:121>).
- Evidence: elapsed183.2vs305.6s 및 pairedseed 악화분포.
- Expected: 동일 budget 효율/순수정보이득 claim 에는 elapsed/path/sampleweight 제어.
- Observed: 추가 stationaryupdates,noise/time,all-samplemetricweight 차이.
- Impact: maneuverbundle 효과는유효하나 probe 항상유리/시간효율 claim 불가.
- Required: 기존데이터 drive-only/commonstationmetric 재분석;equalelapsed 대조필요시별도사전등록.
- Affected: 모든 P0/P1 해석. 기존통계계산오류는아님.

### F10 — MAJOR: Local tracking prior 와 global observability 구분

- Source: [experiment.py:155–159](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/experiment.py:155>), [filters.py:316–349](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/filters.py:316>), [hs_lut.py:138–162](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/hs_lut.py:138>).
- Evidence: truth-nearinitialization,nearestestimatedinversebranch,idealsymmetry,selectedlocalranks.
- Expected: global heading/localization claim 에는 multipleinitialheading/position 및 6stateobservability.
- Observed: .1m/5°initialprior 와 known anchor;π/mirrorambiguity 잔존가능.
- Impact: coldstartglobal unique localization 미증명; localRMSE 로증명불가.
- Required: frozenbroad/multimodalinitialconditions, actualRFsensitivityrank/conditioning 및 branchidentitymetric.
- Affected: R1/routesclaimextent; truthgeneration 자체는정상.

### F11 — MAJOR: Hypothesis contradictions 와 weak primary baseline

- Source: [analysis.py](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/analysis.py>), [scripts/drive_sim/analyze_experiments.py](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/analyze_experiments.py>), [analyze_route_experiments.py](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/analyze_route_experiments.py>); amendmentsA5/A9.
- Evidence: H1stronger62/72,H2routes18worse,H5R2Bcontradiction,H7mixed.
- Expected: preregisteredpopulation 전체와 contradictions 보고.
- Observed: 원 tables 는 contradictions 를포함; summarysuccesscells 로일반우월성주장하면과장.
- Impact: universalmount/probe/inverse/anchorbenefitclaim 불가.
- Required: population/contrast 별 effectdistribution·stronger baseline·negativecells 동시보고.
- Affected: scientificinterpretation; 원 stats 재계산은일치.

### F12 — MAJOR: Receiver/physical representation 미검증

- Source: [corridor_sionna_run.py:41–45,82–96](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/corridor_sionna_run.py:41>), [observation.py:18–76](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/observation.py:18>), [sensors.py:35–82](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/src/qclean_uwb/drivesim/sensors.py:35>).
- Evidence: sixboundarymodel,relativepeakFP 반례,placeholderparameters,nohardwarecapture.
- Expected: physical/hardwareclaim 에는 dualporttiming/gain/CIR,material/antenna/noisevalidation.
- Observed: coherentRFsimulation+syntheticsensors 와 algorithmicFP 에한정.
- Impact: simulationcapability 를 realUWBmeasurement 로승격불가.
- Required: physicalmodel/hardwarecapabilitychecks 를별도 stage 로사전정의.
- Affected: R1/routesLevel4/5claim; missinghardwareevidence 는 UNKNOWN, 자동 FAIL 아님.

### MINOR / INFO

- M01: [parity_gate.py:105–110](<D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/checkout/scripts/drive_sim/parity_gate.py:105>) missing/unusable rows 가남아도 summaryPASS 에포함되지않을수있다. 현재검사 reports 는 missing/unusable=[]라실제영향미확인. Futurefailclosedcoveragecheck 필요.
- M02: nodeG4 가 G2′를사용하나원문 sameasG2. 현재 B 수치는더엄격기준도만족.
- M03: actualanchor2.65 vs 문서 2.7, R2turns3vs4, quantvariancefrequency 상수차이. Execution 을정확히기술할것.
- M04: A14approvaltime 설명과 START_RECEIPT 불일치; exacthumanapprovalchronologyUNKNOWN.
- I01: known anchorA/B 는독립 single-anchor cases; `s`≠q_clean; systematic/material/FFDholdout 없음.

## 9. Claim boundary

### 현재 주장 가능한 것

- 고정된 한 복도·FFD·센서 가정과 좁은 초기 prior 아래에서, 많은 paired Monte Carlo 조건의 range+s heading RMSE 가 odom+IMU 보다 낮았다. Gyro-only 비교와 악화 조건도 함께 제시해야 한다.
- 지정 표본 pose 에서 저장된 Method A/B 관측량 parity 가 통과했다. 원본 trace 독립 검사에서는 strict G3 FAIL, relaxed delay eligibility PASS 를 확인했다.
- 원본 CSV 통계와 선택한 H→observation→EKF 재생이 저장 요약을 뒷받침한다. Full RF regeneration 을 완료한 것은 아니다.
- 실제 LUT 가 ideal angular curve 보다 유리하다는 개발 exploratory 결과가 있으며, angular/FFD correction 의 중요성을 시사한다.

### 조건부로만 주장 가능한 것

- RF-derived s 가 single-anchor tracking 에 유용한 orientation 정보를 제공한다. Known polarization/mount, eligible geometry, model mismatch 및 informative initial prior 를 명시해야 한다.
- Probe 는 일부 불리한 조건의 sampled accuracy 를 개선한다. 추가 정지시간·측정 수와 악화 조건을 함께 보고해야 한다.
- Anchor B 와 route 확장은 기하 민감도를 보여준다. Dual-anchor fusion 또는 다양한 실제 복도의 일반성을 입증하지 않는다.

### 아직 주장하면 안 되는 것

- Original preregistered gates 의 전체 PASS, 유효한 pre-S6 G3 또는 개별 물리 경로 동일성의 완전 검증.
- 검증된 full-channel heading measurement, globally unique heading/position observability 또는 신뢰할 수 있는 covariance/uncertainty.
- Probe·mount·anchor 의 보편적 우월성, 다른 환경·material·antenna·robot 으로의 일반성, 실제 TurtleBot/UWB hardware validity.

| Claim level | 현재 상태 |
|---|---|
| Level 1 — Code validity | PARTIAL: core Jacobian/chain 확인, GSF PSD 결함 및 G3 gate bug 확인 |
| Level 2 — Simulation validity | PARTIAL: controlled diagnostic 결과; LUT/parity/covariance 한계 |
| Level 3 — Research evidence | 제한된 local tracking 가설을 조건부 지지; scientific PASS 아님 |
| Level 4 — Generality | UNKNOWN / 미확립 |
| Level 5 — Hardware validity | UNKNOWN / 미검증 |

## 10. Minimum correction/validation plan

다음은 후속 작업 제안이다. 이번 감사에서는 실행하지 않았다. 새로운 기준은 결과를 보기 전에 고정하고 original FAIL 기록을 보존해야 한다.

| Priority / Purpose | Necessary change | Minimal validation / criterion | Required compute | Affected existing results |
|---|---|---|---|---|
| P0 — Claim/provenance 정정 | strict/relaxed/void/post-S6 판정 분리; actual z·병렬성·승인시점 불일치 명시 | 보고서와 receipt 대조; original FAIL 유지 | 문서/offline | 기존 숫자 재실행 불필요 |
| P0 — G3 evidence 완성 | 전체 set changes 와 원인 기록; identity claim 범위 한정 | 기존 5,630 trace 의 모든 변화·missing/status 검토; 설명 불가는 미검증 표시 | CPU, 새 RF 없음 | Label claim 에 영향; H/S6 유지 |
| P0 — GSF 수학적 안정성 | PSD 를 보존하는 collapse 방식 정정 | 제시한 반례 및 production component PSD 검사; 기준 tolerance 를 먼저 고정 | CPU | 영향 있는 GSF runs 만 replay 여부 결정 |
| P1 — Covariance/model validation | Gyro 재사용, range–s 및 시간 correlation, bias 를 구분 | Matched synthetic sanity checks 및 frozen held-out NEES/coverage 기준; RMSE 와 분리 | CPU, 기존 H | Filter 변경 시 해당 S6 만 targeted rerun |
| P1 — Independent calibration | Held-out trajectory/geometry 에서 noise/offset/R 고정 | Calibration/evaluation 독립성 hash·manifest 확인; original L1/L2 FAIL 유지 | CPU; 필요하면 제한된 RF | 수정 모델 결과는 기존 결과와 분리 |
| P1 — Anchor B coverage | Production 최대 dropped-amplitude positions 에서 A/B 대조 | 기존 G2/G2′ 기준과 complete coverage 요구; FAIL 이면 영향 범위 산정 | 제한된 native RF poses, 별도 후속 scope | B 의 영향 있는 H/S6 만 rerun 판단 |
| P1 — Observation/LUT | FP switch·multipath bias 및 sensitivity map 분해 | Original L1/L2 또는 사전에 고정한 새 모델 기준; held-out noisy error/correlation 검사 | CPU, 기존 H/LUT | s/range fusion 해석 또는 해당 모델 replay |
| P1 — Probe fairness | Drive-only/common-station/time-budget 지표 추가 | Negative/worst/median 동시 보고; elapsed 효율은 matched comparison | CPU, 기존 자료; 필요 시 새 사전등록 | P1 claim; RF 재생성이 항상 필요한 것은 아님 |
| P1 — Observability | Actual 6-state conditioning 및 broad initial roots 검사 | Range gauge, sensitivity FD, rank 와 global ambiguity 구분 | CPU, LUT/H | Global localization claim 을 별도로 검증 |
| P2 — Physical generality | Material/geometry/FFD/solver depth·seed hold-out | 먼저 고정한 convergence/error/robustness 기준 | Controlled RF, 후속 scope | Level 4 주장 전 필요 |
| P2 — Hardware | Dual-port CIR/timing/gain/noise/ranging capability 확인 | 실제 독립 captures·calibration·held-out validation | 실제 장비, 별도 승인 task | Level 5 주장 전 필요 |

새 consistency/hold-out acceptance threshold 의 구체적 값은 후속 사전등록에서 정해야 한다. 이번 결과를 통과시키기 위해 임의의 값을 선택하지 않았다. Validation failure 또는 model change 가 확인될 때 targeted rerun 의 범위를 결정한다.

## 11. Final decision

**`BOUNDED_CORRECTION_OR_VALIDATION_REQUIRED`**.

실행 provenance, 원본 CSV 통계, raw G3, core Jacobian 및 selected H replay 를 확인했으므로 증거 전체가 부족하거나 방법을 즉시 폐기해야 한다는 판정은 타당하지 않다. 반면 LUT FAIL, uncertainty FAIL, GSF PSD 결함, anchor-B coverage 와 calibration/probe/initial-prior 한계가 있어 핵심 물리·수학·통계 타당성 전체를 PASS 로 승격할 수 없다.

현재 결과는 **명시적 한계가 있는 diagnostic local-tracking simulation**으로 보존한다. 강한 논문 claim 은 위의 보완 검증이 끝날 때까지 보류해야 한다. 감사는 여기서 종료한다. Source 수정, tuning, threshold 변경, 새 production campaign 또는 다음 실험 단계는 시작하지 않았다.

### 감사 산출물

- 이 보고서: `INDEPENDENT_SCIENTIFIC_AUDIT_KO.md`.
- `EVIDENCE_INDEX.md`: 실제 접근 가능한 코드·원본 evidence 의 파일 링크.
- `REVISION_FREEZE.json`: 고정 revision.
- `provenance_validation.json` / `audit_provenance.py`: 원본 source/hash/manifest 의 읽기 전용 대조.
- `independent_numerical_evidence.json`: 독립 계산 결과와 범위.
- `pytest.log`: 기존 85 개 tests PASS.
- `selected_raw/`: 선택된 원본 H/LUT/frequency axis 의 감사 사본.

코드 locator 의 공통 root 는 이 폴더의 `checkout/`이다. 독립 계산의 실행 출력은 감사 lane 의 tool 기록에 보존되며 원자료 경로·계산식·검사 범위를 위에 기재했다. CSV 요약 검사 또는 saved-H replay 를 RF 자체 재현으로 표현하지 않는다.
