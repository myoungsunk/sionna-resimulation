# 실제 RF 특징 기반 패킷 보정 선택 — G0/E0–E7 실행 및 비누출 계약

작성 2026-10-23. Source frozen \`cf7a17e5ae6d373c76342b3e3079f565e22a4a14\` (원본 데이터·P1R·P2-A/사다리 1–4 및 기록 불변). 실험 브랜치 \`research/real-rf-packet-selector-20261023\`. 기존 검증의 사후 선택 결과로 유리한 환경을 재선정하지 않는다.

## 목적과 서로 다른 두 질문
1. **오프라인 원인/가능성**: 수신 Full CIR의 feature만으로, 추가 PWIDE 보정이 유익한 packet과 harmful packet을 구분할 통계적 정보가 있는가?
2. **배치 가능한 성능**: 사용자 시간 k의 오직 현재·과거 Full CIR와 \`x_k^-,P_k^-\` 및 train-only POWER μ,V와 fitted PWIDE(held train routes only)만으로 α∈[0,1]를 결정할 때, 정확도·NEES·q99가 기존 BASE보다 개선되는가?

기준 관측: \`z_s^*=sF−μ_POWER−α·Δhat_PWIDE\`, α=0 POWER, α=1 PWIDE.
오프라인 benefit \`D_s=(e−μ)^2−(e−μ−Δhat)^2\`. \`D_s>0\`은 편파 관측 오차 개선에 불과하며 heading improvement와 동치가 아님. B0와 L2가 동일 RF를 재사용하는 경우 독립 sample로 세지 않는다.

## Gate 분리
- **G0/E0–E2 최초 실행**: 원본 \`HP_PACKETS.csv.gz\`, \`HP_SERIES.csv.gz\`, \`R2DIAG_PACKETS.csv.gz\`, 기존 P2 검증의 패킷별 BASE prior(\`L_BASE__d0\`), held-route PWIDE artifacts를 결합한다. B0 평가를 우선하고 L2를 짝진 민감도 분석한다. 현재 BASE prior를 이용한 \`d0\`이므로 복원기는 GT prior가 아니다. 라벨은 \`e_s\` 및 \`s_LoS\`를 사용하는 **오프라인 채점 전용**.
- **E1/E3 우선**: 실제 Full-only F0/F1/F2/F3 특징별 데이터 완전성, harm/benefit 분포, bin과 rank/ROC/AUPRC (방향·임계값 held 선택은 **탐색적**). F2의 \`Jones coherence\`처럼 두 포트 동기위상 필요한 것은 제외. \`FP shift Full−LoS\`, MP-only CIR, GT pose/heading, 정답 \`r_B,r_P,D_s\`, route/case IDs는 classifier features로 금지. 
- **E4 최종 selector 학습 전 필수**: 외부 held H는 PWIDE와 POWER 및 selector 학습 어디에도 사용 금지. 내부 T=2개 route뿐이므로 naive inner OOF에 얽힌 label teacher 누출 가능성을 확인한다. 독립적인 3-way route split은 현재 불가. 분리 불충분한 inner 지표는 *탐색적*이라고 명시한다.
- **E5**: 동일 \`x^-,P^-,R,gating mask\`에서 α=0,1,RF 선택과 GT oracle을 한 번씩 업데이트. 동일 gain·gate로 correction 효과 vs gate·R 변화를 분리.
- **E6**: R2/R4/R5의 7 case, Full B0/L2 정상초기 포함, gyro/odom 동일 스트림, 4state EKF 독립 재귀. base/PWIDE/selector/oracle 비교. t windows 0–2,2–10,10–30,≥30. Heading/XY/q99/NEES/coverage 모두 공개.
- **E7**: R update-only vs gate-only, prior Jacobian, lag1·10 s signed bias를 독립 factorial로 검사. α 선택 상태의 오차-correlation으로 EKF covariance 과신할 위험을 공개.
- E5–E7에 바로 진입해 held H의 성능을 보며 threshold 조정하는 것은 금지. 먼저 G0/E0–E3의 실제 결과와 누출 검사를 통과.

## Source/target 분류
**운용 허용**: Full에서 추출된 sF, log_fp_power, fp_full, s(fp+o), Δs, detector_s_span/energy/delay/port magnitudes, train-only POWER μ,V, BASE/본 filter prior에서 계산한 d0와 HPH, 훈련된 Δhat.
**운용 금지**: \`fp_shift_tap\`, \`mlr_*\`, \`mp_*\`, \`sL_*\`, \`sMGT_*\`, \`e_s\`, \`GT pose\`, true heading/XY error, post-accept mask/future packet, previous results based on held H label.
현재 probe는 BASE prior로 PWIDE 제안을 만들므로 **α 선택을 재귀 갱신하는 운영 모델이 아니다**. Stage 1 결론을 adaptive EKF 성공으로 부르지 않는다.

## QA
- Frozen 3 route: 7 case, 9,519 unique pose. B0와 L2를 분리; packet rows 중복/누락 점검.
- 기존 \`R2DIAG\` oracle d0 기준 PWIDE와 이번 BASE-prior 기준 PWIDE를 혼동하지 않는다.
- B0/L2 pairing time/id and Full \`sF\` parity, 3개 frozen P model의 outer held train_routes H excluded, file artifact provenance, \`PWIDE+μ\` double subtract 금지.
- \`D_s=2r_BΔhat−Δhat²\` algebra exact QA.
- train/test absolute label leakage 없음; 임계값/특징 선택 평가 H에서 수행한 경우 exploratory 명시.
- 회귀/분류 성능과 route-level 재귀 heading 향상을 동일 주장의 증거로 혼용 금지.

## 사전 결정
1. Stage1에서 clean/harm vs severe/benefit의 두 집단 공존과 Full-only feature conditional separation을 정량화한다. If univariate AUROC≈0.5 등 실패하면 E4 feature extension/temporal/active scanning으로 원인 추적.
2. Selector 모델은 train T에서만 alpha/threshold를 고정하며, bias-injection FPR와 correction coverage를 함께 표기한다.
3. Held route BASE 대비 heading RMSE 3route 모두 개선, q99·XY 과도 악화없음, NEES/95% coverage 개선이 최종 조건. 새로운 route/anchor 실측 전까지 일반화 결론 금지.
