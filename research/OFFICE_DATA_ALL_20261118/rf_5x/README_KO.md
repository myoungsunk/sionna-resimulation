# Office O01~O03 RF 5배 밀도 데이터

Office O01~O03의 기존 궤적과 mount 0°·45° 설정으로 RF 관측 간격을 각각 1/5로 줄였다. 기존 0.25·0.50·1.00초 간격은 0.05·0.10·0.20초가 됐다. 기준 anchor는 O0=(5, 2.2, 2.65) m이다.

| 궤적 | 관측 수 / mount | Mount 0° | Mount 45° |
|---|---:|---|---|
| O01 | 956 | [H·pose·QA](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o01-m0-5x-case.tar.gz) · [원시 경로](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o01-m0-5x-raw.tar.gz) | [H·pose·QA](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o01-m45-5x-case.tar.gz) · [원시 경로](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o01-m45-5x-raw.tar.gz) |
| O02 | 1,031 | [H·pose·QA](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o02-m0-5x-case.tar.gz) · [원시 경로](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o02-m0-5x-raw.tar.gz) | [H·pose·QA](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o02-m45-5x-case.tar.gz) · [원시 경로](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o02-m45-5x-raw.tar.gz) |
| O03 | 2,056 | [H·pose·QA](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o03-m0-5x-case.tar.gz) · [원시 경로](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o03-m0-5x-raw.tar.gz) | [H·pose·QA](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o03-m45-5x-case.tar.gz) · [원시 경로](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-o03-m45-5x-raw.tar.gz) |

## 배열 및 원시 경로

각 케이스의 `RADIO_POSE.csv` 행 순서가 H 배열 첫째 축과 같다. `H_FULL.npy`, `H_DIRECT_LOS.npy`, `H_DIRECT_FROM_FULL.npy`, `H_ANALYTIC_DIRECT.npy`는 모두 `complex128`이며 축 순서는 `[pose, frequency, rx, tx]`다. 포트 순서는 Rx와 Tx 모두 LP +45°, −45°다. `FREQUENCIES_HZ.npy`와 LoS 표시, 경로 수, first path 및 전계 대조 결과를 각 케이스에 포함했다.

총 8,086개 관측 중 1,766개는 원본 궤적 H를 참조한다. 6,320개 관측은 신규 추적에서 나온 5,928개 고유 pose에 매핑된다. 원본 궤적과 같은 RT 설정으로 고유 pose당 257개 주파수 bin에서 직접 추적했다. 설정 및 소스 해시는 실행 증거 아카이브의 `FULL_PLAN.json`, `SOURCE_SHA256.json`, 각 추적 배치의 `RUN_MANIFEST.json`에 있다. FFD bank는 [기존 Office 소스](../source/)에서 받는다.

`PROVENANCE.json`은 관측 행을 원본 케이스 또는 신규 추적 배치의 행에 연결한다. 신규 경로는 6개 raw 아카이브를 같은 디렉터리에 풀어 `BATCHES/<batch_id>/raw_paths/bin_*.npz`에서 찾을 수 있다. 원본 재사용 행의 경로는 상위 [Office 색인](../)에 연결된 기존 궤적 Release에 있다.

## 실행과 무결성

Snowball 실행은 2026-11-20 07:53:55 KST에 완료됐다. 신규 추적 300/300 배치, 6개 케이스 병합 및 최종 검증이 모두 통과했다.

- [입력·실행·코드·추적 매핑 아카이브](https://github.com/myoungsunk/sionna-resimulation/releases/download/office-route-rf-5x-20261119/office-route-rf-5x-evidence.tar.gz)
- [최종 QA](COMPLETION.json), [아카이브 목록](ASSET_MANIFEST.json), [아카이브 SHA-256](SHA256SUMS.txt)
