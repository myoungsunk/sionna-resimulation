# Stage 2·3·5 수정 결과에 따른 과학적 판정 프로토콜

> 결과를 보기 전에 해석 프레임을 고정한다. 이 파일은 코드를 실행하지 않으며 어떤 성능 수치도 예측하지 않는다.

## 비교 순서

1. **동일한 원본 데이터인지**: 450a21f commit 및 old Stage 2 residual SHA와 Stage 3 legacy ALL parity가 일치하지 않으면 모든 후속 비교 무효. Stage 3 OFF의 E1 parity 기준은 절대오차 1e-10이다.
2. **Stage 2 시간상관의 정의**: `lagN_n_pairs`가 충분한 셀만 평가한다. 필터링한 표본 배열의 ACF가 아니라 원래 Full RF의 native index 차이 N에 대응하는 ACF만 사용한다. packet lag와 실제 경과시간 분포를 함께 보고한다.
3. **Stage 2 공분산 부호 안정성**: `bootstrap_stability`가 `STABLE_POS/NEG`일 때에도 이는 8/16/32초 블록 부트스트랩에 대한 민감도 기준일 뿐, 인과적 상관 확정이 아니다. 3가지 길이 중 일부 NA면 불확실성을 명시한다.
4. **Stage 3 모집단 효과**: `R_SAMPLE_CONTRASTS.csv`에서 같은 `mean_model`, `structure`를 고정하고 `accepted_A_B`-`all` 차이를 비교한다. 대각/전체 R 교체 효과는 동일 모집단 내에서 별도로 비교한다. route-heldout B0 학습이고 test route/bias 재학습은 금지.
5. **Stage 3 성능 지표**: 실제 Heading RMSE·XY RMSE·앵커 거리 RMSE·Heading NEES를 각각 평가하고, 기존 BB의 10% 이상 악화 및 주요 경로 R4_aA 악화 여부를 따로 판정한다. Arm 간 gap 감소만으로 채택하지 않는다.
6. **Stage 5 관측성**: data-only/prior-aided를 나누고, SVD와 eigen rank·회전 gauge·sigma_t가 별도 경로로 일치하는지 확인한다. 0 검산 건을 PASS로 부르지 않는다. 측정 잔차 시간상관이 빠진 Fisher의 σ는 경험적 RMSE가 아니다.

## 후속 실험의 분리

- **이번 패치에 없음**: AR/GM 지속 잔차 state, correlated measurement model의 시간 진화, Stage 4 첫 통과 후 CUT, bias-state/Q 새 스윕, 새 앵커 RF 재생성.
- **새로운 실험 조건**: Stage 2 수정 통계에서 수용 조건부 시간상관이 실제로 확인되고, Stage 3 정적 R 교정만으로 잔여 성능 문제가 남을 때만 별도 프로토콜로 시간상관 상태를 시험한다. 새로운 학습·기준 임계값 조정은 사전등록한다.
- **해석상의 주장 경계**: '오차 상쇄 붕괴' 및 '시간상관 때문에 EKF가 실패한다'는 아직 경쟁 가설이며 이번 패치 PASS만으로 인과 확정되지 않는다.
