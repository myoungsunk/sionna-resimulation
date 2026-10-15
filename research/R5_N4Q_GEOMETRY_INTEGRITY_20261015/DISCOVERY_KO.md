# N4-Q 계획 기반 구현 사전 파악 (2026-10-15)

상태: **DISCOVERY_COMPLETE / IMPLEMENTATION_NOT_STARTED / EXPERIMENT_NOT_RUN**.

사용자의 현재 지시는 “우선 파악부터”다. 첨부 계획서의 “이번 작업에서는 코드 수정·실험 실행을 하지 않음”은 해당 문서 작성 당시 상태로 읽으며, 향후 구현을 영구 금지하는 사용자 지시로 간주하지 않는다. 이번 턴은 현재 사용자 stop gate에 따라 파악 및 브랜치 문서 업로드까지다. 신규 Q0–Q7 검증 실행이나 결과 PASS는 없다.

## 1. 첨부 원본과 브랜치 계보

- 입력 파일: N4_Heading_Observability_RF_Integrity_Verification_Plan_KO_20261015.md, 212줄, 21,649 bytes.
- 원 파일 SHA256: 9535810cc63fde934acdc44984153d14100f8381bc7801f481d43c48d58cf422.
- 사용자 제공 계획서는 PLAN_KO.md에 보존한다.
- N4-C 기준: [research/r5-n4c-joint-sr-recursive-20261015](https://github.com/myoungsunk/sionna-resimulation/blob/4a22ee5ca52d9fb82ec4bb611ebc45260a09d51f/research/R5_N4C_REPORT_20261015/RESULTS_KO.md), SHA 4a22ee5ca52d9fb82ec4bb611ebc45260a09d51f.
- POL-V1 참조: [research/r5-n4b-polar-geometry-20261015](https://github.com/myoungsunk/sionna-resimulation/blob/63ab1835dbec33bfe8e0726d7bf271960ca4317f/research/R5_N4B_POL_V1_20261015/RESULTS_KO.md), SHA 63ab1835dbec33bfe8e0726d7bf271960ca4317f.
- 두 브랜치는 공통 조상 1338ccc929272bad75e456e96de61d6ed212fb13에서 분기했다. N4-C를 base로 POL 쪽을 비교하면 POL은 8커밋 ahead, 6커밋 behind다. N4-C tree에는 POL-V1 디렉터리가 없고 POL tree에는 N4-C 디렉터리가 없다.
- 따라서 새 N4-Q 브랜치는 N4-C의 재귀·평균/공분산 대조군을 보존하는 base로 시작한다. POL-V1 기하 로직은 위 별도 SHA에 묶어 참조한다. 파악 단계에서 코드 병합은 하지 않았다.
- 조회한 두 tree는 truncated=false다. 두 tree와 조회된 브랜치 목록에서는 신규 N4-Q 전용 코드 및 Q0–Q3 계약 산출물을 찾지 못했다. 저장소 전체 모든 파일 내용까지 검색한 결과라는 뜻은 아니다.

## 2. 실제 존재하는 재사용 구현

| 기존 구현 | 확인한 함수/역할 | N4-Q에서 재사용 가능한 범위 |
|---|---|---|
| [p3_rf_adapter4.py](https://github.com/myoungsunk/sionna-resimulation/blob/4a22ee5ca52d9fb82ec4bb611ebc45260a09d51f/research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py) | FrozenLut 보간, model(), LoS h/H, 원 R0 | Q0 각도/포트/LUT/Jacobian 기준, Q1 실제 LUT 직접 평가 |
| [n4b_pol_geometry.py](https://github.com/myoungsunk/sionna-resimulation/blob/63ab1835dbec33bfe8e0726d7bf271960ca4317f/research/R5_N4B_POL_V1_20261015/n4b_pol_geometry.py#L145) | physical_features(), s/포트비/균형도/Hψ, 조건부 정보량 | Q1 기하 계산 출발점; I_geom과 실제 prior I_op 명칭/입력을 분리해야 함 |
| 같은 POL 코드 | prior_stress(), exact archived truth/time/pose binding, original J4 pre-RF prior | Q0 prior 데이터 연결 및 Q4 참조 스트레스 보존 |
| [n4b_rf_errors.py](https://github.com/myoungsunk/sionna-resimulation/blob/4a22ee5ca52d9fb82ec4bb611ebc45260a09d51f/research/R5_N4B_20261015/n4b_rf_errors.py#L247) | create_dataset(), 원 관측 parity, e_r/e_s, fp_tap/strong_port, centered covariance/NLL, Full–LoS/시간상관 분석 | Q2 RF 관측기와 잔차 모델 재사용. 기존 요약 CSV만으로 새 packet 단위 분해가 완료된 것은 아님 |
| [n4c_joint_sr4.py](https://github.com/myoungsunk/sionna-resimulation/blob/4a22ee5ca52d9fb82ec4bb611ebc45260a09d51f/research/R5_N4C_20261015/n4c_joint_sr4.py) | POWER_JOINT, joint_prior_nis(), correlated_sr4(), recurse(), score() | Q6의 고정 대조군. Q0–Q3에서는 새 필터 구현/실행 대상이 아님 |

POL physical_features()의 기존 레퍼런스는 diag(0.1²,0.1²,rad(5)²), R_s,ref=0.0081이다. P를 주면 position–heading cross covariance를 포함한 Schur 조건부 정보량을 계산한다. 따라서 모든 수학을 처음부터 새로 구현할 필요는 없다. 단, 기존 Ipsi_nominal 필드가 P 입력에 따라 실제 prior 정보량도 담을 수 있으므로 새 계약에서는 고정 기준의 I_geom과 실제 prior I_op을 명시적으로 분리해야 한다.

## 3. 단계별 충족 여부

| 단계 | 기존 충족 부분 | 새로 필요한 부분 |
|---|---|---|
| Q0 | 원 코드의 asset/source SHA·parity 검증과 성공 workflow, frozen LUT/observer | N4-Q 기준 입력/코드 manifest; seam/knot/port/angle 회귀 검사; 기존 숫자 재현; 허용오차 예외 분리 |
| Q1 | oracle/실제 prior LoS s, B, Hψ, 국소 정보량 | ±2/5/10° 직접 LUT 차이, 기울기 대비 곡률/비대칭, heading profile 다중해/평탄영역, grid/seam flag, 정보량–판별력 검증 |
| Q2 | range/s residual, native Full/LoS, FP branch/tap, μ·중심공분산·상관·시간진단 | packet별 e_MP/e_LUT/e_pose와 innovation 항등식; RF Integrity와 기하 라벨 분리; LoS/null controls와 holdout score 검증 |
| Q3 | Hψ/Balance 층화 분석 | 독립된 두 축의 4분면, train/validation 고정 threshold, 조건 매칭/표본 충분성, 혼동/false alarm/harm 비교 및 사례 출력 |
| Q4–Q5 | J4 prior stress 및 여러 RF 잔차 모델 | 실제 prior 학습/불확실도 전파·OOD·분리 모델과 같은 packet likelihood 논리 |
| Q6 | 기존 Joint4/SR4·POWER_JOINT 재귀 코드/원 결과 | 새 분리 모델을 적용한 정확도·bias·XY·NEES/coverage 검증. 앞 단계 근거 없이는 진행하지 않음 |
| Q7 | 동일 복도의 R2/R4/R5 데이터 | 독립 장면/새 Full–LoS 회전·곡선 RF 및 noise realization. 이번 조회에서 확보 확인 안 됨 |

“기하와 오염을 분리 정의”하는 것이 두 변수가 통계적으로 독립이라는 뜻은 아니다. 기하가 FP/CIR와 공변할 수 있으므로 stratification/matching과 두 축의 상호작용을 함께 보고해야 한다.

## 4. 기존 결과의 확인 수준

GitHub에서 다음 실행 메타데이터가 completed/success임을 현재 조회했다.

| 기존 실행 | 실행 커밋 |
|---|---|
| [POL-V1 38717297007](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38717297007) | 003b97bf4ba70b7bfa2669ce2c081517a24d58d5 |
| [POL 검증 38717840304](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38717840304) | 5e1dd5cb1dd2382ad1ab7ce44a441a83b08a4502 |
| [N4-C 38714046562](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38714046562) | 7ae79e2372efaef114670f88e5e9be51cb8d3442 |
| [N4-C 검증 38715157425](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38715157425) | 0cbd15606c3b0051f3b0ee266cba86dbc5e34f61 |

Mount0/45 |Hψ| 중앙값 0.51568/1.63864, nominal Iψ 32.13/318.48, M45 oracle→실제 prior joint95 87.74%→79.67%(B0)/80.18%(L2)는 POL 결과 문서에 있다. POWER_JOINT 16 Full 조건의 4지표 비악화/개선도 N4-C 결과 문서에 있다. **이번 턴은 그 숫자의 새 재현 실행이 아니다.**

입력 ZIP manifest 상 식별자는 RF 11782748118, R2 11940333419, N4B 11960766768이다. 관련 원본 ZIP SHA는 기존 코드/워크플로에 고정돼 있다. 이번에 바이너리를 내려받아 fresh SHA 검증하지 않았으며, artifact metadata 직접 조회도 정상 결과를 확보하지 못했다. 따라서 현재 다운로드 가능성/CRC/실제 byte hash는 Q0에서 확인해야 할 항목으로 남긴다. 만료/소실로 단정하지 않는다.

## 5. 구현에 앞서 고정할 사항

1. **평가 모집단 구분:** 9,519 Full 관측의 RF/기하 bank, R2 재귀 979시점(성능은 t≥30s 829시점)을 구분한다. POL prior 전달 검사는 실제 코드상 979시점이다. 기존 87.74%→79.67%를 829시점 성능값으로 옮겨 적지 않는다.
2. **선행 감사의 2개 정정 반영:** B0 harm은 978시점 진단과 공통 829시점 지표를 분리하고, N3 fold 가중평균 AUROC와 pooled AUROC 명칭을 구분한다. 기존 결과를 덮어쓰지 않는다.
3. **label 및 gate 사전 설정:** I_geom 기준 prior·Rs를 고정하고, Q_geom/MP 각각의 high/low threshold, validation split, 최소 독립 location/block 수와 허용오차를 config에 수치로 기록한다. 첨부는 원칙을 주지만 모든 수치까지 정한 실행 명세는 아니다.
4. **평탄/모호/경계 처리:** |Hψ|가 작을 때 1/Hψ로 heading을 역산하지 않는다. ambiguity와 knot/seam을 별도 상태로 보존한다. 실제 LUT yaw 재평가는 Geometry 자료이며 새로운 Full RF 관측을 생성한 것이 아니다.
5. **oracle 구분:** e_MP는 paired native 관측에서 오프라인 계산하고 e_LUT/e_pose 및 oracle harm에는 GT를 명시한다. 온라인 입력에는 native LoS나 GT를 넣지 않는다. Q2/Q3의 원인분해용 평가 prior와 Q4의 실제 불확실도 모델은 구별한다.
6. **M45/LoS/OOD 한계:** R4/R5 학습에 Mount45가 없다. POWER_JOINT의 LoS 조건부 inference도 이전 N4-C에서 미실행이다. 두 상태를 성공으로 승격하지 않는다.
7. **단계 경계:** 첫 구현 범위는 Q0–Q3용 분석/검증 모듈과 계약 산출물이다. 구현 후에도 Q0 감사/고정이 먼저이며, 실패·입력 부족이면 해당 상태를 기록한다. Q4–Q7로 자동 확대하지 않는다.

## 6. 이번 변경과 다음 작업 경계

이번 업로드: 이 사전 파악 문서, 사용자 제공 계획서. 기존 소스/입력/결과/워크플로 변경·삭제·이동 없음. 문서용 commit에 [skip ci]를 사용하며 신규 실험을 dispatch하지 않는다.

이번 검사: 첨부 212줄/파일 SHA, 두 branch head/tree 및 공통 조상 비교, 핵심 함수와 결과 문서 검토, 4개 기존 workflow 성공 상태 확인. 구현을 하지 않았으므로 신규 코드 단위검사나 수치 실험은 실행하지 않았다.

다음 구현의 시작점은 이 branch의 N4-Q 패키지다. Q0–Q3에 필요한 순수 LUT/정보량 계산·packet 오차분해·4분면 라벨/집계와 사전 고정 설정 및 표적 검사를 추가하고, 먼저 Q0 증거를 확보하는 범위다. **현재 파악 단계는 여기서 종료한다.**
