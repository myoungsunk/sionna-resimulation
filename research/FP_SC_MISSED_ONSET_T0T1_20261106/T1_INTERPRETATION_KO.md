# T0/T1 첫 결과 — 놓친 FP 오류의 탐지 신호와 남은 구별 문제

기준 결과: RUN_001 at 471af52b2ac763042756aadc70d84a9db803deb9. 실행: GitHub Actions 42192603200 SUCCESS. 이전 CSV codec 입력 오류 중단 42192337856은 보존했다. 전송 인코딩 alias 외 detector/VAB/원래 점수의 수치 변경 없음. 자체 검산이며 독립감사 아님. Linux runner에서 기존 waveform을 읽었으며 Snowball 실행이라고 부르지 않는다.

## 완료 범위

T0: 원시 online/evaluator payload SHA 및 시간·pose를 확인하고 Full/Native-LoS 6,272 packet의 기존 raw와 참조 tap 모두 재현. 원본 scalar strongest-RX 검출도 6,272개 일치. T1: P/M·prior·GT를 detector에 주지 않고 양 RX의 에지와 원래 tap 불일치를 전수 계산. 원래 FP를 교체하거나 EKF·S3·기존 E1-02/E2를 실행하지 않았다.

Full 3,136: raw 오류 1,003 / 정상 2,133; 미교체 오류998. 오류는 참조보다 늦음748·빠름255; 1tap916·2tap이상87. 이 분류는 실제 행에서 재계산했다.

## 결과: detection과 correction을 구분

| CIR-only 진단 | 오류 경보/1003 | 정상 오경보/2133 | 미교체998 경보 | 오류에서 가상 tap 정확 일치 |
|---|---:|---:|---:|---:|
| VAB 지원 최소tap | 997 | 2133 | 992 | 367 |
| 양 RX 자체peak30% crossing 중 이른 값 | 343 | 229 | 341 | 233 |
| 양 RX VAB 지지 lobe의 실제edge 중 이른 값 | 406 | 431 | 404 | 240 |

경보는 현재 raw와 대조 에지가 다르다는 뜻이다. 열잡음이 검출됐다는 뜻이 아니다. VAB최소tap은 edge-1 후보 때문에 정상 모두에서 달라져 그 자체로 오류탐지 정책이 될 수 없다.

양RX30%는 기존 PM이 교체하지 못한341건에서 신호를 제공한다. 그러나 이 에지를 무조건 FP로 쓰면 정상229건도 참조에서 벗어나며, 오류233건의 exact 개선과 상쇄되어 전체 exact는 2133→2137에 불과하다. 실제 교체를 실행한 결과가 아닌 동일 waveform의 가상 비교이다. local-edge는 오류경보를 늘리지만 정상431건을 건드려 현재 형태 그대로 채택하지 않는다.

## 실제 미교체 R4 구간

| R4 시각 | 기존 raw | 참조 | RX0 30%edge | RX1 30%edge | 이른 edge의 의미 |
|---|---:|---:|---:|---:|---|
| 33.6s (k168) | 33 | 31 | 33 | 32 | 이전 점수는 ORIGINAL_BEST; 양RX 불일치를 찾지만 정확 복구는 아직 아님 |
| 34.0s (k170) | 31 | 31 | 30 | 31 | 현재 raw는 정상인데 이른 RX0에 따르면 오경보 |
| 34.6s (k173) | 32 | 30 | 32 | 30 | 이전 점수는 ORIGINAL_BEST; RX1 에지가 참조와 일치 |

여섯 교체 사례를 다시 고른 것이 아니라, 이번 전수 FEATURE.csv에서 원래 미교체 오류와 인접 정상대조를 함께 확인했다. 세 사건은 이미 노출된 하나의 구간이며 독립 표본3개라는 주장은 하지 않는다.

## 중요한 새 제한: 지금 입력은 noise_variance=0

6개 canonical case의 기록된 RF noise_variance가 모두0이다. Native-LoS에서도 양RX30% 에지가 기존 strongest-RX 참조와 868/3136 다르고, local-edge도838/3136 다르다. 따라서 이번 앞선 후보/오경보를 단순 열잡음 때문이라고 부를 수 없다.

참조는 'direct-only 채널에서 기존 strongest-RX30% detector로 얻은 operational tap'이다. 새 earliest 정의와 이 참조는 직접파만 있어도 달라질 수 있다. 그렇다고 참조를 사후 바꿔 성공률을 올리지 않는다. 기존 라벨은 고정하고, 별도의 기전 대조로 동일한 새로운 detector를 Full/LoS 각각에 적용하는 비교와 포트별 직접파 응답을 검토해야 한다. 물리적 최초 경로와 detector tap을 구별한다.

## 다음 분석의 우선순위 — 아직 미실행

1. 양RX30%로 새로 경보한 **미교체 오류341건 vs 정상229건**을 우선 비교한다. 동일한 포트-switch/진폭비/상승 폭/각포트 peak-relative threshold 차이가 두 집단을 구분하는지 확인. 양RX 정보를 유용하게 활용할 가능성은 확인했지만 오류확정 신호는 아직 아님.
2. 남은 미교체657건을 늦은FP/빠른FP, 동일lobe/다른lobe, 참조가 실제edge와 일치/edge내부로 나눈다. 너무 이른 raw255건에 '더 이른 tap'을 답으로 강제하지 않는다.
3. clean Native-LoS의 868건을 별도 대조하여 포트별 detector 정의 차이를 먼저 정리한다. 새 noisy-CIR/CFAR 실험은 별도 noise recipe·false alarm 기준을 고정한 뒤에만 실시. 현재 noiseless 결과를 잡음제거 성능으로 주장하지 않는다.
4. 이 구별 신호가 확인되기 전에는 P 중심 보상·M 수정·FP교체·F01/F11/EKF를 동시에 바꾸지 않는다.

판정: **T0 데이터/기준선 재현 완료, T1 탐지 신호 전수 분석 완료. CIR-only earliest 규칙의 운영 채택은 NO-GO. 다음은 경보의 진위 구별 분석.** 기존 실패 기록 및 VAB 주안 보존.
