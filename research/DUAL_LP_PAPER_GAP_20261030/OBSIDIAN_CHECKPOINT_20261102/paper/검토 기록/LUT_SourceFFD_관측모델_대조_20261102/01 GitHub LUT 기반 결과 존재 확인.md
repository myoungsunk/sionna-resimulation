# GitHub의 LUT 기반 대응 결과 확인 — 2026-11-02

질문 ID: `DLP-LUT-SOURCEFFD-GITHUB-EVIDENCE-20261102`. 역할: AUDITOR, 읽기 전용 근거 확인 및 자체 정리. 실행·다운로드 재채점·원고 수정 없음. 기존 동결 계약은 변경하지 않았다. 로컬 적용 지침은 이 폴더 `CONTRACT.json`에 해시가 기록된 COMMON_CONTRACT.md와 ROLE_AUDITOR.md다.

## 판정

**과거 LUT 기반 EKF·POWER 결과와 LUT→SourceFFD 비교표는 GitHub에 있다. 현재 Anchor B의 R2/R4/R5 × B0/L0/L1/L2 일반 EKF·MB_VAR 결과를 LUT로 교체한 완전 대응 실행본은 이번 검색에서 확인하지 못했다.** 이 부재 판정은 아래 검색 범위에 한정하며, 저장소의 모든 과거 commit과 artifact 내부를 전수 검색했다는 뜻이 아니다.

### A. 원 LUT의 DR/S/J/SR 실행 결과 — 존재

- [R2 Anchor A, mount 0/45°, B0/L0/L1/L2 결과](https://github.com/myoungsunk/sionna-resimulation/blob/dc9c422f1d7d23c69b1ae732433ad2c4147e90ec/research/EKF4_RANGE_S_STAGED_20261014/R2_MOUNT0_45_GYRO_BIAS_B0_L0_L1_L2_RESULTS_20261015_KO.md).
- 원 RF LoS/Full, DR3/DR4/S3/S4/J3/J4/SR3/SR4, one-step/recursive, 256 metrics rows. 979시점 중 t≥30 s의 829시점을 평가한다.
- `FrozenLut`와 원 R0 사용. Anchor A의 R2 결과이므로 현재 Anchor B 12조건과 구분해야 한다.
- [성공 실행 38664617622](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622), [결과 artifact 11940333419](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622/artifacts/11940333419).
- 실시간 API metadata에서 artifact `expired=false`, 23,284,709 bytes, SHA256 `ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399` 확인. 만료 시각은 2026-11-14T01:21:18Z다. 이번 작업에서 ZIP 내용을 다시 다운로드·채점하지는 않았다.

### B. LUT 기반 R0/POWER_JOINT 및 극점 수정 대조 — 존재

- [POLE_RECURSIVE 결과](https://github.com/myoungsunk/sionna-resimulation/blob/a33e5a923782300b61585f45e9874ee73394d9fe/research/POLE_RECURSIVE_20261016/RESULTS_KO.md).
- [실제 runner](https://github.com/myoungsunk/sionna-resimulation/blob/a33e5a923782300b61585f45e9874ee73394d9fe/research/POLE_RECURSIVE_20261016/pole_recursive.py)의 `setup()`과 `run()`은 FrozenLut를 생성하고 원본/극점 수정 표를 각각 사용한다.
- R2 Anchor A, mount 0/45°, 네 bias, J4/SR4. Full에서는 BASE_R0와 POWER_JOINT, LoS에서는 BASE_R0. 48개 원본/수정 paired 조합.
- 극점 수정은 원 0° 행만 바꾸는 별도 후보이며 원 LUT와 동일 방법으로 취급하면 안 된다. 이는 SourceFFD 실행도 아니다.
- [결과 artifact 12027528128](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38857292101/artifacts/12027528128). 실시간 metadata에서 `expired=false`, 3,195,453 bytes, SHA256 `6328e1f2555fe3adacb44e72774665bd50519111b734336082aa9cbe72fe140e` 확인. 만료 시각 2026-11-15T05:46:07Z.

### C. 과거 LUT 결과와 SourceFFD 결과의 비교표 — 존재

- [FFD source P0–P3 결과](https://github.com/myoungsunk/sionna-resimulation/blob/4b82e9801a1e065593fdd67a0f3ebd721ba29848/research/FFD_P0P3_20261016/RESULTS_KO.md), §4의 `Heading old`/`Heading source+refit`, XY, gyro RMSE 표.
- R2 Anchor A, mount 0/45° × 네 bias의 기존 POWER와 SourceFFD+재학습 비교다. 예: mount 0° B0 heading 1.773241→1.798910°, XY 0.162103→0.149970 m. L2 heading 1.991423→1.558988°, XY 0.191677→0.157194 m.
- 이는 관측함수와 learned mean/covariance를 함께 바꾼 비교다. 관측함수만 교체한 효과로 해석할 수 없다.
- 해당 GitHub 요약은 전체 P1/P2/P3 runner·256 trace·세부 CSV 정본이 별도 `FFD_SOURCE_P0P3_20261016.zip`에 있음을 명시한다. 요약 공개와 원시 결과 전부의 저장소 커밋은 구분한다.

### D. 현재 Anchor B 3경로·4 bias의 일반 EKF / MB_VAR를 LUT로 실행한 결과 — 미확인

- [reflect_model/common.py](https://github.com/myoungsunk/sionna-resimulation/blob/4ad94fe652d847592aa78ba017dd0a6a517652a1/research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/common.py)의 `base_model()`은 검증된 두 bank로 SourceFFD를 생성한다.
- MB_VAR 진단과 causal isolation은 이 경로를 재사용한다. [causal_isolation.py](https://github.com/myoungsunk/sionna-resimulation/blob/3af005b8491b5668c0989b82bc3cbc990cfcf8b7/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_causal_isolation_20261029/causal_isolation.py)도 `diag_mbvar`를 불러 `model.batch`를 사용한다.
- MB_VAR 보정, RF 입력, 센서·초기화·Q/R·gate를 유지하면서 관측함수만 LUT로 교체한 현재 12조건 실행본은 확인하지 못했다. 과거 POWER_JOINT는 현재 MB_VAR와 동일한 방법이 아니다.
- 앞서 확보한 Anchor B 8-arm 로컬/스노우볼 재생 기록은 별도 근거다. 이번 확인에서 그것의 GitHub 게시 여부를 확정하지 않았다.

## 검색 범위와 한계

GitHub connector로 실시간 공개 저장소를 조회했다. default branch 코드 검색 두 건은 결과가 없었으므로 이를 부재 근거로 삼지 않았다. 브랜치 목록은 100+100+13=213개를 확인하고 관련 브랜치를 선별했다. 아래 7개 commit의 recursive tree는 모두 `truncated=false`였다.

- main: `fd2f75781f24be1b6d70d81c0ac86cd61b4f585b`
- FFD source: `4b82e9801a1e065593fdd67a0f3ebd721ba29848`
- pole paired: `a33e5a923782300b61585f45e9874ee73394d9fe`
- pole systematic: `aa0f747728f6ec884d8ab38ade2e750edc0df335`
- DS state/info: `4ad94fe652d847592aa78ba017dd0a6a517652a1`
- MB_VAR causal: `3af005b8491b5668c0989b82bc3cbc990cfcf8b7`
- 후속 evidence: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`

R2 bias 결과 본문은 별도로 commit `dc9c422f1d7d23c69b1ae732433ad2c4147e90ec`에서 확인했다. 결과 서술, 실행 코드의 관측함수 선택, artifact 존재를 구분해 확인했다. GitHub 쓰기, workflow dispatch, 새 시뮬레이션은 수행하지 않았다.
