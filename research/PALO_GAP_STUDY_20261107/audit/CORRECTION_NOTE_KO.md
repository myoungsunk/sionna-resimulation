# 독립 감사 지적에 따른 추가 증거

원본 코드·636개 궤적·최초 보고서·해시 manifest는 변경하지 않았다. 이 문서는 원본 보고서의 재수용 사건 범위를 정정하고 감사 중 추가한 증거를 연결한다.

## 확인된 기록 누락

CONTRACT.md §4는 거부 뒤 재수용의 오차와 공분산 전후를 평가하도록 명시했다. 최초 `analysis/REACCEPTANCE_EVENTS.csv`는 Heading의 전후값만 완전히 기록했고 XY에는 사후 NEES만 있었다. 또한 baseline/RF/development 76개 궤적만 다뤄 random/sensitivity 궤적을 제외했다.

따라서 최초 보고서의 **608건은 전체 636개 궤적의 총수가 아니라 해당 76개 궤적의 부분집합**이다. 이 누락은 전체 궤적 RMSE·NEES·정책 결정·원시 X/P 계산을 바꾸지 않지만, 공분산 사건별 검증의 완전성을 제한했다.

## 추가 분석

`reacceptance_supplement.py`가 기존 NPZ만 읽어 전체 636개 궤적을 같은 기준(이전 거부 >=5프레임, 기존 평가 구간 유지)으로 집계했다. 새 실험·정책 변경·임계값 변경 없음.

|그룹|재수용 정책-사건 수|
|---|---:|
|baseline|94|
|RF|400|
|random|356|
|sensitivity|13,275|
|development|114|
|합계|14,239|

새 `REACCEPTANCE_ALL_ARMS.csv`에는 Heading과 XY 오차, Heading 분산, XY 공분산의 xx/xy/yy 및 trace, Heading/XY NEES의 전후 값, 95% 기준 교차와 분산 감소·오차 증가 여부가 모두 있다. 원본 608개 사건은 이 표의 부분집합이며 기존 수치 일치를 재검사했다.

수준·정책·인공 오류 seed 간 반복이 포함되므로 14,239건을 독립 물리 사건으로 해석하지 않는다. 낮은 NEES나 기준 교차 수만으로 통계적 보정 여부를 인증하지 않는다. 추가 표의 최종 독립 감사 판정은 INDEPENDENT_AUDIT_KO.md를 따른다.


## Ungated Heading 대조의 명시적 연결

기존 독립 감사 완료 결과 `PALO_EXACT_ORACLE_20261107_01/results_v2/full_{level}_oracle_heading.npz`를 참조했다. 시간·pose ID·참값이 이번 입력과 같고 각 수준에서 gated Heading 파일과 SHA256까지 동일하다. 평가 구간은 t>=40초다. 16개 ungated RF 조건 모두 해당 ungated Heading보다 Heading RMSE가 높다. 따라서 gate 차이를 숨긴 비교가 아니다.

|수준|Heading RMSE (deg)|XY RMSE (m)|평가/전체 수용수|두 Heading 파일의 SHA256|
|---|---:|---:|---:|---|
|B0|0.04297509302036197|0.08983532642096288|38/48|e726c41b0b4ae1d6f2e43a6c0f9a0cd32dbaa867238ffcd9cff3c0f30729a5df|
|L0|0.043904029130394866|0.06094876695148473|44/57|2880c5dab307630c04f1d82fb5433e65c6d4b53b9723a9537d9a797c349e3eb5|
|L1|0.1023253445568468|0.12205780887334226|91/117|2b5389963b93dde330cb2ffba7e1a478d73aace4112790e525767139c8b04a0e|
|L2|0.08284357723329948|0.10590053570517298|92/163|16fa215a6d0a4c5f65f90a7bdada1e3df43ebf1af71acf9e9120c99ec4b23032|

원래 실험을 재실행하거나 결과를 변경하지 않고 누락된 대조 참조를 추가했다.
