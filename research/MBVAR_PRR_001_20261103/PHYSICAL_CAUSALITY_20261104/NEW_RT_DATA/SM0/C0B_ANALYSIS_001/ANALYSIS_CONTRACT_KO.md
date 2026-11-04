# C0-B-Q0 — 개정 SM0 채널의 복소 간섭 및 검출 tap 분석

역할 IMPLEMENTER. 사용자 2026-11-04 승인에 따라 전체 SM0 데이터 독립감사 통과 뒤에만 실행한다. 공통 연구 지침 및 IMPLEMENTER 역할을 적용하며 실제 지침/입출력/코드 해시는 실행 영수증에 기록한다.

## 고정 입력과 순서

SM0 요청의 15 pose 전체를 사용한다. R4 194는 PRECISION_AMENDMENT_001/REVALIDATION_002에서 수용된 보존 RAW를 재사용한다. R4 168,172,173,234,500,525,729와 R5 401,465,979,980,982,983 및 R2 525는 BATCH_AMENDED_001의 신규 원시 데이터다. 첫 canary는 사후 계약 재검증이고 14개는 실행 전 개정 규약 고정임을 구별한다. hotspot 선택은 모두 기존 결과를 보고 정한 설명용 표본이다.

독립 data acceptance와 분석 code GO가 실제 raw 및 코드 해시에 묶여 있어야 한다. qa.py로 모든 입력의 개정 수치 기준을 재검사한다. complex64 원본 위상 per-ray field를 semantic chain별 complex128로 합산한 채널만 분석한다. original_field 및 raw a/tau/metadata는 그대로 보존하며 F64는 분석 채널로 쓰지 않는다.

## 계산과 보고

기존 독립 코드감사 대상 diagnostics.py의 Hann257, 1028-point IFFT×257 및 두 RX 중 strongest peak branch의 30% leading-edge를 사용한다. 기존 archived Full/LoS와 새 분석 채널의 Full/LoS tap이 각각 같아야 한다. 같지 않으면 STOP이며 맞추기 위한 shift/scale/pose 삭제는 금지한다.

각 pose에서 다음을 빠짐없이 보고한다.

- Full/LoS tap, signed s 및 포트 전력, 거리, tap shift.
- eMP = sF(fpF)−sL(fpL), same-tap = sF(fpL)−sL(fpL), detector-choice = sF(fpF)−sF(fpL). 항등식 residual을 보고한다. 두 항을 독립적인 물리 원인 비율로 해석하지 않는다.
- 각 semantic chain을 제거한 복소 채널에서 고정 tap signed s와 detector 재계산 signed s를 모두 보고한다. 각 체인은 복수 ray를 포함할 수 있으며 frequency간 동일 ray 추적을 주장하지 않는다.
- 각 물리 면에 닿은 모든 체인을 함께 제거한다. 면별 결과는 중첩되는 다중반사 체인을 공유하므로 면 효과끼리 더하지 않는다. 물리 재시뮬레이션이 아니라 저장된 ray 성분을 제거한 오프라인 반사실이다.
- 포트별 coherent power allocation은 direct와의 cross term 및 reflection–reflection cross term을 포함하며 전체 반사에 의한 전력 차이와 closure를 검사한다. signed ratio 제거 효과는 비선형이므로 합산 기여율로 쓰지 않는다.
- R4 168/172/173의 인접 hotspot, 234 작은 오염 대조, 525/729, R5 465/982와 R2 525 무 tap 이동 대조를 동일 원장에 보존한다. 가장 큰 surface effect는 단순 설명용 abs(delta_s_fixed) 기준으로 전체 표에서 자동 선택하며 다른 효과를 숨기지 않는다.

영 denominator인 반사실 signed s는 undefined로 남기고 건수를 보고한다. 원래 Full/LoS composite가 영/비유한이면 STOP한다. data/code hash 불일치, QA 실패, tap 불일치 및 power closure 실패 시 분석 중단하고 부분 산출물을 보존한다.

## 검증과 주장 한계

실행 전 loader의 F64 우회 차단·변조 거부 및 진단 수식을 독립 코드감사한다. 실행 뒤 별도 검산기로 15개 전체 FFT/detector와 same-tap 항등식, 모든 chain/surface removal, power closure 및 archive parity를 검증한다. 결과 및 감사 후 GitHub에 푸시한다.

허용 주장은 선택된 시뮬레이션 pose에서 특정 저장 반사 체인이 포트 전력·편파비·검출 tap을 어떻게 바꾸는지다. 실제 환경 빈도, 새로운 RF 일반화, 온라인 검출 성능, 경로의 과거 원본과 완전 동일성, EKF Heading/공분산 과신 인과성은 주장하지 않는다. C1–C3와 SM1/SM2는 실행하지 않는다.
