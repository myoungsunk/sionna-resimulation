# G1-MODEL-001 v3.4 S2′ 1차 계산

실행 ID는 `RUN4_20261113T105130Z`다. [동결 사양 v3.4](../SPEC2_KO.md)의 §8 판정은 **`FULL_6 / STOP`**이다. 6개 case의 90° station 122개와 station bootstrap 1,000회 × 공통 난수 200경로를 사용했다. 독립 모델은 모든 기준을 통과했고, Markov 모델의 누적 포함률은 84.38%로 기준 88%에 미달했다. **Step 3는 보류했다.**

- [실행 보고서](s2_out/REPORT_KO.md)와 [§8 판정](s2_out/S2P_VERDICT.json)
- [독립 검증 기록](s2_out/INDEPENDENT_CHECK.json)과 [Markov 포함률 진단](s2_out/MARKOV_COVERAGE_DIAGNOSTIC.json)
- [경로별 결과](s2_out/S2P_NOMINAL.npz), [부트스트랩 집계](s2_out/S2P_BOOTSTRAP.npz), [난수·RF 선택 기록](s2_out/S2P_DRAWS.npz), [station별 지표](s2_out/S2P_CURVES.csv)
- [5개 공통 case B0 짝 비교](s2_out/B0_COMPARISON.json)와 [DR 잔여 편향 민감도](s2_out/S2P_SIGMA_BETA_STAR.csv)
- [동결 실행 명령과 SHA-256](MANIFEST.json), [진입 검사 G-E2E′ 결과](entry_gate/outputs/S1P_G_E2E.json), [진입 검사 매니페스트](entry_gate/MANIFEST.json)

본 계산 매니페스트의 `root_sha256`, `output_sha256`, `code_sha256`에 열거된 파일과 격자 색인을 실행 당시 바이트로 보존했다. `grid_files` 중 J와 최소 잔차의 `.npy` 배열은 Snowball의 `/home/KMS/RUN4_20261113T105130Z/grid/`에 있으며, 색인과 [M1-R 배열 해시](GRID_SHA256.txt), [M0 배열 해시](M0_GRID_SHA256.txt)를 여기에 실었다. 이 폴더의 `entry_gate/`에는 별도 실행 `RUN4_20261113T094312Z`의 매니페스트와 진입 판정에 사용한 증거를 실었다. 진입 검사 매니페스트에 열거된 전체 기록은 해당 Snowball 실행 폴더에 보관했다.

독립 검증은 저장된 경로와 station bootstrap의 재집계, 난수와 RF 행 선택 재현, B0의 짝 일치와 민감도 교차점 확인을 포함한다. 실행 범위와 미실행 arm은 [보고서](s2_out/REPORT_KO.md)에 기록했다.
