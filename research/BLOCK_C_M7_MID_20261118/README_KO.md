# BLOCK_C M7 원본 설정 — 근·중거리 횡방향 station 보강

질문 ID: `BLOCK-C-M7-MID-SWEEP-001`. 역할: IMPLEMENTER.

사용자 지정 범위는 기존 중앙선의 근·중거리 x 26개에 y=±0.30, ±0.45 m를 추가하여 생성·검증하고 GitHub에 업로드하는 것이다. 끝점 확장, x=1.0 및 0.15 m 격자 생성은 이번 범위에 포함하지 않는다.

## 동결 입력과 생성 범위

- BLOCK_C 원본 공간·재질·FFD, 앵커 B=(10,0,2.65) m, 수신기 높이 0.45 m, mount 0°.
- x=4.35+0.45i m, i=0..25: 4.35–15.60 m, 총 26개. 원본 중앙선 40개 x에서 이미 생성한 원거리 14개를 제외한 좌표다.
- 각 x에서 y(m): −0.45, −0.30, +0.30, +0.45. 총 104개 새 위치이며, 기존 중앙선 40위치 및 원거리 추가 56위치와 물리적 중복이 없어야 한다.
- yaw −180°부터 +170°까지 10° 간격 36개: 3,744 RF pose.
- 관측 표는 +180°를 포함하는 37행/위치, 총 3,848행. ±180°는 같은 RF pose_id를 참조한다. clean H이며 열잡음을 추가하지 않는다.
- RT 설정과 계산 코드는 기존 M7 원본 호환 실행을 유지한다. 전체 solver JSON 일치, refraction=true, 100,000 rays, max_depth=3, seed=20260924, 기본 17 node와 원본 적응형 추가 추적, 원본 H 합성을 사용한다. 유한 반사면 검사·직접파 계수 대체·경로 후처리 필터는 OFF다.
- 동결 Method B commit: `047cce2acb244ec2d7badc563345ccdd1f48613f`. 원본 소스·FFD·image·새 실행 코드와 입출력 해시를 계약 및 manifest에 기록한다.
- 기존에 검증한 `run_blockc_m7_sweep.py`와 계약의 위치·pose 수를 사용하는 `finish_blockc_m7_far_sweep.py`를 변경 없이 재사용한다. 새 host 스크립트는 좌표·범위와 실행 기록만 설정한다.

## 검사와 주장 범위

1. 26×4 위치의 완전성, 기존 자료와 중복 0건, 원거리 14개와 근·중거리 26개의 x 분할, pose 중복, ±180° 참조, 몸체 벽 여유 및 입력 SHA를 검사한다.
2. 원본 R2/R4/R5 각각 3 pose, 총 9 pose의 H가 원본과 정확히 같아야 본 생성을 시작한다.
3. 같은 trace에서 H_full, 직접파 기여 H_LoS, PATHS_NEAR 및 위치별 전체 raw trace를 저장한다. 새 H_full 전체를 같은 trace에 대한 원본 합성 함수 결과와 대조한다.
4. 병합 뒤 coverage·SHA·G4 직접파 모델(p90 |Δs|≤0.005)·G8 동일 trace 직렬화 기준을 유지해 검사한다.
5. 기존 데이터·FAIL 기록을 보존하고 G-T2·G-V 봉인 데이터를 읽거나 heading 오차를 계산하지 않는다. c₀ 추정·신뢰구간·공간 독립성은 이번 생성에서 검증하지 않는다.

완료 후 기존 데이터와 새 데이터의 좌표 합집합이 40개 x × 5개 y의 200위치인지 확인한다. 이는 파일 간 좌표 coverage 확인이며, 별도 통합 H 파일을 생성하는 작업은 아니다. 위 검사는 데이터 생성과 명시한 무결성 범위에 한정한다.

## 실행 결과

Snowball run ID: `BLOCK_C_M7_MID_20261118_x5z74dk2`.
실행 코드 commit: `3f85de60951ea0e9f3e8e24b3d5a9ee83b5e2cde`.
실행 시각: 2026-11-18 12:18:22–12:22:14 KST. 세부 UTC 시각은 원본 manifest에 보존한다.

- 생성 PASS: 추가 104위치, 3,744 RF pose, 3,848 관측 행. 위치·물리 pose 중복 및 기존 자료와의 위치 중복은 0건이다.
- 모든 위치에서 원본 적응형 추적으로 21 node를 사용했다. 본 생성 solver 호출은 2,184회, export용 추가 RT 호출은 0회다. 전체 raw trace 104개를 저장했다.
- 원본 R2/R4/R5 각각 3 pose의 복소 H 계수 9,252개가 정확히 일치했다. 별도 바이트 비교에서도 각 route의 SHA-256이 원본과 같았다. 이 9 pose 표본에 한정한 원본 대조다.
- 새 3,744 pose의 H_full은 같은 trace를 원본 H 합성 함수에 넣은 결과와 배열 값이 정확히 같았다.
- G4 PASS: 관측 3,848행 기준 p90 |Δs|=2.8396430007404666e-7, 최대=7.678169355318509e-7. 기존 p90 기준 0.005를 유지했다.
- G8 직렬화 PASS: 3,744 pose에서 최대 상대·절대 재합성 오차 0. PATHS_NEAR에는 7,632 경로 행을 저장했다.
- 원본 대조 44.34초, 본 생성 171.11초, 병합·검증 15.69초, 합계 231.14초(3분 51초). 기존 1순위 149.60초의 약 1.55배다. 코드 준비·복사·업로드 시간은 제외한다.
- results 폴더 저장량은 324,222,740 byte(324.22 MB)다. 입력·대조 출력·로그·자원 기록을 포함한 전송 대상은 328,909,538 byte다.
- 로컬 복사본 234개 파일의 SHA-256, 결과 파일 129개, 계약 입력 21개와 실행 코드 55개의 해시를 확인했다. RT 설정 파일은 기존 중앙선·원거리 실행과 바이트 단위로 같다.
- 세 실행의 좌표를 대조해 40개 x × 5개 y = 200위치, 중복 없는 7,200 RF pose와 관측 7,400행을 확인했다. 파일별 pose_id는 각 run 안에서 유효하므로 여러 실행을 함께 읽을 때에는 (run_id, pose_id)로 구분한다.
- 기존 데이터·FAIL 기록 및 G-T2·G-V 봉인을 유지했다. heading 오차·c₀ 추정은 계산하지 않았고, 끝점 확장이나 별도 촘촘한 격자는 생성하지 않았다.

[전체 실행 증거](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/)에 입력, 계약, 원본 대조, 로그, 자원 기록과 결과를 보관한다.

| 파일 | 내용 |
|---|---|
| [H_full.npy](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/results/H/BLOCKC_B/H_full.npy) | 다중경로 H, complex128, shape (3744,257,2,2) |
| [H_LoS.npy](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/results/H/BLOCKC_B/H_LoS.npy) | 같은 full trace의 직접파 기여 |
| [STATIONS.json](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/inputs/STATIONS.json) | 추가 104위치 |
| [rf_poses.json](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/inputs/rf_poses.json) | H 배열 행에 대응하는 pose_id·x·y·yaw |
| [M7_RT_CONFIG.json](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/inputs/M7_RT_CONFIG.json) | 원본 solver 전체 설정 및 node 정책 |
| [completion.json](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/results/completion.json) | 전체 검증과 결과 SHA-256 |
| [COORDINATE_COVERAGE.json](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/COORDINATE_COVERAGE.json) | 기존 중앙선·원거리·신규 근중거리의 좌표 합집합 검증 |
| [PATHS_NEAR.npz](../../artifacts/BLOCK_C_M7_MID_20261118_x5z74dk2/results/paths/BLOCKC_B/PATHS_NEAR.npz) | 같은 trace의 근접 지연 경로 계수·지연·상호작용 |
