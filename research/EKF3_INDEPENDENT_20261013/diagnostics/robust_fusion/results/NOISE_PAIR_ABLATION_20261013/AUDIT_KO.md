# M1 구성요소 ablation 독립 코드 감사

판정: ACCEPT (코드). Reviewer: /root/ablation_audit, 읽기 전용 감사.

M0/M1-A/B/C가 요청한 네 구성을 구현한다. M1-A는 기존 R0·NIS gate·Joseph 보정·Range 연산 순서를 보존하고 Bias 상태만 추가한다. M1-B는 실제 3-state이며 원본 EKF3 예측과 기존 M1의 고정 prior·고정 선형화·단일 block-Huber 보정을 사용한다. M1-C는 기존 RobustBiasEKF를 직접 사용한다. 파라미터 재조정, 온라인 truth 유입, 학습 모델 변경은 발견하지 않았다.

근거: ablation/run_ablation.py의 계약 검증·모델 구성·원본 재현 대조, ablation/robust_pose_ekf.py의 상태 차원 변경, d6_d9_common.py의 Bias4 예측·R0 보정, ablation/test_ablation.py의 독립 Gaussian 계산·robust 정상조건·gate 거부·계약 변경 차단 검사.

RF 묶음에는 평균·분산·Huber·NIS gate 제거가 포함되므로 Huber 단독 원인으로 해석하지 않는다. E1 전체 재귀 결과는 공간 중복의 역사적 상태 영향을 포함하는 탐색 결과이며 확증으로 주장하지 않는다. 코드 ACCEPT는 성능 개선 또는 scientific_PASS를 의미하지 않는다.

부모 실행 확인: 신규9 + 기존49 = 58 tests PASS. 소규모 모델당12셀 완료, M0/M1-C 기존 결과 최대 차이0, 허용치1e-8 유지. 전체 실행 완료·재현 증빙은 별도 PARITY.json 및 FULL_MANIFEST.json을 기준으로 한다. 후처리 analyze_ablation.py는 부모가 작성했으며 trace 재집계와 저장 지표의 일치를 실제 자료에서 확인한다.
