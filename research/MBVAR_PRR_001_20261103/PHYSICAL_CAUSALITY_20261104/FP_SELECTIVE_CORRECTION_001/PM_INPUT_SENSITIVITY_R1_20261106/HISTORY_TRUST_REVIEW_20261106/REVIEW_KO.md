# FP-SC-HISTORY-TRUST-001

2026-11-06. 역할 AUDITOR(동일 작업자 코드·증거 점검; 독립 감사 아님).
검토 HEAD: 255cec44da3f2e9a285d87e5fa61686ccb64ccc3.
판정 REDIRECT: 일반 이력의 신뢰성은 미입증. 현재 VAB 보호 유지.

## 범위
코드 읽기, 저장된 진단 NPZ 조회, 선택된 원본 Hrf의 CIR 변환 및 기존 후보 생성기로 등록 술어 대조만 수행했다. select, TrustedHistory.observe/support, detection_loop, EKF는 실행하지 않았다. E1-02/E2 미실행. 기존 실패·VAB 주안·임계값 변경 없음.

## 경로 구분
detection.py RawDetectionHistory.support는 reset_trust 후 None, observe_raw도 reset_trust한다. prepare_detection은 P/M/PM을 HOLD한다. 현재 VAB는 신뢰 이력을 형성하지 않는다.
selection.py TrustedHistory.observe는 bridge Evidence 또는 selector_ready=false를 거부한다. 이 일반/legacy 경로는 selected_tap 후보가 valid, non-overflow, supported, support>=0.15, prior 존재, 폭<=1.5m, prior residual<=1을 2회 연속 만족하면 저장한다. history_trust_eligible, Decision action/reason, confidence, margin, 독립 prior integrity는 검사하지 않는다.
실패 시 streak만 0으로 바꾸므로 기존 t/detector_m은 남는다. support는 age>2s일 때 사용을 중단한다. 적격 관측이 계속되면 매번 타임스탬프가 갱신되므로 절대 유지시간 상한은 없다. advance는 |ds|>0.2*elapsed+0.02일 때 reset한다. 시간/pose 역행은 예외다.
engine.py 일반 open_loop는 결정 후 observe한다. ArmProcessor는 EKF gate rejected여도 사용 가능한 관측이면 C/D/E/F에서 observe에 도달할 수 있다. VAB 보호를 해제할 근거가 아니다.

## 실제 입력 사례(오프라인 술어 대조)
원본: E1_02_PREPARATION_R1_20261105/INPUTS/{case}/online.npz Hrf.
참조와 prior 구간: PM_INPUT_SENSITIVITY_R1_20261106/RUN_001/{case}_{ONLINE,EVALUATOR}.npz.
기존 generate_candidates(TWO_PORT_UNION, noise_var_per_bin=0)와 from_pool 사용. 선택 결과를 만들지 않고 raw를 유지한다는 조건 아래 observe의 수치/후보 술어만 확인했다. GT는 평가에만 사용.

|case|k|t|raw|reference|legacy support|prior 구간(tap)|prior residual|등록 술어|
|---|---:|---:|---:|---:|---:|---|---:|---|
|R4_B0_Full_10|49|9.8|51|49|0.9999473281|47.997006–50.002994|0.9940301174|true|
|R4_B0_Full_10|50|10.0|51|49|0.9999627372|47.997006–50.002994|0.9940301174|true|
|R4_B0_Full_10|51|10.2|49|49|0.9998841155|47.997006–50.002994|0|true|
|R5_B0_Full_10|33|6.6|51|49|0.9999660843|47.997006–50.002994|0.9940301174|true|
|R5_B0_Full_10|34|6.8|50|48|0.9999841058|46.997006–50.002994|0|true|
|R5_B0_Full_10|35|7.0|50|48|0.9999415571|46.997006–50.002994|0|true|

모든 표 행에서 valid/nonoverflow/supported 조건을 만족했다. R4 ds=0, R5 ds는 약 0.04m/0.2s로 advance의 reset 경계 0.06m를 넘지 않는다.
R4는 prior 구간 밖이지만 residual<=1 조건이 추가 0.15m까지 허용하므로 등록 술어를 만족한다.

R4 저장된 VAB 민감도 진단: k49 PM=1.129860, k50 PM=1.146218, k51 PM=0.957090으로 모두 임계값 2 미만이다. k51의 M 구간 49.601552–52.409935는 참조 49를 벗어나지만 추가 벌점은 오탐 임계값에 이르지 않는다. k52에서는 raw49를 사용해 M 구간이 47.595805–50.404188로 돌아온다. 이는 legacy support와 다른 VAB 진단이며 legacy 선택기를 실행한 증거가 아니다.

## 허용 결론
실제 입력의 잘못된 raw FP가 legacy 등록 조건을 연속해서 만족할 수 있다. 갱신이 계속되면 2초 만료는 장기 자기유지를 막지 못한다. 잘못된 선택→이력→다음 선택의 구조적 순환은 일반 실행기에 존재한다. 그러나 이번에 폐루프를 실행하지 않았으므로 지속 고착이나 EKF 자기강화의 실제 발생·빈도는 미검증이다. R4 사례는 회복하며 영구 고착의 증거가 아니다.
다음에는 독립 근거에 기반한 P/M별 신뢰 계약, 실패 시 만료 정책, 장기 동일 오경로·gate 기각·정상 복귀 검증이 필요하다. 결과에 맞춘 임계값 변경은 하지 않았다.
