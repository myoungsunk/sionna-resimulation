# 극점 theta=0° LUT 수정 후보 — 4-state 재귀 검증 (2026-10-16)

**코드 감사·수치 Jacobian·원본 재현 PASS. 원본 FFD 직접 재생성은 미실행이며 Production 적용 보류.**

## 증거

- 기존 극점 원인 분석: https://github.com/myoungsunk/sionna-resimulation/tree/research/lut-pole-azimuth-singularity-audit-20261016/research/POLE_LUT_SINGULARITY_20261016
- 이번 성공 실행: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38857292101
- 전체 원본/수정 결과 artifact: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38857292101/artifacts/12027528128
- Artifact zip SHA256: 6328e1f2555fe3adacb44e72774665bd50519111b734336082aa9cbe72fe140e.
- 기존 46×180×180 원본 LUT θ=0 층만 s_old[0,0,(j+k+90)%180]으로 변환. θ≥2° LUT 원본 데이터는 완전 동일, 원본 파일은 그대로 보존. 실제 원본 FFD bank는 확보되지 않아 source rebuild 성과라고 주장 금지.
- 원본 RF/R2/N4-B/N4-C archive, 센서·LUT source Git blob 검증, 중앙차분 near-pole Jacobian 검사 통과. 48개 원본 R0/POWER_JOINT 상태·공분산·Gate 기준선 재현 통과.

## 원본 Full RF R0 Mount0, 829개 평가 시점

| Bias / Filter | 기존 Pose NEES | 수정 Pose NEES | 기존→수정 Heading RMSE |
|---|---:|---:|---:|
| B0 J4 | 2591.16 | 356.72 | 7.489960°→7.491321° |
| B0 SR4 | 2150.75 | 335.87 | 7.515656°→7.516035° |
| L0 J4 | 8402.05 | 345.55 | 7.499065°→7.500714° |
| L0 SR4 | 6198.60 | 357.14 | 7.495901°→7.495282° |
| L1 J4 | 383.24 | 337.74 | 7.539918°→7.530548° |
| L1 SR4 | 343.22 | 339.55 | 7.550649°→7.539266° |

## 중요 반증 결과

전체 원본/수정 대비 48개 재귀 조합 중 상태가 유의미하게 변한 조합은 **6개**로 모두 위의 R0/Full/Mount0/B0,L0,L1/J4,SR4에 해당한다. 변경된 RF Gate 판정 0건. 나머지 42개 조합은 수치 동일: POWER_JOINT 모든 Full RF B0/L0/L1/L2 Mount0/45, 원본 R0 LoS 모든 Bias/Mount, Full R0 Mount45 및 Full R0 Mount0 L2 포함.

이유는 원본 POWER 등의 사전 추정이 문제 되는 θ<2° LUT 입력을 방문하지 않기 때문이다. 따라서 극점 수정이 7.5° 수준의 Full R0 Heading RMSE를 낮추는 것이 아니며 POWER_JOINT의 기존 Pose 과신을 고쳤다는 주장도 불가하다.

일부 B0/L0 Full R0의 극단적 Pose NEES에는 극점 특이성에 의한 h/H 왜곡과 재귀 P 수축의 기여가 큰 것으로 드러났다. 하지만 수정 후 Pose NEES 300 이상으로 여전히 매우 크므로 전체 과신 문제가 해결된 것은 아니다.

## 기존 Native LoS 원인 감사 (별도 기존 브랜치)

R5 Anchor B pose706: 진짜 LoS s −0.946821, 원본 LUT −0.069205, 수정 후보 −0.945594. 9519 Native LoS 원본 RMSE .014184→.009616; θ<2° 5개의 RMSE .454941→.001143; θ≥2° 9514개 값 완전히 동일. Jacobian 중앙차분 통과.

## 다음 검증 게이트

원본 FFD 안테나 bank를 확보하여 θ→0+ 근방에서 직접 복소 LoS 채널을 재생성하고 first LUT layer/Jacobian을 대조할 것. 그다음 동결된 R5 극점 오염 레이블을 교정해 P2/N4-B train split을 **재학습**하며, 업데이트된 RF error predictor로 고정 R2/R4/R5 대응을 재평가할 것. R5 4-state 재귀는 시간 동기된 wheel/gyro controls 없이는 수행하지 말 것. 원본 θ≥2° LoS-LUT tail 최대 .046651은 별도 검증.

**최종: 수치 후보 보정 PASS / 원본 FFD 재생성 및 전체 재학습·R5 재귀 입력 부족 HOLD.**
