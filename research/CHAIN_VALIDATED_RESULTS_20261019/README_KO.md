# POWER1·Joint4 가설 검증 최종 인도 — 2026-10-19

**실제 계산 완료:** 기존7조건×4Bias×24방법=672개 재귀실행, 새5주로/8앵커조건×4Bias×6방법=192개 재귀실행. 총60개 case-bias,864개 방법별 전체 재귀 결과를 별도 scorer로 다시 검산했다. 기존 자료 28/28, 새 자료32/32 모두 완료. 동일 RF에 비교군을 늘린 것이므로864개 독립 실험은 아니다.

**후보 승인과 계산 완료는 다르다.** 시간상관 모델은 R2 M45와 새 주로 다수에서 개선됐지만 R5 A 및 C03 A 등에는 악화가 남았으며 범용 최종 모델 승인 아님. POWER1·Joint4는 기준선으로 유지한다.

## 결과 문서

- [기존자료 A–E 실행·해석](RESULTS_A_E_KO.md)
- [새 주로 F 고정후보 결과](RESULTS_F_NEW_ROUTES_KO.md)
- [검수된 원표·국소 개입·P4·편파 기여](evidence/)
- [새 주로 입력 QA·재채점·모든 Bias](external_evidence/)
- [등록된 실제 추론 코드](../CHAIN_HYPOTHESIS_20261019/)
- [독립 검산·잔차분해 코드](../CHAIN_REVIEW_20261019/)

## 이번에 근거가 추가된 사항

1. **기억 자체의 효과를 분리했다.** 지속 잔차2상태를 추가하되 기존 POWER 관측분산을 지속/빠른성분으로 나눠 중복확대하지 않았다. 같은6상태에서 rho=0인 대조는 POWER1과 전체 재귀 주변상태·공분산·Gate가 일치했다. 따라서 새로운 기억 후보의 차이를 단순한 상태차원 증가나 분산 일괄 확대만으로 설명할 수 없다.
2. **정답 reset 없는 국소 개입이 이후 결과를 바꿨다.** 사전 훈련 Q75를 넘는 detector_s_span 이벤트에서만 기억을 켜고 다시 POWER1로 복귀해도 R2M0 B0의 이벤트 이후RMSE1.9143→1.6596°,포함65.10→72.36%. 개입 전 상태/P 차이0,미래 RF 변경0. 그러나 R4A에서 같은 방식은 악화했으므로 모든 오류의 시작점이 특정 한 이벤트라는 결론 아님.
3. **시간모델의 이득과 실패가 모두 재현됐다.** 기존R2M45 B0 .9826→.6781°,signed -.6309→+.1806°,포함63.57→100%; R5A B0 4.5561→8.7641°,포함39.68→16.36%. 100% 시간포함률은 perfectcalibration이 아니다.
4. **관측 예측이 좋아져도 Heading 상태는 더 틀릴 수 있었다.** R5A B0 기억후보는 빠른성분으로 남는 s 잔차RMSE .192920→.118477, 표준화innovation lag1_s .880833→.651001, 평균NIS2.272301→2.090946로 좋아 보였지만 Heading RMSE4.5561→8.7641,HeadingNEES9.1844→22.6708로 악화. 즉 innovation 적합도 개선을 상태 신뢰도의 증명으로 사용할 수 없다. RF잔차/상태 귀속·평균모델·선형화 중 어떤 항이 지배적인지 완전히 확정한 것은 아니다.
5. **상태–RF편향 교차공분산을 버리는 대조가 신뢰도를 훼손했다.** R2M45 B0에서 정상 기억후보와 crossblock삭제 후보의 평균NIS는1.4386/1.4551로 유사하지만 HeadingNEES .6319/7.9180,포함100/17.01%. '잔차를 잘 맞추는 것'과 '실제 상태 불확실성 유지'의 차이가 직접 드러난다. crossblock삭제를 일부 RMSE이득만 보고 채택하지 않는다.
6. **P4 점수와 행동을 분리했다.** 같은 prior에서 lowrisk647중343개는 POWER가 더 유리했고, 동일 위험점수로 평균만 바꿀지 공분산만 바꿀지에 따라 재귀결과가 달랐다. 분류기는 역사적 target을 사용한 새 HGB 재구성이다. 과거 classifier byte-parity는 아니다.
7. **co-response와 간섭을 분리했다.** 직접파와 같은 두포트 비율의 성분만 더하면 fixedtap s는 수치정밀도 내 동일. M45의 효과적 co-response 비중은 다소 높지만, 일부 상쇄조건13점에서 co상대위상만 정렬하면 delta_sRMSE .2899→.0581. 실제 입사파 순수 편파를 직접 측정한 것이 아니라 수신포트 응답 분해다.
8. **새 경로를 실제로 시험했다.** 후보·R4/R5 train 파라미터를 변경하지 않은 M45 신규32조건에서 기억후보는26조건 RMSE개선(>0.1%),3조건 >10%악화. 새오피스8조건 모두RMSE개선. 하지만 C03A B0 .5835→1.4643 악화, O02 B0도포함41.90→57.86%로 개선되지만 명목95%와 차이가 크다. 새경로는같은복도3개+같은오피스2개이고5독립scene이 아니다.

## 가설 판정

| 가설 | 결과 | 범위 |
|---|---|---|
| 같은 패킷분산에서 시간적 기억이 Heading/신뢰도에 영향을 준다 | SUPPORTED_BUT_LIMITED | no-memory등가 확인, 실RF 일부·새경로 다수개선 |
| 단일 Gauss–Markov 잔여편향 모델이 모든 FullRF에 우월 | FALSIFIED_FOR_CURRENT_MODEL | R5A·C03A 실패 |
| 한 물리특징 이벤트에서만 모델을 바꿔도 이후오차가 달라진다 | CONFIRMED_IN_REPLAY | 공통prefix+원상복귀+미래RF고정; 경로별부호차이 |
| 선택한 첫 detector이벤트가 모든 오류의 유일원인 | NOT_ESTABLISHED | 경로별전체사건 원인제거 실험은 아님 |
| P4 오염검출 점수는 곧 POWER사용 효용이다 | FALSIFIED_FOR_RECONSTRUCTED_POLICY | 같은prior행동비교·재귀분리 |
| Gate를 완전히 없애면 근본 해결 | NOT_SUPPORTED | 28조건 중 >10%열화14 |
| SR4·4회iteration만으로 편향·과신이 해소 | NOT_SUPPORTED_IN_TESTED_SETTINGS | 효과작음/조건의존; SR4폐기아님 |
| 실제 상태와 편향상태의 상관을 무시해도 신뢰도 유지 | FALSIFIED_IN_TESTED_CASES | M45 NEES/coverage강한악화 |
| co성분 자체만으로 fixedtap편파비왜곡 | FALSIFIED_BY_ALGEBRA_AND_TEST | 완전parallel성분은소거; 상쇄+비parallel조합은중요 |
| 넓은 환경 일반화·완전Bayesian일치성·하드웨어실증 | NOT_ESTABLISHED | 2개의실내scene/가상센서/현재경로범위 |

## 실험 경계

- 모든 방법은 기존과 같은 알려진 초기조건을 사용한다. GT 기반 초기조건·센서생성·훈련label·사후평가는 있으며, **운용중 GT reset,GT기반이벤트선택,GT기반보정 입력은 없다**.
- 시간모델은 정규화 잔차좌표에서의유효 모델이다. tau/fraction/기저B(q)의물리적정확성 및분리식별성을증명한것은아니다.
- 새 경로 F의 관측간격은 희소하며 전체 .25s motion 예측,원RF시점에서만갱신. 가짜CIR보간/없는RF패킷추가는없다.
- 모델의 교차공분산·P4행동·Gate/noGate·SR4/제한iteration 대조를수행했으나 복구병렬필터·정식가관측성·개별벽경로의원인확정까지실행한것은아니다.
- 로컬계산도구 오류는GitHub Actions로전환,artifactredirect인증 및503문제는수정/재시도로처리했다. 동일FFD를복원했고비수치문제로가설검증을중단하지않았다.

## 전체 수치 인도

- [기존 A–E 모든 상태·공분산·관측·진단 ZIP (약334MB)](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39252522326/artifacts/12188081569)
- [기존 A–E 독립검수 ZIP (약310KB)](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39255330193/artifacts/12188067493)
- [새 경로 F 모든 재귀결과 ZIP (약44.8MB)](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39256517334/artifacts/12188722472)
- [최종 문서·원표·새경로 검수 ZIP](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39259364036/artifacts/12188847905)

Actions artifacts는2026-11-18에만료되는보관본이며영구파일이라고표현하지않는다.코드와게시된CSV/JSON·보고서는이브랜치에보존된다. 원FFD/RF원본은중복게시하지않고INPUT_RECEIPT로동결출처를연결한다. 재현환경은Python3.13.5 NumPy2.3.5 SciPy1.17.0 pandas2.2.3 scikit-learn1.8.0, BLAS thread1.
