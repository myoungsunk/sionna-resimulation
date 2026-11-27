# BLOCK_C M7 추가 sweep 결과

[실행 계획](https://github.com/myoungsunk/sionna-resimulation/blob/1e26547c0e58d17f443525d83134b057859b4497/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8/lut_replace/block_v2/two_scale_s1/sweep_ext/PLAN_SWEEP_EXT_KO.md)에 따라 Snowball에서 326위치·12,708 RF pose를 생성했다. BLOCK_C 앵커 B와 원본 M7의 반사·투과 설정, 최대 깊이 3, 광선 100,000개, seed 20260924를 사용했다. 기본 17개 주파수 노드에 적응 추적을 적용했고, `H_full`, `H_LoS`, `PATHS_NEAR`를 같은 trace에서 만들었다.

| 실행 | 위치 | RF pose | RT 추적 | 원본 대조·병합·검증 포함 | 원본 결과 |
|---|---:|---:|---:|---:|---|
| A | 125 | 4,500 | 29.22초 | 92.19초 | [Run A](../../artifacts/BLOCK_C_M7_EXT_A_20261127_ZTuwVf7S/) |
| C | 9 | 1,296 | 15.43초 | 65.92초 | [Run C](../../artifacts/BLOCK_C_M7_EXT_C_20261127_Wqwau3Xq/) |
| B | 192 | 6,912 | 55.54초 | 126.42초 | [Run B](../../artifacts/BLOCK_C_M7_EXT_B_20261127_J85C8uA7/) |

세 실행 모두 G0·G4·G8을 통과했다. Run C는 기존 10° 격자의 324 pose에서 Full·LoS 채널 행이 모두 바이트 단위로 일치했다. [GC 기록](../../artifacts/BLOCK_C_M7_EXT_C_20261127_Wqwau3Xq/GC_FULL_LOS.json)

Run B는 [A의 조건부 실행 판정](A_TRIGGERS.json)에 따라 시작했다. A2의 네 중심 중 두 곳에서 Dδ(20 cm)가 2° 이상이었다. [A 추출 입력과 해시](A_PROVENANCE.json)와 [기존 V1 재현 확인](OLD_ONLY_CHECK.json)을 함께 제공한다.

각 실행의 `results/H/BLOCKC_B/`에는 복소 채널 배열 `(pose, 257, 2, 2)`가 있고, `results/paths/BLOCKC_B/`에는 경로와 trace 기록이 있다. pose 표와 위치별 원본 trace도 `results/`에 포함된다. `results/completion.json`에는 원본 결과 파일의 SHA-256과 검사 결과가 있다. `.npy`와 `.npz`는 Git LFS로 받는다. [로컬 검증 스크립트](verify_local_run.py)는 Python과 NumPy 환경에서 실행할 수 있다.
