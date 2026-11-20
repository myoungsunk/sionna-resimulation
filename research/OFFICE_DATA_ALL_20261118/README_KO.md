# Office RT 실험 데이터 전체 색인

2026-11-18에 GitHub의 기존 Office 브랜치와 Release를 먼저 확인하고 Snowball 원본과 대조했다. 기존 자료의 위치는 유지하고, 빠져 있던 원시 경로와 새 전 방향 sweep을 이 폴더에 추가했다. 확인 결과와 기존 브랜치의 커밋은 [EXISTING_GITHUB_CHECK.json](EXISTING_GITHUB_CHECK.json)에 기록했다.

## 데이터 다운로드 위치

| 자료 | 내용 | 위치 |
|---|---|---|
| **새 35 station 전 방향 sweep** | −180°~+180°, 10° 간격. 고유 RF 1,260 pose, 관측 1,295행. 257 bin 직접 trace | [H_full.npy](full360/H_full.npy), [RF pose](full360/rf_poses.json), [관측 순서](full360/SAMPLES.json), [전체 결과](full360/) |
| **기존 35 station sweep 원본 전체** | 0°~180°, 10° 간격, 665 pose. H와 누락됐던 raw sweep NPZ 35개, 과거 파일럿·형상·검증 기록 포함 | [원본 아카이브](payloads/OFFICE_GITHUB_ORIGINAL35_20261118.tar), [파일별 SHA-256](payloads/OFFICE_GITHUB_ORIGINAL35_20261118.tar.json) |
| **O01·O02·O03, mount 0°** | 각 192·207·412 RF pose의 Full/Direct-LoS H, 시간순 pose, QA. 42 batch의 raw paths·검증·입력·로그도 별도 첨부 | [기존 GitHub Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/office-m0-rf-20261026-complete) |
| **O01, mount 45°** | 원래 궤적의 H·경로·pose·검증 | [O01 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/route-rf-o01-20261019-r01) |
| **O02, mount 45°** | 원래 궤적의 H·경로·pose·검증 | [O02 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/route-rf-o02-20261019-r01) |
| **O03, mount 45°** | 원래 궤적의 H·경로·pose·검증 | [O03 Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/route-rf-o03-20261019-r01) |
| **O01~O03, mount 0°·45°, RF 5배 밀도** | 관측 8,086행의 H·pose·QA, 신규 300개 trace 배치의 원시 경로, 실행 기록 | [데이터 색인](rf_5x/), [GitHub Release](https://github.com/myoungsunk/sionna-resimulation/releases/tag/office-route-rf-5x-20261119) |
| **과거 O01 파일럿** | 초기 시도와 RF_R02의 원본 H·경로·입력·로그. 당시 판정 유지 | [파일럿 아카이브](payloads/OFFICE_GITHUB_PILOT_20261118.tar), [파일별 SHA-256](payloads/OFFICE_GITHUB_PILOT_20261118.tar.json) |
| **mount 준비·파생 입력** | 기존 feature·label·timeline, 검증 및 코드 | [기존 inputs 브랜치](https://github.com/myoungsunk/sionna-resimulation/tree/e4ccdd737fac9961261b7483095a79e515297111/research/OFFICE_CORRIDOR_POWER_PWIDE_TRANSFER_20261026/mount_inputs_20261027) |
| **모델·transfer 실행 결과** | 기존 모델, scores, QA, 실패·재시도 기록, EXECUTION_EVIDENCE | [기존 실행 브랜치](https://github.com/myoungsunk/sionna-resimulation/tree/9ec8790f0985132c5e7b2e9293ce53cdfff7714c/research/OFFICE_CORRIDOR_POWER_PWIDE_TRANSFER_20261026/run_mount0_45_20261027), [transfer 자료](https://github.com/myoungsunk/sionna-resimulation/tree/33e9849be8c5c62d45eb7e5ade7e85438b8fa247/research/OFFICE_CORRIDOR_POWER_PWIDE_TRANSFER_20261026) |
| **준비 상태 감사 기록** | 보존된 READINESS_DATA_AUDIT와 검사 코드·lock | [아카이브](payloads/OFFICE_GITHUB_READINESS_20261118.tar) |
| **Office 형상·RT 생성기·설정·FFD** | 원본 커밋 819fa93의 동결 소스 92개 파일. LP ±45° FFD bank 원본 포함 | [source](source/), [실행 설정과 해시](full360/RUN_CONTRACT.json), [소스 전송 검사](SOURCE_COPY_CHECK.json) |
| **2D 맵과 추출 위치·궤적** | 35 station, O01~O03 경로, 좌표표 및 맵 생성 코드 | [맵](maps/office-rt-map.png), [PDF](maps/office-rt-map.pdf), [맵 자료 전체](maps/) |

대형 NPY·NPZ·TAR 파일은 **Git LFS**로 저장했다. GitHub 파일 페이지의 **Download raw** 또는 Git LFS를 사용해 실제 바이너리를 받는다. 파일 목록만 있는 LFS 포인터와 원본 배열을 구분해야 한다. 기존 궤적 Release의 아카이브는 Release의 Assets에서 받는다.

기존 35 station의 H와 PASS 기록은 원래 [Office 브랜치](https://github.com/myoungsunk/sionna-resimulation/tree/b05af070a87981f8712fdd41eac4c1bbb882e9c7/results/OFFICE_SNOWBALL_20261008_819fa93)에도 있다. 이번 확인에서 그 브랜치의 raw sweep NPZ 35개가 빠져 있음을 확인해 위 원본 아카이브로 보충했다. 기존 기록의 “raw NPZ는 Snowball에 보존”이라는 설명은 당시 상태를 나타낸다.

## 새 전 방향 sweep의 설정과 검증

Office의 기존 35개 위치, anchor O0=(5, 2.2, 2.65) m, 수신 높이 0.45 m, mount 0°를 사용했다. 기존 Office 생성기·형상·재질·FFD와 RT 옵션을 유지했다. `refraction=true`, `samples_per_src=100000`, `max_depth=3`, `seed=20260924`이며 257개 주파수 bin을 각각 직접 추적했다. 전체 설정은 `full360/RUN_CONTRACT.json`이 기준이다.

−180°와 +180°는 같은 물리 pose다. 따라서 고유 RF 표는 위치당 36개이고, 관측 순서 표는 위치당 37행이다. +180° 관측은 −180°의 `pose_id`와 `h_row`를 참조한다. H는 `(1260, 257, 2, 2)`의 `complex128` 저장 배열이다. 내부 연산 정밀도는 원본 생성기를 유지했다.

- 원본 기준 chunk 검증 **70/70 PASS**, 문제 0건.
- 기존 0°~170° 구간의 복소 계수 **647,640개가 비트 단위 일치**, 최대 절대 차이 **0**.
- H와 원시 경로 목록은 같은 trace에서 저장했다. 경로 파일은 `full360/rf_poses.json`의 `raw_trace_path`로 찾는다.
- 생성·원본 기준 검증 시간은 **3,372.592초, 약 56분 13초**다.
- [실행·검증 설명](full360/README_KO.md), [검증 결과](full360/VALIDATION.json), [기존 데이터 비교](full360/ORIGINAL_OVERLAP_CHECK.json).

기존 O01~O03 궤적과 파생 모델 자료는 각각의 원래 receipt·plan·설정을 기준으로 해석한다. 파생 입력/transfer 실행을 새 RF trace로 세지 않는다. 이전 실패 및 재시도 기록과 원본 데이터를 그대로 보존했다.

## 보관과 무결성

기존 M0/M45 Release의 데이터 아카이브 7개는 GitHub의 현재 `uploaded` 상태와 서버가 제공하는 SHA-256을 확인했고, Snowball 원본 아카이브의 SHA-256과 모두 일치했다. 신규 폴더의 파일 해시는 `FILES_SHA256.json`에 있다.

```console
python verify_package.py
```

이 검사는 내려받은 파일의 해시를 확인한다. 원래 실험의 판정 기준이나 결과를 바꾸지 않는다. Snowball의 원본 실행 폴더와 로컬 수신 자료도 보존했다.
