# RF causal Stage 7–8 패치 전달 검증

## 고정 기준

- 기준: GitHub `myoungsunk/sionna-resimulation` exact `4d2414a7238176b6e116cae2d10546e724b66b8d`.
- 기준 파일: `research/DS_REASSESS_STAGE235_V21_20261028/code`.
- GitHub `results/PATCH_V2_FINAL.json`에서 원본 실행 코드 **10개 SHA256**를 가져와 패치 설치기에 하드 고정했습니다. 실제 GitHub API에서 10개 값을 다시 대조했습니다.
- **적용 방식:** 기존 GitHub checkout을 쓰기 변경하는 git apply가 아니라, `APPLY_PATCH.py`가 코드만 다른 빈 CodeOut에 복사하고 3개의 신규 Python 파일을 추가합니다. 기존 `dsreassess/engine.py` 등은 복사본도 byte-equal입니다. `git apply` 호환 unified diff는 별도 제공합니다.

## 실행한 QA

1. Python syntax `compileall` PASS.
2. 4상태 원본 EKF 코드와 신규 개입/접속코드를 묶은 합성 tests **15/15 PASS**. 기존 패키지의 8개 합성 tests 및 신규 7개.
3. `git apply --check` 후 테스트용 코드 사본에 실제 적용, unified diff SHA 및 테스트 15/15 PASS.
4. 패치 설치기 독립 합성 Git fixture 시험 PASS: Git HEAD·기준 소스 해시·최종 manifest 확인, 신규 복사본 생성, 원본 변경 없음, 두 번째 경로 재사용 시 중단, Windows CRLF/LF 자동 정규화.
5. 첫 GT pass ±10s의 2s smoothed residual 분해, exact GT 편파 oracle, original A_B mask/원 측정/R 고정, 2×2 차이의 차이 수치 항등식 검증.
6. first pass 종료 직후 suffix 재귀 계산의 원래 BASE/EXDS full replay `x/P` parity (합성). 두 번째 통과 시작 packet의 엄격한 제외 경계 검증.
7. Stage 8 각 Arm의 `K_r ν_r + K_s ν_s = Kν` 및 full NPZ 입력/출력 필드 검증.

## 이번 QA에서 **수행하지 않은 것**

- 원본 Sionna/SourceFFD bank/E1 LFS trace를 사용한 *실제* 재귀/입력-parity 실행은 사용자 환경에서 해야 합니다.
- 실제 패치된 `4d2414a` checkout에 대한 로컬 폴더 복사 실행은 시행하지 않았습니다. GitHub 결과 manifest SHA와 고정 API를 대조하고, 합성 Git fixture에서 설치기를 검증했습니다.
- 편파 오차의 물리적 근원/시간상관 인과/다중경로 모델의 일반화 여부를 실험 결과로 판정하지 않았습니다.

## 실제 실행 시 강제 게이트

- HEAD 정확히 `4d2414a`, 원본 실행 코드 10개 SHA/manifest 일치.
- 원래 SourceFFD/E1 blob 및 입력 해시 검사.
- Stage 7 모든 case의 BB/MB `x,P,prior,Pprior,K,H,h,ν,μ,R,acc` 오차 최대 `1e-10` 이하.
- GT 오라클의 `z-h(GT)-μ` 계산 오차 `3e-12` 이하.
- Stage 8의 full posterior x/P suffix 재현 `1e-10` 이하.
- 15개 Arm/조건 및 Stage 8 24개 Arm/조건 모두 결과 생성, 각 단계 SHA/QA PASS.
- 코드·입력·선택 조건·출력 매니페스트가 맞지 않으면 즉시 중단하고 절대 `CAUSAL_FINAL_QA.json`을 만들지 않음.

최종 `TECHNICAL_QA_PASS_NOT_SCIENTIFIC_CAUSAL_PROOF`는 숫자적 재현 확인이지 과학적 원인의 최종 입증은 아닙니다.
