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
Workflow는 `analysis_package.tar.xz`에서 소스를 풀고, 검증된 FFD bank Actions 아티팩트 및 기존 LFS 입력을 받아 해시 검사 후 실행합니다.
실행 로그 및 실패 기록은 `fp-native-b-causal-<run_id>` Actions 아티팩트에 보존하며 원본 소스를 덮어쓰지 않습니다.

필수 FFD bank 아티팩트는 GitHub Actions run 38875080492, `ffd-verified-original-38875080492`이며 보존기한 내 사용해야 합니다.

**상태 구분:** 코드 정적·합성 검사 PASS는 과학 결과 PASS가 아닙니다. 실데이터 PASS는 실제 Actions `RESULTS.json` / `B_K_REPLAY/RESULTS.json`과 검증 완료 로그를 확인한 이후에만 주장합니다.
원본 노출된 하나의 corridor·seed10 데이터이므로 외부 환경으로의 일반화/독립 감사는 아닙니다.
