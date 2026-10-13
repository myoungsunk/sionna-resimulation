# FP 이전 window 방향 비교

메인 checkout의 소스·git·기존 결과는 수정하지 않았다. 별도 side 결과에만 저장했다.

- 동결 RF 7조건, 3경로, t>=30초의 6201 Full–LoS 대응쌍.
- 원본 FP 및 기준포트 FP 각각에 단일 tap, FP 포함 이전3/4 tap, 이후3/4 tap 적용.
- PRE3=[k-2,k-1,k], PRE4=[k-3,k-2,k-1,k]. 두 RX에 같은 window.
- 전력 균등 적분 후 signed ratio 계산. 가중치나 threshold 변경 없음.
- 사전 주후보 CO_PRE4. P0 39자산 SHA/shape/pose PASS. 기존 단일tap 및 POST3 parity 최대차0.

| 기준점 | 단일tap | 이전3 | 이전4 | 이후3 | 이후4 |
|---|---:|---:|---:|---:|---:|
| 원본FP | 0.17090971 | 0.15187446 | 0.14748617 | 0.21948342 | 0.24591017 |
| 기준포트FP | 0.16204233 | 0.14120524 | 0.13650613 | 0.19916596 | 0.21801275 |

값은 RMS(sFull-sLoS). CO_PRE4는 기존 FP보다 약20.1% 감소했고 모든7조건·3경로에서 감소했다. 기존 dense single-tap 값0.14758268보다 약7.5% 낮다. 현재 비교에 dense anchor의 pre window는 포함하지 않았다.

CO_PRE4에서 FP 자체의 평균 에너지 가중치는 Full69.26%, LoS70.78%였다. 이전4 window는 상대적으로 작은 전력의 leading 구간을 더하므로 이후4 window의 후반peak 편중을 피한다. 이것이 직접파 복원이나 Heading 개선의 증명은 아니다.

경로 R2/R4/R5 CO_PRE4 RMS는 0.14947368/0.14684488/0.11669421. 대응 LoS 관측모델, Heading 민감도, 잡음 견고성, EKF gate는 아직 검증하지 않았다. scientific_PASS=false.

최초 출력 저장 시 anchor별 열이 달라 schema error가 발생했다. 공통 열 이름으로 수정한 뒤 전체를 재계산해 exit0로 완료했다. 수신 알고리즘이나 값은 수정하지 않았다.
