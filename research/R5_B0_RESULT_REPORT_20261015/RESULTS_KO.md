# R5-B0 물리 품질 Hard/Soft RF 융합: 단계별 재감사 및 실행 결과 (2026-10-15)

## 0. 범위와 기준선
- 연구 소스 계보: `PHYSICS_RS_STAGED_20261015` 기준 고정 커밋 `b437fd154a9cf38f6b0bfe11a21c59ca63e0b25e`; 후속 브랜치 `research/r5-b0-hard-soft-physics-20261015`.
- 원본 J4/S4/SR4, RF LUT/FFD, UWB Range, `R0=diag(0.0068578637,0.0081)`, gyro motion input **변경 없음**.
- 실제 Gyro Bias는 **B0=0°/s**, estimator 상태 `[x,y,ψ,b_g]`의 `b_g`는 **추정 가능한 상태로 유지**. RF 오염이 0-bias에서도 거짓 bias를 유도할 수 있는지를 관찰.
- 훈련은 R4/R5만, R2 전체 held-out. R2 Anchor A mount0/45, paired Full/LoS, sensor seed0 각 979 프레임 중 t≥30s 829 평가 시점. 단일 corridor/scene/seed.
- Physics `G0,G2,G3,G4,G5`는 원래 `features.py` 그대로. G3/G5의 complex-frequency Jones features는 원 DWM1000 하드웨어에서 추출 가능하다는 증거 없음 (research-only).

## 1. 실제 감사와 소스
- [최종 Cloud Run 38688494790](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38688494790), source `41cb0e7e8f0e11d4dc4c89f77d2320b1477258d1`.
- [원시 x/P, 측정·품질·G5 결과 artifact 11951360261](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38688494790/artifacts/11951360261), artifact ZIP SHA256 `f31a04cf2ba39011a5d685b13985b947b1659e5b63c3a5910ec68175fa7e806a`.
- 최초 Run 38688382468은 list-valued split metadata를 Pandas 단일 행 DataFrame으로 저장하는 코드 오류로 중단; **폐기**. JSON dictionary 직접 저장 방식으로 수정한 최종 실행에서 preaudit 재수행 및 모든 단계 성공.
- 최종 Preaudit `GO`, 22개 원본 RF/시료 asset SHA256 검사, 7개 수치 regression/negative semantic 검사. 원본 14채널 feature 추출 + 원본 R2 4 trace `z_s,z_r` parity 최대 1e−12 이내.
- 원래 R0 J4와 각 환경의 원본 연산 비교. 3/4 조건 strict1e−9 archive parity, B0 Full Mount0 1조건 max state `7.58e−8`, max P `6.06e−10`, gate 차이0. 이전 Physics RS 연구에도 발생했던 누적 부동소수점 차이이며 strict PASS로 소급하지 않음. 첫12 프레임 원본 scalar-source canary는 별도 1e−12 이내.
- 물리 G5 R_s-only의 기존 보고값 복제: B0 Full Mount0 `4.3038300984°`, Mount45 `1.3487738341°`; Physics 보고의 반올림 값 4.3038°/1.3488°와 정합.

## 2. 사전 고정한 새 비교군
- `DR4`, `R0_J4` (기준).
- `SOFT_G0/G2/G3/G4/G5_RS`: 원래 Physics 방식 `Rs=clip(pred_e_total_squared, .0081, .81)`, joint NIS 99% gate.
- `SOFT_G5_MEAN`: signed conditional mean of `e_total`, learned R4/R5 only, test B0 R2, original Rs.
- `SOFT_G5_MEAN_RS`: signed mean correction + inflation-only G5 Rs.
- `HARD_ALL_G5_p50/p75`: `P(|eMP|>.1|q)` proxy > 0.5/0.75면 range+s 모두 버림.
- `HARD_S_G5_p50/p75`: risk above threshold면 s만 버리고 Range-only scalar gated update.
- `HARD_S_G0_p50`: G0-only proxy control.
- `HARD_S_G5_p50_RANDOM_MATCH`: test case별 risk mask 개수와 동일한 고정 난수 대조, 배포용 아님.
- 동일 gyrobias B0 controls/initial perturbation 사용, 원본 추정기에 GT/oracle 입력 금지.

## 3. B0 Full RF Heading RMSE

| Method | Mount0 (°) | Mount45 (°) |
|---|---:|---:|
| DR4 | 0.483996 | 0.483996 |
| R0_J4 | 7.489960 | 0.844960 |
| SOFT_G0_RS | 5.844317 | 1.094342 |
| SOFT_G2_RS | 4.270782 | 1.399023 |
| SOFT_G3_RS | 4.686569 | 1.383262 |
| SOFT_G4_RS | 4.681237 | 1.559029 |
| SOFT_G5_RS | 4.303830 | 1.348774 |
| SOFT_G5_MEAN | 4.598999 | 1.182711 |
| **SOFT_G5_MEAN_RS** | **3.362419** | 1.350003 |
| HARD_ALL_G5_p50 | 5.806109 | 4.010993 |
| HARD_ALL_G5_p75 | 5.806148 | 1.109492 |
| HARD_S_G5_p50 | 5.013281 | 3.590724 |
| HARD_S_G5_p75 | 5.451263 | 1.315785 |
| HARD_S_G0_p50 | 5.676353 | 4.425602 |
| HARD_S_G5_p50_RANDOM_MATCH | 7.171618 | 1.155036 |

**판정:** signed mean+Rs가 Mount0 기존 J4 대비 약55.1% 개선하나 Mount45에서 악화. B0 DR4 0.484°는 여전히 전 RF 융합 대비 정확. 새 정책 전역 채택 실패, 국소적 RF 개선만 관찰.

## 4. 신뢰도·Bias / Pose 악화

| B0 Full | Mount0 R0 | Mount0 G5_MEAN_RS | Mount45 R0 | Mount45 G5_MEAN_RS |
|---|---:|---:|---:|---:|
| Heading NEES | 87.490 | 11.998 | 3.834 | 5.792 |
| Heading 95% coverage | 17.129% | 36.309% | 59.107% | 43.064% |
| Pose NEES | 2591.147 | 347.896 | 86.872 | 134.355 |
| Pose 95% coverage | 17.129% | 17.732% | 0% | 0% |
| Final b_hat (deg/s, true=0) | +0.014318 | +0.021247 | −0.000601 | −0.000950 |

범용 과신 개선 없음. 특히 수렴 Heading RMSE가 낮아도 4-state에서 강한 가짜 bias 또는 x,y 조건부 과신이 남을 수 있음.

## 5. 실제 Hard Gate MP proxy가 Heading 위해성을 판별하는가?

추가 고정 분석:
- [원본 J4 사전/사후 Heading 위해성 Run 38689008284](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38689008284), source `b4fa00b8d95687cb686c91f3fc5a846b3ef4f0cf`.
- [오프라인 시점별 3,912행 artifact 11952230425](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38689008284/artifacts/11952230425), artifact ZIP SHA256 `1ecf12151cb12b828ea07eeb51f482bf62ba5d63159f5bb04d6ae65f8f34feb0`.
- Train: Full RF R4/R5, test B0 R2. `|s_full−s_nativeLoS|>.1` MP proxy AUROC = Mount0 `0.858584`, Mount45 `0.864079`, Brier `0.133213/0.149832`. **AUROC ≠ packet별 84% 검출 확률**.
- MP proxy high `p>.5` 비율: Full Mount0 19.02%, Full Mount45 40.18%; LoS Mount0 29.86%, LoS Mount45 43.46% — clean LoS를 과도하게 배제하는 경향.
- 기존 R0 J4의 실제 수용 업데이트에 대해 `(post ψ−GT)²−(prior ψ−GT)²>0`인 시점 비율 (독립 GT offline):
    - Full Mount0 low q: 44.23% (n_applied=789), high q: **32.81%** (n_applied=128).
    - Full Mount45 low q: 46.58% (n_applied=571), high q: 49.34% (n_applied=227).
- 동일 조건 Mount0의 평균 signed 오차 제곱 변화: low q −0.17279 deg², high q −0.51362 deg². high MP risk에서 오히려 원래 J4 갱신이 평균적으로 더 유익한 경우가 확인됨.
- 오프라인 위해성은 **기존 Joint4 경로의 한-step update harm**으로 정의되며, 다른 Gate 정책의 새로운 재귀 궤적에 대한 반사실은 아님. Hard Gate의 재귀 후과는 앞 실험에서 따로 직접 측정함.

**핵심:** `P(MP proxy bad|q)`를 직접 Hard RF 폐기 확률로 해석하지 말 것. 원래 물리 오염의 강도보다 현재 DR prior/geometry/Jacobian과 결합된 **조건부 Heading 업데이트 위해성/정보량**이 중요.

## 6. 후속 판정
- `technical_experiment=PASS` / `full_operational_scientific_PASS=false`.
- Hard MP-proxy gate: 전역 채택 중단. 데이터 기반 원인 검사 완료.
- Soft signed mean+Rs: Mount0 개선·Mount45 후퇴, NEES 여전히 큼. 모델의 조건부 평균·분산, R_r / R_rs / cross-time correlations 및 pose covariance로 확장할 필요.
- Bias-free ground truth B0 우선 유지하되, 3-state(b 고정)와 4-state(b 자유) 추가 비교해 가짜 Gyro Bias에 의한 Heading 오류 증폭 여부 검토.
- 실제 RF가 Heading을 돕는지 여부를 예측하는 목표로 quality target 전환 (훈련·평가 scene disjoint, prior/innovation/geometry 포함), 동시에 Dynamic LoS Gradient + CIR/편파 물리 피처의 추가 정보 검증.
- 별도 Heading scan factor를 적용할 때 scan packet은 일반 J4/SR4에서 중복 사용하지 않음.
