# P1 검증 구현 수정 — 학습·정책 결과 생성 전

Label run 39378144903의 105개 분할은 모두 성공했다. Train retry1 run 39380603592는 HGB 적합 이전에 `DUPLICATE_P1_FIT_DIFF`로 중단했다. 이는 원 계약에 없는 pickle 바이트 동일성 검사를 구현하면서 발생한 오류다.

105개 원본 P1 pickle을 refit 없이 읽어 비교했다. 같은 outer/inner fold의 모든 비수치 필드는 같고, fitted 수치의 최대 차이는 1.1102230246251565e-16이었다. 작은 차이도 pickle SHA를 바꾸므로 파일 digest를 수치 동등성 판정으로 사용할 수 없다. 하위 부동소수점 차이의 실행 환경 원인까지 확정하지 않는다. 전체 비교 결과는 preparation_failures/P1_STORAGE_DIAGNOSIS.json에 있다.

수정은 입력 training key·fitter 설정·cutpoint의 동일성 검사를 유지하고, scaler/Ridge/offset/C 및 모든 원 관측 q에서 μ/C를 기존 ScalarPower의 fitter parity 기준 1e-12로 비교하는 것이다. 각 원본 pickle SHA와 입력 key hash는 그대로 보존한다. fitted 값을 교체하거나 반올림하지 않고 label을 재생성하지 않는다.

PROTOCOL_LOCK.json, label 명단·효용, HGB 설정, OOF/δ 규칙, 평가 명단·과학 판정식은 변경하지 않는다. 원본 105개 label archive와 실패 model artifact 12248687338을 보존하며, 수정 commit 뒤 retry2에서 같은 label을 다시 검증하고 학습한다. 새 검증 결과는 P1_NUMERICAL_EQUIVALENCE.csv에 남긴다.

기존 보존 retry1 run 39380765996은 당시 존재한 107개 archive를 성공적으로 보존했다. 로컬 회수 대기기는 사전에 기대한 116개와 달라 count assertion으로 중단했으며 파일을 삭제하지 않았다. 최종 retry2 모델·평가 및 보존 retry1 자체의 artifact까지 포함한 별도 최종 보존·회수로 마무리한다.
