# PALO IMM V2 — 구현→결과→적대적 리뷰→수정→재실행 계약

실행 전 계약. 신규 필터 성능은 아직 미측정. 동일 작성자의 별도 수식·결과 교차감사이며 외부 독립 감사로 표시하지 않는다.

## 1. V2-A 최소 구현
- 정상 G: 기존 s-domain LUT, R_G=.0081; 오염 C: 같은 평균 h(x), R_C>R_G의 넓고 정규화된 Gaussian. 오염 C도 R_C에 일치하는 약한 Joseph 갱신을 수행. Uniform/OFF 모델과 top-2 pruning은 사용하지 않는다.
- 각 모드에 x=(px,py,psi,bg), 전체 P를 유지. row-stochastic T[i,j]로 조건부 혼합한 뒤 동결 운동모델로 예측. 예측 가능도(정규화 항 포함)로 모드 가중치를 갱신. 상태정보가 모드별로 보존되며 pruning 질량은 0.
- Gaussian은 실수축 위의 원래 S4 근사이며 s의 물리 범위 [-1,1]을 보장하는 정확한 채널 분포라고 주장하지 않는다.
- 대조: DR, 원래 S4 NIS99, NIS<=.5, NIS<=2, 같은 emission/T를 가진 즉시 축약(collapse), mode-conditioned IMM. 신규 혼합 정책에는 별도 NIS hard gate를 추가하지 않으며 S4는 외부 기준선. collapse vs IMM이 보존 효과의 주대조.

## 2. 데이터와 파라미터 동결
- 원본 single-metric-inputs Actions #42466288321 아티팩트 (로컬 ZIP SHA256 46c6070a138f181d73f21796160fba1d52291faef1097f77d205963ddc12e140), 포함된 원본 manifest 98개 파일의 SHA256/Git blob/크기 전수 확인.
- 기준선 S4/DR 16조건 X<1e-7, P<1e-8, NIS<1e-7, mask 불일치0 모두 통과 전 신규 결과 실행 중단. 이전 15/16 실패 허용치를 완화하지 않는다. Python3.11, numpy2.2.4, scipy1.15.2, pandas2.2.3 동결.
- 정상 R_G 고정. R_C와 T는 R2 AnchorB의 t<120초 600개 reference-state residual에서 2분산 HMM으로 추정. 고정 3초기값(.04,.16,.36) 중 개발 likelihood 최댓값만 선택. 각 전이 count에 .5 regularization; R_C floor=1.01*R_G. 과학적으로 확정된 확률이 아닌 근사 파라미터.
- 참 상태는 개발 파라미터 식별과 사후 scoring에만 사용. 추론 함수 입력에는 z, IMU/odom controls, initial x/P, 동결 R_C/T만 존재. 실제 바이어스 수준 이름·시간·LoS 측정·참 상태는 입력하지 않는다.
- 주평가 t>=140초. t>=40 결과는 학습/평가를 섞은 기술통계로 별도 표시. R2/R4/R5 모두 이미 관찰한 동일 복도 개발 경로이며 blind/generalization으로 주장하지 않는다.

## 3. 적대적 감사
확률 정규화/비대칭 T 방향/두 번째 모멘트/원형 헤딩/정보형 대 Joseph 수식/모드 복귀/모드 삭제 없음/zero-weight/미래 suffix 인과성/입력참값 차단을 검사. 실험 후 원시 NPZ에서 별도 코드로 metrics, likelihood, Joseph 결과, 전체 혼합 X/P 재계산. P 양정치 및 LUT 범위 위반은 숨기지 않고 중단·기록.

동일 관측모델의 설명력과 실제 헤딩 개선은 별개. 기존 알려진 k201, k483–485 반례와 큰 bias drift를 포함. 결과가 나쁘면 그대로 기록하고 임계값을 시험 결과에 맞춰 조정하지 않는다.

## 4. 리뷰 후 수정 범위
V2-A에서 지적된 실제 구현/모델 결함을 먼저 문서화. 단순 모멘트/정규화 구현 오류는 수정 후 재계산. 독립 폭 Gaussian이 지속적인 RF 잔차를 설명하지 못하는 증거가 확인되면, 합의된 V2-B 대안인 RF offset 한 변수 c의 지속성만 추가하는 수정 검토. 이때 기존 LUT/Rs/T/초기조건/개발구간은 유지, c=white 한계에서 V2-A 동일성이 필수 감사 조건. 새 classifier/임계값/센서는 추가하지 않음. 수정으로 성능이 좋아진다고 미리 가정하지 않는다.

모든 결과·실패·감사·실행 source를 새 브랜치에 보존. Actions 실행·검산 성공과 과학적 성능 채택을 별도로 판정한다.
