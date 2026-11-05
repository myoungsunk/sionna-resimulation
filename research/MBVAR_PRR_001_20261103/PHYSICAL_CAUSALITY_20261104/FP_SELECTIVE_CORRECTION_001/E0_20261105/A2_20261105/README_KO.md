# E0 A2 — controls 재생성에 의한 수치 재현

원본 `RUN_E0_001`은 R4/R5 `ds` 배열의 원 SHA와 불일치하여 차단되었습니다. 그 결과와 원 계약은 보존합니다. 이 추가 실행은 **원래 sensor recipe를 현재 Linux 환경에서 한 번 재생성하고 새 입력으로 동결**한 뒤, 기존 W0 재귀의 모든 상태·관측모델·gain·공분산과 gate를 원 기록과 비교합니다.

허용오차는 기존 `1e-10` 그대로입니다. pose·timestamp·수용 mask는 exact equality입니다. 역산 controls, ULP 조정, 재귀 결과를 본 후 runtime 선택은 금지합니다. 성공하더라도 “원본 controls 바이트 복원”으로 표시하지 않습니다.

- [사전 amendment](AMENDMENT.json)
- [판정 지표](METRIC_SPEC.json)
- [별도 사전 검토](../audit/PRE_RUN_A2_REVIEW.json)
- [첫 실행](../RUN_E0_001/RUN_MANIFEST.json)

이 폴더의 controls는 입력 준비 산출물입니다. 실험 실행과 결과 감사는 별도 코드·입력·환경·실행 잠금 후에 기록합니다. E1 이후는 자동 승인되지 않습니다.
