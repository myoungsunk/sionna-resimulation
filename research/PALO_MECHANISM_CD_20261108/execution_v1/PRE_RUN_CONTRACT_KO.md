# PALO C·D 실제 실행 사전 계약

설계 기준: 657af33d5bd52c1fc706546b18c75a0a8901312b의 MECHANISM_CD_DESIGN_KO.md.
원본 입력: 4c43020f04fbbf7d0510f792c4ab99a1d9f5ddb5.
재귀 donor: 16450dc14366ba4ed2cb4e151952493f0efc944f의 baseline S4/DR/Heading Oracle.

## 범위
- C0: LoS/Full × B0/L0/L1/L2에서 S4와 DR4를 처음부터 재생하여 저장 X/P/NIS/mask 대조. X<=1e-7, P<=1e-8, NIS<=1e-7, mask mismatch=0. 입력 SHA256/Git blob 확인.
- C1: frozen nonlinear LUT의 hTT,hET,hTE,hEE로 innovation을 공통 RF+모델 불일치·위치·헤딩 성분으로 분해. 순수 다중경로만으로 해석하지 않음.
- C2: p,psi,전체 4x4 P의 8개 요인조합. S4↔DR를 주 대조, S4↔Heading 및 DR↔Heading은 보조. 전체 74,784조합 중 주 대조 24,928. gate 이전 전체 후보가 주 분석.
- C3: signed gain의 직접 heading/위치 교차항, innovation-vs-gain의 대칭 산술분해를 구분. 국소 혼합 상태/P는 자연적으로 생성된 이력으로 주장하지 않음.
- C4: alpha={0,.05,.10,.25,.50,1}, 헤딩/XY 공동 허용 구간. 평균과 P를 일관되게 약화. 각도 래핑은 명시적으로 기록.
- D: S4↔DR의 모든 사전게이트 손익 불일치 사건과 사전 고정 사례 k={201,483,485,525,630,962,973}. 각 S4/DR checkpoint에서 10개 개입(off,mean-only,P-only,on,on-no-bg,bg-only,alpha .05/.1/.25/.5) 후 동일 규칙 S4 또는 RF-off로 20초까지 진행.
- D의 ON 개입은 원래 gate에 의한 선택과 별개인 의도적 개입이다. initial_gate를 기록하여 분석자가 구별할 수 있게 한다.
- S4 continuation은 매번 자기 X/P에서 frozen LUT/H를 다시 계산한다. 원래 donor의 mask나 Jacobian을 강제로 사용하지 않음.
- 미래 측정 OFF에서 같은 평균·다른 P의 평균 궤적 동일성을 음성대조한다.
- 원래 코드의 scalar 연산으로 벡터화 코드와 off-trajectory 후보/예측의 일부를 독립식 대조. 전수 양정치/유한성 및 저장 시 valid 마스크 검사.
- 0/1/5/10/20초의 signed heading/XY/bias, 적분·최대오차·NEES·포함률·재수용을 저장. 100/120/140초 분할 경계와 자료 끝을 넘는 horizon은 제외. 120~140은 gap 진단으로 보존하되 학습/평가 인증에 사용하지 않음.

## 승인하지 않는 해석
새 detector 학습·임계값 선정·온라인 성능 인증 없음. 이 실험은 단일 경로/anchor/seed의 모델 내부 개입이며, 실제 반사경로 단독 원인·인과 기여율·독립 환경 일반화·공분산 통계적 보정·전역 최적성은 주장하지 않는다.
D의 단위는 checkpoint/개입/미래규칙 조합이며 독립 물리 사건 수가 아니다. mean-only/P-only/bias-only는 진단용 혼합 분포로 정상 Bayesian posterior를 뜻하지 않는다.

## 게시
코드와 결과는 기존 설계 브랜치의 execution_v1/ 아래에 보존. GitHub Actions가 원본 SHA를 검증하고 완료한 결과를 새 커밋으로 게시한다. 원본 연구 자료를 덮어쓰지 않음. 실패 로그도 artifact에 보존. 원시 X/P는 분할 NPZ로 게시하며 경계 이후 미사용 배열에는 NaN 패딩과 명시적 valid 마스크를 둔다.

사전 합성검사: 임의 LUT/양정치 P 200개에서 관측 Jacobian 수치미분 대조 최대차 2.62e-7, rank-one/Joseph P 최대차 5.56e-17. 실제 RF 검사와 구분.
독립 과학 감사는 별도이며 이번 실행은 자체검산이다.
