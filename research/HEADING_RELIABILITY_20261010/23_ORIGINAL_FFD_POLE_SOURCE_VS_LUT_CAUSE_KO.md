# 23 — 원본 FFD 필드 대 LUT 보간 극점: 실제 원인 분리 검증

작성 2026-10-11. **실제 원본 SHA256 LFS bank 2개로 검증 완료**, LFS pointer 대체 아님. Original RF 및 원본 hs_lut 수정 없음.

실행 증거:
- [원본 FFD raw LP±45 다운로드, SHA 검증 및 Cartesian 극점 계산](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38116318149)
- [기존 9519 native LoS 출력 대비 원본 theta0/2/4 LUT slice 대조](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38116260202)
- 재현 코드: audit_raw_ffd_polar_basis.py, run_pole_slice_lut_native_diagnostic.py (현재 브랜치).
- 두 FFD bank digest 원래 BANK_MANIFEST.json과 일치: plus45 b29ae471... / minus45 39729fe9...; 실제 LFS 파일 247MB 수준, 개별 소스가 저장소에서 134B pointer처럼 보이더라도 GitHub Actions git lfs pull 성공함.

## 1. 가장 결정적인 실제 원본 데이터 사실

원본 FFD Etheta/Ephi를 실제 spherical basis에서 복소 Cartesian E 벡터로 변환하여, theta=0의 원본 361 방위각 샘플을 서로 비교했다.

| FFD port | f=6.5 GHz, theta=0 Cartesian 복소 E across phi 상대 RMS 변동 |
|---|---:|
| LP+45 | 2.86e-8 |
| LP−45 | 2.78e-8 |

6.25 및 6.75 GHz에서도 2.4–2.8e−8 범위. Raw Etheta/Ephi 값 자체는 phi에 따라 다르지만, **물리 좌표로 변환한 FFD는 극점에서 거의 완벽하게 연속적**. 원본 FFD가 phi 각마다 서로 다른 물리 편파를 생성한다는 가설을 기각할 강한 근거.

두 원본 bank를 이용해 source hs_lut.los_s_direct()의 FFD Cartesian contraction를 재계산하고 기존 R5A/B near-pole native solver의 clean LoS s 13개와 비교:
- max abs(native LOS−direct FFD) **0.000675**
- 반면 native clean LoS와 frozen LUT는 극점에서 max abs **0.877616**.
예: R5-B pose706 native LoS −.946821, direct FFD −.946501, frozen LUT −.069205.

## 2. 분리한 LUT slice 직접 진단

원본 frozen LUT의 theta=0 slice에서, 같은 물리 yaw=0에서 anchor 접근방위 8개를 바꾼 predicted s range는 약 **1.953**(거의 전체 −1..+1 범위).
theta=2 slice의 같은 range **0.0104**, theta=4 slice **0.0209**.

앞서 사전 등록한 물리근거 기반 diagnostic 대조:
(1) original trilinear theta0/2 interpolation,
(2) theta<2일 때 theta2 slice를 hold하는 theta-clamp,
(3) theta2,4 slice에서 theta<2를 1차 외삽해 클립하는 모델.

기존 native LoS 9개 관측(rho<0.1m)에서:
| 모델 | clean LoS 대비 s RMS | absolute max |
|---|---:|---:|
| Original LUT | **0.339094** | **0.877616** |
| Theta clamp 2° | **0.001374** | **0.002129** |
| Theta 2°/4° extrapolation | **0.001159** | **0.001477** |

원래 theta>=2 지역의 예측값은 그대로이고 그 지역에서 차이가 발생하지 않았다. 따라서 극점 오류의 주요 원인은 **극점 slice와 그 slice를 직접 혼합하는 선형 theta interpolation**이다. 이 진단 결과만으로 clamp/extrapolation을 최종 운영 h 또는 올바른 analytic Jacobian으로 승인하지 않는다.

## 3. 소스에서 확인되는 기하학적 생성 원인

source build_lut()는 theta=0에서도 phi_tx,phi_rx 축을 격자로 만들고, 정확한 수직 진행 방향 dxy=0에 대해 az_v=atan2(vy,vx)로 receiver yaw를 역산한다. 그러므로 theta=0에서 az_v는 물리적인 유일한 방향이 없으며, build_lut grid (theta0,phi_tx,phi_rx) 좌표는 실물 로봇 body_yaw에 대한 일관된 chart가 아니다.

theta>0인 경우 anchor-robot bearing과 phi_rx 차로 yaw가 정의되지만 theta=0에서는 bearing이 소멸한다. 보간기가 **phi_rx에 따라 달라지는 theta0 grid**와 theta=2 grid를 trilinear로 섞어, 사실상 같은 수직 방향에서 수신 LP 비율이 접근 방위에 따라 1.95까지 이동하는 허구적 변화를 만든다. 이 영향은 s_model의 atan2(phi) chain Jacobian에서 1/rho 형태로 확대되어 P6 EKF의 위치/heading gain을 불안정하게 한다.

이 진단은 충분히 source-backed하지만 추가적인 Sionna native arbitrary XY near-pole validation과 corrected LUT Jacobian 전체 수치 parity 없이 원래 F01/L1 scientific failure는 해제할 수 없다. FFD bank itself is smooth; LUT parameterization at the polar singularity is responsible for current stored near-pole mismatch.

## 4. 다음 물리적으로 일관적인 correction 방향

- 극점에는 phi_tx/phi_rx 2D 독립축이 아니라 실제 world RX yaw 및 **Cartesian 방향벡터와 field**가 원천 입력이 되는 h(p,psi) 표현을 써서 방향 chart singularity를 피한다.
- 기존 phi grid 보간 자체를 유지하려면 theta<2° 영역에 별도의 gauge-consistent theta0 reference를 재생성하고, theta->0 접근 경로로도 value 및 Jacobian이 연속인지 검증.
- 보호장치: 임시 rho_est와 radial covariance confidence를 이용한 quality abstention arm (0.1m/0.25m), 원본 s LUT를 수정하지 않고 비교. Theta-clamp/extrapolation은 진단용 모델이므로 새 SHA/version 없이 원본을 조용히 덮어쓰면 안 된다.
- 독립 물리환경, mount0/45, full7/12 LoS and multipath near pole, 6state EKF poseNEES/coverage 재시험 후에야 change adoption.

**판정:** FFD 원본 필드의 극점 방위 불연속은 지지되지 않는다. Frozen LUT theta0 극점 chart/interpolation 결함은 source와 native clean data로 강하게 지지된다. Filter consistency PASS는 아직 아님.
