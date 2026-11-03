# DLP-R1B-CH4-001 — P2 보정 전 관측오차 분석 상태

**상태: `NOT_RUN`.** P0의 동결 복소 채널 RMS 기준이 실패하여 P1 전체 917개 pose의 RF 생성이 열리지 않았다. 따라서 917개 관측 시계열과 평가 767개 시점에 대한 평균·표준편차·조건부 통계 및 그림은 산출하지 않았다. 8개 canary의 원시 관측은 P0 검증 근거로만 남겼다.

## 유지한 분석 정의

관측은 `z=[r, s]ᵀ`이며 다음 식은 추가 평균 보정을 적용하기 전의 오차를 정의한다.

\[
\mathbf e_k^0=\mathbf z_k^{Full}-\mathbf h(\mathbf x_k^{GT})
=\big(\mathbf z_k^{Full}-\mathbf z_k^{LoS}\big)
+\big(\mathbf z_k^{LoS}-\mathbf h(\mathbf x_k^{GT})\big).
\]

첫 성분은 같은 pose에서 Full과 독립 Native LoS의 관측 변화다. 두 번째 성분은 Native LoS 관측과 동결 SourceFFD 연속 모델의 차이다. 두 번째 성분을 미리 0으로 놓거나 첫 성분만을 전체 관측오차로 보고하지 않는다. 기존 거리 bridge는 유지하며, 이 오차 정의에서 추가 평균·학습 보정을 하지 않는다.

Source–Native LoS 관측기 정합 통과는 Full 관측오차가 작다는 뜻이 아니다. H 정합 게이트, Full–LoS 관측 변화, GT 기반 관측오차, EKF 혁신은 서로 다른 양이다. 기존 평균을 제거한 잔차를 보정 전 오차로 표시하지 않는다.

## 재개 후 필요한 산출물

전체 917개 원본 시각의 Full/LoS, 두 오차 성분과 합, tap·strongest-port·직접경로 식별을 같은 pose ID로 묶어야 한다. 시간·경로 단계·거리·각도·민감도별 집계는 동결 구간과 표본 수를 함께 보여야 한다. 전체 원시 관측과 P3 평가 구간 `t >= 30 s`를 구분하며, canary 8개를 전체 경로의 표본 통계로 대체하지 않는다.

이 문서는 실행 상태와 분석 계약을 남긴 것이다. 관측오차 그림·성능 개선 주장의 결과 보고서로 사용할 수 없다. 중단 근거: `08_QA_PARITY_AND_LIMITATIONS.json` 및 `audits/P0_CANARY_RAW_AUDIT_FINAL.json`.
