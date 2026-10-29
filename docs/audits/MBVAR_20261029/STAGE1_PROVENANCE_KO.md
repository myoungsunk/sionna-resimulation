# 1단계: 실행·코드·입력 출처

기록일: 2026-10-29. 역할: AUDITOR. 이 문서는 같은 대화에서 수행한 검사를 정리한 것이며 독립 감사라고 주장하지 않는다.

적용 지침: 저장소 AGENTS.md와 [COMMON_CONTRACT](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/COMMON_CONTRACT.md), [ROLE_AUDITOR](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/ROLE_AUDITOR.md). 정책 기준 커밋은 `73d589ebd0b9da37fc60d2e34c87de5ffb95c107`이다. 로컬 지침은 보조로 읽었으며 동결 정책을 덮어쓰지 않았다.

자료 범위: 접근 가능한 GitHub 코드·workflow·실행 로그·manifest·선택한 artifact, 동결 저장소 bytes, 기존 대화의 직접 검사 기록. 기존 노트는 탐색·과거 결과 설명에만 사용했다. 원래 상위 대화의 개별 감사 전문을 모두 확보한 것은 아니다. 아래 브랜치별 문서는 이번에 확보한 근거를 통합한 기록이며 미확보 전문을 복원한 문서가 아니다.

## 브랜치 기준

게시 직전 원격 ref를 다시 읽었으며 6개 모두 이전 1단계 기준과 같았다. HEAD와 아래 실행 SHA는 서로 다른 기준이다. HEAD의 모든 코드가 해당 과거 실행에 사용됐다고 보지 않는다.

| 브랜치 | 게시 시 HEAD | 기존 감사 기준 |
|---|---|---|
| research/ds-state-info-var-forensics-20261028 | `4ad94fe652d847592aa78ba017dd0a6a517652a1` | 이전 1단계 기준과 동일; 개별 과거 감사 전문의 별도 SHA는 미확보 |
| research/mbvar-premodel-diag-20261029 | `06a8a0922e0f4b2fef79316bcfd77035475c2715` | 이전 1단계 기준과 동일; 개별 과거 감사 전문의 별도 SHA는 미확보 |
| research/mbvar-control-correction-20261029 | `0a0e2237f085fa32683e4ae603cf5ca2372d2130` | 이전 1단계 기준과 동일; 개별 과거 감사 전문의 별도 SHA는 미확보 |
| research/mbvar-causal-isolation-20261029 | `3af005b8491b5668c0989b82bc3cbc990cfcf8b7` | 이전 1단계 기준과 동일; 개별 과거 감사 전문의 별도 SHA는 미확보 |
| research/mbvar-e2-e5-revalidation-20261029 | `af8e0a1b5299ae5e279f9b602afd2f1bb710c4e3` | 이전 1단계 기준과 동일; 개별 과거 감사 전문의 별도 SHA는 미확보 |
| research/mbvar-time-gm-differencing-math-20261029 | `cf4b19ab02ea93c254b606a27128960f24880598` | 이전 1단계 기준과 동일; 개별 과거 감사 전문의 별도 SHA는 미확보 |

## 실제 실행 기준

| 실행 | 실행 ID | 실행 SHA | 구분 |
|---|---|---|---|
| PB (상위 실행) | [40652679303](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40652679303) | `8c8adfeb09a1648d2113e63d3350ff5fc26b181b` | 계산; forensics 신규 실행 증거 아님 |
| control | [40820579727](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40820579727) | `3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18` | 계산 |
| causal | [40825807998](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40825807998) | `4e14448a8af81c3e99cd257f23cb07615ebd8a15` | 계산 |
| revalidation | [40830330560](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40830330560) | `aa1027b7ab44078a797bf26556879a99cb8de3d8` | 계산 |
| revalidation recovery | [40831583667](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40831583667) | `419c18303aa29bacdeef724e1c67f07e7e5322a3` | 복구 집계; 계산 실행과 구분 |
| initial-state cross | [40830802359](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40830802359) | `fe5d3edf4969c53862308ab8dace4d58601d111d` | 초기상태 교차 |
| time-GM | [40828341230](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40828341230) | `7fab61cb1b26240b8031b77e277bc6ab92651245` | 계산 |
| mean upstream | [39574195919](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39574195919) | `902ddcaf0f8e59734bb8026d3bcdc36eab506a27` | 평균 보정 상위 출처 |

premodel은 manifest에 2026-10-29 02:42–03:01 UTC cloud 실행, 기반 소스 `4ad94fe652d847592aa78ba017dd0a6a517652a1`가 기록되어 있다. scratch 실행본의 실제 bytes·로그는 확보하지 못했다. forensics 신규 스크립트의 실행 SHA/receipt는 MISSING이다.

실행 이후 변경: forensics는 신규 진단 코드의 실행 연결이 미확인이다. premodel HEAD는 코드·manifest·결과 저장 기록이며 과거 scratch 동일성은 미확인이다. control HEAD에는 실행 이후 결과·정정·계획과 PREMISE_CHECK_NOISE.json이 추가되어 있어 계산 SHA와 분리한다. causal/time-GM HEAD는 계산 이후 결과 문서를 포함한다. revalidation HEAD는 계산 snapshot 및 복구 집계·corrective 결과를 포함한다. 모든 사후 변경을 새 계산으로 간주하지 않는다.

## 실제 의존성 및 다음 감사 경로

다음 공통 경로는 import 이름만으로 동일하다고 판정한 것이 아니다. workflow checkout/추출, sys.path, 고정 소스 및 일부 snapshot Git blob/파일 해시 비교를 사용했다. 실행 시 module.__file__ 전수 기록은 없으므로 실제 동적 해석의 완전 증명은 아니다.

| 영역 | 확인 코드·호출 | 입력 → 출력 | 브랜치별 경로·한계 |
|---|---|---|---|
| A 입력·시간 | [common.load_control](https://github.com/myoungsunk/sionna-resimulation/blob/9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13/research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/common.py#L78-L85); [fetch_inputs](https://github.com/myoungsunk/sionna-resimulation/blob/9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13/research/DS_MASK_CAUSAL_X1_X2_20261026/reflect_model/fetch_inputs.sh#L6-L51) | CONTROL NPZ, FFD bank → 시간·pose_id·관측·평균·기본 R·mask | REFLECT_ROOT와 frozen 9bcd 추출; artifact 입력 bytes 직접 검증은 남음 |
| A/PB 준비 | [build_controls / main](https://github.com/myoungsunk/sionna-resimulation/blob/8c8adfeb09a1648d2113e63d3350ff5fc26b181b/research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py#L58-L73) | B0 trace의 nu+h+mu → z, bias별 mask 재생성 | 주요 로드 main 163–190; score t≥30 |
| B 공통 필터 | [core.py](https://github.com/myoungsunk/sionna-resimulation/blob/9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13/research/EKF4_RANGE_S_STAGED_20261014/core.py); [SourceFFD](https://github.com/myoungsunk/sionna-resimulation/blob/9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13/research/FFD_P0P3_20261016/source_model.py) | 초기 x/P, 평균·R·mask → 예측/갱신 | common, PB, DG, K wrappers를 구분; 필터 수학 감사는 후속 범위 |
| B premodel | [DG imports/load/run](https://github.com/myoungsunk/sionna-resimulation/blob/06a8a0922e0f4b2fef79316bcfd77035475c2715/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code/diag_mbvar.py#L19-L88) | PB/core 공통 경로 → 진단 replay | scratch 당시 import 경로·버전 직접 확인은 미완 |
| B control/revalidation | [K load / R_var / run](https://github.com/myoungsunk/sionna-resimulation/blob/3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py#L62-L115); [revalidation wrapper](https://github.com/myoungsunk/sionna-resimulation/blob/aa1027b7ab44078a797bf26556879a99cb8de3d8/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_e2_e5_revalidation_20261029/revalidate.py#L20-L45) | CONTROL·분산 모델 → replay / 조건별 출력 | EffectiveModel 및 transition wrapper 별도; 저장 code snapshot 동일성 확인 범위만 재사용 |
| C 잔차·상관 | [acf_stats / summarize](https://github.com/myoungsunk/sionna-resimulation/blob/3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py#L213-L270) | 선택 eps → ACF 및 요약 | 선택 표본의 초 환산 문제는 2단계에 기록 |
| C causal/time-GM | [causal acf1](https://github.com/myoungsunk/sionna-resimulation/blob/4e14448a8af81c3e99cd257f23cb07615ebd8a15/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_causal_isolation_20261029/causal_isolation.py#L30-L33); [moments / whiten](https://github.com/myoungsunk/sionna-resimulation/blob/7fab61cb1b26240b8031b77e277bc6ab92651245/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_time_gm_20261029/time_gm_study.py#L32-L85) | accepted residual / 원래 시간 인덱스 → 서로 다른 ACF | 동일한 ACF 구현으로 합치지 않음 |
| D 개입·판정 | [permute_eps](https://github.com/myoungsunk/sionna-resimulation/blob/3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py#L322-L341); causal / time-GM entrypoint | 순열·decimation·state model → CSV / manifest / 보고서 | 표본 개수 블록과 실제 시간 구간 구분; 계산과 복구 집계 구분 |

## 평균 보정과 분산 보강

Δs 기반 평균 보정은 관측 예측의 평균 μ에 들어간다. MB_VAR의 편파 분산 보강은 기본 관측 공분산에 추가 분산을 적용하는 경로이다. 이번 단계에서는 출처와 호출 연결을 구분했으며 두 효과의 인과효과를 판정하지 않았다. sg 거리 평가가 예측 전 이전 posterior를 쓰는 경로는 확인된 동작이며 이번 감사에서 새 결함으로 등록하지 않았다.

## 출처 지도·준비 상태

CONTROL trace 14개 → common/PB/DG/K → residual·ACF/개입 → 실행별 CSV·manifest·문서로 이어진다. FFD bank 및 FULL/LoS RF의 원시 bytes와 과거 실행 입력 artifact bytes 연결은 남아 있다. 상위 학습은 출처·분할 메타데이터까지만 조사했다.

causal 및 time-GM 작은 결과 artifact는 실행→artifact→내부 manifest→결과 해시 연결을 확인했다. 이것으로 입력 artifact 무결성까지 증명하지 않는다. [공백별 근거](STAGE1_GAP_CLOSURE_KO.md)를 참조한다.

1단계 종료 판단: READY_WITH_GAPS. 정적 코드·동결 입력 감사 범위는 특정되었으나 forensics 실행 감사와 premodel 과거 scratch 동일성은 BLOCKED이다. 준비 상태는 시스템 정확성 PASS가 아니다.
