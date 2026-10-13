# DR EKF 코드 감사 및 개발 실행 결과

- 기준 커밋: `3032a58925ad4d1e3acec85865958e6580d79be7`.
- 작업 브랜치: `codex/dr-ekf-causal-followup-v2-20261013`.
- 실행 환경: 로컬 Windows / Python 3.10. 클라우드 D6 cache는 제공되지 않음.
- 수정은 로컬 감사 사본에만 적용. GitHub push 및 V5 사전등록/확증은 실행하지 않음.

## 감사 결과 및 수정

1. V5의 사전등록 해시가 일부 과학적 의존성과 입력을 누락: frozen source 전체 Python, scoring, motion CSV 및 체크섬까지 해시 봉인하도록 보강.
2. V3/V4가 미래 확증 seed를 개발에 사용할 수 있음: CLI 개발 seed를 8000:8032로 제한.
3. V0가 비대칭 공분산과 잘못된 heading/conditional NEES, heading sigma를 놓칠 수 있음: 검증 및 손상 캐시 회귀 테스트 추가.
4. V3 음수 steps 입력을 거부하도록 추가.
- 독립 read-only 감사: 최초 REDIRECT, 수정 후 V3/V4 개발 실행 ACCEPT.
- 원본 테스트 10/10, 수정 후 19/19 PASS. compileall exit 0.
- angle wrap 인접 Hessian의 heading 혼합/대각 도함수를 해석식과 대조.
- 패치의 기준 커밋 적용 가능성을 별도 index에서 git apply --cached --check로 확인.

## 실행 상태

| 단계 | 범위 | 결과 |
|---|---|---|
| V0 | 로컬 캐시 상태 확인 | INCOMPLETE_NO_D6_VERDICT; 63개 MISSING |
| V1 | 공식 D6 대조 준비 확인 | NOT_READY |
| V2 | GitHub D5_PF_VALIDATION.json | PARTIAL_VALIDATION; V1 COMPATIBLE, V2/V3/V4 NOT_RUN |
| V3 smoke | R2, drift 0/2, seed 8000:8002, 80 steps | exit 0, DEVELOPMENT_ONLY |
| V3 full-route pilot | R2, drift 2, seed 8000:8004, 전체 979 samples | exit 0, DEVELOPMENT_ONLY |
| V4 pilot | R2, drift 2, seed 8000:8004, 전체 경로, 8 oracle subsets | exit 0, DEVELOPMENT_DIAGNOSTIC |
| V5 | 후보 및 커밋된 사전등록 없음 | NOT_RUN |

## V3 전체 경로 파일럿

| 방법 | ANEES | 말기 ANEES | coverage95 | 위치 RMSE (m) |
|---|---:|---:|---:|---:|
| BASE | 160.653817 | 512.925242 | 0.496984 | 1.910596 |
| MEAN2 | 99.631966 | 299.899410 | 0.403498 | 1.879929 |
| COV2 | 87.181092 | 246.608448 | 0.566647 | 1.910336 |
| BOTH2 | 55.105061 | 142.914861 | 0.449638 | 1.879680 |

## V4 파일럿

| Oracle subset | ANEES | 말기 ANEES | coverage95 | 위치 RMSE (m) |
|---|---:|---:|---:|---:|
| none | 160.653817 | 512.925242 | 0.496984 | 1.910596 |
| bg | 3.354714 | 4.568185 | 0.963209 | 0.429786 |
| sf | 18.028089 | 19.171181 | 0.590169 | 0.971164 |
| eps | 2.398298 | 2.957420 | 0.964113 | 0.429979 |
| bg+sf | 2.243397 | 2.502447 | 1.000000 | 0.402299 |
| bg+eps | 3.394063 | 4.698260 | 0.945416 | 0.432329 |
| sf+eps | 2.460923 | 2.968221 | 1.000000 | 0.429305 |
| bg+sf+eps | 2.143978 | 2.355179 | 1.000000 | 0.402214 |

## 해석 및 남은 조건

- 4 seed · 단일 셀 개발 파일럿이다. 9셀 × 32 seed 개발 캠페인 및 300 seed 확증 결과가 아니다.
- V4 oracle 개입은 참값 정보를 제공하는 진단이며 배포 가능한 개선으로 취급하지 않는다. Fisher 지표는 공유 입력 C를 무시한 근사다.
- V3의 두 보정은 Gaussian quadratic Taylor 근사이며 전체 고차 모멘트 오차를 모두 분해했다는 주장은 불가하다.
- V5 후보는 이 파일럿만으로 채택하지 않았다. 클라우드 D6 감사와 PF 자료 및 충분한 개발 결과 후 후보 하나를 사전등록해야 한다.
- 클라우드에서 필요한 데이터: D6 7 arm × 9셀의 seed 8100–8399 캐시 63 NPZ, out/D6_CONFIRMATION_s8100-8399.json, 최신 out/D5_PF_VALIDATION.json, 관련 manifest 및 완료 로그. 폴더 구조를 유지한다.
- 원래 D6 spec/prereg/harness 및 로컬 원본 out 파일은 실행 전후 SHA256 동일. 클라우드 D6에는 쓰기를 수행하지 않았다.

## 변경·산출물

- 변경 소스 4개: common.py, v3_second_order.py, v4_calibration.py, v5_independent.py; 회귀 테스트 1개.
- 기존 데이터 이동/삭제 없음. 필요한 파일만 추출한 감사 사본이며 배포는 audit_fixes.patch를 원본 커밋에 적용하여 수행한다.
- audit_fixes.patch: 소스 및 테스트 변경 패치. source_changes.json: 전후 해시.
- execution_receipt.json, v3_fullroute_receipt.json: 실제 명령·시각·종료 코드·소요 시간.
- 각 단계 디렉터리: JSON 결과 및 manifest. 각 단계 .log: stdout/stderr.
- 다음 작업: 클라우드 D6 cache/out 수령 후 새로운 출력 폴더로 V0 → V1 → V2 실행.
