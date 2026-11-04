# SM0-PRECISION-001 — 위상 정밀도 계약 개정

- 역할 IMPLEMENTER. 질문 SM0-PRECISION-001.
- 사용자 승인 2026-11-04, 「제시한 수정 방향을 적용하여 수정한다」.
- 기준 Git 5e13c6025074d74c90644412d5a006f6c2a20e13, PR #28.
- 공통 지침 COMMON_CONTRACT.md 및 ROLE_IMPLEMENTER.md. 실제 해시는 실행 영수증에 기록한다.

## 변경 이유와 적용 범위

기존 F64 실제 분석 채널은 첫 canary LoS 재현 기준을 실패했다. 기존 STOP_MISMATCH, 원시 데이터, 감사 및 판정은 수정하지 않는다. 이 개정은 첫 canary 결과를 확인한 뒤 승인된 사후 프로토콜 변경이다. 첫 canary 재검증은 독립적인 새 표본 검증이 아니다. 아직 실행하지 않은 14개 pose에는 향후 실행 전 고정할 규약이다.

이번 작업은 코드 수정, 보존 원시 데이터 재검증 및 독립감사에 한정한다. 신규 PathSolver 호출, 나머지 pose 실행, FFT/물리 기여 분석, C1–C3 진행 권한을 생성하지 않는다. 기존 GO는 새 코드 해시와 일치하지 않으며 새 생산 실행에는 별도의 독립 GO가 필요하다.

## 두 계산 경로

1. 원본 호환·실제 분석 채널은 원본 compute.py의 `a[:,0,:] * np.exp(-2j*np.pi*np.float64(f)*tau)[None,:]`이다. 원시 a complex64, tau float32, NumPy 1.26.4를 유지한다. 주파수는 float64 scalar이고 결과 per-ray field는 complex64이다. 위상 보상, 정렬, 스케일 적합, 경로 삭제를 금지한다.
2. 원본 Full 재현은 위 field의 원래 complex64 reduction으로 검증한다. 실제 그룹 분석에는 같은 per-ray field를 complex128로 승격해 합산한다. 이 그룹 Full도 별도로 원본 Full 기준을 통과해야 한다. 직접파 field도 LoS 기준을 통과해야 한다. 평균오차 뒤에 포트별 실패를 숨기지 않도록 RX별 오차도 동일 기준으로 검사한다.
3. F64 검산은 원시 a/tau를 double로 승격한 삼각함수·math.fsum 독립 합과 F64 경로/그룹 합을 비교한다. F64 채널은 이 개정에서 실제 분석 채널로 사용하지 않는다. 원본과의 F64 차이는 삭제하지 않고 진단값으로 계속 보고한다.

## 고정 기준

| 검사 | 기준 |
|---|---|
| 원래 complex64 Full / archive Full | relative L2 ≤ 1e-3, 전체 및 RX별 |
| 실제 분석 그룹 Full / archive Full | relative L2 ≤ 1e-3, 전체 및 RX별 |
| 원래 직접파 / archive LoS | relative L2 ≤ 1e-5, 전체 및 RX별 |
| F64 그룹 합 / 독립 scalar F64 합 | relative L2 및 max-normalized ≤ 1e-8 |
| 호환 그룹 합 / 호환 per-ray scalar fsum | relative L2 및 max-normalized ≤ 1e-8 |
| 재계산 per-ray / 저장 original_field | 비트 일치 |
| F64 재계산 / 저장 F64 field 및 합 | 동일 기준 ≤ 1e-8 |

기존 1e-3, 1e-5, 1e-8을 완화하지 않는다. 실제 분석 채널을 F64에서 원본 호환 field로 바꾸는 명시적인 계약 개정이다. 허용오차가 같아도 기존 계약의 통과로 소급 해석하지 않는다. 모든 배열/참조는 유한하며 정규화 기준이 0이면 실패한다. 원시 필드, 그룹, 직접파 인덱스, 원본 archive와 입력 해시를 검증한다.

## 결과와 주장

AMENDED_NUMERICAL_PASS는 개정 계약 아래의 수치 재현 결과다. 독립감사 완료, 새 데이터 전체 수용, 물리 경로 완전 동일성, 반사 인과성 및 EKF Heading 인과성을 의미하지 않는다. 과거 원본 ray 계수 부재도 해소되지 않는다. postprocess 및 후속 단계는 이 수정으로 자동 실행하지 않는다.
