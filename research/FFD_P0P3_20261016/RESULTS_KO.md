# FFD source 기반 P0–P3 재실행 결과 — 2026-10-16

## 실행과 게시 범위

제공된 FFD NPZ 두 개를 실제로 사용해 P0 물리 관측 대조, P1 재학습, P2/P3 재귀·동일-prior 검증을 완료했다. P4–P7은 실행하지 않았다. 원본 LUT와 과거 POWER baseline은 덮어쓰지 않았다.

GitHub에는 bank identity receipt, 검증된 실제 NPZ artifact, source_model.py, p0_initial.py와 이 요약을 게시한다. 전체 P1/P2/P3 runner·독립 재검산 코드·256개 trace·세부 CSV 정본은 대화에서 제공한 FFD_SOURCE_P0P3_20261016.zip에 포함한다. 전체 세부 코드/결과가 모두 이 브랜치에 커밋되었다고 주장하지 않는다.

## 1. 원본 bank 보존

기존 Git LFS 객체가 사용자가 전달한 파일과 전체 바이트·SHA256 모두 일치했다. 중복 포인터 변경 없이 원본을 유지했고, GitHub runner에서 실제 두 NPZ를 다운로드·검증해 artifact로 추가 보존했다.

- LP_plus45_bank.npz: 247727983 bytes; SHA256 b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b.
- LP_minus45_bank.npz: 247743979 bytes; SHA256 39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9.
- Run 38875080492, artifact 12034154094: 실제 bank 전체를 포함. ZIP 495473098 bytes, SHA256 cad003e294edc59a4eecdbce39c02bec43d91524ecef37c93978a356ba519e8e. Actions 보관기간30일과 기존 LFS 원본을 구별한다.

각 bank complex64 E_theta/E_phi shape=(257,181,361). 주파수6.2504GHz 시작,1.95MHz 간격,257점. 전계 유한성/azimuth seam 확인. 개별 원시 .ffd export 파일은 제공되지 않아 재-export 검증을 수행하지 않았다.

## 2. P0: 핵심 원인과 실제 수치

source 전계를 world Cartesian 좌표로 변환하고 기존 RX^T TX contraction, 주파수별 진폭/위상, Hann/4N IFFT, strongest RX의30% leading edge 및 두 port 공통 tap을 유지했다. s 예측은 10m 고정 LUT 대신 실제 가정 상태의 거리·관측 tap을 사용한다. GT나 native LoS를 추정기 입력으로 넣지 않는다.

| 검사 | 결과 |
|---|---:|
| Native LoS 대조 | 9519점 |
| 전체 source-native s RMSE | 6.592045e-7 |
| 전체 source-native s 최대절대차 | 1.082114e-5 |
| Native first-path tap 불일치 | 0 |
| theta>=2deg angular-interpolation 성분 RMSE | 0.001817198 |
| theta>=2deg fixed10m 대 actual-distance 성분 RMSE | 0.009572385 |
| 위 거리성분과 기존전체잔차 상관 | 0.982282 |
| 독립 direct/source 구현 복소채널 상대최대차 | 3.912e-13 |
| 일반 active-cell Jacobian FD 최대차 | 9.544e-9 |
| 정확한 극점 Jacobian FD 최대차 | 1.245e-10 |
| cap/seam 검사 중 cell/tap 모두 유지 시 FD 최대차 | 1.602e-7 |

따라서 기존 극점 밖 잔차를 전부 각도 보간오차로 부르는 해석은 기각한다. 거리/관측 tap 의존성이 주요 성분이다. 성분은 독립이 아니므로 RMSE를 합산하거나 원인비율로 환산하지 않는다.

극점에서는 source-bank의1deg/3deg Cartesian ring으로 local polynomial cap을 구성하고0.1..0.5deg에서 기존 source 보간과 연결했다. fit에 사용하지 않은2deg ring의 최대 상대 전계오차1.786e-6. source-only 보간 확장이지 별도 EM solver의 subdegree 정답이 아니다. 실제9519 fixture는 cap 밖이다. yaw+2pi불변, port swap의 s부호반전/tap불변을 확인했다. 잘못된 Hermitian contraction 음성대조의 s RMSE는0.139497이었다.

Native RT 복소채널과 비트동일하지 않다. TX+45 column 상대최대차3.254e-4, RMS7.311e-5가 남는다. 사후 common-complex-scalar 정합 후에도 잔차가 있으므로 모든 차이를 공통위상으로 단정하지 않는다. 사후정합은 추정/학습에 사용하지 않았다.

Range detector 예측은 Native tap과 일치하지만, 이번 EKF 비교는 원래 continuous bridge h_r=d+B_OLD, B_OLD=-0.5315983906250129m를 유지한다. 양자화 Range likelihood의 최종 해결이라고 주장하지 않는다. 새로운 scalar3D LUT를 생성한 것이 아니라 source-bank 직접 관측모델을 검증했다.

## 3. P1 전수 재학습

Full9519+NativeLoS9519=19038개 packet. 기존14개 관측 trace의14502시점을 대조했다. 실제 packet feature는 그대로이며 source s target만 재계산했다. Range bridge/label은 동결했다.

N4-B는 고정R0 포함9개구성: 세 heldout route(R2,R4,R5)에서 새 learned fit24개와 원본parity learned fit24개. 각버전 평가구성27개. 별도로 G0..G5 second-moment forest18개를 source target으로 재학습했다. 중간안내의10개/30개는 집계메타 오류였고 계산루프는 실제9구성을 실행했다.

train-only scaler, signed mean, bin boundary, ridge/covariance를 새로 적합했다. old-fit parity의 최대 mean차1.78e-15,cov차1.11e-16,NLL차6.82e-13. 원본 계수 재사용이 아니다. train/test 동일XY 제거를 적용했으나 한corridor이며 공간적으로 매우근접한 점이 존재한다. R2 train에는 Mount45가 없다. 독립장면 일반화로 해석하지 않는다.

## 4. P2/P3 재귀 결과

2 mounts x4bias x(24Full+8LoS arms)=256 trajectories. 전체979시점 재귀, t>=30s의829점 평가. 동일prior 비교1368개. 모두 기존 RF 실현/센서seed를 사용하며 독립실험256회가 아니다. matched mask는 offline control이다.

| Mount | Bias deg/s | Heading old | Heading source+refit | XY old m | XY source m | Gyro RMSE old deg/s | Gyro RMSE source deg/s |
|---:|---:|---:|---:|---:|---:|---:|---:|
|0|0|1.773241|1.798910|0.162103|0.149970|0.021603|0.018839|
|0|0.01|1.756724|1.796573|0.159512|0.150014|0.021560|0.019014|
|0|0.05|1.712307|1.795003|0.153566|0.150948|0.022275|0.019983|
|0|0.20|1.991423|1.558988|0.191677|0.157194|0.032662|0.027706|
|45|0|0.815147|0.982634|0.084934|0.087113|0.013260|0.015522|
|45|0.01|0.812545|0.979990|0.084599|0.087038|0.013228|0.015454|
|45|0.05|0.810551|0.974161|0.083248|0.086808|0.013199|0.015284|
|45|0.20|0.727425|0.941907|0.078587|0.086513|0.012312|0.014629|

Heading 단위deg. 물리정합 향상이 전체 state accuracy 향상을 자동 보장하지 않는다.

s 제거 후 Range+quality만 남기면8/8조건에서 Heading이 악화한다. H_bg=0이며 pose-bias crosscov를0으로 제거하면 K_bg=0이다. sourcePOWER M0-B0 끝점 gyro contribution: Range -0.111081deg/s, s +0.112253deg/s, 합 +0.001172deg/s. 같은실현경로의 대수적분해이며 채널제거 재귀경로와 동일하지 않다.

Mean 제거: M0-B0의 같은 sourcePOWER prior/mask에서는 Heading1.798910→1.799453deg지만, 전체재귀에서는4.218403deg. 상태/이득/Gate의 누적효과를 한 번 업데이트로 대체할 수 없다.

기존M45의 Crs제거4/4개선은 source관측으로 바꾸자4/4소폭악화로 바뀌었다. 이전 mount별 경향을 모델불변 일반메커니즘으로 주장하지 않는다. 현재 작은 차이를 Crs의 보편적 필수성으로 승격하지도 않는다.

동일829 Full패킷에서 sourceNLL: M0 POWER -1.681675, G4 -1.696062. G4의NLL은조금좋지만 B0재귀Heading은3.131978deg로POWER1.798910deg보다나쁘다. M45 NLL은POWER -1.095822, G4 -0.697584로G4가이미나쁘다.

## 5. 해결되지 않은 것

M45-B0 sourcePOWER: narrow-axis NEES16.614296, nominal95 interval 포함시간비율16.7672%, 실제조건부오차RMS4.378cm, 예측sigmaRMS1.063cm. oldPOWER의 narrowNEES14.200102/포함16.4053%보다 일관성이확보됐다고볼수없다. 조건부공분산뿐아니라오차도함께변환했다.

NativeLoS B0에서 sourceR0 대 sourcePOWER:
- M0 Heading0.502160→2.108206deg, XY0.060253→0.269707m.
- M45 Heading0.153262→1.356951deg, XY0.033041→0.145885m.

정상LoS 보호 실패와 조건부XY 과신은 그대로남는다. Full-only empirical correction을정상LoS에일괄적용하는모델을최종승인하지않는다.

B0 Full sourcePOWER의 accepted update 중 FPtap crossing: M0 6/959,M45 12/932. FFD cell crossing 각각136,119. 경계를기록했으며 crossing을과신의유일원인으로단정하지않았다.

## 6. 재검산과 Claim

기존Full frozenR0/POWER16경로 Gate불일치0, 최대state차5.113e-8,cov차4.087e-10. 허용오차내재현이며비트동일은아니다.

별도Cholesky산식으로256경로/212224평가시점을 재채점: 최대상대차1.496e-14. 원본unbatched core/SR4의384개업데이트대조: 최대state차1.388e-16,cov차8.47e-22,Gate전부일치. 독립적인수치재계산이지외부사람감사를뜻하지않는다. SR4저장K는priorjoint진단값이며SR4순차기여분해에사용하지않았다.

P0 bank입력차단은해제했다. source관측정합과P1재학습실행은확인됐고P2/P3메커니즘근거는현R2/corridor범위의SUPPORTED_BUT_LIMITED다. LoS-safe와consistent covariance 주장은현재후보에서FALSIFIED다. 새장면/하드웨어일반화는NOT_TESTED다. empirical RF update를정규화된Bayesianposterior로부르지않는다.
