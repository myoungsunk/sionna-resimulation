# 05. 원고 v4 조정 계획 — 물리적 관측구조를 중심으로

원고 기준: `1aac4d38a6fa335116bcecbebc91ba53c876ecfd`의 `PAPER_MANUSCRIPT_WORKING_DRAFT_KO.md`. **이 계획은 원고를 수정하지 않았다.** 실제 수정은 구현 결과·별도 감사 이후 새 버전에서 수행한다.

## 1. 바꿀 중심과 바꾸지 않을 대상
중심을 ‘Range mean + polarization R를 바꿨더니 RMSE 감소’에서 **‘실제 Dual-LP의 state-dependent 물리 관측을 어떻게 사용하는가: 원하는 yaw 민감도와 잔여 구조오차의 전달을 분리’**로 이동한다.

단일 anchor B, R2/R4/R5 mount0, 네 gyro, 4-state, 기존 integer r와 s, MB_VAR/self, mean+variance 하이퍼파라미터는 고정한다. Range-only/Conventional EKF/3-anchor/새5-state의 결과를 현재12조건 증거로 추가하지 않는다. baseline은 기존 보정 BB_ORIG다.

## 2. 원고 §1–4 구조 유지
| 원고 위치 | 현재 유지 | 조정 계획 | 필요한 근거 |
|---|---|---|---|
| §1.1 관측 정의 | s, 단일앵커, TX+45/RX±45, Native LoS offline | FFD→좌표변환→CFR/CIR→공통tap→signed s→J chain와 위치/yaw 민감도를 먼저 설명 | 기존 source 검증 + V1 F1 |
| §1.2 잔차 분석 | 3경로 Range RMS 감소, 남는 편파 오차 | mean/std/RMS를 분리; Full–Direct와 Direct–surrogate 오차 분해; R4-B signed mean 악화도 기록 | 기존 D3 + V1 |
| §1.3 상관 | 시간순 ACF 표 | 정적 field를 주행하며 읽은 지속성으로 표현. 독립 시간 drift/kernel은 주장하지 않음. 의미 있는 투영상관이 확보되면 보충 | V4 조건부 |
| §2.1 모델 구성 | EXDS Range mean replacement, sigma hand table | 물리 기반 h/J와 경험적 R를 명시적으로 분리. table이 true missing variance를 유일하게 복원한다고 쓰지 않음 | D3/E[V]·V3 |
| §2.2 재귀 갱신 | prediction 전 sigma lookup, 원본 4-state | same-prior gain shrink 항등식과 range/pol signed update 구조. 실제 recursive prior/gate 변화는 별도 | V2 F2 |
| §3.1 설정 | 12조건, seed0,t>=30, self 비교 | 동일 구조/하이퍼파라미터 vs route별 학습가중치 구분; 표본 분모·학습–예측·hash 연결 | V0/V5 |
| §3.2 결과 | 12/12 Heading,8/12 Heading+XY, 전체 표 | variance-only12/12도 추가. 결합의 의미는 R2/R5-B8조건이 양 단독보다 낫다는 비교에서 제시 | 기존 exact scores + V2 |
| §3.3 설명 보강 | fixed/self 구성요소 비교 | constant-vs-lookup 결과를 추가하되 좋지 않아도 포함. fixed 가중치 효과와 self 시스템효과 분리 | V3 F3 |
| §4 한계 | R4-B 작은 heading 이득/XY 악화 | 원인 확정된 범위만 signed correction·prior·gate로 연결. 한 scene·seed0·공간시간 불식별 범위 보존 | C7 + audit |

## 3. 지금 쓸 수 있는 안전한 핵심 문단 (결과 추가 전 초안)
본 연구는 Dual-LP 수신 안테나의 두 직교 선형편파 포트가 로봇 자세와 입사 방향에 따라 보이는 차등 응답을 이용하여 단일 UWB 앵커 환경의 Heading 관측을 구성한다. 포트별 복소 FFD를 실제 송수신 기하에 따라 변환하고, 관측 생성과 일치하는 CIR 및 공통 첫 경로 탭 연산으로 정규화 편파비와 상태 Jacobian을 정의한다. 이를 통해 거리 관측만으로 단일 시점에서 직접 제공하기 어려운 yaw 민감도를 보완하되, 편파 관측이 평면 위치와 Heading에 동시에 의존하는 구조를 4상태 Joint EKF에 반영한다.

다중경로는 포트별 차등 응답과 첫 경로 선택을 변화시키므로, yaw 민감도가 존재한다는 사실만으로 편파 관측을 독립적이고 정확한 각도 제약으로 취급하지 않는다. 보존된 관측에서 거리 평균 교체 전후의 잔차, 편파 잔차의 기하 의존성과 주행에 따른 지속성을 구분하고, CIR·인접 tap 편파 특징으로 예측한 전체 거리 오차 평균의 교체와 거리 조건별 편파 신뢰도 조절을 결합한다. 복소 FFD 관측함수는 물리 기반이며, 추가분산은 잔여 모델오차의 영향을 보수적으로 다루는 경험적 설정으로 구분한다.

선택한 R2-B·R4-B·R5-B의 네 gyro-bias 조건에서 기존 동일 구조를 적용한 결과, Heading RMSE는12조건 모두 감소했다. R2-B·R5-B의8조건에서는 결합이 두 단독 개입보다도 두 지표에서 우수했으나, R4-B에서는 분산 단독이 결합보다 우수하고 작은 Heading 이득과 XY 악화가 공존했다. 이는 관측 잔차 제곱오차 감소와 재귀 상태추정 오차 감소가 동치가 아님을 보여주는 제한 조건으로 남긴다.

위 문단은 기존 증거만으로 쓰는 문장이다. ‘어떤 signed update가 개선을 일으켰는가’, ‘거리 lookup 자체가 더 좋은가’는 V2/V3 결과 전에는 확정하지 않는다.

## 4. 결과가 들어올 위치와 조건부 문장
- V1 지지: ‘선정한 세 경로의 안정 detector 구간에서 J_spsi와 포트별 차등 응답을 확인하였다’ 뒤에 실제 분모·Fig1을 추가한다. 전상태 관측가능성의 증명으로 확대 금지.
- V2 지지: ‘공통 prior에서 [확인된 range/pol correction 변화]가 나타났으며, fixed 재귀에서도 [실제 효과]가 유지됐다.’ 실제 값과 trace가 없으면 빈 문장으로 남긴다.
- V3 지지: ‘이 비교에 사용한 train-only 상수보다 lookup이 [범위]에서 [효과]였다.’ MIXED이면 case별 결과를 보고하고 universal distance advantage를 쓰지 않는다.
- V4가 ACF밖에 지지하지 않음: ‘시간순 상관은 설계 동기이며, 본 모델은 full temporally correlated likelihood를 구현하지 않는다.’를 유지한다.
- V5 model weight 없음: ‘보존된 학습 예측을 사용한 재생’으로 제한하고 온라인 학습·실시간 새 inference를 검증했다고 쓰지 않는다.

## 5. 그림·분량 원칙
main figures는 F1 물리 관측/J/잔차, F2 same-prior 갱신, F3 constant 대 lookup의 최대3개를 목표로 한다. 기존 Table3 12조건을 삭제하지 않는다. mean/std/RMS 및 ACF의 세부 packet 표, hash/source, negative tests, 분모 차이는 보충자료로 보낸다. RA0–RA5의 전 이력을 본문에 재현하지 않으며 원고의4단계 논리를 유지한다.

## 6. 실제 개정 인수 조건
새 원고는 기존 파일을 즉시 덮어쓰지 말고 버전별 commit을 남긴다. 모든 새 결과문장에는 claim_id·artifact·run_id·independent verdict와 분모를 연결한다. 기존12조건 수치가 달라지면 변경된 모델 결과로 재정의하기 전에 source/parity 차이를 먼저 조사한다. 저자는 최종 결론과 범위를 정하고, 제안자는 설계–근거 연결을 검토하며, 구현자나 자동CI가 독립 감사 또는 원고 승인을 대신하지 않는다.
