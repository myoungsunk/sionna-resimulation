# R5 Full RF Heading — 단계별 실집행 영수증 (2026-10-15)

## 기준선 보존
- 연구 브랜치: `research/r5-fullrf-heading-staged-20261015`.
- 동결된 S4, Joint4, SR4/원본 P3·P4 실험 변경 없음.
- 동결 기존 R2 유효 실행 `38664617622`, RF 아카이브 SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`, 유효 R2 결과 SHA256 `ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399`.
- **과학적 성능 개선 실증 아님**. 아래 결과는 독립 재계산·특징량/조건부 실험이다.

## R5-0 / R5-1: PASS
- Actions [Run 38686018805](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38686018805), source `689382abbf96ebc549135a3d052e1e09c0c6a424`, artifact 11949916481.
- 사전 소스 감사 GO(오류 0), archive SHA/CRC PASS.
- 기존 R2 16개 recursive trace, 64개 별도 점수 행을 자체 scorer로 재계산해 원래 수치와 parity 통과.
- Full Mount0 B0 : DR4 Heading RMSE 0.484°, S4 15.356°, J4 7.490°, SR4 7.516°.
- Full Mount0 B0 : J4 Heading NEES 87.49, Heading 95% coverage 17.13%; S4 final gyro-bias −0.09304°/s(실제 0). RF 오염이 zero-bias에서도 심한 오류를 만든다는 근거.
- GT는 offline 평가용, 추정기는 고정; 인과 분해/다중 scene 검증은 미완료.
- 초기 실행 38685965972는 감사 전 NumPy import 오류로 실패해 폐기; 수정 후 완전한 재감사에서 통과.

## R5-2: PASS (물리 특징량의 오프라인 정합 감사)
- Actions [Run 38686274314](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38686274314), artifact 11949896907.
- 7 RF case, 9,519개 관측과 matching LoS native offline label 결합; P1/P2 합성 s 최대 절대 오차 4.2194e−13.
- oracle `|s_Full−s_LoS_direct|`와 Spearman: total first path log-power −0.5735, RMS delay spread +0.4314, s +0.4268, JSD −0.1506.
- 처음 R5-2 실행 38686200835는 SciPy 미설치로 실패; pinned SciPy 포함 재감사·재실행 PASS.
- 이 값은 관측 오염의 상관이지 독립적으로 보정된 Heading 품질 확률이 아님.

## R5-3: PASS (오프라인 MP proxy 조건부 예측, Fusion은 미실행)
- Actions [Run 38686638510](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38686638510), artifact 11950351879.
- Leave-one-route-out R2/R4/R5 heldout; 원본 총 9,519 행. 목표는 `|s_Full−s_nativeLoS|>0.1` (oracle), NOT Heading <=5°.
- Heldout-frame 가중 Brier:
  - route train-prior: 0.184999
  - range only: 0.147199
  - range+power+s: 0.137732
  - CIR only: 0.160510
  - range+power+s+CIR: 0.135407
- CIR 추가 증분 Brier 개선 = 0.002325 (상기 비교에서), scene 독립성 및 통계적 유의성 미확정.
- 현재 확립된 것은 프록시 예측의 **한 복도 내 held-route** 성능뿐. 학습된 위험도를 R_s(q)나 Heading covariance로 해석하거나 EKF에 적용한 결과가 아님.

## R5-4: PARTIAL PASS (기존 각도별 Full/LoS oracle gradient 시험)
- Actions [Run 38686458810](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38686458810), artifact 11950995824.
- 원본 169개 yaw-site 그룹, 3,133개 관측, 관측당 16개/19개 각도, sweep span 71.4~90°.
- `D(s_full−s_direct-native-LoS)`와 covariance `R_s D Dᵀ`, 가정 `R_s=0.0081`; noise-free full RF의 misfit로 noncentral `χ²`의 **가정상 검출확률**을 계산.
- 가정상 평균 Gradient detection power=0.490745, `|e_MP|>0.1` 시점이 하나 이상인 site 비율 0.585799.
- 부호/gradient mismatch를 MP 100% 확정으로 사용하지 않는다. Offline yaw truth로 matching했으며 gyro angle errors, lever arm, frozen-LUT 차분, 실제 스캔 시간상관, Heading factor는 아직 시험하지 않았음.
- 기존 고정 R2 재귀 archive에는 각도별 Full RF가 없지만, 별도의 원본 channel diagnostic에는 Full yaw-resolved 169개 그룹이 존재함. 전체 신규 생성 전 이 자료를 제한된 지표로 재사용 가능.

## 아직 미완료 (과장 금지)
- R5-3 **실제 RF covariance/mean correction filter ablation**, Joint4/SR4 재귀 적용: NOT RUN.
- R5-4 frozen-LUT finite difference + gyro-induced misfit 오류/회전축 이동/shape Heading likelihood 정합: NOT RUN.
- R5-5 필요시 물리적 새 yaw-resolved Sionna/FFD 채널 생성과 원본 parity: NOT RUN.
- R5-6 실제 nuisance-marginalized Heading likelihood + Gradient+CIR calibration: NOT RUN.
- R5-7 paired recursive benchmark with new quality/scan factors including Heading/Position/Bias RMSE, NEES, 95% coverage: NOT RUN.
- R5-8 robot stop/scan 10s/20s adaptive operational cost: NOT RUN.
- R5-N MAP nonsmooth solver는 다른 트랙 유지. 과거 비매끄러운 근사 후보 결과를 기존 smooth convergence PASS로 소급하지 않음.

## 다음 진행 게이트
1. R5-3의 `e_MP` 프록시와 실제 `|Heading error|>5°` 신뢰도를 분리하고, original R2 pose_id/time에 feature matching이 가능한지 확인.
2. R5-4 기존 169개 Full yaw 응답과 frozen LoS LUT를 동일 RF observer 정의로 맞추고, first-path tap jump/near-null/grid seam 및 angular window covariance 확인.
3. LoS 거짓 제거율과 Full 복합 quality discrimination, nuisance제거 후 Heading 정보량/다중해를 평가한 뒤에만 새로운 scan-heading factor를 적용.
4. 마지막에만 Joint4·S4·SR4 기준선과 종합 재귀 성능 및 NEES/coverage 비교.
