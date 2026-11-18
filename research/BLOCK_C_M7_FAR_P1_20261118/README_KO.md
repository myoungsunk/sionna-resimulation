# BLOCK_C M7 원본 설정 — 원거리 추가 station 1순위

질문 ID: `BLOCK-C-M7-FAR-SWEEP-P1-001`. 역할: IMPLEMENTER.

사용자가 최종 지정한 범위는 1순위 생성 및 GitHub 업로드까지다. 2순위 0.15 m 격자와 왼쪽 x=1.0 확장은 보류한다.

## 동결 입력과 생성 범위

- BLOCK_C 원본 공간·재질·FFD, 앵커 B=(10,0,2.65) m, 수신기 높이 0.45 m, mount 0°.
- x(m): 1.20, 1.65, 2.10, 2.55, 3.00, 3.45, 3.90, 16.05, 16.50, 16.95, 17.40, 17.85, 18.30, 18.75.
- 각 x에서 y(m): −0.45, −0.30, +0.30, +0.45. 총 56개 새 위치.
- yaw −180°부터 +170°까지 10° 간격 36개: 2,016 RF pose.
- 관측 표는 +180°를 포함하는 37행/위치, 총 2,072행. ±180°는 같은 RF pose_id를 참조한다. clean H이며 열잡음을 추가하지 않는다.
- RT 설정과 계산 코드는 기존 M7 원본 호환 실행을 유지한다. 전체 solver JSON 일치, refraction=true, 100,000 rays, max_depth=3, seed=20260924, 기본 17 node와 원본 적응형 추가 추적, 원본 H 합성을 사용한다. 유한 반사면 검사·직접파 계수 대체·경로 후처리 필터는 OFF다.
- 동결 Method B commit: `047cce2acb244ec2d7badc563345ccdd1f48613f`. 소스·FFD·image·새 실행 코드와 입출력 해시를 계약과 manifest에 기록한다.

## 검사와 주장 범위

1. 14×4 위치의 완전성, pose 중복, ±180° 참조, 몸체 벽 여유와 입력 SHA를 검사한다.
2. 원본 R2/R4/R5 각각 3 pose, 총 9 pose의 H가 원본과 정확히 같아야 본 생성을 시작한다.
3. 동일 trace에서 H_full, 직접파 기여 H_LoS, PATHS_NEAR 및 station별 전체 raw trace를 저장한다. 모든 새 H_full을 원본 합성 함수의 결과와 대조한다.
4. 병합 뒤 coverage·SHA·G4 직접파 모델(p90 |Δs|≤0.005)·G8 동일 trace 직렬화 기준을 그대로 검사한다.
5. 기존 데이터·FAIL 기록을 보존하고, G-T2·G-V 봉인 데이터를 읽거나 heading 오차를 계산하지 않는다. c₀ 추정이나 신뢰구간·공간 독립성은 이번 생성에서 검증하지 않는다.

이 검사는 데이터 생성과 위 무결성 범위에 한정한다. 이전의 물리적/통계적 결론이나 전체 연구 gate 통과를 뜻하지 않는다.

## 실행 결과

Snowball run ID: `BLOCK_C_M7_FAR_P1_20261118_927et1yb`.
실행 코드 commit: `1a33be29913d14beee067f24ae508fd84248513a`.
2026-11-18 02:46:00–02:48:30 UTC에 실행했다.

- 생성 PASS: 추가 56위치, 2,016 RF pose, 2,072 관측 행. 위치·물리 pose 중복 0건이다.
- 모든 위치가 원본 적응형 추적으로 21 node를 사용했다. 본 생성 solver 호출은 1,176회, export용 추가 RT 호출은 0회다. 전체 raw trace 56개를 저장했다.
- 원본 R2/R4/R5 각각 3 pose의 H 계수 9,252개가 정확히 일치했다. 별도 바이트 비교에서도 각 route의 SHA-256이 원본과 같았다. 이 표본에 한정한 원본 대조다.
- 새 2,016 pose의 H_full은 동일 trace를 원본 H 합성 함수에 넣은 결과와 배열 값이 정확히 같았다.
- G4 PASS: 관측 2,072행 기준 p90 |Δs|=3.119685763691706e-7, 최대=8.395754392265253e-7. 기존 p90 기준 0.005를 유지했다.
- G8 직렬화 PASS: 2,016 pose의 최대 상대·절대 재합성 오차 0. PATHS_NEAR에 8,208 경로 행을 저장했다.
- 원본 대조 42.67초, 본 생성 94.25초, 병합·검증 12.67초, 합계 149.60초. 코드 준비·복사·업로드 시간은 제외한다.
- results 폴더 저장량 239,901,200 byte(239.90 MB). 입력·대조 출력·로그·자원 기록을 포함한 전송 대상은 243,776,878 byte다.
- 기존 데이터·FAIL 기록 및 G-T2·G-V 봉인을 유지했다. heading 오차·c₀ 추정은 계산하지 않았다. 2순위와 x=1.0 확장은 실행하지 않았다.

[실행 증거 전체](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/)에 입력, 계약, 원본 대조, 로그, 자원 기록과 결과를 보관한다.

| 파일 | 내용 |
|---|---|
| [H_full.npy](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/results/H/BLOCKC_B/H_full.npy) | 다중경로 H, complex128, shape (2016,257,2,2) |
| [H_LoS.npy](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/results/H/BLOCKC_B/H_LoS.npy) | 같은 full trace의 직접파 기여 |
| [STATIONS.json](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/inputs/STATIONS.json) | 추가 56위치 |
| [rf_poses.json](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/inputs/rf_poses.json) | H 배열 행에 대응하는 pose_id·x·y·yaw |
| [M7_RT_CONFIG.json](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/inputs/M7_RT_CONFIG.json) | 원본 solver 전체 설정과 node 정책 |
| [completion.json](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/results/completion.json) | 전체 검증과 결과 SHA-256 |
| [PATHS_NEAR.npz](../../artifacts/BLOCK_C_M7_FAR_P1_20261118_927et1yb/results/paths/BLOCKC_B/PATHS_NEAR.npz) | 동일 trace의 근접 지연 경로 계수·지연·상호작용 |
