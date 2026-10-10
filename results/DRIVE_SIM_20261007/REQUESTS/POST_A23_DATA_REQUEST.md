# A23 이후 검증용 데이터 요청서 (Q2·joint 및 L2 원인 분해 포함)

작성: 2026-10-10. 이 문서는 요청서이며 분석 결과가 아니다. 승인된 합격 기준은 없고, F01/F02 및 `scientific_PASS=false`는 그대로 유지한다.
새 RF·필터 실험은 요청하지 않는다. 이미 실행한 Q2(1,200)·joint(450)·L2(8 pose, 2,056 호출) 결과의 **원자료**와, 분해에 필요한 Sionna 보조 출력만 요청한다.
형식은 A23 패키지(`CAUSE_CHECK_A23_EXECUTION_20261010/`)와 같이 **LFS pointer 없이 전체 바이트**, 40 MiB 초과 파일은 무손실 조각 + 해시 manifest로 한다.

## 이 자료로 답하려는 질문

| ID | 질문 | 자료 블록 |
|---|---|---|
| D1 | L2 실패(최대 0.0104)에서 고정 10 m LUT의 phase 항과 tap 선택 항은 각각 얼마인가? 거리 보정만으로 L2가 통과하는가? | B |
| D2 | 실제 `s` 잔차(RMS 0.18)에서 LoS 체인 오차와 다중경로 기여는 각각 얼마인가? (R2-A m0 먼저, 이후 다른 경로) | C |
| D3 | range 편향·시간 상관과 s 오차의 joint 상관 중 무엇이 NEES 팽창을 만드는가? joint의 추가 효과가 "불확정"인 이유는 표본 부족인가 분산인가? | A |
| D4 | 시간 상관 오차의 정렬성(어느 시점·어느 자세에서 s와 range가 동시에 틀리는가) | A, C |

## 블록 A — Q2·joint 실행 원자료 (A23과 동일 구조)

1. `ARMS_*.csv`, `ARM_UNIT_STATS_*.csv`: R1–R8(range), J1–J3(joint) 전 행. 열 이름은 A23 `ARMS_q1.csv`와 동일 유지. 행 수(1,200 / 450)와 중복·누락 0 검사 결과를 `VERIFICATION.json`에 기록.
2. `RUN_MANIFEST_*.json`: argv, source/input/settings 해시, 난수 키 `(seed, drift, stream id)`, **joint의 stream id**, `corr` 설정값(J2의 목표 상관 계수와 실제 계수), J3의 block 길이.
3. `ARM_TARGETS.json`, `RESIDUAL_STATS.json`: Q2/joint가 사용한 목표 통계 전체(s·range 각각의 평균·분산·ACF, 교차상관, 거리 3분위·tap 4분위 조건부 통계). A23에서 쓴 것과 같은지 해시로 비교 가능해야 한다.
4. `TRACES/*.npz`: **seed 0–4 × drift 0–2 × 모든 Q2/joint arm + A0, M0, S3, S8**. 키는 A23 trace와 같이 유지(`est, cov6, err, nees, s_log, r_log, obs_s, obs_range, e_s, e_r, truth, t, gyro, ds_odom, dth_odom`).
   - joint arm은 추가로 **실제로 주입한 오차 시계열 `e_s`, `e_r`와 이를 만든 block 시작 인덱스 배열**(J3) 저장. A23은 seed 0–1만 trace가 있어 joint 상관의 추가 효과를 판단할 표본이 없다.
5. `A0_CHECK.json` 재확인(Q2/joint 실행 전 fingerprint 게이트 통과 기록), `paired_closure_*.csv`(per-drift와 seed 평균), 최종 보고서.
6. 선택: 모든 seed의 `cov6` 최솟값·비대칭 요약(trace가 없는 seed에 대한 보고용).

## 블록 B — L2 원인 분해용 호출 단위 자료 (8 pose, 2,056 호출)

L2의 각 호출(pose × 거리)에 대해 CSV 1개(행 = 호출)와, 아래 중간값을 요청한다.

- 식별: `pose_id, distance_m, anchor_xyz, rx_xyz, yaw_deg, mount_deg`
- 각도: `theta, phi_tx, phi_rx`(LUT 조회에 쓴 값, deg)와 **LUT 격자에 스냅하기 전 값**
- 값 3종: `s_sionna`(max_depth=0 전체 체인), `s_los_exact`(실제 거리 직접 LoS를 같은 체인에 통과), `s_lut`(고정 10 m LUT 보간)
- 체인 중간값 (두 RX branch 각각): 첫 경로 tap 인덱스, 30% 선단 임계 교차의 **tap 이하 위치**, 선택된 branch, 첫 경로 전력 P1·P2, sub-tap 오프셋
- LUT 쪽 같은 중간값: 인접 4개(trilinear 8개) 격자점의 tap 인덱스 8개와 보간 가중치
- `s_los_exact − s_sionna` 가 최대 8.57e-7 이라는 결과가 나온 호출의 행 전체(상한 확인용 분포: 분위수와 최대 3행)

선택(있으면): 각 호출의 `H` (257×2×2, complex) 원본 — 2,056 × 257 × 4 × 16 B ≈ 34 MB.

이 자료가 있으면 L2 오차를 (1) 전파 phase/지연 (2) tap 선택 불일치 (3) 보간으로 분리할 수 있다. 분리 결과가 "거리 보정만으로 해소"인지 "tap 선택이 남음"인지는 아직 모른다. 요청서가 결론을 미리 정하지 않는다.

## 블록 C — 잔차 분해용 Sionna 보조 출력 (실제 RF 재계산, 가장 중요)

현재 있는 것은 전체 `H`(다중경로 포함)뿐이다. 잔차를 분해하려면 **같은 pose에서 LoS만 계산한 `H`**가 필요하다.

각 케이스에 대해 같은 timeline/rf_poses로:
1. `H_LoS_<case>.npy` — Sionna `max_depth=0`(LoS 직접 경로만), shape = 기존 `H_<case>.npy`와 동일(`poses×257×2×2`). 기존 `H_<case>.npy`와 pose 순서·주파수축 동일, 해시 manifest.
2. (R2-A m0만, 권장) 경로 단위 출력: 각 pose의 `a, tau, theta_t/phi_t, theta_r/phi_r`, 상호작용 종류(반사 횟수·면). 첫 경로 직후 두 번째 경로의 지연 간격과 진폭비를 보기 위한 것.
3. 기존 `H_<case>.npy`가 아직 없는 케이스의 전체 `H`: 우선순위 순서

   | 순위 | 케이스 | 이유 |
   |---|---|---|
   | 1 | R2-A m0 (H_LoS만; 전체 H는 이미 있음) | D2 기준 케이스 |
   | 2 | R2-B m0 | 앵커 B에서 LUT 불일치가 작은 이유 |
   | 3 | R5-A m0, R5-B m0 | polar 특이점(θ_geo<2°) 노출 |
   | 4 | R4-A m0, R4-B m0 | 지그재그 |
   | 5 | R2-A m45 | 프로브 의존성 |

   각 케이스의 `timeline_*.csv`, `rf_poses_*.json`, 해당 S6 결과 CSV와 SHA256 포함.
4. 같은 pose들에 대해 `hs_lut_2deg.npy`를 다시 만들 필요는 없다(해시만 확인).

이 자료가 있으면 `r_s = [s(H_full) − s(H_LoS)] + [s(H_LoS) − LUT(truth)]`로 나누어 앞 항을 다중경로, 뒤 항을 LoS 체인/LUT 오차로 정량화할 수 있고, range도 같은 방식으로 나눌 수 있다. 어떤 분해가 우세한지는 아직 모른다.

## 블록 D — F01 경로 선택용 최소 확인(요청 사항 아님, 확인만)

- "실제 거리 직접 LoS와 Sionna 차이 최대 8.57e-7"이 **어떤 호출 집합**(8 pose 전체? 2,056 전부?)에서 나온 값인지 명시.
- L2 8 pose의 pose 좌표와 G3 gate 시 Sionna 8 pose가 같은 집합인지.
- 이번 실행의 Docker image ID, Python/NumPy 버전, source 해시(A23과 동일하면 "동일"로 기재).

## 형식 요건

- 브랜치: 사용자 `codex/…` 브랜치(예: Q2/joint/L2 결과 브랜치). 저는 읽기만 한다.
- 모든 CSV에 행 수·열 정의, 모든 파일에 SHA256과 바이트 수를 manifest로.
- 큰 파일(>95 MiB)은 40 MiB 조각 + 복원 manifest. 복원 스크립트는 브랜치에 있어도 되나, 저는 자동 모드 제한으로 실행하지 않고 `git show`로 이어 붙여 해시를 대조한다.
- 완료 주장 금지: 이번 자료 게시를 "분해 완료"나 "F01 해결"로 기술하지 않는다.

## 이 자료로도 할 수 없는 것

- 다른 경로·mount의 NEES/정확도 일반화(Q2/joint는 R2-A m0 범위).
- F02의 승인된 통과 기준 설정(사용자 승인 필요).
- G3 chronology 복구(새로운 clean production 실행과 사전 검사 보정이 필요).
- 실제 하드웨어 정확성.
