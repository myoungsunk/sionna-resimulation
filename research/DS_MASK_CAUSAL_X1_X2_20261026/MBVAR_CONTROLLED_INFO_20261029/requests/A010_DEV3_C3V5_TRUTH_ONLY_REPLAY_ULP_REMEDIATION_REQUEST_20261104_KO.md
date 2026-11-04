# MBVAR-INFO-001 — DEV3 C3V5 TRUTH_ONLY 원본 바이트 재생 오류 시정 검증 의뢰서

**문서:** A010-C3-TRUTH-ULP-001 · **2026-11-04** · IMPLEMENTER_SELF_RUN / USER_AUTHORIZED_NONINDEPENDENT  
**현 상태:** C3V5 전체 1,080행 재현성 **미완료 / BLOCKED_SOURCE_TRUTH_REPLAY**, 독립 과학 PASS 아님.  
**S1 원본:** [Actions #41769652106](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41769652106), SHA 0bd5d706710f172ff6becb562eadd7573b5d3ffd, artifact ID 13296915471, outer SHA256 c5625668e1dcd00852fa3661b06b2e3ffafde236bb3424efa36def5846985481.  
**C3 최초 시도:** [Actions #41780677692](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41780677692), original source S1 ZIP unchanged, manifest hash check PASS but C3 group execution에서 ERR_A010_TRUTH_ONLY_REPLAY.  
**원인 분리:** [Read-only Actions #41781114661](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41781114661), 768개 truth component SHA 대조(6 fields × 4 roles × 16 cells와 각 8항목): 648 동일, 120 불일치. 관측된 불일치 field 20/22/27/29; 각 field에서 원본과 다시 계산한 Xtrue, poses, ds_true, dth_true가 해당됨. 확인된 수치 최대 절대 차이 Xtrue 8.88e−16, poses 1.11e−16, ds_true 6.94e−18, dth_true 4.44e−16. 모든 dts/prior_P0/mu는 0차.

**해석:** Float64의 최하위 비트 차이와 일치하나 원본 SHA256 불일치는 사실이다. C3 원래 하드 게이트에선 오류를 거부하는 게 정확하다. 단일 재생 작업의 런타임이 오차를 만든 원인은 CPU/라이브러리 차이의 **유력 가능성**이지, 아직 전체 runner별 환경 증명은 수행하지 않았다. 이 상태를 G5 FAIL로 혼동하거나 임의로 PASS로 바꾸지 말 것.

## 1. 권장 수정의 본질 — S1 truth 원본을 authority로 고정

- 원본 S1 저장 `TRUTH|field|role|cell|Xtrue/poses/dts/ds_true/dth_true/prior_P0/mu/pose_keys_sha`를 **source manifest ZIP SHA256와 per-array index SHA**로 정확히 검증한다. 입력/score reference를 C3가 다시 생성한 새 truth로 대체하지 않는다.
- C3는 **원본 저장 truth만 scoring 및 검증에 사용**한다. 재생성된 로컬 truth는 별도의 `TRUTH_GEOMETRY_NUMERIC_DIAGNOSTIC` 경로로 독립 비교하고, 각 배열 shape/dtype/units·max_abs/max_scaled error·SHA를 함께 기록한다.
- 평가에 쓰이는 `z,x0,ds_m,gy_m,Sigma_model,dts,taps` 7개 추정기 입력과 original FFD source/method는 불변. 원본 바이트 SHA 게이트를 하나라도 누락하거나 소급 완화하지 않는다.
- `Xtrue`를 estimator 진단 start 선택/solver에 유입하지 않는다. Truth-start oracle 전용; 9개 truth-free grid, operating E′, F2 1e−3/30, original strict G5·C10·NEES/field sensitivity 설정 전부 유지.
- 비교 수치 tolerance가 필요한 경우 CPU 반올림의 수학적 상한을 별도로 사전 기록하고, 이미 본 DEV3 수치에 맞춰 과학 임계값을 설정했다는 주장을 하지 않는다. 가장 강한 근거는 **사용한 scoring 원본 truth의 source bytes SHA 일치**다.

## 2. 절차적 요구

1. 이전 실행 SHA 및 실패 원본 artifacts를 보존하고, 이 이슈를 `AMENDMENT-010-TRUTH-REPLAY-ULP-001` 같은 **새 prospective exploratory correction amendment**로 문서화한다. 이번 오류는 DEV3 일부를 이미 본 후 발견되었으므로 관련 후속 결과도 NONINDEPENDENT_EXPLORATORY로 유지한다.
2. original S1 `MANIFEST.json`의 source_git_sha, 49개 원래 code_sha256와 전체 10개 ZIP/array index sha를 검증한다. 수정 C3 source에서는 archived S1 source SHA를 특별히 명시해 provenance를 검사한다. 과거 source hash를 새 코드 hash인 양 변경하지 않는다.
3. 초소형 데이터 subset **실제 DEV3 원본** 1~2개 registered row에서 모든 truth bytes 및 estimator-array hashes, 비용, P/C10/NEES/terminal seed consistency를 검증한다. 같은 new C3 source로 두 runner를 돌려 수치 재현성 범위와 nonfinite/extra-descent를 기록한다.
4. Negative fixtures: S1 original truth byte 1bit 변조, manifest SHA 변조, 외부 key 주입, field/role/cell 누락, 자료형/shape 변경, 수치 편차 초과 시 FAIL. 다른 field의 truth 복사도 reject.
5. SHAs와 테스트 통과 후 정확히 **DEV3 C3 20~29 × 2 groups × 3 sensor seeds → 1,080 등록 Batch**, E′+9 terminal **10,800 행** 전체를 다시 재생한다. 누락·중복 0건, 원본 S1 receipts 불변, original G5·H/CAL 별도 verdict.
6. `SOURCE_TRUTH_HASH_EXACT`와 `GENERATOR_NUMERIC_PARITY`를 별개 gate로 기록한다. CUDA/CPU 버전의 마지막 비트 오차를 조용히 지우지 않는다. 입력 source SHA와 S1 cost/P/Prior/4×4 C10 일치 실패 시 여전히 STOP.
7. HOLDOUT2/reserve/RT는 열지 않는다. RT Sionna 별도 Track R 요청서 `requests/P3_RT_SELF_RUN_SIMULATION_VERIFICATION_REQUEST_20261104_KO.md`를 따라 준비한다.

## 3. 필수 산출물

- C3_TRUTH_REPLAY_HASH_DIAGNOSTIC.json (원본 읽기전용 #41781114661 원본 보존).
- A010_TRUTH_SOURCE_LOCK.json, A010_TRUTH_NUMERIC_PARITY.csv, SOURCE_VS_REPLAY_FULL_C10.csv, A010_S1V5_ORIGINAL_SHA_RECEIPTS.json.
- 1~2 row diagnostic two-runner 원본 artifacts·SHA; 이후 1080-row C3V5_ROWS.csv/10,800 R5 receipts, FULL C10/NEES/CH4 H/CAL sensitivity, G5 status, 실패 로그와 MANIFEST.
- 최종 판정: `C3_SOURCE_TRUTH_REPLAY_PASS/FAIL`, `C3_G5_NUMERIC_PASS/FAIL`, `R5_PRECISION_PASS/UNRESOLVED_PRECISION`, `H_CAL_STABILITY/REVIEW_REQUIRED` 별도. 모든 아티팩트는 `USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY` 명시.

**STOP:** 작성 시점 C3를 과학적으로 PASS 선언 금지, 최초 실패 실행 결과 삭제 금지, 원본 하드 게이트 무단 완화 금지. 이 문서는 **시정 검증 요청서**이지 적용 완료 보고서가 아니다.
