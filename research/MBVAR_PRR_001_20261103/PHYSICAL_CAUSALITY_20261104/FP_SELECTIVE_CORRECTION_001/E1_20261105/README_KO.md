# E1-01 — CIR 후보 가용성 canary

E0의 조건부 기능적 재현 관문을 통과한 뒤 실행하는 **후보 존재 여부** 시험입니다. 현재 CIR만 사용하는 단일 후보 생성 규칙을 고정하고 `STRONGEST_ONLY`와 `TWO_PORT_UNION`을 비교합니다. 후보 생성 API는 GT·LoS 라벨·route·prior·history를 받지 않습니다.

고정 규칙은 공통 최대 진폭의 6% prominence, local lobe의 30% amplitude leading edge와 ±1 tap, 15% local amplitude support입니다. 한 RX의 정상 편파 null을 허용합니다. 유효한 원 tap은 fallback으로 보존하며, 신호가 무효이면 후보를 만들지 않습니다. 후보가 64개를 초과하면 모두 기록하되 usable pool로 인정하지 않습니다.

동적 R2/R4/R5의 원 B0 seed10 pose 3,136개에 대한 Full·Native-LoS와 G4 24조건의 Full·direct를 합쳐 **6,320 waveform, 12,640 packet-mode 행**을 평가합니다. 동적 Full의 큰 참조 오류(≥2tap)가 주 모집단입니다. G4는 별도 정적 보조 대조이며 동적 분모에 합치지 않습니다.

두 RX 후보의 usable reference recall이 전체 및 분모가 있는 각 경로에서 95% 이상인지 판정합니다. packet·시간 연속 episode·정적 coordinate 분모를 공개합니다. 관측률의 기술적 통과도 독립 RF 환경에 대한 안전확률이나 정정 성공을 뜻하지 않습니다.

**이 실험은 FP를 교체하지 않으며, 오선택 식별·P/M 선택기·관측모델 재보정·EKF 개선·실시간 운용을 평가하지 않습니다.** 원 tap 보존은 후보 구성의 불변조건이며 false-correction safety rate로 해석하지 않습니다. 후보 규칙 실패 후 같은 실행의 기준·파라미터를 바꾸지 않습니다.

- [정확한 규칙과 분모](POLICY_SPEC.json)
- [E0 선행 관문](../E0_20261105/audit/H0_GATE_REVIEW.json)
- [실행기](../../../../../scripts/fp_sc_e1.py)
- [순수 후보 생성기](../../../../../src/qclean_uwb/fp_sc/candidates.py)
- [별도 checker](audit/check_candidates.py)

실제 실행은 새 code/input/environment/execution lock, 별도 코드 검토와 현재 사용자 지시에 결속한 GO 후에만 허용됩니다. 상세 후보와 제외 lobe 로그는 무손실 gzip으로 기록합니다. 모든 검토에서 외부 독립기관의 ACCEPT를 받았다고 주장하지 않습니다.
