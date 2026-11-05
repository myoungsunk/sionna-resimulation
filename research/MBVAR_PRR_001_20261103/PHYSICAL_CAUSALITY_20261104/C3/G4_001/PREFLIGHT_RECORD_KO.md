# G4 실행 전 검증 기록

실제 24조건 분석·SourceFFD 초기화 전의 합성 수학 및 동결 의존성 검사 기록이다. 실제 RF 생성·EKF·학습은 없다.

- preflight_001: 9검사 중 1오류. 유효한 상수 합성 스펙트럼의 CIR이 0에 가까운 tap에서 원소별 allclose를 통과하지 못했다. 실제 RF 실패가 아니다. 자연 종료1, 종료 확인·소유권 해제 기록 보존.
- preflight_002: 감쇠 envelope 합성에서도 동일 오류. 원인은 peak 대비 극소 tail의 FFT 반올림에 원소별 상대오차를 요구한 추가 QA였다. 자연 종료1 및 종료 확인 보존.
- preflight_003: 넓은 CIR tail을 가진 합성 9검사 통과. 이 통과만으로 결함 해결을 주장하지 않았다.
- 독립 CODE 검토에서 유효한 상수 입력을 유지하고 기존 계약의 joint/RX별 Erel·Emax 정의를 적용하도록 REDIRECT했다. 임계값 1e-8과 zero-reference STOP은 그대로 유지했다. 과학 데이터·원래 모델·계약 원문은 변경하지 않았다.
- preflight_004: 최종 코드 10검사 통과. 상수 스펙트럼 회귀, 의도적 CIR 변조 검출, zero-reference STOP 포함. 직접 DFT 대조, amplitude/power 구별, RX 동률·순환 tap, signed 포트 교환, coherent cross term, surface 합집합, schema·scope 음성검사, toy 모델 FD·단위·branch 및 원래 모든 의존성·런타임·BLAS1 검사 통과. 실제 모델 초기화는 하지 않았다.

각 실행의 command·stdout/stderr·exit 및 관리 종료 기록은 logs/에 있다. 실행 전 결함 수정과 독립 GO를 실제 G4 결과감사와 구분한다. 자동 과학 재실행 또는 원래 데이터 재생성은 없었다.
