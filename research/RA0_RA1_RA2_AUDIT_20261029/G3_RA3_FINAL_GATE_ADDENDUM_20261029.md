# G3 26 ray → H 영향 → RA3 재감사: 재검증 추가 기록 (2026-10-29)

## 감사자 최종 상태: `REVISION_REQUIRED / PHYSICAL_RELEASE_BLOCKED / SELF_REVIEW_ONLY`

본 추가 기록은 기존 보고서를 덮어쓰거나 G3 물리적 FAIL을 소급 수정하지 않는다. GitHub 원본 `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`, 감사 관련 `audit/g3-26ray-ra3-20261029` 및 실행 #40852794655, #40850815112, #40851669162, #40852149539의 산출물을 재교차 확인하고, 별도 표준 라이브러리 `G3_RA3_FINAL_REAUDIT_20261029/tools/auditor_crosscheck.py`를 실행해 exit 0 및 MANIFEST SHA 검사를 통과시킨 기록이다. 동일 모델 세션의 감사이며 사람·기관 차원의 독립성은 주장하지 않는다.

## 1. 확정 범위와 미해결 범위

- 원 아카이브 5,630 위치, 354,410 ray, strict >5e-14 s: **26 ray/24 위치**, relaxed >2e-13 s: 0. 각 그룹 Boolean FAIL 6/6은 전체 354,410개 ray가 실패했다는 뜻이 아니다.
- 0개 station에 대해 PASS를 내던 초기 `phase='drive'` 누락 검사기 결함은 이미 확정·수정된 과거 문제다.
- 이미지 후보 집합을 `TIE_S=1e-13 s`로 묶은 후 `5e-14 s`로 검사하는 절차가 인공 FAIL을 만들 수 있다는 합성 반례는 확정. 실제 원인과 혼동하지 않는다.
- **원 trace `tau`까지 확인된 ray는 1/26**: R2-A pose915/ray62. 병합 전/후 잔차가 모두 5.1090357159952736e-14 s인 `UNMERGED_STRICT_FAIL`. **이 ray의 tie-only 원인은 배제**되며, Sionna 내부 경로/누적 숫자 정밀도 중 어느 원인인지는 미확정.
- **나머지 25/26 raw `tau`는 미확보**. 개별 원 ray ID 및 실제 병합 전 잔차를 원 receipt에서 도출할 수 없으며 23 위치 중 25개 슬롯을 `BLOCKED_RAW_TAU`로 유지. 동률 후보가 23/24 위치에 존재한다는 사실을 실제 원인 증명으로 사용하지 않는다.
- 원 timeline/trace 좌표차의 지연 영향 상한 약 1.997e-15 s는 strict 5e-14 s보다 작아, **좌표 소수 반올림 하나만으로 초과를 설명할 수 없음**.

[26개 ray별 미해결 출처 원장](g3/G3_26_RAY_OPEN_EVIDENCE_20261029.csv)은 누락을 0으로 치환하거나 경로 ID를 지어내지 않는다.

## 2. H 영향, 최소 재실행의 확정 논리

원 H의 보관 SHA와 관측 추출 parity는 별도 통과한 이력이다. **G3 checker-only 수정은 기존 H 바이너리와 packet에 영향을 주지 않으므로 H 재생성·BB/MB_VAR 재실행 요구 없음**. 반대로 이러한 동일성은 원 H의 물리적 진실성을 보증하지 않는다.

R2-A 한 ray의 지연을 이상적인 image delay로 *가상 조정*했을 때 두 mount에서 `relative |ΔH|₂ ≤3.08e-7`, `|Δs|≤2.18e-14`, `Δr=0`, first-path switch 0. **오직 이 한 가상 교정**의 packet 영향이 허용오차 내임을 검증. 나머지 25개와 실제 RT 교정 영향을 외삽하지 않는다.

실제 채널 수정이 확인되면, *최대* 24 trace 위치×2 mount=**12 H store의 48행**을 별도 patch로 재생성한다. 각 변경 행은 257 bin, 양 port, first-path tap/r,s, packet 일치성을 비교한다. `r,s`/packet이 바뀐 case만 최초 변경 packet부터 재귀 필터를 재실행한다. 최대 7 case×4 gyro=28조건, 우선 BB_ORIG·MB_VAR **56 trajectory**, 변경된 주장을 모두 다시 제출하려면 최대 기존 **392 PB score 행**, 별도 S6 주장은 최대 **54,000 score 행**에 대한 영향 재평가가 필요할 수 있다. 기존 원자료와 결과는 덮어쓰지 않는다.

**아직 성립하지 않는 주장:** 26개 원시 ray의 H 물리 영향 없음, 또는 26개 물리 원인 모두 확정. 이를 선언하지 않고 `BLOCKED_PHYSICAL_SOURCE`로 유지한다.

## 3. RA3 구현 정의 / 기존 성능 재생

원 `pol_bias_model/exp_pb.py`의 VAR는 `rho(x_{k-1}^{+})`에서 `sigma_b`를 조회한 후 predict. 비교 구현은 `rho(x_k^{-})`에서 조회. 원 코드에 `predicted`라는 주석이 있다는 사실만으로 실행 정의를 덮어쓰지 않는다. 동일 BASE gate, mu_B/mu_M, R, Q, 센서 및 초기 상태로 7 case×4 bias×2 background **56개 arm** 전수 비교했고 LEGACY 원 `exp_pb.run`과 별도 재구성 state/P가 최대차 0을 확인.

기존 BB_ORIG 대비 MB_VAR Heading 개선 수 **23/28 → 23/28**, XY **20/28 → 20/28**, 동시 **19/28 →19/28**. 개선/미개선 부호 변화 **0/28**. 그러나 실수 RMSE는 전수치 동일이 아니며 MB_VAR에서 Heading 최대 **0.006278°**, XY 최대 **0.060967 cm** 변화. 두 정의를 각각 `MB_VAR_LEGACY`, `MB_VAR_PRIOR`로 관리해야 함. 결과를 원 H 물리 검증이나 일반화 근거로 사용하지 않는다.

## 4. 정확한 다음 STOP/GO

- **GO:** RA3 코드 정의·분산 조회 시점의 원 packet 민감도 검증은 종료하고 결과를 보존; 새로운 모델 변형의 과학적 승인은 별개.
- **STOP:** 원 5개 그룹에서 raw `tau`/각 ray 지오메트리가 확보되거나 원 solver를 지정된 **23개 위치에 한해** 재현하기 전에는 G3 물리 결함·모든 H 영향 없음·전체 연구 PASS 선언 불가.
- **GO only on evidence:** 물리적 H 수정 필요가 나타난 위치만 trace→H 행→packet→그 case 재귀 필터 순으로 확대한다. 전체 5,630위치 RT나 모든 연구 392행 선행 재실행 금지.
- **독립적 최종 서명 필요:** 이 보고서는 동일 세션의 여러 계산경로를 포함하지만 `SELF_REVIEW_ONLY`. 외부 감사자는 25 ray 원 데이터, H 후보 SHA 및 재귀 필터 변경분을 재검산해야 한다.

### 출처
- 원 G3 [재검사 README](https://github.com/myoungsunk/sionna-resimulation/blob/f100a983cc389fcdef073592a254add61e7115da/results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/README.md)
- [G3 24개 위치 검산 Action #40852794655](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40852794655)
- [R2-A 원 trace Action #40850815112](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40850815112)
- [R2-A 단일 ray H 반사실적 시험 Action #40851669162](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40851669162)
- [RA3 56-arm 전수 실행 Action #40852149539](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40852149539)
