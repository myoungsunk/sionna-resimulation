# 실제 선택 가능 집합 도달 — 세 검사 결과

**PASS_THREE_REACH_CHECKS**. bridge의 자격 표시만 비교하던 이전 검사에서 나아가, 실제 `select()`가 호출하는 `prepare_candidate_set()`을 통해 전체50,560행을 검증했다. VAB 주안과 기존 실패 기록을 유지한다. E1-02/E2는 시작하지 않았다.

|검사|결과|근거|
|---|---|---|
|1. 실제 select 합성 검사|PASS|신규14개, 기존 bridge18개, legacy24개 총56개 통과. 고정 원본과1,000개 legacy Decision 전체 필드 exact 일치|
|2. 전체 실제 후보 집합 대조|PASS|50,560행·468,366개 후보 레코드, 기대 집합 대비 누락·추가·중복 불일치0|
|3. 완료 관문|PASS|저장 CSV 재집계·분모·해시·기존 증거 보존 확인, VAB87/87 및 원래 누락8건 actual set 포함|

## 실제 선택기에서 확인한 것

- select와 전체 진단이 동일한 공통 후보 구성 함수를 사용한다. 합성 시험에서 실제 select의 공통 함수 호출을 spy로 확인했다.
- 개정 Evidence는 CIR 기반 selection_eligible을 사용하고, 기존 버전은 기존 support>=min_support 조건을 유지한다. 새 RF 순위 점수에0.15 문턱을 재적용하지 않는다.
- edge+2, LEFT_RISE, RF score<0.15 후보가 실제 eligible에 들어가고, 기본 Policy의 정상 PM에서 REPLACE_SUPPORTED로 선택됐다. PM-FORCE/NN-HARD 및 문턱 완화를 사용하지 않았다. 이는 합성 입력/합성 support 아래의 도달·동작 검사다.
- 지원 없음·분모 invalid 후보는 실제 집합에서 제외됐다. invalid/overflow, prior/history 부족에서는 hold하고 집합 구성 전 반환은 NOT_REACHED로 따로 기록했다. 같은 group 및 다른 group 동점에서도 ABSTAIN_AMBIGUOUS를 확인했다.
- arm/mode/candidate config/bridge recipe/selector recipe/Policy SHA 불일치는 차단한다. selector_ready=True로만 바꿔도 개정 select와 history를 사용할 수 없다.

실제 select의 개정 호출은 명시적인 SyntheticSelectionProbe와 Evidence digest를 결속한 합성 단위검사에만 사용했다. 일반 stage runner는 이 인자를 전달하지 않으므로 운영 선택·이력은 여전히 차단된다. 이는 로컬 검사 인터페이스의 범위 표시이며 외부 접근 보안 경계라고 주장하지 않는다.

## 전체50,560행 결과

|대조|행 수|actual eligible 후보 레코드|지원 없는 제외 레코드|큰 오류 참조 actual set|
|---|---:|---:|---:|---:|
|V0|12,640|73,234|19|79/87|
|VA|12,640|159,707|2|84/87|
|VB|12,640|74,179|19|83/87|
|VAB|12,640|161,206|0|87/87|

합계468,326개 eligible,40개 제외이며, 기대 집합과 다른 유입/누락은0이다. VAB의 경로별 큰 오류 참조는 R2 19/19, R4 14/14, R5 54/54. 원래 누락8건 R2:974, R4:729, R5:506/507/510/978/979/980 모두 실제 집합에 포함됐다.

전체 corpus에서는 공통 함수의 **C 모드 집합·순위 구성만** 실행했으며 실제 결정 함수 select는 호출하지 않았다. temporal 조건이 준비된 P/M/PM에서 집합이 같고 조건 부족 시 hold한다는 점은 합성 select 검사로 검증했다. 전체50,560행에서 P/M/PM을 실행했다거나 실제 정정 결과를 얻었다고 표현하지 않는다. 참조는 집합 구성이 완료된 뒤 평가기에만 join했다.

원본 pool 조건으로 직접 계산한 기대 집합과 비교했으며, bridge flag나 공통 helper를 기대값 계산에 재사용하지 않았다. 순위 점수는 별도 scalar 계산과 최대 절대오차8.881784197001252e-16, 사전 허용2e-14 이내였다. 점수 비교는 exact equality 주장이 아니다.

## 실행·검산 증거

- 구현 commit `52fee22c3536f47503e587dde0ec9b64a01ff7f9`. [실행 계약](CONTRACT_KO.md), [코드·정책 잠금](RUN_001/LOCK.json), [입력 해시](RUN_001/INPUT_HASHES.json).
- 로컬 Windows Python3.13.15에서 동결 원본 로그 처리141.89초. 새 RF·실데이터 결정·이력 갱신·EKF 실행0. [실행 영수증](EXECUTION_RECEIPT.json).
- [신규 실제 선택기 시험](test_fp_sc_selector_reach.py.log), [기존 bridge 시험](test_fp_sc_bridge.py.log), [legacy 시험](LEGACY_SYNTHETIC.log), [시험 영수증](TEST_RECEIPT.json).
- [행별 actual/expected 집합](RUN_001/ACTUAL_SELECTOR_SETS.csv), [실행 집계](RUN_001/SUMMARY.json), [최종 세 관문 검산](CHECK_001/GATE.json).
- 원본 candidates.py/candidate_revision.py/Policy 및 기존 E1·R1·bridge R1 기록은 변경하지 않았다. 검산은 동일 작업자의 자체 검산이며 독립 감사가 아니다.

## 완료 범위와 다음 경계

**“새 후보가 실제 선택기 내부의 선택 가능 집합까지 도달하는가”는 완료다.** `selector_ready`를 켜서 완료로 간주한 것이 아니며, 공유된 실제 코드 경로·합성 결정·전체 집합 대조로 확인했다.

실데이터 선택 안전성, 새 점수의 wrongness/gain 기준, tap/group margin 의미 분리, 이력 bootstrap, mapping·모델 결속과 단계 권한 준비는 별도다. 본 검사는 기존 기본 정책의 안전성을 채택하지 않으며, FP 정정·EKF 개선·일반화를 입증하지 않는다. production_selection_adoption=HOLD, E1_02_started=false, E2_started=false.
