# Dual-LP 원고·LUT 실험 작업 체크포인트 — 2026-11-02

사용자가 요청한 현재 작업 상태의 Git 보존본이다. Obsidian 논문 폴더의 원고·그림·표·코드·입출력 해시·검증 기록을 원본 바이트 그대로 복사했다. 캐시와 Python bytecode만 제외했다. 원본 볼트나 기존 저장소 원고를 덮어쓰지 않았다.

## 원고

- [한글 초안](paper/01%20초안%20-%20한글.md)
- [01b 물리 관측·모델·결과 초안](paper/01b%20본문%20초안%20-%20물리%20관측·모델·결과.md)
- [작성·수용 운용 방식](paper/00%20논문%20작성%20시스템%20운용%20방식.md)

문서의 draft/accepted 상태는 원본의 표시를 따른다. 이 푸시는 원고 수용이나 모델 채택을 뜻하지 않는다. Obsidian wikilink·embed는 원본 표현을 보존했으므로 GitHub에서 일부 링크가 자동 표시되지 않을 수 있다.

## 최신 MB_VAR 비교

Anchor B의 순환(R2)·지그재그(R4)·사행(R5) × B0/L0/L1/L2에서 기존 극점 수정 LUT·거리 반영 LUT·SourceFFD를 비교했다. 거리 반영 LUT 12조건을 새 실행했고 기존 수정 LUT 12조건 재현, 실제 prior 37,632건 Jacobian 차분 검사와 입력 불변 검사를 통과했다. SourceFFD는 앞서 재현 확인한 저장 결과를 재채점했다. 자체 검사이며 독립 감사가 아니다.

| 관측모델 | heading RMSE (deg) | XY RMSE (cm) | heading NEES | XY NEES | pose NEES |
|---|---:|---:|---:|---:|---:|
| 기존 수정 LUT | 0.968851 | 6.411489 | 3.446163 | 3.048230 | 5.692454 |
| 거리 반영 LUT | 0.959092 | 6.439532 | 3.536604 | 3.304233 | 5.417322 |
| SourceFFD | 0.959158 | 6.072518 | 3.068593 | 2.785835 | 4.717821 |

같은 t≥30 s 표본을 합산했다. pose NEES는 x,y,heading의 3차원이며 gyro bias를 제외한다. 단일 장면·seed의 상관된 시계열이다. 거리 반영이 모든 오차·NEES를 개선하지 않았으며, 특히 지그재그 경로의 XY·NEES는 증가했다. 이 결과를 일반 성능 우월성이나 통계적 일관성 통과로 확대하지 않는다.

- [최신 결과 폴더](paper/figures/distance_lut_mbvar_20261102_v3/)
- [조건별 비교표](paper/figures/distance_lut_mbvar_20261102_v3/ALL_SCORES_36.csv)
- [실행·자체 검사](paper/figures/distance_lut_mbvar_20261102_v3/RESULT_CHECKS.json)
- [실험 계약](paper/figures/distance_lut_mbvar_20261102_v3/CONTRACT.json)
- [극점 수정 결과·잔여 차이 진단](paper/figures/lut_pole_fix_20261102_v3/)
- [최초 관측함수 교체 결과](paper/figures/lut_observer_swap_20261102/)

![Heading RMSE](paper/figures/distance_lut_mbvar_20261102_v3/F01_HEADING_IEEE.png)

![XY RMSE](paper/figures/distance_lut_mbvar_20261102_v3/F02_XY_IEEE.png)

![NEES](paper/figures/distance_lut_mbvar_20261102_v3/F03_NEES_COMPONENTS_IEEE.png)

PDF 벡터와 PNG 600 dpi를 함께 보존했다. 실패한 준비·검사 실행과 중단한 부분 실행도 별도 버전 폴더로 보존했다. 최신 완결 실행은 각 `v3` 폴더의 계약·검사 기록을 기준으로 한다.

## 재현 범위와 출처

`SNAPSHOT_MANIFEST.json`은 모든 복사 파일의 상대 경로·크기·SHA256을 기록한다. 저장소 기반 커밋은 61475a1f12071cb0fcdbd62a728d833f1d6732b5이며, 실행 당시의 복구 런타임·입력은 각 실험의 파일 해시로 식별한다. 푸시 커밋을 과거 실행의 코드 커밋으로 소급하지 않는다.

이 체크포인트는 로컬 경로가 포함된 실행 코드와 증거를 보존한다. 외부 FFD bank·RF 입력 및 일부 런타임은 계약에 기록된 위치·해시로 참조되며 이 폴더만으로 독립 재실행 가능한 배포본이라고 주장하지 않는다. 새 시뮬레이션은 이 푸시 과정에서 실행하지 않았다.
