# D3B 사전등록 — 독립 DR-only vs MAP prior vs RF Range 분리

## 이전 D3 결과의 해석 수정
최초 D3의 `dr_rf_range_conflict.r_DR_prior_m`는 **실제 독립 DR-only 추정값이 아니라, 이전 RF 갱신을 거친 MAP3/MAP4의 현재 motion prior**였다. D3 네 건에서 MAP prior가 RF Range보다 참거리 오차가 작았다는 판정은 그대로 유효하되, 'DR-only가 RF보다 더 정확했다'고 일반화하면 틀리다. 사용자 질문은 별도의 DR-only 경로와 RF Range를 비교하는 것이므로 정확한 대조가 필요하다.

## 이번 D3B의 단일 질문
**“같은 네 실패 시점에서 RF 관측을 전혀 반영하지 않은 독립 DR-only의 거리 오차가 RF보다 큰가? 이 차이가 실제 MAP solver의 수치적 정체를 설명하는가?”**
이것은 새 G2/G3 실험, 다른 RF 브랜치의 계획 이식, R3 수정, P2 재실행이 아니다.

## 사전 결정한 연산
- 저장된 동일 `INPUTS.npz`의 `initial`, `ds`, `gyro`, `dt`, `Q2`를 사용.
- 3-state `[x,y,psi]`에서 원호 운동을 적분. **매 스텝 RF z를 사용하지 않음**, bias 상태 추정하지 않음; 실제 고정 bias `+0.05deg/s`는 DR 모델에 알려주지 않음.
- `P_DR`은 원래 P2 초기 pose std와 `Q2`로 예측만 반복하는 별도 DR-only 공분산. 입력 사용과 수치/단위/좌표를 기존 `core.predict`와 일치시킨 뒤 독립 복소 원호식으로 이동량을 교차 검사.
- 실패 시점 `k`에서 `r_DRonly=h_r(x_DRonly(k+1))`; 기존 `r_MAPprior=h_r(mu^-(k+1))`; `z_RF`; `r_true`를 나란히 기록. 참값은 사후 분석에만 사용.
- NIS는 **DR-only 예측 (P_{mathrm{DRonly}})**를 사용해 별도로 계산. MAP prior NIS와 절대 혼합하지 않음.
- 네 사례와 해당 조건(3경로×bias+.05)만 현재 원본 ZIP에서 추출. 실제 RF 교정 신뢰도나 223,236 레코드와 표본 단위 혼합 금지.
- 소스·원본 아티팩트 이중 사전감사를 GitHub-hosted workflow에서 D3B numerical diagnosis 전에 수행한다. 새로운 알고리즘 정확도 비교나 solver 변경은 금지.
- 이 대조에서 RF가 DR-only보다 정확해도 **현 MAP 모델의 R/Q를 사후 바꾸거나 RF를 무조건 우선하지 않는다**. 사전등록한 합성 모델에서는 RF likelihood가 이미 포함돼 있으며, 이 결과는 해석과 향후 모델 가설에만 반영.

## 끝 조건
4건 원본 입력 정합, DR-only 시간/운동 일치, RF-only 참오차 정량 비교와 기존 D3 확정된 수치 원인의 독립 보존 → 보고 후 STOP. 실패는 해당 D3B 진단의 미확정으로 기록; 이전 D3 값까지 소급 변경하지 않는다.
