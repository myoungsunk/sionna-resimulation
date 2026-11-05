# VAB 연결 R1 — 구현·비재귀 진단 결과

**PASS_CONNECTION_LOSSLESS_ONLY**. 50,560행·468,366개 후보 레코드의 연결 보존 및 자격 검사를 통과했다. 주안 VAB 유지. 선택기 채택은 **HOLD_SAFETY_NOT_VALIDATED**이며 E2는 시작하지 않았다.

## 핵심 결과

dynamic Full TWO_PORT_UNION, 원래 큰 오류 87건의 참조 위치를 비교했다. 아래는 **선택 결과가 아니라 선택 자격**이다.

|대조|원본 후보에서 usable|기존 점수 자격 ≥0.15|개정 연결 자격|
|---|---:|---:|---:|
|V0|79/87|75/87|79/87|
|VA|84/87|75/87|84/87|
|VB|83/87|75/87|83/87|
|VAB (주안)|87/87|75/87|87/87|

VAB 경로별로 R2 19/19, R4 14/14, R5 54/54가 보존됐다. 기존 점수 자격에서는 각각16/19,13/14,46/54였다. 원래 누락 8건 전부가 VAB 후보에는 들어왔지만 기존 점수 문턱을 그대로 쓰면 **8건 전부 다시 제외**된다. 여기에 원래 V0에서 포함됐던 4건도 기존 점수 문턱에서 제외되어 합계12건이 된다.

전체 두 모드에서 VAB 원본 참조 usable은12,556/12,640행이고 개정 연결 뒤에도12,556행이다. 이것을 전체 corpus 참조100% 또는 선택 성공100%로 표현하지 않는다.

## 원래 누락 8건

|packet|참조 tap|VAB 지지|가장 가까운 지지 edge와 거리|기존 점수|개정 자격|
|---|---:|---|---:|---:|---|
|R2:974:Full|56|LEFT_RISE, RX1|1|0.001235|포함|
|R4:729:Full|55|BILATERAL + LEFT_RISE, RX0·RX1|1|0.009715|포함|
|R5:506:Full|52|BILATERAL, RX1|2|0.078968|포함|
|R5:507:Full|52|BILATERAL, RX1|2|0.043611|포함|
|R5:510:Full|51|LEFT_RISE, RX1|1|0.008264|포함|
|R5:978:Full|56|LEFT_RISE, RX1|1|0.015723|포함|
|R5:979:Full|56|BILATERAL, RX1|2|0.075453|포함|
|R5:980:Full|56|BILATERAL, RX1|2|0.069153|포함|

4건은 모든 지원 edge가2 tap 이상 떨어져 기존 exp(-거리) 점수의 이론상 최대가0.135335이므로0.15를 넘을 수 없다. 나머지4건은 edge가 더 가까워도 양측 prominence 기반 점수가 문턱보다 작다. RX/lobe별 원본 수치는 동결 R1 POOLS에서 확인 가능하며, 이번 후보 로그에는 점수·kind·RX·거리·group과 pool hash를 남겼다. 이는 원래 후보 누락 원인의 재분류가 아니라 **후속 adapter에서 재제외되는 이유**다.

## 구현한 연결

- 고정 후속 소스486f0b6의 패키지를 가져왔다. 변경은 selection.py의 Evidence/Candidate 필드와 guard, engine.py의 명시적 revision delegate, 신규 bridge.py다. 나머지 후속 모듈은 해당 소스와 동일하다.
- 실제 OriginalAdapter.evidence는 명시적으로 RevisionEvidenceAdapter를 주입했을 때 VAB를 사용한다. 기존 경로는 기본값 그대로이며 전역 기본 생성기를 교체하지 않았다. 합성 검사에서 legacy 생성기가 호출되지 않는 것도 확인했다.
- 후보의 tap/raw/signed_s/overflow와 RX/lobe/group/support_kind/left_rise 출처를 실제 후속 Evidence에 보존한다. 후보/config/점수 recipe 버전을 명시적으로 결속한다.
- 선택 자격은 valid AND NOT overflow AND polarization_valid AND CIR-supported다. 점수와 분리했으며0.15를 새 점수에 재적용하지 않았다. 이는 순위 계산에 들어갈 자격이지 교체 승인 조건이 아니다.
- RF 순위 초안은 support_kind별 prominence 또는 left_rise와 해당 tap/peak 진폭 비를 사용한다. 실제 select의 판단에 사용하거나 보정하지 않았다.
- selector_ready=False 및 history_trust_eligible=False다. 기존 select/history.observe가 개정 Evidence를 받으면 명시적으로 중단한다. 따라서 단지 adapter를 주입했다고 E2나 미검증 이력 갱신이 진행하지 않는다.

## 검증·실행 증거

- 구현 커밋: `6d1c6e66719c49e80d08cd21bb175fdb8c8fd80f`. [실행 잠금](RUN_001/EXECUTION_LOCK.json), [입력 해시](RUN_001/INPUT_HASHES.json), [실행 영수증](EXECUTION_RECEIPT.json).
- 로컬 Windows Python3.13.15에서 이미 수집한 원본 로그를 처리했다. 총141.69초. 새 RF, SourceFFD 모델 로딩, 실제 corpus 선택/이력/EKF 실행은0이다.
- 신규 합성 반례18개 통과: edge+2, left-rise, RX null/중복 지지, invalid/noise,64/65/overflow,raw-only,분모 invalid,버전·출처 오류,delegate,실행 차단. [로그](SYNTHETIC_TESTS.log).
- 고정 후속 버전의 ReceiverSelectionTest 24개도 통과했다. 기존 선택/이력 동작에 대한 합성 회귀 검사이며 실제 데이터 E2 실행이 아니다. [로그](LEGACY_SELECTION_SYNTHETIC_TESTS.log), [원본 시험 출처](LEGACY_TEST_RECEIPT.json).
- 50,560행과468,366개 후보 레코드의 메타데이터·출처·자격 불일치0. 별도 scalar 점수 계산 최대 절대오차2.220446049250313e-16, 사전 허용2e-15 이내. 이것을 점수의 exact equality라고 주장하지 않는다.
- 저장된 CSV·후보 로그·집계·분모를 별도 checker로 재대조하여 불일치0. [검산 결과 및8건 상세](CHECK_001/CHECK.json). 동일 작업자의 자체 검산이며 독립 감사 아님.
- [50,560행 CSV](RUN_001/PACKET_BRIDGE.csv), arm별 *_CANDIDATES.ndjson.gz, [전체 집계·정상/오류별 부담](RUN_001/SUMMARY.json)을 제공한다. 원본 group 관계를 보존했으며 그룹을 재계산하거나 새 그룹 병합을 주장하지 않는다.

## 미완료로 남긴 항목과 주장 한계

연결 결함은 본 범위에서 해결·검증했지만, **새 점수의 선택 안전성, tap/group margin 분리, raw wrongness, 이력 bootstrap 기준, mapping/residual model의 새 버전 채택은 미완료**다. 기존 모델을 새 의미에 자동 재사용하지 않는다. mapping_recipe_sha256=None / NOT_VALIDATED가 이를 명시한다.

보관 POOLS에는 복소 위상이 없어 이번 전체 진단에서 phase_available=False다. 원본 복소 CIR을 받는 실제 adapter 경로는 위상을 계산하지만, 전체 corpus의 위상을 재구성·검산했다는 주장은 하지 않는다.

VAB의87/87은 기존 CIR-supported 후보를 선택 자격으로 손실 없이 전달했다는 뜻이다. FP 정정 성공·이력 안정성·EKF 개선·미지 환경 일반화가 아니다. 기존 E1 실패와 E1 R1 전체 결과는 수정하지 않았다. E2_GO=false / E2_started=false.
