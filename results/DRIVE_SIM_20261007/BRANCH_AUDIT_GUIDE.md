# 브랜치 감사 안내 — `claude/cool-dijkstra-hnznhm` (DRIVE_SIM_20261007)

감사 기준 커밋: 이 문서를 포함한 브랜치 HEAD (직전 코드/증거 커밋 `13caea1`, A14). 작성일 2026-10-08.
이 문서는 **어디를 보면 되는지**와 **무엇을 주장하고 무엇을 주장하지 않는지**를 정리한 안내서이며, 새 증거가 아니다. 수치의 근거는 각 항목에 적은 원본 파일이다.

## 1. 한 줄 요약

복도 주행 시뮬레이션: Sionna RT 2.0.1이 만든 pose별 RF 진실 → 두 LP(±45°) 포트의 first-path 전력비 `s=(P1−P2)/(P1+P2)` 관측 → 자이로·휠오도·UWB 거리·`s`를 LoS-only LUT 측정모델로 융합하는 EKF 계열. 프로브 = 제자리 ±45° 회전. **시뮬레이션 전용**이며 하드웨어 검증이 아니다.

## 2. 브랜치 구성

- 작업 브랜치는 이것 하나다. 측정 생성기 `scripts/corridor_sionna_run.py`는 `claude/determined-turing-vxge0c`의 `c13797a`를 merge(`84094a4`, rebase 아님)로 가져왔다. 그 브랜치와 `main`에는 푸시하지 않았다. PR 없음.
- 커밋 저자 두 종류: `Claude`(코드·문서·분석), `myoungsunk`(사용자가 Snowball에서 실행해 푸시한 결과·재검사). 변경 규모(Claude 코드/스크립트/테스트): 약 88개 파일, +9.5k줄.
- AGENTS.md가 언급하는 `scripts/00_inventory.py` 등은 이 저장소에 존재하지 않아 실행하지 않았다. 대신 pytest와 아래 게이트를 사용했다.

## 3. 디렉터리 지도

| 위치 | 내용 |
|---|---|
| `src/qclean_uwb/drivesim/` | config/manifest, trajectory, routes, pattern_apply(방법 B), rf_store, paths(G3), observation(first-path 체인), hs_lut, sensors, filters(EKF/IEKF/UKF/GSF), experiment, analysis |
| `src/qclean_uwb/scenarios/corridor.py` 등 | 복도 설정(기존) |
| `scripts/drive_sim/` | 단계별 CLI (trajectories, rf_b_trace/apply, rf_a_runner, parity_gate, path_continuity, build_hs_lut, run_(route_)experiments, analyze_*, 그림, 탐색 비교) + `run_rf_snowball.sh` |
| `tests/test_drivesim_*.py`, `test_fp_single_tx.py`, `test_path_continuity_script.py` | 단위 테스트 (현재 72 passed, 32 s) |
| `results/DRIVE_SIM_20261007/PLAN.md`, `RUN_SNOWBALL.md` | 계획, Snowball 실행법 |
| `S0/PREREG.json`, `S0/PREREG_AMENDMENTS.md` | **사전 등록 임계값과 수정 기록 A1–A14** (감사 시작점) |
| `S0/REPORT_S0.md` | S0 환경·bank·LoS 재현 보고 |
| `S1/` | 진실 궤적, RF pose 목록, A 방법 과제 목록 |
| `DEV_RESULTS/` | 로컬 개발 증거 (parity, G3, LUT 불일치, SNR 보정, fp-vs-rx, 각도모델 소거) |
| `SNOWBALL_RUNS/01a11582/` | R1 Snowball 결과(snapshot, B 재시작, final) |
| `SNOWBALL_ROUTE_RUNS/01a11669/` | R2/R4/R5 결과(snapshot, final, **`g3_recheck_20261008/`**) |
| `FIGURES/` | `route_overview.png`, `routes_anchors_overview.png` + manifest |
| `DEV_LOCAL/` | git 무시(로컬 개발 산출물; 감사 대상 아님) |

## 4. 실험 구성

- **공간:** 기존 복도 20 × 2.4 × 2.7 m. 로봇 안테나 z=0.45 m, 앵커 z=2.65 m(천장 2.7 m에서 5 cm 아래, `CorridorSetup.anchor_standoff_m`) 보어사이트 하향, 레버암 0.
- **경로:** R1 직진 왕복(y0=0/0.35), R2 직사각 루프, R4 지그재그(±0.45 m), R5 서펜타인. (R3는 R1과 동일해 제외 — 사용자 결정.)
- **앵커:** A(x=4,y=0), B(x=10,y=0). 각각 독립 단일 앵커 시스템(융합 없음).
- **행렬:** 경로 × 앵커 × 장착{0°,45°} × drift{low,mid,high} × SNR{30,10 dB} × seed 0–49. R1 18,000 run, route 54,000 run, 실패 0.
- **프로브:** P0(없음), P1 T=10/20/60 s(주행 시간 기준, 1회 36 샘플=7.2 s).
- **필터 베이스라인:** odom_imu, gyro_only, range, range_s_P0/_noturn/_P1_T*, inverse_heading_P0.

## 5. 감사 순서 제안

1. **`S0/PREREG.json` + `PREREG_AMENDMENTS.md`**: 임계값이 사전에 고정됐는지, 이후 변경이 모두 수정 기록으로 남았는지(임계값을 조용히 바꾼 곳이 없는지). 각 A항목은 "결과를 보기 전/후" 시점을 명시했다.
2. **RF 진실의 동등성(방법 A vs B):** `DEV_RESULTS/PARITY_REPORT.json`, Snowball `PARITY_REPORT`. 코드는 `pattern_apply.py`, `scripts/drive_sim/rf_b_*.py`, `parity_gate.py`.
3. **경로 연속성 G3:** `scripts/drive_sim/path_continuity.py`, `src/qclean_uwb/drivesim/paths.py`, 증거는 `SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/`와 `SNOWBALL_RUNS/.../G3*`.
4. **관측 체인:** `observation.py`(Hann, 1028 zero-pad, IFFT, 30 % 리딩엣지, "TX 열 2-RX 최강" 단일 TX 규칙) + `tests/test_fp_single_tx.py`.
5. **LUT·필터:** `hs_lut.py`, `filters.py`, `sensors.py`, `experiment.py`; LUT 게이트 L1/L2는 `DEV_RESULTS/`, A6.
6. **통계·가설:** `analysis.py`, `scripts/drive_sim/analyze_*.py`, 결과 `…/ANALYSIS/`. 독립 재계산(pandas)으로 ANALYSIS 표와 일치함을 확인했다.

## 6. 게이트 현황 (요약, 정확한 수치는 원본 파일)

| 게이트 | 상태 | 비고 |
|---|---|---|
| G1 재현성 | 통과 (threads=1 비트 동일) | threads=4는 3e-6 차이 → G1은 threads=1로 판정, 임계값 불변 (A1) |
| G2/G2'/G4 방법 B 패리티 | 통과 (Snowball: 817+18 pose, H 오차 max 9.6e-5, \|Δs\| max 7.9e-5, FP 인덱스 100 %) | 앵커 B도 통과 (\|Δs\| max 1.5e-5, A10/A10c) |
| **G3 경로 연속성** | **엄격(5e-14 s) 실패**: R1 y0=0 및 route 6조합 전부. **완화(2e-13 s) 통과** | 완화는 사용자 명시 승인(R1 B 재시작, routes A14). 사전 등록 임계값은 수정하지 않음 |
| L1/L2 LUT 게이트 | **FAIL, 유지** | 결과는 진단용으로만 해석 |
| NEES(pose, 기대값 3) | 과신: 독립 감사 기준 P0 평균 약 44(≈14.6배), routes P0 평균 R2/R4/R5 = 73.6/13.5/45.5. 이전 "20–40배" 표현은 부정확 | |
| scientific_PASS | **false** | |

## 7. 알려진 결함·정정 이력 (감사 시 우선 확인)

- **G3 공허 통과(A12):** 내가 만든 `path_continuity.py`가 route의 `drive` phase를 세지 않아 6개 G3가 `stations: 0`으로 "통과"했다. 수정(`c92da48`: drive phase 포함, 0개면 `NO_STATIONS_FOUND`로 중단, 테스트 추가). 사용자가 수정본으로 재검사(5,630 위치 전수, 누락 0) → 위 6절의 결과. **이전 통과 주장은 무효.**
- **시간 순서:** route S6는 *무효한* 사전 G3 이후에 실행됐고, 유효한 G3는 S6 종료 후에 이뤄졌다. 사전 게이트 순서가 적절했다고 주장하지 않는다. H 12개·S6 37개 파일의 해시가 재검사 전후 동일함은 확인됐으나(`UNCHANGED_H_S6_VERIFICATION.json`) 이는 파일 무결성이지 물리 정확성의 증명이 아니다.
- **완화 G3의 한계(A8/A14):** R4/R5에서 서로 다른 이미지 지연 간 최소 간격(≈1.0e-13 s)이 완화 허용오차(2e-13 s)보다 작다. 경로 *집합* 연속성에는 무해하나 경로별 라벨 유지의 증거는 아니다.
- **앵커 B:** 솔버가 대역 안에서 경로를 떨어뜨림 → union 참조 + 이분 컷 + 구간 보간(A10–A10c). 사전 등록된 screen은 보고용 플래그로 강등(A10b).
- **극점 퇴화(A3):** 앵커 수직축 바로 위에서 방법 B 부정확 → 클리어런스 가드.
- **σ_mismatch 보정:** 평가한 경로 자체에서 맞춤(R1 0.18, routes 0.161) → 낙관 편향 가능.
- **센서 파라미터는 placeholder.**

## 8. 가설과 결과 위치 (요지만; 판정은 ANALYSIS 원본)

H1(range+s가 odom+IMU/gyro_only보다 우수), H2(`s`를 측정으로 쓰는 것이 역산 heading보다 우수), H3(장착 45° vs 0°), H4(프로브 주기·wrong-branch 상한), H5(경로별 장착 방향 예측), H6(루프 폐합/변위 오차), H7(앵커 A vs B, 탐색).
- R1: H1 odom_imu 대비 19/24 · gyro_only 대비 18/24(2개 셀 악화), H2 24/24, H3 12/12 개선 (Snowball S6).
- routes: H1 odom_imu 대비 66/72 · gyro_only 대비 62/72(악화 4), H6 69/72 개선. odom_imu는 A5가 명시한 약한 baseline이므로 gyro_only 비교를 함께 인용해야 한다(F11). H2는 routes에서 18개 셀이 악화(독립 감사 집계). H5는 부분 일치(R4 0°↑ 6/6 일치, R2-B는 등록 예측과 반대 4/6). H7은 혼합. H2는 경로 의존(R4에서 역산이 직접 이상).
- 해석 한계: 프로브 이득은 P0가 나쁜 조건에 집중, 이미 좋은 조건에서는 오히려 악화 가능. 프로브 조건은 정지 회전만큼 경과 시간이 길고(R1 P0/T60/T20/T10 = 183/198/241/306 s) 관측 수와 정지 구간 갱신이 늘어난다. 보고된 개선은 기동 + 추가 관측 + 시간의 결합 효과이며 동일 시간 예산에서의 효율이나 정보만의 이득이 아니다(F09). drive-only/공통 지표 재분석은 아직 없다.

## 9. 탐색적(사전 등록 아님) 항목

- A11 fp 전력 vs rx 총전력 `s`: rx가 더 나쁨(불일치 0.301 vs 0.180).
- A13 각도 모델 소거: LUT vs 이상 곡선 `−cos2·yaw` (R1 개발 H 저장소, seed 0–9). 불일치 rms 0.180 vs 0.294, P0 heading RMSE 6.70° vs 18.49°(0°), 1.38° vs 8.04°(45°). route에는 미적용.

## 10. 주장 경계

- 시뮬레이션 결과이며 하드웨어 검증이 아니다. `s`는 q_clean이 아니다.
- 완화 G3 조건부 결과이며 scientific_PASS가 아니다. L1/L2 FAIL과 NEES 과대는 해소되지 않았다.
- 경로의 물리적 유일성/라벨 등가성은 주장하지 않는다.

## 11. 재현·보관 관련 주의

- **git만으로는 S6 전체를 재생할 수 없다.** `H_*.npy`, `*_trace.npz`, `*_sweep.npz`, `hs_lut*.npy`는 LFS 불가로 git에서 제외(`.gitignore`). Snowball 측 산출물의 SHA256이 `UNCHANGED_H_S6_VERIFICATION.json`/`TRANSFER_MANIFEST.json`에 있다. 재생성 절차는 `RUN_SNOWBALL.md`, `scripts/drive_sim/run_rf_snowball.sh`.
- 보호 경로(`data/raw/`, `results/frozen/`, `reports/release/` 등)는 수정하지 않았다. 모든 변경은 `results/DRIVE_SIM_20261007/`, `src/qclean_uwb/drivesim/`, `scripts/drive_sim/`, `tests/`에 한정된다.
- 로컬 검증: `pytest -q tests/test_drivesim_*.py tests/test_fp_single_tx.py tests/test_path_continuity_script.py` → 72 passed.

## 12. IMU / 오도메트리 / UWB 센서 설정과 출처 (코드: `src/qclean_uwb/drivesim/sensors.py`, 근거 문서: `PLAN.md` S5, `S0/PREREG.json`, A5/A7)

**모든 파라미터는 placeholder(assumption)이다. 특정 논문이나 실측에서 추출·보정한 값이 없다.** 문서와 코드에 명시된 출처는 아래 세 가지뿐이다.

| 항목 | 설정 | 출처 상태 |
|---|---|---|
| 샘플율/속도 | 5 Hz(dt 0.2 s), 0.2 m/s | 설계 선택 |
| 자이로 ARW | 0.015 °/√s (rate noise 0.015 dps/√Hz) | ICM-20648 데이터시트 값으로 기재. 이 세션에서 데이터시트를 직접 열어 확인하지 않았다. 실물 IC 확인 필요(구형 MPU9250과 다름)로 표시 |
| 자이로 bias 잔여 | low/mid/high = 0.01/0.05/0.2 dps (run마다 부호 무작위) | 가정 |
| 자이로 scale factor | 0.5/1.0/1.5 % | 가정 |
| 휠 직경비 오차 E_d | 0.2/0.5/1.0 % | 가정 |
| 휠베이스 오차 E_b | 0.5/0.75/1.0 % | 가정 |
| 로봇 기하 | 휠베이스 0.287 m, 바퀴 반지름 0.033 m | TurtleBot3 Waffle Pi 패키지 값으로 기재, 실물 확인 필요 |
| 오도 비계통 잡음 | var(ds)=2e-5·\|ds\|, var(dθ)=1e-4·\|dθ\|+1e-5·\|ds\| | "Thrun형" 가정 |
| 회전 slip | 회전 샘플당 1 %, Student-t(3)×0.5° | 가정(설계 선택) |
| UWB 거리 추가 잡음 | σ_r = 0.05 m (sweep 0.05/0.10) | 가정 |

**참고한 개념(인용 아님).** 코드 주석의 "Thrun-style non-systematic noise"는 Thrun·Burgard·Fox, *Probabilistic Robotics*의 오도메트리 모션 모델(이동량에 비례하는 잡음) 개념을 따른 것이고, α1–α4 파라미터화나 그 책의 값을 쓰지는 않았다. 직경비 E_d / 휠베이스 E_b라는 계통 오차 구분은 Borenstein & Feng의 UMBmark 계통 오차 정의와 같은 개념이지만, 코드·계획서에 인용이 없고 값도 그 논문에서 가져오지 않았다. 이 두 문헌과의 대응은 작성자(Claude)의 설계 기억에 의한 것이며, 감사 시 인용 정확성을 별도로 확인해야 한다.

**결과 해석에 영향을 주는 점.**
- 필터는 잡음 *구조*(ARW, k_s, k_θ, k_sθ, 거리 σ)를 생성기와 같은 값으로 알고 있다(drift 실현값만 모른다). 실제 센서에서는 이 일치가 없으므로 필터에 유리한 설정이다.
- 필터의 drift prior(σ_b 0.12 dps, σ_SF 1.04 %, σ_ε 0.64 %)는 위 3단계 drift 수준의 RMS에서 정했다(A5). 생성 분포와 prior가 일치한다.
- 실제 자이로의 bias 불안정성(Allan 분석), 온도 의존성, 비선형성, 바퀴-지면 슬립의 직진 구간 발생, 가속도계는 모델에 없다.
- 따라서 H1(range+s가 odom+IMU보다 우수)의 효과 크기는 이 센서 설정에 종속적이며, 특정 하드웨어에 대한 예측이 아니다. drift 3수준 × SNR 2수준은 민감도 범위이지 실측 대표값이 아니다.

## 13. 독립 감사(`INDEPENDENT_AUDIT_20261008/`, 사용자 작성, revision 155bf5a)와의 관계 — 이 안내서 정정

- 앵커 높이는 2.7 m가 아니라 **2.65 m**(천장 − `anchor_standoff_m` 0.05)이다. 필터와 RF 생성은 2.65를 쓰므로 계산에는 문제가 없고, 이 안내서·그림 제목·PLAN의 "2.7 m 앵커" 표기가 틀렸다(수정함).
- NEES: "20–40배"는 부정확했다. 감사 수치로 교체했다(위 6절).
- 감사가 지적한 코드 결함 **GSF 공분산 collapse가 PSD를 깨뜨릴 수 있음**(반례 최소 고유값 −0.245)은 이 브랜치에서 아직 수정하지 않았다. 1차 EKF 결과에는 영향이 없다고 감사는 판단했다.
- 감사의 최종 판정은 `BOUNDED_CORRECTION_OR_VALIDATION_REQUIRED`, `scientific_PASS=false`. 이 안내서의 게이트·한계 서술과 모순되지 않는다. 감사 문서가 우선한다.

## 14. 독립 감사 이후 정정(A15)

`S0/PREREG_AMENDMENTS.md` A15에 기록. 요지: GSF 분할 규칙 PSD 수정(+회귀 테스트), G3 보고서가 모든 set change와 엄격 기준 미매칭 station을 저장, parity 게이트가 누락/비정상 위치를 실패로 처리, 앵커 z=2.65·R2 회전 3개·NEES·H1 이중 baseline·프로브 교란·A14 승인 시점 문구 정정. 저장된 결과와 임계값은 바뀌지 않았고 수정 코드는 이후 실행에만 적용된다. 이전 GSF 결과는 옛 규칙으로 계산된 값이다(R1 개발 표본 120회 reseed 중 비PSD 0건, 운영 규모 영향은 UNKNOWN). 로컬 검증: drivesim·G3·parity 관련 pytest 96개 통과(`shapely`가 없어 전체 `tests/`는 이 환경에서 수집되지 않음).

## 15. A16 진단(F09/F10 일부, CPU 전용, 결과는 `DEV_RESULTS/PROBE_FAIRNESS_R1.*`, `OBSERVABILITY_A16.json`)

- 프로브 공정성(R1 개발 H, 셀당 120쌍): 모든 스케줄에 공통인 주행 위치만으로 채점해도 전체 표본 지표와 차이가 ≤0.15°. 장착 0°에서 P0 6.70° → T10 1.75°(99 % 개선), 장착 45°에서는 ≈0이고 T10은 73 %에서 악화. 경과 시간이 8–67 % 늘고 동일 시간 대조는 없음. 경로(R2/R4/R5) 수치는 Snowball 재실행 필요(`RUN_SNOWBALL.md` §6).
- 관측성(64 조건): odom+IMU만으로는 x0, y0, ψ0 3개 방향 미관측, range만으로는 앵커 중심 회전 게이지 방향 미관측(고유값 0), range+s는 6개 모두 양수. 선형화 heading std 0.16–0.63°는 실제 RMSE의 1/2~1/26(중앙값 1/7)이라 필터 성능의 예측치가 아니다. 초기 heading 프로파일(1° 간격 1차원 단면)에서 Δψ0=0 외 극소 없음, 한계는 A16 결과 절에 명시.
