# PALO C·D 실행 계약 — 설계에 따른 구현 패키지

현재 패키지 상태: **CODE_IMPLEMENTED / SYNTHETIC_QA_PASS / ACTIONS_NOT_STARTED / SCIENTIFIC_RESULTS_NOT_RUN / NOT_PUSHED**.

이 상태는 작성 세션의 실제 상태다. GitHub Actions에서 성공한 경우 `runs/<run_id>/EXECUTION_COMPLETE.json`, `VERIFY_RECEIPT.json` 및 Actions artifact의 `PUBLISH_RECEIPT.json`으로 이후 상태를 확인한다. 이 문서의 준비 상태를 실행 결과로 인용하지 않는다.

## 1. 고정 원전과 대상

- 설계: `657af33d5bd52c1fc706546b18c75a0a8901312b`의 `MECHANISM_CD_DESIGN_KO.md`.
- 원본 RF·LUT·설정: `4c43020f04fbbf7d0510f792c4ab99a1d9f5ddb5`.
- 원본 입력 manifest: `eaf9a386ec8da9cb58aaeec2e3481563de0c0a7f`.
- 저장 S4/DR/Heading Oracle 궤적: `16450dc14366ba4ed2cb4e151952493f0efc944f`.
- R2/Anchor B/seed0; C0는 LoS·Full ×4수준, C/D 주 검정은 Full.
- 각 파일을 기존 manifest의 bytes/SHA256/Git blob SHA1으로 확인한다. LFS 포인터는 데이터로 사용하지 않는다.

## 2. C0 재현 관문

8조건 S4와 8조건 DR4를 같은 입력으로 새로 진행해 X<=1e-7, P<=1e-8, S4 NIS<=1e-7, mask 불일치 0을 요구한다. 벡터화 관측·후보를 동결 scalar 코드와 표본 대조한다. 실패 시 C/D와 결과 게시를 중단한다. 전체 오류 로그는 artifact에 남긴다.

## 3. C1–C4

C1: 원래 비선형 LUT의 hTT/hET/hTE/hEE로 RF+모델 잔차, 위치 성분, 헤딩 성분과 상호작용을 계산한다. Full−LoS는 별도 대조이며 순수 오염 정답이라고 주장하지 않는다.

C2: 위치·헤딩·전체 양정치 P의 2×2×2 교환. S4↔DR 24,928조합을 주 분석으로, S4↔Heading 및 DR↔Heading까지 합쳐 74,784조합을 보존한다. 모든 후보는 gate 이전에 평가하고 gate 변화도 기록한다. b_g는 직접 관측 미분이 0임을 C0에서 확인하며, 4상태 endpoint 재현을 위해 헤딩과 같은 donor에서 가져온다. 이를 현재 바이어스의 직접 측정 영향이라고 해석하지 않는다.

C3: innovation와 gain 차이의 정확 대칭 분해 및 Kpsi의 직접 헤딩/위치 교차항을 기록한다. 요인 주효과·상호작용 대비와 target 손익 부호의 최소 충분 교체집합을 저장한다. 단독 충분성은 겹칠 수 있으며 수치를 더해 인과 기여율을 만들지 않는다.

C4: heading의 원형 각도 허용 구간, XY 허용 구간과 교집합을 정확 계산한다. alpha={0,.05,.10,.25,.50,1} 및 오프라인 연속 Heading 최적 alpha를 기록한다. mean과 P를 일관되게 변경한다. 새 온라인 판정기는 학습하지 않는다.

## 4. D1–D3

사건 집합은 전수 S4/DR endpoint 손익 부호 불일치 + 사전 사례 k={201,483,485,525,630,962,973}이다. 두 donor의 자기 prior를 각각 공통 checkpoint로 쓴다. 사건에 대한 분기 선택은 오프라인 진단이지 온라인 정책이 아니다.

분기는 OFF, mean-only, P-only, 정상 ON, bias 갱신 제거, bias-only, soft .05/.10/.25/.50이다. bias-only는 평균의 b_g만 바꾸고 P는 prior를 유지한다. 인위적 분기를 정상 Bayesian posterior로 주장하지 않는다.

미래 규칙은 (a) 동일 원본 NIS gate 기반 S4, (b) RF-off이다. 각 분기는 매 시점 자신의 X/P에서 exact LUT/H를 평가한다. 기존 donor의 수용 mask를 강제하지 않는다. 현재 사건(q=0)은 개입을 위해 강제로 설정하며, 이후 S4 규칙에는 gate가 유지된다.

0/1/5/10/20초의 Heading·XY·bias·P·NEES·포함률·오차 적분·최대 오차를 남긴다. 40/100/120/140초 경계를 넘는 horizon과 원본 자료 끝을 넘는 horizon은 제외하고 명시적으로 기록한다. mean-only와 ON, OFF와 P-only는 미래 RF-off에서 평균이 같아야 한다.

모든 유효 step의 X/P/nis/mask를 float64 NPZ에 저장한다. 평가 표와 mean/P 차분-차분 상호작용을 별도로 저장한다. 초기 RF-off와 t=140 S4 이력 이후 RF-off는 cold/hot 참조 궤적으로 구분한다.

## 5. 검증과 게시

별도 검산기는 파일 해시·C 분해 항등식·모든 D horizon 지표를 재계산한다. 미래 recursion은 동결 scalar source로 표본 검사하며 그 수를 기록한다. 이것을 별도 에이전트의 독립 과학 감사라고 주장하지 않는다.

통과한 경우에만 결과를 같은 실행 브랜치의 `runs/<run_id>`에 새 커밋한다. source SHA와 원격 head가 다르면 게시를 멈춘다. 강제 push, 기존 결과 덮어쓰기, main 변경을 하지 않는다. Git tree의 blob SHA를 대조하고 원격 ref를 확인한다.

## 6. 해석 제한

현재 검정은 동결 시뮬레이션·추정 모델 내부 메커니즘 진단이다. 반사경로의 물리적 원인, 모든 과거 사건의 전역 인과분해, 실제 온라인 선택 가능성, 새 환경 일반화, 공분산의 통계적 보정은 추가 검증 대상이다.
