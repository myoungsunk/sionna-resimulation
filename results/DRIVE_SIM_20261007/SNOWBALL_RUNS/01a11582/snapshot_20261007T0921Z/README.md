# Snowball DRIVE_SIM 실행 중간 결과

스냅샷: 2026-10-07 09:21 UTC. 업로드 시 09:29 UTC에도 method A RUNNING 확인.

실행 원본: `1b9cf190244f91d0097a82106a02ec1dd5f53220`.

- Preflight: 69 passed.
- Parity: all_passed=true. 개발 결과와 판정은 같지만 주요 오차 수치는 정확히 일치하지 않음. `PARITY_COMPARISON_SNOWBALL_DEV.json` 참조.
- G3 strict: y0 FAIL (unmatched 6), y0.35 PASS. B apply 실행 조건 미충족으로 method A 직접 RF 계산 중.
- L1 FAIL: max 0.023972114650869493, median 0.0005302414729959071. 기존 A6 한계 유지.
- L2 FAIL: 8 cases, max 0.010448905754996851 > 0.005.
- S3/SNR_CALIBRATION.json: MISSING (미생성).
- S6 results CSV, manifest JSON, ANALYSIS: MISSING (미생성).

S6는 요청된 고정 조건으로 실행 예정인 진단 결과이며 L1/L2 FAIL을 유지한다. 전체 완료 또는 과학적/production PASS를 주장하지 않는다. 입력과 임계값은 변경하지 않았다.

`GATE_SNAPSHOT_20261007T0921.zip`에 parity, 두 G3 JSON, 실제 trace receipt JSON, S4 JSON, 상태·출처·DEV 비교가 포함된다. trace NPZ와 원시 H는 포함하지 않는다. JSON 일부는 이 폴더에서도 직접 열람 가능하다.

검증된 ZIP SHA256: `1756f94ff053fdc7031beec221b6340e8d373e80621f2c89f1814f77aeafaa85`.
