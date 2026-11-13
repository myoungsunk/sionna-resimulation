# TB3 trackA 회전 중 heading 오차의 run 간 변동 — 보정 가능성 판정 보고서

- 작성: 2026-11-13 KST
- 판정: **고정 상수 보정 불가(`NOT_CALIBRATABLE_AS_FIXED_CONSTANT`)**. 고정 소프트웨어 조건의 보정 가능성은 **미판정(`OPEN`)**.
- 범위: TB3 waffle_pi의 `/odom` yaw(OpenCR IMU 융합 출력)가 trackA station sweep 운용에서 쌓는 heading 오차. RF는 포함하지 않는다.
- 연결: G1-MODEL-001(`research/G1_SWEEP_HEADING_FLOOR_20261113/SPEC2_KO.md` v3.2 §4.5)의 DR 파라미터 근거.

## 1. 질문

trackA의 회전 중 IMU heading 오차(station당 약 2°)는 일회성 보정으로 제거할 수 있는가? 즉 한 run에서 측정한 station당 오차율을 다른 run에 적용할 수 있는가?

## 2. 데이터

| Run | 날짜(UTC) | 소프트웨어 | 파일 | 커밋 | SHA-256 |
|---|---|---|---|---|---|
| TEACH | 2026-10-04 13:45 | r1.3.1 | `data/raw/tb3_motion_20261004_20261111/trackA/teach/teach.json` | `3018bb5` | `029890d9172844e1ef469e134d85933e35d8bc4e7bd66ab1cdfc27eae5dbe0e3` |
| REPEAT 10/04 | 2026-10-04 14:11 | r1.3.1 | `…/trackA/repeat_20261004_141119/repeat.json` | `14f8a76` | `0bf2ba4ea102935b5ce8d9aac950166d11891850f9293184ffade6db948e3379` |
| REPEAT 11/13 | 2026-11-13 06:13 | r2.1.0 | `…/trackA/repeat_20261113_061314/repeat.json` | `95ec6c0` | `004381dc56276e19f1f8d912c3c5dd739c0277191d6d531fcfb84b97485c2dd0` |
| REPEAT 11/13 bag | 같은 run | — | `…/repeat_20261113_061314/bag/bag_0.db3`(Git LFS) | `95ec6c0` | `84e235b1e12dfc8dd8e65565297988f3bd861e8e75e9faae3669693da96bb082` |

- 세 run 모두 같은 trackA 경로(18 station, 0.45 m 간격), station마다 −60, −30, 0, +30, +60° sweep이다.
- 10/04 run에는 bag이 없다.

## 3. 방법

정의는 `analyze_runs.py` 머리말과 같다.

- **TEACH 증분:** station base의 odom yaw 차분. TEACH는 매 station에서 벽에 정렬하므로, 이 증분은 odom yaw의 오차다.
- **REPEAT 증분:** 마지막 align 캡처의 (odom yaw − ICP yaw) 차분. REPEAT는 TEACH scan에 ICP로 정렬하므로 물리 자세가 TEACH와 같고, 증분은 odom 오차다.
- **Sweep 구간 오차:** base → base_after 사이의 odom yaw 변화에서 같은 구간의 ICP yaw 변화를 뺀 값.
- **이동·정렬 구간:** station 증분 평균 − sweep 구간 평균.
- **짝 차이:** 같은 station에서 두 run의 증분 차이. 정렬 기준을 공유하므로 정렬 오차가 상쇄된다.

## 4. 결과

### 4.1 run별 station당 heading 오차 (단위: °/station, 평균 ± SD, n = 17)

| Run | 소프트웨어 | station당 증분 | 17 station 누적 | sweep 구간 | 이동·정렬 구간 | sweep 후 ICP 잔차 | TEACH와 상관 |
|---|---|---|---|---|---|---|---|
| TEACH 10/04 | r1.3.1 | 2.278 ± 0.521 | 38.73° | — | — | — | — |
| REPEAT 10/04 | r1.3.1 | 1.824 ± 0.809 | 31.01° | 1.332 ± 0.255 | 0.492 | −1.279 ± 0.318 | 0.828 |
| **REPEAT 11/13** | **r2.1.0** | **0.482 ± 0.572** | **8.19°** | **0.208 ± 0.237** | **0.274** | **−0.065** | 0.562 |

### 4.2 짝 차이 (같은 station끼리, °/station)

| 비교 | 평균 ± SD | SE | 조건 |
|---|---|---|---|
| REPEAT 10/04 − TEACH | −0.454 ± 0.478 | 0.116 | 같은 날, 같은 버전 |
| REPEAT 11/13 − TEACH | −1.796 ± 0.514 | 0.125 | 다른 날, 다른 버전 |
| REPEAT 11/13 − REPEAT 10/04 | −1.342 ± 0.591 | 0.143 | 다른 날, 다른 버전 |

### 4.3 run 간 변동

- run 평균(2.278, 1.824, 0.482)의 표준편차: **0.93°/station**. G1 사양서의 기존 가정 σ_β = 0.45의 약 2배다.
- 최대/최소 비: **4.7배**.
- 세 run의 station당 회전량은 같다(약 240°/station). 오차 감소는 주로 **sweep 구간**에서 일어났다(1.33° → 0.21°, 약 6배).

### 4.4 r2.1.0에서 바뀐 설정 (repeat.json `config` 비교)

| 항목 | r1.3.1 | r2.1.0 |
|---|---|---|
| sweep 중 LiDAR trim | 없음 | 있음(최대 3회, 허용 0.3°). 각도당 평균 시도 1.27 → 1.86회 |
| rot_adapt | 없음 | 있음(gain 0.5, max 0.02) |
| yaw_tol | 0.25° | 0.12° |
| fine_passes | 3 | 4 |
| rot_lag | — | 0.04 s |
| 기타 | — | wall_lateral, walls_agree 등 정렬 규칙 추가 |

**날짜와 소프트웨어가 함께 바뀌어, 두 요인의 효과는 분리되지 않는다.** LiDAR trim은 로봇의 물리 heading을 바로잡지만 odom 값 자체는 고치지 않는다. 따라서 위 증분은 trim 여부와 관계없이 odom 오차다.

### 4.5 REPEAT 11/13 bag 진단 (메커니즘 확인 시도)

| 지표 | 값 | 해석 |
|---|---|---|
| 제자리 회전 전체에서 odom/encoder 회전비 | CCW 0.950, CW 0.941 | encoder yaw를 공칭 wheel separation 0.287 m로 계산해 약 5–6% 크게 나온다. encoder는 참값으로 쓸 수 없다 |
| 각속도 < 0.5°/s 구간의 odom/encoder 비 | CCW 0.31, CW 0.18 | 느린 회전을 odom이 덜 기록하는 경향. 다만 encoder 1 tick 잡음으로 생기는 선택 편향이 섞여 크기를 신뢰하기 어렵다 |
| 각속도 < 0.5°/s 구간이 전체 회전에서 차지하는 비율 | 1.2% | 위 효과가 있어도 영향 범위는 제한적이다 |
| 바퀴 정지 후 0.5 s 안의 odom yaw 변화 합 | 5.68° | odom이 encoder보다 늦게 따라온다. 속도 구간별 비율이 이 지연에 오염된다 |

**결론: bag으로 메커니즘을 판별하지 못했다.** 10/04 run에는 bag이 없어 두 버전의 회전 프로필을 직접 비교할 수 없다.

## 5. 판정

1. **고정 상수 보정은 불가하다.** 한 run에서 측정한 station당 오차율을 다른 run에 적용하면 잔차가 0.45°/station(같은 날·같은 버전)에서 1.80°/station(다른 날·다른 버전)까지 남는다. 17 station 기준 누적 7.7–30.5°다.
2. **오차율은 하드웨어 상수가 아니다.** 같은 로봇, 같은 경로, 같은 회전량에서 run과 제어 프로필에 따라 0.48–2.28°/station 범위로 달라진다.
3. **고정 소프트웨어(r2.1.0) 조건의 보정 가능성은 열려 있다.** r2.1.0 run은 하나뿐이다.

## 6. G1 연구에 주는 의미

- "회전 중 IMU 오차는 보정하면 사라진다"는 반론은 현재 데이터로 성립하지 않는다.
- 반대로 r2.1.0 조건의 DR은 r1.3.1보다 훨씬 강하다(보정 없이 17 station에서 8.2°). 이후 실험을 r2.1.0으로 한다면 Goal 1의 DR 기준도 이 값이 된다.
- G1-MODEL-001 v3.2 §4.5에 반영한 내용: 1차 DR 파라미터는 사전등록대로 r1.3.1 값(β 2.046, σ_w 0.486, σ_β 0.45)을 유지하고, r2.1.0 기반 DR(β 0.48°/station, σ_w 0.40°)과 σ_β 0.93을 민감도로 추가했다.

## 7. 남은 질문과 다음 측정

| 질문 | 측정 | 판정 기준 |
|---|---|---|
| r2.1.0에서 run 간 오차율이 재현되는가 | r2.1.0 trackA REPEAT, **다른 날 2회 이상**, bag 포함 | station당 평균이 0.48°의 ±10% 이내면 "고정 소프트웨어 조건에서 보정 가능" |
| 날짜와 소프트웨어 중 무엇이 원인인가 | 같은 날 r1.3.1과 r2.1.0을 연달아 실행, 둘 다 bag 포함 | 같은 날 두 버전의 sweep 구간 오차 차이 |
| 느린 회전 손실(deadband)이 원인인가 | 위 bag에서 회전 프로필(각속도 분포)과 sweep 오차 비교. 가능하면 OpenCR `gyroRaw` 기록 | 느린 회전 비율과 sweep 오차의 관계 |

## 8. 재현

```sh
# 입력 추출
git show 3018bb5:data/raw/tb3_motion_20261004_20261111/trackA/teach/teach.json > teach.json
git show 14f8a76:data/raw/tb3_motion_20261004_20261111/trackA/repeat_20261004_141119/repeat.json > repeat_1004.json
git show 95ec6c0:data/raw/tb3_motion_20261004_20261111/trackA/repeat_20261113_061314/repeat.json > repeat_1113.json
git lfs pull --include="data/raw/tb3_motion_20261004_20261111/trackA/repeat_20261113_061314/bag/*"   # bag 진단용
# bag 배열 추출(rosbags 패키지)과 분석
python -I extract_bag.py <bag 디렉터리> bag_arrays.npz
python -I analyze_runs.py --teach teach.json --repeat R1004=repeat_1004.json --repeat R1113=repeat_1113.json \
    --bag-arrays bag_arrays.npz --out RUN_20261113
```

- `RUN_20261113/RESULTS.json`: 위 표의 모든 수치, 입력 SHA-256. `MANIFEST.json`: 명령, 시각, 출력·스크립트 SHA-256.
- 실행 기록의 경로는 실행 환경(샌드박스)의 임시 경로다. 입력 SHA-256이 기준이다.
- bag 배열(`bag_arrays.npz`, 3.9 MB, SHA-256 `RESULTS.json`의 `bag.sha256`)은 저장소에 넣지 않았다. 위 명령으로 재생성한다. 재생성 결과는 원래 추출과 배열 단위로 일치함을 확인했다.
