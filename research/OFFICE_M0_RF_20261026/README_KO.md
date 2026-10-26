# Office O01/O02/O03 Mount 0° RF 생성

사용자 요청: 2026-10-26. 기존 45° 결과와 비교 가능한 **0° Full/Direct-LoS 쌍**을 별도로 생성한다.

## 범위와 동결 조건

| 경로 | 전체 운동 프레임 | RF 포즈 | 앵커 | 마운트 |
|---|---:|---:|---|---:|
| O01 | 461 | 192 | O0 (5, 2.2, 2.65 m) | 0° |
| O02 | 521 | 207 | O0 | 0° |
| O03 | 1,175 | 412 | O0 | 0° |

- 기존 Office E 공간·물성·높이·주파수·포트 순서를 보존한다.
- 기존 45° 경로의 시간, pose_id, 차체 위치/방향, RF 샘플링을 그대로 유지한다.
- 안테나 방향만 `yaw_antenna_deg = yaw_body_deg`로 설정한다.
- LP_plus45 / LP_minus45는 **안테나 포트 이름**이다. 마운트 0°에서도 이 두 포트와 원본 FFD bank를 유지한다.
- 배열은 경로별 `[N,257,2,2]` complex128. Full과 Direct-LoS는 동일 포즈/시각에서 새로 계산한다.
- M45 배열의 이름만 바꾸거나 회전하여 재사용하지 않는다.
- 차폐된 Direct-LoS는 `LOS_EXISTS=false`와 0 채널로 보존한다.
- 센서 생성·보정 모델 재학습·필터 성능 평가는 이번 RF 생성 범위에 포함하지 않는다.

## 기준 소스

- M45 Release: https://github.com/myoungsunk/sionna-resimulation/releases/tag/route-rf-o01-20261019-r01
- 압축파일 SHA256: `e4f3d130cfd8fc6d59261e3c6d2087243217b3d567d52cc4857299629f82eeca`
- 원본 FULL_PLAN SHA256: `a8d9a2cc14575f90c5d0523552f15a901d5aaef39e07bc9cb3d534b41c5abc35`
- 원본 RF runner SHA256: `5c91c902186df00dbad669ba98c23618c0a2aa9b1a4762618de143dc8de696be`
- 원본 소스 commit: `df1bee938c71ac17b1910edbf94ae563e4610bb7`

원본 Release를 SHA 검증 후 필요한 소스만 추출한다. 당시 생성기로 45° RF CSV를 재생성하여 세 경로 모두 원본 계획의 CSV 해시와 일치해야 한다. 그 후 0° 경로를 생성하고 안테나 방향 이외 모든 운동 값이 같은지 검사한다. 전체 운동 CSV도 이번 산출물에 포함한다.

기존 RF runner의 마운트 검증식과 설명 문장만 0°용으로 바꾼다. RF 계산·Direct-LoS 추출·원시 경로 재계산·FP 검수는 그대로 사용한다. 원본과 변경 후 runner의 해시를 모두 기록한다.

## GitHub Actions

Workflow: `.github/workflows/office-m0-rf-20261026.yml`

1. **prepare**: 원본 소스/계획 해시 검증, 0° 좌표 생성, 긍정·부정 검증, 정확한 FFD bank 복원.
2. **pilot**: O01/O02/O03의 첫 20개 RF 포즈를 각 257주파수 모두 계산하고 검수한다.
3. **full**: 세 파일럿 모두 통과한 뒤 나머지 39배치를 계산한다.
4. **aggregate**: 총 42배치·811포즈가 빠짐없이 있고 원본 QA가 통과했는지 확인한 뒤 경로별로 묶는다.

- 최초 workflow 등록 push는 full 캠페인을 시작한다.
- `workflow_dispatch`가 제공되는 경우 `mode=preflight`는 RF 계산 없이 입력 검증만 수행한다.
- RF 자동 재시도 없음. 실패하면 후속 단계는 중단하며 로그·실패 receipt·부분 결과를 보존한다.
- 동시 RF 작업 최대 2개, 배치당 최대 20포즈, 작업당 시간 제한 180분.
- 총 예상 PathSolver 호출: **811 × 257 × 2 = 416,854**.
- CPU 시뮬레이션이므로 장시간 실행될 수 있다. Actions 시작/완료와 RF 검수 PASS를 구분한다.
- hosted Ubuntu에서 실행하며 Snowball 접속·로봇 동작은 사용하지 않는다.

## 검수 기준

기존 M45 기준을 유지한다.

- Full에서 추출한 direct와 별도 Direct-LoS의 복소 상대 오차 ≤ 1e-4.
- 원본 FFD의 해석적 direct 대비 복소 상대 오차 ≤ 1e-4.
- 직접 경로 지연 오차 ≤ 1e-12 s.
- 유효 direct 표본에서 FP tap 동일, 편파 s 절대 차 ≤ 1e-4.
- 저장한 원시 경로에서 Full 재구성 오차 = 0.
- 파일 SHA, 포즈 순서, 배열 크기·자료형·유한값, 전체 배치 범위 검사.
- 차폐 표본에 허구의 LoS를 채우지 않는다.
- 물리·수치 QA 통과는 추정 정확도나 독립 장면 일반화의 PASS가 아니다.

## 산출물

각 Actions run의 artifact를 사용한다. 기존 45° Release를 덮어쓰지 않는다.

- `office-m0-prepared-<run_id>`: 동결 소스, FFD bank, 0°/45° 대조 좌표, 입력/변경 해시.
- `office-m0-batch-<batch_id>-<run_id>`: 배치 배열, 원시 경로, FP/경로 수, QA, 실행 근거.
- `office-m0-final-<run_id>`: `O01_M0.tar.gz`, `O02_M0.tar.gz`, `O03_M0.tar.gz`, 압축파일 해시, 캠페인 receipt.

최종 묶음은 CASES의 Full/Direct-LoS/visibility/주파수/FP/경로 수, 전체 운동 CSV와 RF CSV, 계획·검증 기록을 포함한다. 원시 경로는 같은 run의 배치 artifact에 남긴다. 보관 기간은 30일이며 GitHub Release 영구 게시는 별도 작업이다.

## 오프라인 확인

```bash
python research/OFFICE_M0_RF_20261026/pipeline.py prepare --root work
python research/OFFICE_M0_RF_20261026/pipeline.py selftest --root work
```

prepare/selftest는 RF를 계산하지 않는다. RF 결과 상태는 실제 Actions receipt로만 판단한다.

