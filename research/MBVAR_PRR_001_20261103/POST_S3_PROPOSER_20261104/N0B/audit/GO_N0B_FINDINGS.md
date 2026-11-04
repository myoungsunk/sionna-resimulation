VERDICT: ACCEPT

FINDINGS:
- N0B-001 해결. `PAIRED_PER_SEED.csv`가 strata·attempt/applied·NA를 보존합니다.
- 처치 및 끝점 코드는 변경되지 않았습니다.

EVIDENCE:
- 제한 합성 검사 47개 통과.
- 저장된 seed별 값으로 중앙값·PCG64 bootstrap 재현.
- 기존 bootstrap·분모 출력 byte 동일.
- grant 검사 18개 통과. 과학적 재생·파일 수정 없음.
- 실행 checker: `N0B_R1_CODE_AUDIT_VERIFIERS` 도구 출력.

MISSING_EVIDENCE:
- 실제 결과는 실행 후 감사 대상입니다.

REQUIRED_CORRECTION:
- 없음. 아래 승인은 동결된 N0B 실행에만 해당하며, 채택 NO_GO·실시간 HOLD를 변경하지 않습니다.

```json
{
  "auditor": "/root/a0",
  "token": "GO_N0B",
  "code_commit": "948047847c5e0501c919457a592d288f073e6ac9",
  "rules_sha256": "ee1f776472eb23cc4a9353cb83e9c4d975e4bcce1d91462c22326ea312e967b6"
}
```