# T3 표 생성 입력·API

`tables.py --source-root EXEC/source --execution-root EXEC --out OUTPUT`를 사용한다. restore.py가 복원한 rf_frozen.zip과 reference_ae OOF_PARAMETERS.csv.gz 및 원래 B0 trace, SourceFFD source/bank, 기존 sensor source가 필요하다. exact engine은 기본적으로 현재 저장소의 CHAIN_HYPOTHESIS에서 읽으며 별도 `--engine-root`로 바꿀 수 있다. 이 문서 작성 단계에서는 구문 검사만 했고 실제 실행하지 않았다.

슬라이드1은 기존 `r2_bias_replay.predict_one/filter_one` API의 DR4/S3/J3/S4/J4만 실행한다. SourceFFD.spectrum은3상태를 허용하지만 batch는항상4열 Jacobian을 반환하므로, 3상태 API에는 첫3열을 전달한다. 4번째 bias 미분은0이므로 물리 모델은 바뀌지 않는다. 3상태 bias 지표는 N/A로 표시한다. 4상태의 공통11지표는 독립 scorer로 계산한다.

Hybrid는 명시적인 ORACLE_DIAGNOSTIC이다. 네 셀의 r/s만 바꾸고 original Full-only POWER mu/C를 고정하여 채널 효과를 분리한다. LoS q나 가상의 hybrid CIR feature로 바꾸지 않는다. 미확보된 E1 ZIP의 정확한 파라미터 정책은 확인되지 않아 이전 E1과 동일하다고 주장하지 않는다.

T6 후에는 `--range-model SRC_TAP --parameters RETRAINED_OOF.csv.gz --parameter-manifest RETRAINED_MANIFEST.json`로 별도 OUTPUT을 지정한다. manifest에 `range_model: SRC_TAP`이 있어야 하며 구 POWER 파라미터를 자동 재사용하지 않는다. T6 adapter는 predictor와 평가 residual에 적용한다.

출력: SLIDE1_LOS.csv, SLIDE2_RANGE_STATS.csv, SLIDE2_HYBRID.csv, SLIDE4_POWER.csv, OLD_LUT_CHANGES.csv, VERIFICATION.csv, MANIFEST.json, RESULTS_KO.md 및 대용량 traces/. 모든 CSV에는 table_scope와 range_model이 들어간다. 이전 구 LUT 값은 사용자 제공 칸만 기록하고 나머지는 NOT_PROVIDED다.

## 주장하지 않는 것

Native LoS/hybrid 진단을 온라인 Full 방법과 같은 추론 조건으로 취급하지 않는다. 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증 및 미확보 E1 ZIP과의 재현 동등성을 주장하지 않는다.
