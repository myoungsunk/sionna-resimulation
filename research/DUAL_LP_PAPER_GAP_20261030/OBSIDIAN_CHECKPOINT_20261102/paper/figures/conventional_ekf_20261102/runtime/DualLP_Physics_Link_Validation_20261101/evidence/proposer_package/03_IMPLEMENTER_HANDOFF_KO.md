# 03. 별도 구현자 인계 — 지금은 구현·실행하지 않는 문서

## 연구 의도
원고 v4의 세 anchor-B 경로·12조건에서 `MB_VAR/self`의 기존 Heading 개선을 **물리 관측→갱신→결과**로 설명한다. 성능을 더 좋게 만드는 새 알고리즘 개발이 아니다. 원래 4-state, integer first-path r, two-port s, mean replacement, sigma lookup 및 self gate를 보존한다. 5-state·sub-tap·SUB3·새 RT·다른 anchor는 이번 인계 범위 밖이다.

## 읽을 파일·순서
1. 원고 기준 commit `1aac4d38a6fa335116bcecbebc91ba53c876ecfd`의 AGENTS.md와 기존 DLP GOV_APPLICABILITY / DLP-EKF-GAPS 초안. 넓은 gaps 과제를 지금 실험으로 무조건 가져오지 않는다.
2. governance ref `250d617ad89a4105fa1af546cc83ceed9de98f42`의 COMMON_CONTRACT와 자신의 ROLE_IMPLEMENTER. 이번 제안서의 06 적용표.
3. 01 계약 → 02 명세 → numeric config → source register → 04 결과 사용 규칙 → 05 원고 계획.
4. 원본 source snapshot의 SourceFFD, exp_pb, diag_mbvar와 학습·CONTROL 입력. 파일 이름만 보고 같은 모델이라고 판단하지 않는다.

## 구현 전 제출할 것
`IMPLEMENTER_PRE_RUN_REVIEW.md`에 적용되는 수식/함수/파일/변경목적, 부족한 입력, 코드 재사용 경계, 예상 산출물, dtype·라이브러리·source 버전을 기록한다. source/model/array 바이트 해시, 학습모형 존재, 12조건 mask·clock, SourceFFD 극점/branch convention을 확인한다. 충돌은 제안자에게 unresolved item으로 반환한다. 제안자 의도·원래 mu/R·case를 임의로 바꾸지 않는다.

**승인 전 허용 범위는 별도로 배정받은 V0 출처/수학 preflight뿐이다.** 새 결과관계 분석과 재귀 비교는 제안자·독립 감사자가 candidate input lock과 수치 설정을 검토한 FROZEN 명세에서 승인된 단계만 수행한다. 현 제출은 그 승인서가 아니다.

## 최소 구현 모듈 계획 (파일은 아직 만들지 않음)
| 역할 | 구현 단위 | 금지 |
|---|---|---|
| 원본 계보 | input/pose/packet source loader와 immutable lock | 현재 branch 최신 파일을 pinned source 대신 자동 사용 |
| 관측 진단 | original observer·source J를 호출하는 instrumentation | observer·tap 선택·R·mean을 보정해 parity를 인위적으로 맞춤 |
| shadow | 같은 prior/lookup 2×2 수치 update | packet별 서로 다른 prior로 gain 효과 비교 |
| constant arm | variance rule injection만 추가 | 상수 mean sigma→square, test tuning, 기존 hand table 재학습 |
| 지표 | original scorer + per-packet updates/selection ledger | 원래 finite·수용집합과 평가 시점을 섞음 |
| QA | independent math oracle와 negative controls | 구현자가 자신의 test로 independent audit 서명 |

## 첫 구현 순서
V0 preflight proposal → source lock candidate → 역할·권한 확인 → V1 observer/J instrumentation → V2 same-prior matched update → V3 constant arm → 승인된 optional V4/V5. 성능 결과에 맞춰 단계 순서나 선택 case를 바꾸지 않는다. 96 legacy traces는 원본 parity를 먼저 통과시키고 새로운 48 constant traces를 계산한다.

## 필수 출력 스키마
- `INPUT_LOCK.json`: 모든 실제 입력 URI/ref/path/bytes/sha256, SourceFFD/mean/CONTROL/scorer code blob, dependency versions. 조회한 링크만으로 sha 확인을 대신하지 않음.
- `RUN_MANIFEST.json`: UTC timestamp, role/contract/frozen approval references, base/governance/execution/config SHA, exact command, hardware, seeds, train/cal/test lookup map, input/output hashes, run status.
- `CASE_LEDGER.csv`: source case/route/mount/anchor/bias/seed/time-window/number-of-packets/independent-scene-count.
- `SCORES.csv`: 12조건×arm×gate 전수, Heading(deg), XY(cm), NIS/NEES/coverage, used count. 학습 or gate별 NA와 실패도 행으로 남김.
- `PACKET_DIAGNOSTICS.parquet`: pose/time key, previous posterior/current prior, rho lookup, mu, R/J/K/nu, corrections, both gate decisions, branch/port, truth-role tag.
- `FIRST_DIFF.csv`: 처음 달라진 rho/sigma/R/nu/K/x/P/mask를 순서대로 표시. 값이 같아야 하는 입력 목록과 numerical tolerance.
- `QA.json`: status별 exact denominator; closed-form identity, sigma=0/mean equality, common-scalar/port swap, time-shift/hash alteration/duplicate negative fixtures.
- `CLAIM_EVIDENCE_LEDGER.csv`, `FIGURE_MANIFEST.json`, `REPORT.md`: 설명·지지범위·반례·제약·결과 사용 위치. 04의 claim IDs와 연결.

## 다른 구현자에게 전달할 프롬프트
> role=IMPLEMENTER, contract_id=DLP-PHYS-LINK-001. 이 패키지의 원고·governance·계약·명세·config·source register를 먼저 읽어라. 목적은 기존 Anchor-B 12조건 MB_VAR/self의 물리적 관측구조와 개선 사이의 설명 검증이며, 새 필터 개발이 아니다. 먼저 입력 lock과 미확정 사항을 반환하고, 과학 실행 승인 없이 V1–V5를 시작하지 마라. 승인된 후에 원본 observer/f/F/Q/mean/R/lookup 시점을 유지한 instrumentation과 constant-variance 대조만 구현하라. 같은 prior·같은 이전 posterior lookup·같은 accepted 키를 보장하고, self-gate 결과는 별도 보고하라. 기존 archive 코드를 실행해 만든 점수와 새 실험 결과의 구분을 지켜라. 모든 12조건과 R4-B 악화 결과를 보존하고 실패/비지지 결과로 설정을 사후 변경하지 마라. 별도 auditor에게 raw source와 manifests·negative fixtures를 인계하며 자기 결과에 독립 감사 서명을 하지 마라.

## 독립 감사자 인계 포인트
같은 governance SHA의 ROLE_AUDITOR를 사용하되 별도 session/provenance와 계산 경로를 기록한다. 최소 세 경로 각각의 deterministic 선정 packet, ±port, near-pole, active-branch-switch 및 최초 gate 차이 packet을 독립 재계산한다. 표본은 결과가 좋다는 이유로 고르지 않는다. 원 구현의 observer/gain helper를 그대로 호출한 검산만으로 independent verdict를 주지 않는다. common scalar invariance, 2×2 identity, constant training fold, map lookup pre-predict 시점, full trajectory baseline trace와 실제 accepted 키를 점검한다. independent source/observer 계산이 불가하면 AUDIT_PENDING이다.
