# provider 활성화 계약 — 구조 정의 / 수치 관문 HOLD

현재 구현을 변경하지 않는 후속 인터페이스 명세. 구조 정의와 수치 수용 기준 완료를 구별한다.
허용 상태는 VALID / UNKNOWN / INVALID 세 개다. 오래됨·불일치·근거 부족은 UNKNOWN의 reason으로 표현한다.
기존 Stage2의 SUSPECT/STALE 상태 제안을 최신 사용자 지시에 맞춰 이 계약에서 대체한다. 과거 문서는 보존한다.

## 출력 필수 항목
- recipe_version, provider_code_sha256, calibration_sha256, evidence_ids 및 evidence_sources.
- prior_id(case/packet/time/원본 state·covariance hash), issued_at, applies_at, expires_at, input_cutoff.
- P와 M 각각 state, allowed(boolean), reason, scope(용도/좌표/단위/오차범위), uncertainty/support_interval 및 보정 근거 ID.
- 전체 state: 구조 이상은 INVALID, 어느 용도라도 유효하면 VALID, 그 밖에는 UNKNOWN. 전체 VALID로 P/M 둘을 동시에 켜면 안 된다.
- reset_generation, downgrade_reason, recovery_requirements. 누락 필수항목은 fail closed.

## 불변 조건
allowed=true는 해당 용도 state=VALID일 때만 가능. VALID라도 scope·시각·prior_id·recipe·보정SHA가 불일치하면 소비자가 거부한다.
근거 없음/보정 없음/시간 만료/재초기화/불일치에서는 UNKNOWN, 수치·공분산·시간순서 구조 위반은 INVALID.
독립 근거가 없는 현재 dataset에서 정확한 P/M VALID를 만들어내는 로직은 구현하지 않는다.
P 자격은 P의 위치·Heading/모델 의존 범위를 충족해야 한다. M은 별도로 과거 rawFP 근거·실제 경과시간·이동량 불확실성·reset 세대를 충족해야 한다.
P VALID가 M VALID를 암시하지 않는다. C-only flag, 현재 FP 판정, 같은 측정의 innovation으로 현재 prior를 인증하지 않는다.
재초기화 시 기존 이력 세대를 폐기한다. 유한 숫자 복귀/일시적 일치만으로 복구하지 않는다. 검증된 초기 근거와 필요한 과거 창을 새로 확보해야 한다.
기각 관측을 삭제하지 않는다. main NIS/shadow mask 출처를 별도 유지한다.

## 수용 지표와 미확정 수치
위험한VALID=용도오차한계 위반VALID/VALID. 활성화=VALID/전체. P/M 각각 전체·경로·개입·episode별로 보고.
VALID=0이면 위험한VALID는 N/A, 활성화는0. '안전0%' 또는 실용성PASS로 표시 금지.
불확실성: 포함률+폭. 시간: 오류 후 강등 지연과 정상 복귀 후 활성화 지연. 미복구는 검열/미복구로 기록.
허용 오차·허용위험·최소활성화·최소독립episode 수는 용도 요구와 독립 자료가 확인되기 전 임의로 정하지 않는다.
현재 세 노출 경로/단일 환경의20초 블록은 독립 표본 수를 늘려주는 근거가 아니다. 기존 mapping95% 재사용 금지.
수치 예산이 정해지기 전에는 UNDETERMINED이며, 결과를 보고 숫자를 정하면 새 계약의 사후개발로 기록한다.

## 다음 관문
provider 수용+별도 실행 승인이 모두 충족돼야 E1-02 C/P/M/PM을 실행한다. 이때 selected_tap=raw_tap, 탐지율/오탐/보류/활성 및 전체분모 공개.
현재는 HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING 유지. 별도 C-only 결과는 이를 해제하지 않는다. E2 정정 안전성은 별도 미실행 단계다.
