# FP Native–B 인과 분해 및 B/K1/K2 폐루프 재현 (2026-11-08)

기준 원본 커밋: `c141839093d1a2e4a76f91eea632cb6467163e28`.
원본 R0–R5 입력·코드·결과를 변경하지 않는 별도 Actions 검증입니다.

## 검증 범위

1. Native/ B 측정치의 NN/BN/NB/BB 폐루프 W0 비교 (동일 초기조건·운동모델·SourceFFD, R2/R4/R5 B0 Full seed10).
2. 네 정책 자체 shadow 게이트와 Native 게이트 고정 대조.
3. B-only 기준선의 원래 R5 trace parity와 native W0 trace parity 검증.
4. B-only, K1_R/K2_R, K1_RS/K2_RS의 실제 재귀 재실행 및 저장 R5 trace 모든 상태·공분산·게이트·선택 기록 parity 확인.
5. NN 대비 BN/NB/BB Heading·XY MSE 차이, 상호작용, NEES3, 범위 및 s 혁신의 직접 효과/상태 피드백 분리.

## 실행

`.github/workflows/fp-native-b-causal-20261108.yml`은 이 브랜치 push 및 workflow_dispatch에 반응합니다.
Workflow v3는 GitHub Release `fp-sc-original-npz-20261108`에서 NPZ 6개와 FFD bank 2개를 받고 저장소에 고정한 SHA-256 및 크기를 검증합니다. LFS와 만료되는 Actions 입력 아티팩트에 의존하지 않습니다.
체크아웃한 Python 소스를 직접 실행하며 과거 analysis_package.tar.xz는 보존만 합니다.

R2, R4, R5 Native/B 기준선 재현을 먼저 통과해야 K 재현과 전수 계산에 진입합니다. 자연/고정 게이트의 pooled MSE와 실제/가상 한 단계 효과를 분리합니다.
보정 민감도는 frozen, zero_mean, zero_mean_common_R 세 설정입니다. B 전용 보정 학습이나 일반화 검증을 뜻하지 않습니다.

결과는 fp-native-b-baseline-<run_id> 및 fp-native-b-causal-v3-<run_id> 아티팩트에 30일 보존합니다.
세부 변경 계약은 [REPAIR_CONTRACT_20261108.md](REPAIR_CONTRACT_20261108.md), 사전 로컬 검증은 [LOCAL_VALIDATION.json](LOCAL_VALIDATION.json)을 참조합니다.

**상태 구분:** 코드 정적·합성 검사 PASS는 과학 결과 PASS가 아닙니다. 실데이터 PASS는 실제 Actions `RESULTS.json` / `B_K_REPLAY/RESULTS.json`과 검증 완료 로그를 확인한 이후에만 주장합니다.
원본 노출된 하나의 corridor·seed10 데이터이므로 외부 환경으로의 일반화/독립 감사는 아닙니다.
