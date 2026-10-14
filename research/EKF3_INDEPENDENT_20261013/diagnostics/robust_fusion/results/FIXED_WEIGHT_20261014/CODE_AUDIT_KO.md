# 독립 실행 전 코드 감사

판정: ACCEPT. 감사자: /root/ablation_audit. 대상: fixed_weight_control.py, test_fixed_weight_control.py, run_fixed_weight_comparison.py, FIXED_WEIGHT_PLAN_KO.md.

- 동일 prior를 복제해 네 보정을 비교하며 대조군 posterior는 재귀 전파하지 않는다. M0와 Cauchy donor를 분리한다.
- 원본 R0 prior NIS gate 통과 후에만 고정 1/3의 R_eff=3R0를 적용한다. 초기조건·운동 입력·기존 세 모델은 유지한다.
- GT는 평가 전용이며 재학습이나 온라인 oracle 입력은 없다.
- 입력·계수·참조 해시, 동일 prior/gate, Gain/보정/Joseph 정합 및 기존 세 모델 요청 셀 parity 1e-8 검사가 있다.
- 1/3과 Cauchy의 평가 정보량/likelihood 동등성을 주장하지 않는다. scientific_PASS=false 및 단일 장면 탐색 경계가 적절하다.

필수 수정 없음. 이 판정은 실행 전 코드와 계약에 대한 것이며 실제 결과는 후속 감사 대상이다.
