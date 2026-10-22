# P2 실행 핸드오프 · 운영 절차 · 결과 판정

## 구현 완료된 P2-A smoke 계약

- 연구 브랜치: research/d0-cir-p2-recursive-20261022
- 00_P2_EXECUTION_PROTOCOL_KO.md: 사전 가설/선택 없는 판정
- 01_FAILURE_TO_P1R_RETEST_KO.md: P2 실패 시 P1R 복귀 분기
- p2_train.py: P1R와 같은 CIR/WIDE/NARROW HGB(train T only), calibration R(train T inner leave-one-route-out) serialize
- p2_replay.py: 실제 odom+gyro 4-state EKF, 각 arm 독립 재귀, 현재 state에서 d0 계산, BASE/DR/range-only/shared R/WIDE/CIR/narrow/oracle. BASE score가 strict held-route 평가 기준과 1e-7 이내 일치하는지 확인
- p2_aggregate.py: 누락 arm/case/initial/parity QA 후 요약
- workflow .github/workflows/p2-cir-d0-recursive-smoke.yml: outer H=R2/R4/R5 train-only 모델 3개 준비, R4_aA_m0 Full B0 NOM/±10° P5 smoke, 결과 집계. 의도적으로 7-case full run을 자동 시작하지 않음 — smoke QA 실패 시 데이터·모델 해석 방지

### Smoke 실행 후 필수 검사

1. train (R2,R4,R5) 3개 job success + QA JSON train_routes에 held route가 없는지 점검.
2. smoke R4_aA_m0: 3개 initial (NOM/+10°P5/-10°P5), 9 arm, 결과 CSV/series 존재.
3. \`BASE_POWER\` normal 초기의 P2 replay와 기존 strict \`BASE\` 점수 격차 <1e-7. Source/FFT/observer/POWER params/B0 seed parity 실패 시 **STOP**.
4. WIDE vs CIR_ONLY: shared R 값 동일, μ_s 이중 차감 0, gate 수용·상태 prior별 d0가 arm 고유인지 기록.
5. LoS train label과 Full evaluation GT는 모델 inputs에 없고, ORACLE만 LoS 평가표를 사용할 것.
6. PSD P/Joseph, heading wrap, NaN/inf, cross-covariance dimensions, P0 at init 5° 확인.
7. code review: estimator가 truth variable에 접근하지 않는지 정적 감사; offline scoring과 ORACLE은 별도 예외.

### Smoke 통과 후 full run

1. Train 3개 artifact 재사용 혹은 동일 seed/학습방식 재구축. **재학습한 경우 train R과 predicted teacher OOF parity도 재검사**.
2. 7 case 별 독립 job: 3 conditions(full B0, full L2, los B0), 9 초기 조건(NOM,±10 P5/PM,±20 P5/PM). 동일 케이스의 세 condition을 하나의 source bank stage로 묶어 자산 다운로드 중복 감소.
3. 모든 job 성공 전 aggregate 금지, 실패한 case를 삭제하지 말고 failure table에 포함. 총 7 case ×3 conditions×9 init×9 arm = 15309 case-condition-init-arm rows? 실제 산술은 7×3×9×9=1701 rows이다. 목표 1701 score rows.
4. t-split(0–2,2–10,10–30,>=30,all)과 prior heading/xy error d0, LoS ehat residual(offline), gate mask, update step, gyro bias 보존.
5. Route-heldout R2/R4/R5의 heading RMSE/NEES/coverage/XY/range 별도 table. ±10/20 P5 초기과신과 PM matched prior 대조. P2 주행 중 GT-matched 동적 P 사용 금지.
6. Bootstrap: 10s timeblock case별 paired bootstrap 2000개, 추정표본 3 route임을 명시. 선택된 case/path만 합격이라 주장하지 말 것.

### P2 실패 진단 순서
- Baseline parity 실패 → **코드/자산 감사**, P1R 모델 수정 금지.
- WIDE와 CIR_ONLY 모두 heading 악화 → 위치 prior/거동/LoS oracle부터 분리. oracle 개선 없으면 단일 anchor heading LUT 관측성/기초 EKF 문제.
- WIDE만 악화 → train-only P1R-XY/PR/IN/AUG를 한 변수씩 실행 (01 문서).
- heading RMSE는 개선, NEES/coverage만 악화 → 모델을 새로 훈련하기 전에 residual R/prior correlation/temporal covariance P2-B 수행.
- q99 증가 → FP shift, large d0 false-alarm, repeated multipath streak, initial error 미수렴과 gate 별도 분해.
- P2-A+B가 통과하면 P2-C Δs range correction 결합. range 단독 이득을 heading 개선으로 오해하지 않도록 GRAW/RONLY를 분리.

### 재현 가능한 최종 산출물
- case/arm/route/warmup/initial score CSV + per-step trace (gzip)
- route-level summary + initial-condition q99 and divergence tables
- sha receipt/source snapshot and train-only calibration R CSV/JSON
- failing cases + reasons without omission
- run ID, source SHA, git branch, P1R version pinned
- 무리하게 P2 정상 수행을 단정하지 않으며 full run 전에는 **P2 성능 미판정**.

현재 브랜치의 code와 smoke workflow는 구현본이다. 전체 factorial/P2-B/P2-C 자동화는 smoke 승인 게이트를 통과한 뒤 별도 workflow에서 완성한다. 오차 개선 목표를 먼저 합격시키기 위해 오프라인 GT 이용이나 평가 route 튜닝을 하지 않는다.
