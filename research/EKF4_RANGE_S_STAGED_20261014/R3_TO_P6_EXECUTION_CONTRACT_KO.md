# R3 → P2 → P6 단계적 구현·검증 계약 (2026-10-14)

## 승인된 연구 목적
사용자 요청: R3의 float64 비용 평가/스텝 수용 결함을 **원인 기반 자율 수리**하고 GitHub-hosted Actions에서 회귀/대표 P2/전체 P2/가용한 P3→P6로 순차 진행. **각 진단·시험·실험을 시작하기 이전에는 같은 Git SHA의 사전 코드/입력 감사**가 있어야 한다. 사용자 요구보다 더 강한 과학 통과조건을 만들지 않는다. 후속 단계는 자신의 **실제 계산·입력 적격성** 조건으로 판단하며 P2가 모든 경로에서 우수하다는 주장은 P3의 파일 감사 선행조건이 아니다.

## 불변
- 기원: `research/ekf4-range-s-staged-20261014`의 공개 커밋 `2781ee299f6908399acbb6bec91efb6e81cdc366`.
- P2_SPEC.json `548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7`, synthetic.py `c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643`.
- 입력 seed 10000–10099, 3 paths × 2 true bias × 100 trials × 120 steps × EKF3/EKF4/MAP3/MAP4, RF `SyntheticRF`, Q/R, prior, gyro bias, model, local optimization objective, 80 iteration, gradient_tol=1e-8.
- 참값을 생성/점수 계산에만 사용, model selection에는 미사용. Range와 s를 한 번만 반영. 로봇 물리·원본 FFD·측정·LUT는 변경하지 않음. 과거 실패 기록은 소급 수정 금지.

## R3 수치 문제·수리 가설
D3: 원본 네 실패에서 저장된 full Gauss–Newton step은 80자리 고정밀 목적함수를 7e-17–3e-16 감소시키고 다음 gradient ≤2e-10이나, float64 `J(y+d)-J(y)` 계산은 큰 양수(5e-14–9e-14)로 반대 부호였다. 기존 R2는 직접 Armijo 비용 비교에 `+4eps` 반올림 여유를 두며 아주 작은 불명확 스텝을 accept했고, true-gradient-integral 분기는 64eps/작은-step guards를 요구해 full GN이 탈락했다.

**수리 가설 R3:** 직접 비용 변화가 충분히 큰 경우만 float64 Armijo를 사용하고, roundoff 근방에서는 독립 선적분 항등식 `ΔJ=∫_0^1 ∇J(y+t d)ᵀd dt`를 4/8분할 Simpson으로 비교하여 *같은 목적함수*에서 감소하는 스텝을 판단하면 네 고정 사례와 실제 P2 수렴이 개선된다. 후보 gradient 증가·적분 불일치·비유한·chart 이탈 등 실제 구현 실패는 중단하되, 특정 로그 branch 결손은 수학 결과를 무효로 만들지 않는다. 임의 tolerance 증가 및 자동 fallback-to-prediction 금지. 적분은 비선형 수치 진단의 근사이지 인증된 global convergence proof가 아니다.

## 단계/선행 감사/범위
P0 pre-run audit: 현재 Git SHA, source hash, P2 spec/input, provenance, 진단코드 AST, callback, fallback, truth leak, 파일 경로와 출력, 결과에 영향을 주는 표본 단위까지 검토. `PRE_RUN_AUDIT.json=GO` 아니면 그 단계 실행 없음.
R3-1: source audit → 원 P0/P1 24 test·R1/R2 regression 15 test → 네 신규 고정 failed-step NPZ/JSON 무결성 감사와 fullstep 독립 고정밀 진단 + R3 solver stationarity/비유한/반례. 실제 실패 입력 외의 수학 tests도 점검.
R3-2: source audit → 대표 P2 (각 path/bias seed 0, 24 model-trials) → 정확도/수치 실패를 분리. 하나의 model 실패는 해당 case INVALID; 다른 case는 보존. 실제 수치 blocker면 우선 해당 사례 집중 진단·수리.
P2-full: R3 대표가 해당 회귀 결함 없이 진행되면 **사전 full-code audit 새 영수증** 후 동결 원본 600 paired trial을 전체 실행. 결론을 'P2 ALL-PATHS 효과'와 경로별 CI·정상 bias 손실·coverage·solver success로 분리. 실패/불일치를 숨기거나 성공한 경우만 평균해 일반 성능 주장 금지.
P3: 동결 실제 RF/LoS/Full/LUT 입력·source·경로·좌표 적격성, 사용 가능한 원본 parity 검사. P2의 과학 우월성 여부에 영향받지 않는 별도 기준.
P4: 동일 prior에서 기존 EKF3/RF baseline, 4-state, fixed linearization, Range-first joint relinearization 차이; 각 비교의 acceptance mask/likelihood/data provenance를 유지. 실행 불가능한 arm은 범위 제한만 기록.
P5: local Gaussian vs 위치 적분한 다봉 Heading posterior. 기존 G3 TV 0.387>0.001 실패는 그 적분 기준만 invalid; 무관한 P4/local 필터 결과까지 무효화하지 않는다.
P6: 각 범위에서 재귀/공분산/coverage를 평가. 실제 RF 원본 파일·관측 모델·수치 적분·독립 장면을 갖추지 못한 주장은 NOT_VALIDATED. 다른 단계가 완료되지 않았다면 'P6 SUCCESS'를 주장하지 않음.

## 비용/중단
- 신뢰 가능한 numerical fix 없이 같은 오류가 반복되면 가장 작은 failed-step → 해당 코드 원인 분석 → 필요한 regression 수정 (모델/데이터 계약 변경 없음), 새 소스 감사 이후 다시 실행.
- 수리 가설이 반증되면 해당 가정과 데이터 비교. 수리 실패가 타 결과와 무관하면 그 결과만 CASE_INVALID.
- 실제 사용 불가능한 원본 FFD / 참값 부족은 해당 RF inference 범위의 NOT_RUN/BLOCKED_SOURCE. 자동 생성/가짜 데이터 대체 금지.
- 최종 보고서: 실행 커밋과 제출 커밋 분리, 감사 영수증·결과 ZIP/원시 trace/CI/hashes 제공. **최종 P6 또는 확인된 실제 blocker에서 종료**. 사후 임계값 완화 금지.
