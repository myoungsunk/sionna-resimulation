# Signed a_i a_j 느린 공분산 검증 결과

**과학 판정: INCONCLUSIVE.** 이번 자료에서 signed heading 등가 공분산의 필요성을 입증하지 못했다. 실행·감사 상태와 모형 지지는 분리한다. 독립 감사 결과는 [AUDIT_KO.md](AUDIT_KO.md)에 기록한다.

기준 계획은 `bd28eac6a0e235412bdced9f08505148191e39d2`. 기존 M7·G-T2/G-V 봉인·S2′ STOP·Step3 HOLD는 유지했다. RF 생성, EKF 재생, M7 모수 수정·채택은 하지 않았다.

## 주 분석

원시 noise-free Full O30−LoS O30와 실제 RF 생성 pose에서 구한 signed ∂s/∂ψ [s/rad]를 사용했다. donor 평균·모수만 학습했고 holdout 평균은 주 점수에 사용하지 않았다. S0=qK, S1=qK+θ diag(a)Kdiag(a), S2=qK+u diag(|a|)Kdiag(|a|). 점수는 높을수록 좋으며 nats/packet이다.

10 s cluster 안의 앞/뒤 5 s×원본 시간 인덱스 짝/홀로 component를 고정했다. 모든 적격 packet은 정확히 한 번 쓰고 off-diagonal lag는 0.4–5 s 안이다. 2,000회 짝 bootstrap(seed20261116), 주 구간은 10 s이며 5/20 s는 보조다.

| 궤적 | 공통 거리 | packet / cluster | S0 | S1 signed | S2 unsigned | Δ10 [95% CI] | Δ12 [95% CI] | 판정 |
|---|---|---:|---:|---:|---:|---|---|---|
| R2 | 6–10 m | 330 / 10 | 0.567614 | 0.573362 | 0.571784 | +0.005747 [-0.739116, +0.557908] | +0.001578 [-0.002541, +0.008005] | INCONCLUSIVE |
| R4 | 6–10 m | 235 / 6 | -0.703163 | 0.076369 | 0.077028 | +0.779532 [+0.007508, +1.905170] | -0.000659 [-0.001624, +0.000631] | INCONCLUSIVE |
| R5 | 없음 | 0 / 0 | — | — | — | — | — | NO_SUPPORTED_FOLD |

R4의 S0 대비 개선은 확인되지만 signed 대 unsigned 차이는 확인되지 않았다. R4 전체·근거리 또는 R5의 signed 구조로 일반화하지 않는다. pooled로 합쳐 지지 부족을 가리지 않는다.

## Signed contrast와 반증 대조

매칭한 양수 a_i a_j 쌍의 e_i e_j 평균에서 음수 쌍 평균을 뺀 값이다. 주 잔차는 donor 평균만 뺀다.

| 궤적 | S1 예상 contrast | 실제 raw contrast [95% CI] | 유효 bootstrap / 시도 |
|---|---:|---|---:|
| R2 | +0.003771 | -0.029890 [-0.065292, -0.000142] | 1988 / 2000 |
| R4 | +0.023420 | -0.004307 [-0.012003, +0.000416] | 1984 / 2000 |

R2는 예상과 반대 방향이며 donor p99 winsor에서도 유지된다. R4는 contrast CI가 0을 포함한다. 부호가 한쪽만 들어온 bootstrap draw는 contrast를 정의할 수 없어 무효로 기록했다. 유효 sign cluster는 R2 4개, R4 5개다.

N2/N3는 양쪽 모두 `NO_PERMUTABLE_BLOCK_SUPPORT`, 시간 holdout도 세 궤적 모두 `NO_SUPPORTED_TEMPORAL_FOLD`다. 해당 검사가 통과했다고 표현하지 않는다. 보수적 층화·guard에서 지지가 사라진 결과이며 검사 규칙을 사후 완화하지 않았다.

## 입력·수치·모수

P0 관측 O30 독립 재계산 차이 0, tap 일치. SourceFFD–raw LoS 최대 s 차이는 R2 1.048e−5, R4 2.362e−6, R5 5.140e−6으로 사전 max1e−4 이내였다. 안정 구간의 ±0.1°/±0.01° 차분도 최대 정규화 오차 2.09e−5/2.10e−7로 문턱 이내다. 불연속점은 기록하며 공분산 자료에서 자동 제외하지 않았다.

정확히 중복된 arc/yaw만 S0 예비 적합에서 축약한다. 중복 잔차가 다르거나 비중복 unique kernel이 near-singular면 중단한다. ε=1e−8 max(q0,1e−6)는 donor S0로 한 번 정하고 모든 모형에 공통 사용했다.

| holdout | q (s²) | θ (rad²) | √θ (degree) | ε | θ=0 경계 |
|---|---:|---:|---:|---:|---|
| R2 | 0.003691795 | 0.08053083 | 16.259 | 1.0923e-09 | False |
| R4 | 0.01601365 | 0.05939817 | 13.964 | 5.7654e-10 | False |

이 raw RF 공분산 모수는 M6의 느린 성분 기반 σθ≈2°와 정의·적합 대상이 다르다. 수치가 물리 yaw bias의 표준편차임을 뜻하지 않는다. 모수 수는 S0/S3 1개, S1/S2 2개이며 in-sample 이득은 증거로 사용하지 않았다. Gaussian 가정·꼬리 통계는 RAW_RESIDUAL_DESCRIPTIVE.json, condition/Cholesky는 p3/HOLDOUT_SCORES.json에 남겼다.

## 평활의 인공 상관·민감도

동일 D3 알고리즘에 독립 백색 잡음을 통과시킨 200회 대조다. 수치는 평균 pair product/주변분산이며 Monte Carlo 구간을 RF 일반화 CI로 해석하지 않는다.

| 궤적 | 원시 백색 | 겹치는 평활 창 | 비중첩 창 | 독립 백색 stream 교차 |
|---|---:|---:|---:|---:|
| R2 | -0.0005 | 0.4666 | -0.0218 | -0.0018 |
| R4 | 0.0013 | 0.4926 | -0.0077 | 0.0076 |
| R5 | 0.0002 | 0.4781 | -0.0055 | -0.0005 |

따라서 D3 평활 잔차만으로 물리 상관을 입증할 수 없다. 주 분석은 평활하지 않은 원시 RF 잔차를 사용했다. D3 원본 slow/eps는 별도 정의로 비교하고 합치지 않았다. 고정 E0 gate 교집합·D3 지원 교집합·전체 g 민감도는 supplemental/FIXED_FIT_SENSITIVITIES.json, 고정 kernel 4조합·donor별 중심화·oracle holdout 중심화·winsor는 p3/SENSITIVITY.json에 전부 보고했다. 어느 결과도 주 모형 선택에 쓰지 않았다.

## 별도 앵커·TEACH/REPEAT 지지

앵커 A는 원본 Full/LoS·SourceFFD·미분을 다시 확인하고 B donor 모수를 동결 적용했다. A·R2/R5는 지원 부족이다. A·R4 176 packet/4 cluster에서 Δ10=+0.911546 [−0.037869,+1.860961], Δ12=−0.003090 [−0.006986,−0.001168]로 unsigned가 더 좋았다. 보조 이전 진단이며 B의 주 판정과 합치지 않는다.

비봉인 G-T1_B 원본만 KMS 계정으로 읽어 확보하고 manifest SHA를 확인했다. 7,872개 원본 RF pose와 8,888개 protocol label row를 구분했다. TEACH/REPEAT·회전에서 양/음 감도는 존재하지만 elapsed-time 필드가 없어 0.4–5 s 쌍이나 독립 10 s cluster를 만들지 않았다. sequence_index를 초로 바꾸지 않았으며 기하 지원표만 게시했다. G-T2/G-V는 열지 않았다.

## 수정 이력·감사·재현

- attempt01은 RF JSON의 6자리 직렬화와 evaluator 원정밀도 차이를 1e−10으로 비교해 STOP했다. 원본과 실패 코드는 보존했다. 실제 RF 생성 좌표를 primary로 하고 round6 exact provenance를 검사하는 수정안만 감사 후 attempt02로 진행했다.
- 초기 P1의 donor 간 매칭 오류는 감사가 발견했다. donor별 선매칭으로 수정하고 p1_revision_02를 새로 동결했다. 이전 파일은 보존했다.
- 초기 P2의 작은 고유값 제거 범위를 exact duplicate로 제한하고 signed ML→heldout·rad/degree refit 검사를 추가했다. revision02 T00–T09와 실제 runner 정보 차단을 독립 재실행한 뒤에만 P3를 승인했다.
- P3 원 JSON은 마지막 R5 continue 뒤 저장되지 않아 R5 key가 없다. 재생·적합을 다시 하지 않고 PRIMARY_SUMMARY.json과 CSV에 NO_SUPPORTED_FOLD, n=0을 명시했다. 원 JSON은 수정하지 않았다.

검증 코드·동결 계약·배열·원본 입력 해시·단계 해시·명령은 같은 attempt와 상위 코드 폴더에 있다. Git 기준은 계획 commit이고 실행 코드는 새 파일 SHA로 고정했다. 실행·독립 감사 완료는 signed 가설 지지 또는 H3 채택을 뜻하지 않는다.

허용 문구: **시험한 장면의 공통 원거리 지지에서 R4의 공분산 확장은 s-only보다 예측력이 높았으나, signed Jacobian 구조의 필요성은 확인되지 않았다. R2의 signed contrast는 예측과 반대였다.**
