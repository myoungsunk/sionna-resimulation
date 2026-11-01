# DLP-PHYS-LINK-001: R1–R5 사후 감사 보완 / 실행 / 게시

**이 자료는 잃어버린 원본 `15503350…`의 복원이 아니다.** 기존의 재구현·재실행 패키지 `DualLP_Physics_Link_Validation_RERUN_20261101.zip`(219,512,794 bytes, SHA-256 `d2c9ab428ae676579a79907451a7523615876d3075f24f6abe7ee279ba75f7b2`)에서 검증한 코드와 trace를 수정하지 않고, **사후 감사 R1–R5의 누락된 보장과 상세 원장을 새로 실행하여 추가한 V2 패키지**다.

## 핵심 판정

|항목|V2 상태|증거|
|--|--|--|
|R1 원본/재구현/게시 구분|원본 MISSING, 재구현 검증됨, 원격 게시 별도 영수증|`RECONSTRUCTION_PUBLICATION_RECEIPT_V2.json`|
|R2 기계 판독 실행 허용|RETROSPECTIVE_REPAIR_AUTHORIZED; 과거 승인으로 소급하지 않음|`contracts/RUN_ADMISSION_RECORD_V2.json`|
|R3 실제 평균 동일화|24회 독립 평균 치환 배치, 총 25,088 packet-call; 모든 실제 산술 오차 허용 이내|`results/NULL_AND_MUTATION_TESTS_V2.json`|
|R4 필수 QA 완결성|**필수 5,288개 + 추가 R6 2개 = 총 5,290개 전부 통과**; 사전 선언한 5,288개 ID와 정확히 일치, 누락/중복/추가→BLOCKED|`results/REQUIRED_CHECKS_V2.*`|
|R3/R4 오염 시험|67회 고의 오염, 67회 모두 의도된 FAIL/BLOCKED 감지 (고의 주입 검사가 성공)|`results/NULL_AND_MUTATION_TESTS_V2*`|
|R5 첫 분기|144개 재귀 비교 전부 prior/lookup/R/K/NIS/mask/post state/P를 값으로 기록, 동일 prior 48개 별도|`results/FIRST_DIVERGENCE_DETAILS_V2.*`, `results/SAME_PRIOR_SHADOW_DIVERGENCE_V2.json`|
|R6 선택 진단|물리 3,136 packet과 shadow 50,176 후보를 정확한 case/pose/time으로 연결하고 896개 거리/방위/tap 구간 집계|`results/PHYSICS_SHADOW_STRATA_V2.csv`|

## 코드와 변경하지 않은 것

- `code/repair_v2.py`: source bundle을 **읽기 전용**으로 사용해 실제 평균 치환/Schur/필수 검사/오염 시험/첫 분기 집계를 실행한다.
- 원 `diag_mbvar.run`, SourceFFD, CONTROL, FFD, 기존 `CONFIG_LOCK.json`, 원본 132개 재귀 trace, 전체 144개 성능 결과, 기존 QA는 **변경하지 않았다.**
- R3/R4 계산은 과거의 `True` flag가 아니라 직접 계산한 measured error와 `all(required_checks)`로 판정했다. Python 최적화(`-O`)에서도 별도로 실행해 PASS를 확인했다.
- 별도 사전 독립 서명/원본 원격 커밋은 확보되지 않았다. 새 실행의 성격은 `RETROSPECTIVE_RECONSTRUCTION_REPAIR`, 검토 역할은 `SELF_REVIEW_ONLY`.
- 과학 결론은 `MIXED`: R2/R5에서 lookup 우수, R4에서 상수 우수 및 XY 손실이라는 기존 결과를 그대로 남긴다.

## 재실행

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python code/repair_v2.py \
  --source-root /path/to/DualLP_Physics_Link_Validation_RERUN_20261101 \
  --out /new/append_only/DLP_PHYS_LINK_REPAIR_V2_20261102
```

`source-root`가 `out`과 같거나 포함 관계이면 실행을 거부한다. 이전 결과를 보지 않고 만든 독립 pre-run 시험은 아니며, `V4`는 선택/미실행, `V5` 원 모델 fresh inference는 BLOCKED다. 이 패키지의 검증 완료는 **감사 지적 R1–R5 보완의 기계적 실행 범위**에만 해당한다. 외부 독립 감사·과학적 일반화·전체 인과 확인을 뜻하지 않는다.

관련 감사 원본: https://github.com/myoungsunk/sionna-resimulation/blob/daf9999057c0ac32ae0ca8be20021ae9f31d1d22/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_POSTRUN_AUDIT_20261101/IMPLEMENTER_REPAIR_HANDOFF_KO.md