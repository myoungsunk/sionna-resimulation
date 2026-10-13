# P1 — 독립 3-State EKF 구현 및 단위 검증 (2026-10-13)

## 판정·범위

- P0 입력 무결성: `b0957181e0e5238e160e69a04d052f23559e666c` PASS. 39개 파일, 7개 RF case, 3개 route; 동결 데이터와 P0 증빙은 수정하지 않았다.
- **P1 구현: CODE_COMPLETE. 국소 수학 및 합성 통합 테스트: 26 PASS.**
- 이번 단계에서 기존 RF H / 실제 LUT를 사용한 full-route 측위 성능 시험은 **NOT_RUN**. 신규 시뮬레이션 및 데이터 추가 없음. `scientific_PASS=false` 유지.

## 독립성

`ekf3.py`는 단독 NumPy 구현이다. `DriveFilter`를 상속하지 않으며, 6×6 행렬을 일부 잘라서 3×3으로 사용하지 않는다. 기존 `src/qclean_uwb/drivesim/*`, frozen Sionna H, 기존 LUT, P0 문서 및 결과를 변경하지 않는다. 상태는 `[x_m,y_m,yaw_rad]`, 공분산은 항상 3×3. `archived_direct_s_model` 어댑터만 사용 시 기존 `qclean_uwb.drivesim.hs_lut.s_model`을 읽기 전용으로 호출한다.

## 네 함수의 정확한 역할

| 함수 | 구현된 식/계약 | 주의 |
|---|---|---|
| `predict(ds,dtheta,dt)` | SE(2) 원호 적분, `F3`, `G(3×2)`, `P-=FPFᵀ+GQᵤGᵀ+Q_model` | Q 입력 = 기존 Sensor-v2 wheel/gyro 각도 증분 잡음 기반. 기본 Q_model=0은 W0/noise-only 출발 가정이다 |
| `update_heading(s,Rs,s_model=...)` | 직접 `s`: `H_s=[∂x s, ∂y s, ∂ψ s]`의 scalar update | 진짜 독립 절대각은 명시적 `kind="absolute_heading", validated_absolute=True`에서만 허용. DR prior로 선택된 역-LUT root는 독립각으로 취급하지 않는다 |
| `update_range(r,Rr,anchor,tag_z)` | 3D slant range + 고정 first-path detector offset, `H_r=[(x−ax)/d,(y−ay)/d,0]` | `Pψx,Pψy`를 통한 간접 yaw gain 허용. 물리 antenna delay로 고정 offset을 해석하지 않는다 |
| `update_joint(s,r,Rs,Rr,Rsr)` | `H=[H_s;H_r]`, `R=[[Rs,Rsr],[Rsr,Rr]]`로 **단 한 번**의 2D 공동 업데이트 | 공동 NIS가 거절되면 전체를 거절하고 유리한 센서만 선택해 재처리하지 않는다. 한 항목의 실제 결측에는 그 항목을 제거해 scalar로 업데이트한다 |

보정은 `innovation=z−h(x−)`, `S=HP−Hᵀ+R`, `K=P−HᵀS⁻¹`이며 Joseph `P+=(I−KH)P−(I−KH)ᵀ+KRKᵀ`를 사용한다. `S` 계산·Kalman Gain은 역행렬을 명시적으로 구하지 않고 `numpy.linalg.solve`를 사용한다. PSD 검사에서 임의 eigenvalue clamp 또는 jitter는 시행하지 않는다.

Gate: scalar 99% χ²(1)=6.6348966, joint 99% χ²(2)=9.2103404. 측정 전후 x/P, F/G/Q, Innovation/H/R/S/K, pre-gate NIS, Gate 결과는 `FilterStep` 반환 객체에 포함한다. 측정값 None/NaN은 명시적 결측으로 skip한다.

## 검증 범위

독립 수학 검증 24개, 30-step D0/A/B/C 합성 스모크 및 기존 LUT adapter 인자 계약 스텁 검증 2개, 총 26개 PASS. 측정 Jacobian은 XYψ 전부 유지하며 SE(2) `F/G`는 수치 미분으로 확인했다. 2×2 비대각 공분산, Joseph PSD, 누락 관측, Joint gate 전체 거절, 공통 prior clone 독립성도 검사했다. 정확한 로컬 실행환경·해시 일치는 `P1_UNIT_TEST_RECEIPT.json` 참조.

실행 명령:

```bash
python -m pytest -q research/EKF3_INDEPENDENT_20261013/test_ekf3.py research/EKF3_INDEPENDENT_20261013/test_ekf3_smoke.py
```

## 기존 자료와 연계되는 제한 사항

- `R0`에서 `R_r=0.0068578637 m²`, `R_s=R_thermal+0.0081`, `R_sr=0`는 출발 대조군이지 충분히 검증된 실제 RF 공분산이 아니다. 조건부 편향·시점 간 colored-noise·상태–RF 오차 상관은 미해결이다.
- 저장된 RF H/LUT를 연결하는 실제 adapter parity는 P2 전 필수. 현재 검증한 adapter는 **스텁 기반 API 호출 계약**이며 채널 데이터 재생을 뜻하지 않는다.
- 원 Tnone trajectory legacy-Euler와 exact SE2 모델 간 작지만 알려진 불일치, 극점 근처 LUT Jacobian, F01/F02 OPEN은 그대로다.
- 3-State에 없는 gyro bias·gyro scale·wheel asymmetry·slip은 W2 stress 세계에서 존재할 수 있으므로 필터가 이를 추정하지 못하는 한계도 그대로 공개한다.
- 단일 복도 자료와 공통 noise-free RF 채널에 반복적으로 sensor seed를 적용하는 것은 독립 환경 검증이 아니다.

## 다음 게이트

P1 = `CODE_COMPLETE / LOCAL_UNIT_TESTS_PASS`; P2 = `NOT_RUN`; `scientific_PASS=false`.

P2에서는 **별도 검증 절차**로 P0의 실데이터 해시 확인, 동결 observer parity, LUT 실제 함수·타임라인·sensor_v2 입력 호환을 확인한다. 이후 같은 prior 한-step D0/A/B/C 비교와 full-route paired replay에서 Heading/위치 RMSE, NEES/NIS/coverage를 검증한다. P1 단계의 26개 단위 테스트를 P2 실측/채널 성공으로 확대 해석하지 않는다.
