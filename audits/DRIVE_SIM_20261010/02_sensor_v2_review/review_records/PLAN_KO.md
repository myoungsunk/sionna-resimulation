# sensor-v2 독립 보완 계획
기준: 2337c33 + COPIED_SOURCE_MANIFEST.json에 기록한 기존 미커밋 sensor-v2 구현. 원 checkout 변경 없음.
현재 1단계 결과는 산술 검증으로 수용하되 과거 배열 직접 검증은 아님.
추가 변경: sensor-v2 설정/측정 입력의 NaN/Inf, shape 불일치를 조기 거절. legacy 경로 및 모델 수식 변경 없음.
검증: 새 입력 회귀시험 및 기존 sensor-v2 unittest의 legacy/해석/공분산 시험. RF/MC 캠페인 재실행 없음.
다음 과학 검증: sensor-v2의 noise-only→bias/asymmetry→known/unknown wheelbase→fixed/RW bias→slip 분리. matched range R, RF 없는 대조군 우선. RF 가중치/gating 및 조건부 R는 후속 별도 단계.
합격: 유한 정상 입력 출력 불변, 비정상 입력 명시 오류, 기존 회귀시험 성공. 과학적 일관성 채택 기준은 새 시험 전에 별도 고정.
