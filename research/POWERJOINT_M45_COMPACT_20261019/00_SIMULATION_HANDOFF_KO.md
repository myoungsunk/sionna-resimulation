# POWER_JOINT Mount 45° 추가 주로 시뮬레이션 요청 (축소 확정본)

**요청일:** 2026-10-19  
**상태:** RF 시뮬레이션 *요청*, 미실행.  
**주관:** 기존 복도 R2/R4/R5와 GitHub 오피스 E형 장면. 새로운 물리 장면/재질을 생성하지 않음.  
**동결 실행 입력:** [01_ROUTE_REQUEST.json](01_ROUTE_REQUEST.json). 우선 이 파일의 6개 경로를 고정하며, 전회 16장면·128조합 계획은 폐기.

## 1. 기존 GitHub 장면과 입력
- **복도:** `src/qclean_uwb/scenarios/corridor.py`의 원래 복도 (20×2.4×2.7 m), 천장 A=(4,0,2.65), B=(10,0,2.65) m. 기존 R2/R4/R5 데이터와 물리·편파 설정을 일치시켜야 하며 독립 scene이 아니다.
- **오피스:** `claude/office-e-layout` 기반 `src/qclean_uwb/scenarios/office.py`, 10×12×2.7 m, 책상 윗판 24·칸막이 12, 앵커 O0=(5,2.2,2.65) m. 모델의 chipboard/wood 재질 가정 유지. `OFFICE_SETUP.json` SHA `7b48fc6682d1bc8a500913273722babcfb54166a71fae81ba097f421a30c5a41`.
- 오피스 기존 `results/OFFICE_SNOWBALL_20261008_819fa93/full35_stride1`의 **35 정지 위치 × 19 yaw × 257 frequency** 완료 기록(행렬 검증 PASS)은 참고·파일럿 검사용이다. 연속 움직임 또는 +45° 장착 주로의 Full/LoS paired H가 아니므로 기존 값을 이어붙여 최종 주로 자료로 사용하지 않는다.
- 코드 기반 브랜치: `research/powerjoint-m45-corridor-office-routes-20261019`; 원 오피스 기준 `b05af070a87981f8712fdd41eac4c1bbb882e9c7`. 물리 source FFD 수정 참조 `research/ffd-source-p0p3-20261016` @ `4b82e9801a1e065593fdd67a0f3ebd721ba29848`; source 모델/검증은 입력계통 혼합 금지.
- LFS 원본 LP+45 `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b`, LP−45 `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9`.

## 2. 6개 신규 주로 (모두 robot antenna Mount 45°)
| ID | 환경 | 지오메트리(경유점, m) | 주된 시험 |
|--|--|--|--|
| C01 | 복도, A/B | (2,0)→(16,0)→(2,0) | 같은 장소 정·역, 앵커 최근접 통과, E1/E3 |
| C02 | 복도, A/B | (2.5,−0.55)→(16,−0.55)→(16,+0.55)→(2.5,+0.55)→처음 | 측방 기하와 방향별 상관 E3/E4 |
| C03 | 복도, A/B | (3.5,0)↔(11.5,0) 왕복 2회, 각 정차 ±10° yaw scan | 동일 지점 재방문, 편파·Bias, P5/E5 |
| O01 | 오피스 O0 | (0.5,0.75)→(9.5,0.75)→처음 | 바닥 가로 통로 LoS 보호, P4 |
| O02 | 오피스 O0 | (3.3,0.75)→(3.3,11.25)→처음 | 중앙 종방향 LoS, E3/E4 |
| O03 | 오피스 O0 | 오른쪽 x=9.5와 왼쪽 x=0.5의 세로통로를 y=0.75 가로통로로 연결·왕복 | 차폐/회복, FP tap, P4/P5 |

기본 6개 경로, 9개 주로-앵커 조건(C01–C03 × A/B = 6, O01–O03 × O0 = 3). 채널은 조건별 Full·Direct-LoS **같은 시각/pose에서 쌍으로** 납품. 오피스에 존재하지 않는 Anchor B는 생성하지 않으며 E6 듀얼앵커 오피스 claim은 제외.

## 3. 원천 RF 생성 계약
- full 257 bin: `f=6,250,400,000 + k×1,950,000 Hz`, k=0…256; `H[n_rf,257,2,2]` complex128, RX ±45 × TX ±45. 송신 +45 관측식과 필요시 2×2 복소 채널을 구별.
- **Tag yaw 안테나 = body yaw + 45°**. 앵커 회전, RX/TX 순서, 복소 켤레 및 `antenna mount` 재정의 금지.
- Full 및 Direct LoS는 같은 Sionna scene·seed·reference pose·송수신 조건 및 first-path detector에서 생성. LoS가 물리적으로 막힌 시점은 **`los_exists=false`**로 표시하고 가상 Direct LoS를 강제로 만들지 않는다.
- Sionna RT 2.0.1, specular reflection and refraction, `max_depth=3`, diffraction/scattering off는 기존 오피스 구현과 같다. seed 20260924 기준을 먼저 고정. 신규 seed로 누락 path 수가 달라져도 독립 장면이라고 주장하지 않는다.
- 반드시 **legacy Method-B / Native H 혼합 비교 금지**. 이미 V01b에서 고차 경로 탐색 누락 및 일부 FP tap 불일치가 확인되었으므로, H·(s)·tap·경로 개수·원본 blob SHA를 먼저 검수.
- 연속 주행 pose와 RF 샘플을 만들기 위한 helper:
```bash
python research/POWERJOINT_M45_COMPACT_20261019/02_prepare_routes.py --out results/POWERJOINT_M45_COMPACT_20261019/POSES
```
  실행 시 Source OfficeSetup의 실제 `position_allowed`와 보수적 robot margin·연속 시각 검사. Helper는 **RF 계산이나 Sensor-v2 생성을 수행하지 않음**.
- 이동 제어열 dt 0.25s, v 0.2m/s, 제자리 yaw 15°/s, 이동 중 RF 목표 약 1 Hz + 모든 scan sample/경유점. 필요한 경우 FP-tap 전환 경계 부근의 **사전 고정된 범위에서만** RF 밀도 추가, 이후 평가 지표로 샘플을 선택하지 않음. 타임스탬프 전체 보존.
- Sensor-v2 wheel/gyro를 별도 생성할 때 bias B0/L0/L1/L2, `synthetic-from-GT` 명시; 실제 센서 원본 로그처럼 표기하지 않음.

## 4. 최소 납품 파일
각 `case_id`에 `ROUTE_POSE.csv`, `RADIO_POSE.csv`, `H_FULL.npy`, `H_DIRECT_LOS.npy`, `LOS_EXISTS.npy`, `FIRST_PATH.csv`, `PATH_COUNTS.csv`, `SENSOR_V2.csv`, `SCENE_METADATA.json`, `RUN_MANIFEST.json`, `SHA256SUMS.txt`.
배열 순서·dtype·주파수(Hz)·거리(m)·Yaw(도/라디안)·시간(s)·포트 인덱스 명시. 셀 보간으로 Full H를 만들어냈다면 정확한 interpolation contract 별도 표시하고 GT/DIR LoS 사용의 경계 검사.

## 5. 수용 게이트와 논문 분리
- **Gate A:** 원본 Git blob/LFS SHA + scene config SHA + 실측 pose 충돌·단조 시각 + 동일 Anchor A/B 동기 확인.
- **Gate B:** 동일 생성기로 Full/Direct-LoS H 생성; nfreq=257; finite/port 순서·FP tap·observer 일치; legacy/Native 동등성 검사 실패 시 재생성. 코드/원본 불일치 시 과학 결과 중단.
- **Gate C:** 모델 훈련은 R2/R4/R5의 등록된 train fold만 사용하고 새 route evaluation held-out 유지. 오피스 **scene-out 평가**는 모든 성능 지표 계산 전 계수 동결. P4 LoS 비열화, P5 조건부 XY 좁은 축 NEES/포함률, P3 `Mean × C_rs × Gate`와 E3 방향·E5 Bias 전이 비교.
- 동일 복도 신규 루트는 독립 경로일 뿐 독립 물리 환경이 아니다. 오피스도 하나의 새 환경이고 O01/O02/O03이 독립 3장면은 아니다. Scene-cluster CI나 광범위 일반화 Claim은 별도 환경·반복 RF가 추가될 때만.

## 6. 단계별 담당자 요청
1. **Pilot**: C01·O01의 경로별 10~20 RF pose를 먼저 계산하고 H·s·FP parity QA.
2. **Main**: 6개 route 전수 계산하고 동일 scene/branch 고정; 비용 초과 시 C01,C02,O01,O03를 우선, 나머지 queue. 일부 성공을 전수 PASS로 표시 금지.
3. **Receipt**: 실행 환경·Git commit·패턴 bank SHA·seed·scene SHA·H/pose SHA·실제 성공/실패와 미완료 건수를 issue에 댓글로 보고하고 데이터 URL/아티팩트를 연결.
4. 오피스에는 Snowball `/home/KMS/OFFICE_SNOWBALL_20261008_819fa93`의 기존 raw NPZ를 **참조**할 수 있으나, 연속 RF 경로의 재계산은 새 출력폴더에서 수행. 사용자가 요청하지 않은 물리 환경 변경 금지.

**이 문서의 기록 상태는 SIMULATION_REQUESTED이며, 생성 결과나 과학적 성공을 뜻하지 않습니다.**
