# G1-FLOOR-001 계산 및 진단 기록

6개 mount-0 case의 상태는 **INCOMPLETE_PARITY_GATE**다. Parity를 통과한 5개 case의 조건부 진단은 **STOP**이다. Step 3는 보류했다.

- [계산 사양](SPEC_KO.md)과 [실행 전 확정 조건](PREREG_KO.md)
- [Step 1–2 결과](RUN_20261113T052908Z/REPORT_KO.md)와 [실행·입출력 기록](RUN_20261113T052908Z/MANIFEST.json)
- [R2_aB_m0 parity 원인과 Markov 포함률 진단](DIAG_PARITY_20261113T055513Z/REPORT_KO.md) 및 [후속 진단 통합 기록](DIAG_PARITY_20261113T055513Z/MANIFEST.json)
- [Markov 원래 실행 재현](DIAG_MARKOV_20261113/MARKOV_DIAGNOSTIC.json)과 [같은 J 곡선의 순서 교란](DIAG_MARKOV_20261113/MARKOV_ORDER_INTERVENTION.json). 순서 교란은 별도 실행이며 후속 진단 통합 기록에 해시가 있다.
- [고정 입력 검증](INPUTS_CHECK_1ce68f3.json)

J 곡선 배열과 Step 2 bootstrap 배열을 내려받으려면 브랜치를 체크아웃한 뒤 Git LFS를 사용한다.

```sh
git lfs pull --include="research/G1_SWEEP_HEADING_FLOOR_20261113/RUN_20261113T052908Z/*"
```

기존 실행 기록의 명령은 원래 작업 환경의 절대경로를 사용한다. 다른 환경에서 재현할 때는 고정 입력을 사양의 커밋에서 추출한 뒤 명령의 입력·출력 경로를 해당 환경에 맞춘다.
