# 실제 진폭비 기반 adaptive 가중

사용자 요청: FP 이후 진폭이 8배이면 전력영향 64배를 고려해 실제 신호에 적응하는 가중치 적용. 구현: E_k=P1_k+P2_k, A_k=sqrt(E_k), raw_w=min(1,(A_FP/A_k)^2)=min(1,E_FP/E_k), normalized_w=raw_w/sum(raw_w). 동일 가중치로 s_k를 평균한다. FP보다 약한 tap은 증폭하지 않도록 raw_w<=1. 8배가 이미 전력비를 의미한다면 이 규칙의 상대가중치는1/8이며 다시 제곱하지 않는다.

전력에 같은 raw_w를 곱한 뒤 ratio를 계산하는 대조군도 별도 저장했다. E_k>=E_FP 구간에서 이 대조군은 각 tap의 유효 전력 기여를 균등화하므로, s 자체에 inverse-energy 가중을 주는 방식과 다르다. 실제 RF 크기가 오류분산을 뜻한다는 가정은 하지 않는다.

## 실행결과

7조건, 6201쌍, t>=30s. 보간16N/30%crossing/4개 평가시점 및 window 시간폭 불변. 조건 또는 threshold 사후 탐색 없음.

| 방식 | 기준포트 FP 시작 | 세밀한 시점 시작 |
|---|---:|---:|
| 단일tap | 0.16204233 | 0.14758268 |
| 고정 64:16:4:1 s가중 | 0.16941009 | 0.15532418 |
| adaptive s가중 | 0.18383775 | 0.16890633 |
| adaptive 전력가중 대조 | 0.20067156 | 0.18820730 |

원본FP RMS=0.17090971. adaptive+세밀화는 원본보다 약1.17% 낮지만 5% 감소요건 미달이며, R2/R4에서는 원본보다 악화되고 R5에서만 개선했다. 새 weighting 후보는 NOT_SUPPORTED_IN_THIS_DEVELOPMENT_COMPARISON. scientific_PASS=false.

Full의 세밀화 adaptive 평균 가중치는 [55.39099,23.56955,12.72847,8.31098]%, LoS는 [56.07423,23.31893,12.46304,8.14381]%. 고정64:16:4:1은 첫tap75.29%이므로 이번 adaptive는 평균적으로 후반을 더 반영했다. 기존 pulse 상승 자체에도 반응하므로 진폭 증가를 multipath 신뢰도와 동일시할 수 없다. 이 결과로 exponent를 추가로 변경하지 않았다.

검증: 합성 proportional-port, dense/coarse complex parity, amplitude8→relativeweight1/64, scale invariance, normalized sum 검사PASS. 원본W2 최대차0. 이전 고정64실행과 12402 온라인 행의 키·단일tap값·세밀한시점·fallback이 정확히 동일. 실행 exit0 및 process 종료 확인. 입력과 기존 결과 보존. 새 weighting용 LoS 관측모델/Heading/EKF는 NOT_RUN.
