# G1-MODEL-001 v3.3 RUN3

실행 ID는 `RUN3_20261113T085001Z`다. [동결 사양 v3.3](https://github.com/myoungsunk/sionna-resimulation/blob/cb5496afeebe8f48ffebc2d541a3af0733ca0d42/research/G1_SWEEP_HEADING_FLOOR_20261113/SPEC2_KO.md#L231-L266)의 G-SNAP과 G-E2E를 Snowball에서 실행했다. 독립·Markov 모델에 각각 250쌍을 적용했다. G-E2E 판정은 **INCONCLUSIVE**다. Markov 누적 포함률의 점추정 차이는 0.000%p, 95% 신뢰구간은 [−2.497, +2.497]%p로 허용폭 ±2.0%p를 넘었다. 사양에 따라 S2′ 본 계산과 §8 판정은 시작하지 않았다. Step 3는 보류 상태다.

- [실행 보고서](outputs/REPORT_KO.md)
- [G-E2E 결과](outputs/S1P_G_E2E.json)와 [짝별 경로 집계](outputs/S1P_G_E2E_PATHS.csv)
- [경로 CSV 재집계 검증](outputs/REAGGREGATION.json)과 [G-SNAP 결과](outputs/S1P_SNAP.json)
- [실행 명령과 SHA-256](outputs/MANIFEST.json), [격자 색인](grid/S1P_R5_aA_m0_M1R_JOINT_INDEX.json), [배열 해시](outputs/S1P_J_SHA256.csv)

매니페스트의 출력 경로는 이 폴더 기준이다. 코드 해시 항목은 `code/`에 있다. 실행에 사용한 사양서와 [RUN2](../RUN2_20261113T072631Z/)에서 인용한 R0·G-OBS 증거도 실행 당시 바이트로 보존했다. `code/launch.sh`와 `code/bias.sh`의 경로는 Snowball 실행 환경을 가리킨다.

J와 최소 잔차의 대용량 `.npy` 배열은 실행 서버에 보관했다. 격자 색인과 배열 해시는 이 폴더에 포함했다.
