# N4-B POL-V1: Mount·Heading 기반 FFD 정합 특징량과 Range–s 오차·신뢰도 재검증

실험 기준일: 2026-10-15

**판정: 실행·원본 정합·수학·독립 결과감사 PASS. 새 FFD 특징량의 범용 조건부 관측오차 모델 채택은 HOLD.**

## 1. 실험 출처와 기존 연구 보존

- 본 실험: [Actions Run 38717297007](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38717297007)
- [본 실험 원시 결과 11963440700](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38717297007/artifacts/11963440700) · SHA256 348c0761e7c6ec06057a5e80b799739e302ba869c9e6d368bce10628a8ba7bae
- 독립 검증: [Actions Run 38717840304](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38717840304) · [추가 수치 결과 11963516070](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38717840304/artifacts/11963516070) · SHA256 41dea0c1f19b8742ab07c395a2096bbd0087e3d6c2524a7b7df0e8e7d4e41b57
- [실험 소스](n4b_pol_geometry.py) · [독립 감사 소스](n4b_pol_review.py) · 두 GitHub Actions workflow 함께 보존
- 원 Full/LoS 22개 원본 파일 SHA 검증, 14,502개 원 P3 Range·s 관측 재현, 원 N4-B 6개 모델 × 9,519개 관측 = **57,114개** 조건부 평균/공분산/NLL 정합 확인 (허용오차 ≤1e−8).
- Frozen LoS LUT 2° FFD / Range detector / EKF4 Joint4/SR4 / R0 보존. 이 N4-B에서는 새 EKF 필터를 실행하지 않음.
- 새 모델 9개 + 보존 기존 모델 6개 = 15개. 원 N4-B와 동일 Ridge alpha30, 동일 route held-out, 동일 공간 중복 제거, 동일 binning/shrinkage.
- 본 실행 전 3차례의 실패 실행(단위테스트 schema 연결, 라이브러리 검색경로, 샘플 yaw/원본 robot route 불일치)을 결과로 쓰지 않음. 최종 실행에서 원 R2 RF trace의 exact truth/time/pose_id만 사용하도록 수정 후 재감사.

## 2. 실제 FFD 편파 작동점

사용자 제공 이상 LP 각도식의 포트 축 간격을 π/2로 구별한다. 단순 mount+heading 상대각에는 Anchor 상대 방위·입사 고각·TX/RX FFD 편파 투영이 빠지므로 반드시 Frozen LUT를 기준으로 한다.

- 예상 LoS 포트 전력 분배 M1=(1+s_LOS)/2, M2=(1−s_LOS)/2.
- 우세도 Mdom=max(M1,M2), 균형도 B=1−s_LOS².
- 실제 LUT Jacobian Hψ=∂s_LOS/∂ψ; unit test에서 2개 실제 3D FFD 좌표 finite difference PASS.
- 명목 정보량 Iψ_nom=Hψ²/(R0s+Hxy Pxy_nom Hxyᵀ), Pxy_nom=diag(0.1²,0.1²) m². **실제 필터 prior를 쓴 정보량은 아래 별도 비교**.
- RX/TX 상대 azimuth는 Frozen EKF4와 동일 φtx=atan2(−v,u), φrx=atan2(−v,−u)−(ψ+mount)와 송신 고각을 사용한다.
- M1, M2, Mdom, B는 동일 LoS s_LOS에서 계산된 결정론적 변환이고 독립 관측 4개가 아니다.
- 실제 강한 포트의 FP 전력 및 물리 SNR과 예측 정합 포트 비율은 다른 의미다.

### R2 Anchor A, FULL RF 대응된 정답 Pose LoS 작동점 (중앙값)

| 특징량 | Mount0° | Mount45° |
|---|---:|---:|
| 예상 LoS 우세 포트 비율 | 0.91337 | 0.68386 |
| 예상 LoS 포트 균형도 B | 0.31651 | **0.86479** |
| 실제 FFD abs(Hψ), rad⁻¹ | 0.51568 | **1.63864** |
| nominal Iψ, rad⁻² | 32.13 | **318.48** |
| 단순 코사인 port1 match−실제 FFD M1 절대차 | 0.44915 | 0.61354 |
| Full signed s residual μs | +0.04850 | +0.00692 |

**해석:** Mount45의 기존 Heading 우세를 단일 co-pol 강포트의 전력 정합만으로 설명할 수 없다. 오히려 두 수신 포트 균형과 실제 FFD Jacobian이 Mount45에서 더 높은 것이 관찰됨. 이 표의 정보량은 LoS 명목 수치로, Full RF systematic error와 연속 상관을 포함한 실제 Heading 정보량은 아님.

## 3. N4-B 조건부 Gaussian 평가: 정답 Pose 기반 기하 상한

동결 Full RF 9,519관측·same-corridor 3route leave-one-route-out. 수치가 낮을수록 joint NLL이 좋음.

| 특징량 그룹 | 평균 joint NLL ↓ | 95% joint 포함률 |
|---|---:|---:|
| 원 R0 | +0.01700 | 85.28% |
| 기존 Simple diagonal | **−1.59720** | **94.66%** |
| Simple+우세 포트 비율 | −1.30895 | 91.49% |
| Simple+LoS balance | −1.33552 | 91.23% |
| Simple+signed s_LOS | −1.45134 | 93.16% |
| Simple+실제 FFD Hψ | −1.58514 | 94.66% |
| Simple+nominal Iψ | −1.53065 | 94.30% |
| Simple+Heading/Mount 주기각 | −1.52788 | 94.31% |
| Simple+전체 FFD 기하 | −1.35467 | 90.41% |
| 기존 Simple+G4 detector features | **−1.70385** | 92.58% |
| Simple+G4+전체 FFD 기하 | −1.63505 | 90.58% |
| 기존 전체 G5 연구용 | −1.45860 | 87.00% |
| **G5+FFD 기하 연구용** | **−1.80132** | 90.26% |

**핵심:** 해석 가능한 Simple 물리 모델은 대부분 FFD 특징량을 추가해도 개선되지 않았다. 단순히 Balance가 크거나 정합도가 높다는 이유로 Rs를 낮추면 안 된다. G5+FFD는 pooled NLL −0.3427 개선 (180개 동일 복도 공간블록 CI [−0.5612,−0.1077])이나 R2 세 테스트 사례에서는 모두 악화.

### 기존 모델 대비 증분 효과 (NLL 차이, 음수=개선)

| R2 holdout case | Simple+Hψ vs Simple | SimpleG4+FFD vs SimpleG4 | G5+FFD vs G5 |
|---|---:|---:|---:|
| AnchorA Mount0 | +0.0090 | −0.0252 | +0.2359 |
| AnchorA Mount45 | **+0.0272** | **+0.0690** | **+0.0591** |
| AnchorB Mount0 | +0.0056 | −0.0721 | +0.1033 |

G5+FFD의 전체 점수 이득은 R4/R5 평가에서의 매우 큰 개선에 의해 주도된다. 훈련 R4/R5에는 Mount45가 없으므로, R2 Mount45 일반화 성공으로 주장 불가.

추가 공간블록 95% 구간:
- Simple+signed s_LOS vs Simple: +0.1459 [0.0869,0.2163] → 악화
- Simple+Balance vs Simple: +0.2617 [0.1730,0.3624] → 악화
- Simple+Hψ vs Simple: +0.0121 [0.0042,0.0207] → 작은 악화
- Simple+Iψ vs Simple: +0.0665 [0.0350,0.1014] → 악화
- SimpleG4+FFD vs SimpleG4: +0.0688 [−0.0400,0.1965] → 추가 효과 미확정
- G5+FFD vs G5: −0.3427 [−0.5612,−0.1077] → pooled 개선, R2 악화

## 4. Mount·Heading 작동점별 Range/s 오차는 실제로 달라지는가?

R2 AnchorA FULL RF에서 정답 Pose FFD |Hψ|=1 rad⁻¹를 사전에 정한 층화 기준으로 사용.

| Mount | |Hψ| regime | 표본 | μs | Vs | Corr(e_r,e_s) |
|---|---|---:|---:|---:|---:|
| 0° | 낮음 | 967 | +0.05246 | 0.03941 | +0.6429 |
| 0° | 높음 | 336 | +0.03713 | 0.03903 | +0.2476 |
| 45° | 낮음 | 477 | +0.04689 | 0.07693 | +0.4085 |
| 45° | 높음 | 826 | **−0.01616** | **0.03668** | **−0.2627** |

Mount45에서 FFD Heading Jacobian이 높은 구간은 낮은 구간보다 s 중심분산이 약 52% 낮으며 Range–s 상관의 부호도 달라졌다.

그러나 이는 동일 복도·Anchor·Route의 위치/상대방위·FP 검출변화와 공변할 수 있다. |Hψ| 증가 그 자체가 RF 분산 감소의 독립적인 인과 원인이라고 단정하지 않는다.

포트 Balance가 높은 것 자체도 s 분산 감소 충분조건이 아님: Mount45 B>0.8 그룹 Vs 0.05199, B≤0.8 그룹 Vs 0.05290. 모든 그룹의 μr, μs, Vr, Vs, Crs, ρ와 수량은 독립 감사 결과 CSV에서 확인 가능.

## 5. 실제 EKF 갱신 이전 Pose/P를 사용한 편파 정보량 신뢰도

R4/R5 **정답 Pose 기하**로 학습한 Simple+FFD를 R2 원본 Joint4의 RF 갱신 **직전** 추정 Pose/P로 재계산. 비교 평가 pose/time/id 979개/조건이 원 archive와 일치; R2 sample Pose와 archived truth 최대 차이 5×10⁻⁷ 이내.

| R2 case, Full RF | 정답 Pose 모델 NLL | J4 pre-RF Pose 적용 NLL | oracle 95% | pre-RF 95% |
|---|---:|---:|---:|---:|
| M0 B0 | −1.8127 | −1.6552 | 97.34% | 97.04% |
| M0 L2 | −1.8127 | −1.8036 | 97.34% | 97.34% |
| **M45 B0** | −1.0564 | **−0.7575** | 87.74% | **79.67%** |
| **M45 L2** | −1.0564 | **−0.7688** | 87.74% | **80.18%** |

**핵심:** 실제 pre-RF Heading이 이미 오염된 상황에서 피처의 LoS 예상 편파 작동점이 바뀌고, 특히 Mount45에서는 새로운 품질 예측이 악화한다. 학습은 여전히 oracle GT 기반이므로 이 결과가 실전 배포형 정상화 likelihood를 제공한다는 의미는 아니다.

## 6. 최종 게이트

- **기술실행 PASS**: 물리 특징량 재정의, actual FFD Hψ/azimuth, 기존 N4-B 57,114 baseline prediction parity, 15 모델 비교, 9,519 Full 데이터, R2 pre-RF Joint4 prior 스트레스, Mount별 조건부 RF 구조 감사.
- **관측된 물리 효과**: Mount45에서 높은 포트 균형과 Heading Jacobian/명목 정보량; 기하 작동점에 따라 편파 오차·Range–s 상관 분포가 바뀜.
- **미입증**: FFD 새 피처의 전역 held-out likelihood 개선, 실제 pre-RF prior 학습·보정, 독립 장면 일반화, LoS에서의 거짓 신뢰도 보정 감소, 정규화 p(z|x), 실주행·EKF Posterior NEES 개선.
- **N4-C와의 관계**: 기존에 확인된 POWER_JOINT 동결 후보를 대체하거나 성능을 소급 향상 주장하지 않는다. POL-V1는 신뢰도 예측을 geometry/stress 층화할 분석 근거로 보존. 향후 실제 prior uncertainty marginalization/독립 Anchor+Mount 검증을 거친 뒤에만 EKF covariance에 적용.
- 과학적 모델 채택 **HOLD**.

재현 원자료: 본 실행 POL_V1_FINAL.json, POL_V1_GEOMETRY_ORACLE.csv.gz, POL_V1_HELDOUT_PREDICTIONS.csv.gz, POL_V1_PRE_RF_PRIOR_TRANSFER.csv, POL_V1_BLOCK_BOOTSTRAP.csv; 독립 감사 POL_V1_AUDITED_CASE_REVIEW.json, POL_V1_GEOMETRY_STRATA_RS.csv, POL_V1_MOUNT_CASE_INCREMENTAL_NLL.csv, POL_V1_CAUSAL_PRIOR_AUDIT.csv.
