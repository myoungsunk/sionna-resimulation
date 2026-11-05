# FP-SC-VAB-BRIDGE-R1 실행 계약

사용자 승인: VAB 연결 수정, 연결 무손실·합성 반례 검사, 기존 50,560행의 비재귀 연결 진단, GitHub 게시. E2 금지. 주안 VAB, 기존 실패 및 R1 결과 불변.

역할 IMPLEMENTER 및 동일 작업자 자체 검산. 독립 감사 아님. 질문: 기존 R1 후보를 후속 Evidence로 전달할 때 후보·지원 의미가 손실되는가? 기존 adapter 점수 자격과 얼마나 다른가?

기준 E1 HEAD 0df23a953bb3a3bb98133d07ed0271d7832528b0. 후속 코드 486f0b6c008e7a953ada75a03a941ffa46994985의 src/qclean_uwb/fp_sc/followup을 그대로 가져와 selection.py/engine.py에 명시적 연결 및 안전 차단을 추가하고 bridge.py를 신설한다. 기존 생성기·원본 결과는 변경하지 않는다. 작업 브랜치 implement/fp-sc-001-e1-run-20261105.

COMMON_CONTRACT SHA256 a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb, ROLE_IMPLEMENTER의 실제 파일 해시는 실행 부속 기록에 남긴다. 로컬 governance fallback이며 MBVAR-INFO 전용 규정은 해당하지 않는다.

## 고정 정의

- 대상은 저장된 6,320파형 × 두 모드 × V0/VA/VB/VAB=50,560행. 새 RF 재생성 없음. 이미 수집·검산된 로컬 원본 POOLS/CSV 사용. 사용자의 이번 요청은 실행 호스트를 지정하지 않았으므로 로컬에서 비재귀 JSON 진단을 수행한다.
- bridge는 후보 tap, raw, supported, signed_s, overflow, group/lobe/RX support records와 후보 메타데이터를 보존한다. invalid signed_s는 source_signed_s=None, polarization_valid=False로 보존하고 수치 자리값0은 선택 자격이 없다.
- selection_eligible=raw_valid AND NOT overflow AND polarization_valid AND supported. 이 이름은 순위 계산에 진입할 자격이며 교체 허가가 아니다.
- 기존 점수=max_l[min(1,prominence/G) exp(-abs(tap-edge))], 기존 자격=raw_valid AND NOT overflow AND supported AND 기존점수>=0.15.
- 순위 초안=max_l[min(1,b/G) min(1,A/H)], b는 BILATERAL일 때 prominence, LEFT_RISE일 때 left_rise. 초안을 기록하고 별도 scalar 곱셈/나눗셈 계산과 절대오차 2e-15 이내 비교한다. 확률 또는 보정된 신뢰도 아님.
- history_trust_eligible=False, selector_ready=False. 기존 select와 history.observe는 개정 Evidence에 명시적 오류를 내어 E2/미검증 이력 갱신으로 진행하지 않는다. 과거 legacy Evidence는 기존 행동 유지.
- 보관 POOLS에는 복소 위상이 없으므로 phase_available=False. 위상을 복원했다고 주장하지 않는다. CIR을 받는 실제 adapter 경로는 위상을 계산하며 합성 검사한다.
- mapping_recipe는 미검증/None으로 표시한다. 후보/recipe 버전은 결속하되 mapping·residual model 재사용이나 선택 안전성 채택은 금지.

## 검사·관문

1. 합성: edge+2, low bilateral/high left rise, one RX null, two RX, zero/nonfinite/noise, plateau/boundary,64/65/overflow,raw-only,invalid polarization,version/kind/group/duplicate failures, 실제 OriginalAdapter delegate, legacy V0/B0, 선택 및 이력 실행 차단.
2. 입력 원본 파일 해시·각 pool hash·행 key 유일성·모든 arm 키 일치 확인. 각12,640행, 전체50,560행 필수. 입력 누락/변조는 중단.
3. 후보·메타데이터·그룹·출처·raw·signed_s 무손실, 자격 조건 독립 재계산, scalar 점수 비교. 불일치0만 통과. 원본 참조 usable과 개정 eligibility 참조 포함이 정확 일치해야 함.
4. 레이블/참조는 adapter 계산을 마친 뒤 평가 단계에서만 join. 실제 select/history/open_loop/ArmProcessor 호출0. 정상·오류 및 corpus/channel/mode별 부담 공개. 기존 R1 group 병합은 기존 증거를 참조하고 새 그룹 재생성 안 함.
5. 기존 E1/R1의 전체 및 경로별 큰 오류 분모87/R2 19/R4 14/R5 54를 유지. VAB가 주안이며 타 arm 사후 대체 금지. 평가 결과에 맞춰 recipe·문턱 수정 금지. 실패 run 보존 후 새 run 번호 사용.

## 허용 결론

PASS_CONNECTION_LOSSLESS_ONLY 또는 실패. 후보를 후속 Evidence와 연결하고 자격이 보존됨까지만 주장. FP 정정, 안전한 선택, 이력 안정성, EKF, 일반화는 미검증. 결과 보고에서 연결 완료와 선택기 채택 HOLD를 구분한다. E2_GO=false.
