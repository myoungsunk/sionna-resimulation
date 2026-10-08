# 독립 감사에 대한 수정(대응) 보고서 — DRIVE_SIM_20261007

대상 감사: `INDEPENDENT_AUDIT_20261008/INDEPENDENT_SCIENTIFIC_AUDIT_KO.md` (고정 revision `155bf5a`, 판정 `BOUNDED_CORRECTION_OR_VALIDATION_REQUIRED`, `scientific_PASS=false`).
대응 범위: 브랜치 `claude/cool-dijkstra-hnznhm`의 `155bf5a..2baa37f` (본 보고서 작성 시점 HEAD). 작성: Claude(작성자측), 2026-10-08.

## 0. 한 줄 결론

감사의 판정과 claim boundary를 **그대로 수용**한다. 이번 대응으로 (a) 코드 결함 3건(GSF PSD, G3 보고 절단, parity 누락 통과)을 고쳤고, (b) 문서·표기 오류를 정정했으며, (c) 감사가 요구한 진단 4건(프로브 공정성, 관측성, 일관성 원인 분해, held-out σ)을 **R1 개발 H 저장소 범위에서** 수행했다. **BLOCKER 두 건(F01 측정모델 검증 실패, F02 공분산 불일치)은 해소되지 않았다.** 원인은 좁혔으나 고치지 못했다. 저장된 결과·임계값·판정은 어느 것도 바꾸지 않았고 `scientific_PASS`는 false로 유지한다.

## 1. 감사 지적별 대응

상태 약어: **FIXED** 코드/문서 수정 완료, **DOC** 문서 정정만, **DIAG** 원인 진단 수행(미해결), **PARTIAL** 일부만 수행, **OPEN** 미수행, **N/A** 수정 대상 아님.

| ID | 감사 지적(요약) | 대응 판단 | 조치와 증거 | 상태 |
|---|---|---|---|---|
| F01 BLOCKER | LUT 검증 실패(L1 max 0.0240>0.01, L2 max 0.0104>0.005); σ로 덮을 수 없음 | 동의 | 게이트 임계값·FAIL 기록 유지. 잔차 구조를 분해(A17 B): 잔차는 ρ₁ 0.90–0.96, κ≈14–21의 강한 자기상관. held-out 측정모델 검증과 FP 전환/멀티패스 영향 분해는 **미수행**. claim은 이미 "진단용"으로 하향 | **DIAG / OPEN** |
| F02 BLOCKER | pose NEES 약 44(기대 3), 공분산 과신 | 동의(표현 정정: 일괄 20–40배는 부정확, 평균 약 14.6배, 경로별 13.5–73.6) | A17 A: 모델 일치 합성 관측에서 NEES 0.9–1.5로 **필터 구조는 일관**, 실제 RF 잔차에서만 15–93. 백색 불일치(E2)로는 재현 안 됨 → 가장 유력한 원인 후보는 LUT-채널 잔차의 시간/기하 구조이며 **분리는 끝나지 않았다**(A17 정정 노트). A17 C: σ 재측정(V1)·분산 인플레이션(V2) 모두 사전 제안 기준(NEES≤6, 커버리지≥0.90) 불충족, σ 추가 튜닝 없음 | **DIAG** |
| F03 MAJOR | G3 공허 통과와 게이트 시점 | 동의 | 수정은 이미 `c92da48`(A12). 보고 문구: strict 실패 / relaxed(2e-13 s, 사용자 승인) 통과 / 이전 6건 무효 / S6 이후 사후 검사. A14·A15에 시점 UNKNOWN까지 명시. 사전 게이트 순서가 올바랐다는 주장 없음 | **DOC** |
| F04 MAJOR | delay 클래스 ≠ 물리 경로 동일성, `set_changes[:50]` 절단 | 동의 | 코드: 모든 set change와 엄격 기준 미매칭 station 저장(`path_continuity.py`, 회귀 테스트). **Snowball trace로 재실행하지 않았으므로** 전체 변경 원인 검토는 미수행 | **PARTIAL** |
| F05 MAJOR | 앵커 B production 최대 dropped amplitude(0.048/0.048/0.045) > parity 표본(0.035) | 동의 | 코드/문서 변경 없음. Snowball에서 표적 parity 필요(§4) | **OPEN** |
| F06 MAJOR | σ_mismatch를 평가 경로에서 보정 | 부분 수행 | A17: R1 lateral 0.35에서만 재측정(σ 0.2012) → held-out lateral 0.0에서 V0(0.18)과 사실상 동일. 즉 R1 범위에서는 in-sample 보정이 일관성 실패의 원인이 아님. **R2/R4/R5는 미수행**(H 저장소 필요) | **PARTIAL** |
| F07 MAJOR | 자이로 증분 재사용, 휠베이스 오차 미모델 | 부분 동의 | A17 A: 휠베이스 오차 제거(E3)·odom heading 갱신 제거(E4)로 NEES 불변 → 이 실행에서는 주원인 아님. 이차 효과와 교차공분산 수식 모델링은 **미수행**, 코드 변경 없음 | **DIAG** |
| F08 MAJOR | GSF collapse가 PSD를 깨뜨림(반례 −0.2452) | 동의(코드 확인) | `reseed` 재작성(교차공분산 포함 Schur 보수 분할), 반례·k∈{2,3,5,9,21}·상관 4종·heading floor 회귀 테스트. R1 개발 120회 reseed 중 옛 규칙 비PSD 0건. 저장된 GSF 행은 옛 규칙 값이며 재생성하지 않음 | **FIXED** |
| F09 MAJOR | 프로브 효과와 시간·관측 수 교란 | 부분 수행 | A16 A: 공통 주행 위치 지표 추가. R1 개발: 공통 지표와 전체 지표 차이 ≤0.15°, 장착 0° 이득 유지(T10 −4.77°, 99 % 개선), 45°는 ≈0/T10 73 % 악화. 경과 시간 +8–67 %, **동일 시간 대조 없음**, 경로는 Snowball 재실행 필요 | **PARTIAL** |
| F10 MAJOR | 국소 추적 vs 전역 관측성 | 부분 수행 | A16 B: 실제 LUT 6-state 조건화(64 조건), 초기 heading 1° 단면. odom만 3방향, range만 회전 게이지 방향 미관측, range+s 6방향 관측. 다중 초기 조건을 필터에 통과시킨 실험은 **미수행** | **PARTIAL** |
| F11 MAJOR | 가설 모순과 약한 기준선 | 동의 | 안내서·A15에 H1 이중 baseline(R1 19/24·18/24, routes 66/72·62/72), H2 routes 40/72 개선·18/72 악화, H5 R2-B 모순, H7 혼합 명시. 아래 §3 참조 | **DOC** |
| F12 MAJOR | 수신기·물리 표현 미검증 | 동의 | 변경 없음. 시뮬레이션 능력 ≠ 하드웨어 검증, Level 5 UNKNOWN 유지 | **N/A (OPEN)** |
| M01 | parity 게이트가 누락/비정상 위치에도 통과 가능 | 동의(코드 확인) | `coverage_complete` 검사 추가(누락·비정상 → 실패), 테스트. 저장 보고서는 둘 다 빈 목록이라 판정 불변 | **FIXED** |
| M02 | G4 원문 "G2와 동일"인데 node 코드는 G2′ 사용 | 동의 | 코드/문서 변경 없음. B 수치는 더 엄격한 G2도 만족(감사 확인). 후속 실행 전 G4 문구와 코드를 맞출 것 | **OPEN(경미)** |
| M03 | 앵커 z 2.7→2.65, R2 회전 3 vs 4, 양자화 분산·주파수 상수 | 부분 수행 | z(안내서·그림·PLAN), R2 회전 수, NEES 표현 정정. 양자화 분산/주파수 상수 차이는 **미확인** | **DOC(부분)** |
| M04 | A14 승인 시각 vs START_RECEIPT 불일치 | 동의 | A15에 "승인 시각은 이 저장소로 확정 불가, 승인이 S6·재검사에 앞섰다고 주장하지 않음" 기록 | **DOC** |
| I01 | 앵커 A/B는 독립 단일 앵커, `s`≠q_clean | 동의 | 문구 유지 | N/A |

## 2. 감사 최소 보정 계획(§10)의 이행 현황

| 우선순위 | 항목 | 이행 |
|---|---|---|
| P0 | Claim/provenance 정정 | **완료**(A15, 안내서 12–16절, 그림 정정). 숫자 재실행 없음 |
| P0 | G3 증거 완성 | 코드 완료(전체 변경·미매칭 station 저장), **Snowball 재실행·원인 검토 미완** |
| P0 | GSF 수학적 안정성 | **완료**(수정·반례 테스트). 영향 있는 GSF 행의 재생성 여부는 사용자 결정 |
| P1 | 공분산/모델 검증 | 원인 분해 완료(R1), 모델 변경·held-out 합격은 **미완** |
| P1 | 독립 보정 | R1 lateral 간 held-out만 수행. 경로 단위 held-out **미완** |
| P1 | 앵커 B coverage | **미수행** |
| P1 | 관측/LUT | 관측성 진단 완료. FP 전환·멀티패스 분해는 **미수행** |
| P1 | 프로브 공정성 | R1 완료. 경로·동일 시간 대조 **미완** |
| P1 | 관측성(전역) | 국소 조건화·단면 완료. 광역 초기 조건 **미완** |
| P2 | 물리 일반성, 하드웨어 | **미수행**(별도 범위) |

## 3. 감사 해석을 반영한 주장 정정(현재 사용할 표기)

- 가능: 한 복도·지정 FFD·placeholder 센서·좁은 초기 prior 아래에서 range+s의 heading RMSE가 odom+IMU보다 낮은 조건이 많았다(gyro_only 대비도 함께 인용, 악화 셀 포함).
- 조건부: 프로브 이득은 기동·추가 관측·추가 시간의 결합 효과. 장착 0°에서 R1 개발 데이터로는 재현되나, 45°에서는 이득이 없거나 악화.
- **H4는 프로브 필요성이나 최적성의 증거가 아니다**: 20° 기준으로 P0도 R1 24/24, routes 72/72에서 이미 충족하고, T60이 전부 선택됨(감사 6.1). `wrong_branch`는 `|오차|>20°`의 운영 지표이며 실제 역해 식별이 아니다.
- **H2는 routes에서 혼합**(40/72 개선, 18/72 악화), H5는 R4만 지지, H7은 탐색적.
- 금지 유지: 게이트 전체 PASS, 유효한 사전 G3, 경로 물리 동일성, 검증된 full-channel heading 측정, 신뢰할 수 있는 공분산/보호수준, 보편적 우월성, 하드웨어 유효성.

Claim level(감사 §9): Level 1 코드 타당성 PARTIAL(GSF PSD·G3 결함은 수정했으나 재감사 전) / Level 2 PARTIAL / Level 3 조건부 / Level 4·5 UNKNOWN. 변경 없음.

## 4. 남은 작업과 필요한 실행

1. **Snowball(CPU, RF 신규 없음):** `routes-continuity`를 A15 코드로 재실행해 전체 set change 목록과 `strict_unmatched_stations`를 확보하고 원인(어떤 이미지 클래스가 나타나고 사라지는지)을 검토한다.
2. **Snowball(CPU):** `RUN_SNOWBALL.md` §6의 경로 재실행 + `probe_fairness.py analyze`(공통 위치 지표), 이어서 경로 단위 held-out σ/일관성 평가(`consistency_diagnostics.py`를 경로용으로 확장하는 새 사전 등록 필요).
3. **Snowball(native RF, 제한적):** 앵커 B에서 production 최대 dropped-amplitude 위치(0.048/0.048/0.045)와 최소 yaw 조합에 대한 A/B 표적 parity(F05).
4. **설계 결정(사용자):** F01/F02를 풀 방향 — 측정모델 개선(L1/L2 경로) 또는 상관 오차 상태 도입. 둘 다 새 설계와 새 사전 등록 필요. 일관성 수용 기준값(NEES≤6, 커버리지≥0.90, 정확도 ≤1.25배)은 **어시스턴트 제안이며 사용자 승인 전**.
5. **결정(사용자):** 옛 규칙으로 계산된 GSF 행을 재생성할지, 사전 게이트 순서(F03)를 문서 차원에서 어떻게 확정할지.

## 5. AGENTS.md Done 정의에 따른 보고

1. **변경한 파일(코드):** `src/qclean_uwb/drivesim/filters.py`(GSF 분할, `s_var_inflation`), `experiment.py`(공통 구간·커버리지 열, 진단 훅), `scripts/drive_sim/path_continuity.py`, `parity_gate.py`, `plot_routes_anchors.py`.
   **추가한 스크립트:** `probe_fairness.py`, `observability_check.py`, `consistency_diagnostics.py`, `gsf_psd_incidence.py`.
   **테스트:** `test_drivesim_filters.py`, `test_drivesim_experiment.py`, `test_path_continuity_script.py`, 신규 `test_parity_gate_coverage.py`, `test_observability_check.py`.
   **문서:** `S0/PREREG_AMENDMENTS.md`(A15–A17), `BRANCH_AUDIT_GUIDE.md`(12–16절), `RUN_SNOWBALL.md`(§6), `PLAN.md`(앵커 z 한 줄), 본 보고서.
2. **이동한 파일:** 없음.
3. **손대지 않은 것:** `PREREG.json` 및 모든 사전 등록 임계값, 기존 A1–A14 본문, Snowball 결과(`SNOWBALL_RUNS/`, `SNOWBALL_ROUTE_RUNS/`)와 H/S6/ANALYSIS 파일, 감사 폴더 `INDEPENDENT_AUDIT_20261008/`, 보호 경로(`data/raw/`, `results/frozen/`, `reports/release/` 등).
4. **실행한 검증:** `pytest tests/test_drivesim_*.py tests/test_fp_single_tx.py tests/test_path_continuity_script.py tests/test_parity_gate_coverage.py tests/test_observability_check.py` → 99 passed. `shapely`가 없어 전체 `tests/`는 이 환경에서 수집되지 않았다(감사 쪽에서 85개 통과). AGENTS.md가 언급한 `scripts/00_inventory.py` 등은 이 저장소에 없다.
5. **생성한 산출물:** `DEV_RESULTS/` 의 `GSF_PSD_INCIDENCE.json`, `PROBE_FAIRNESS_R1.{csv,json}`, `OBSERVABILITY_A16.json`, `CONSISTENCY_CALIB.{csv,json}`, `CONSISTENCY_HELDOUT.{csv,json}`; `FIGURES/routes_anchors_overview.*`(앵커 z 정정). 모두 R1 개발 H 저장소 기반이며 증거 계층은 E3(개발).
6. **남은 위험:** F01·F02 미해소(공분산 신뢰 불가), 경로 단위 held-out 미수행, 앵커 B 최악 위치 미검증, G3 변경 원인 미검토, 이전 GSF 행은 옛 규칙 값, 일관성 수용 기준은 미승인 제안값, 개발 증거는 `DEV_LOCAL`(git 제외) 입력에 의존해 이 브랜치만으로 재생성 불가.
7. **다음 권장 명령:** Snowball에서 `bash scripts/drive_sim/run_rf_snowball.sh routes-continuity` (A15 코드), 이어서 `RUN_SNOWBALL.md` §6의 경로 재실행.

## 6. 이 보고서의 증거 수준

- **직접 확인한 감사 주장:** GSF 분할 결함(코드·반례 테스트 재현), parity 누락 통과(코드), `set_changes[:50]`(코드), 앵커 z 2.65(코드), R2 회전 3개(timeline).
- **감사를 신뢰하고 수용한 주장(재계산하지 않음):** 원본 Snowball 해시 대조, 5,630 trace 독립 G3 재계산, 72,000 run 통계 재계산, 선택 H 재실행, dropped-amplitude 최댓값, NEES 표, 가설별 개수(H2 40/72, H5 등).
- 이번 대응의 수치(A16/A17)는 모두 R1 개발 H 저장소와 LoS-only LUT 위의 **진단**이며 사전 등록된 가설 검정이나 route 결과가 아니다.
