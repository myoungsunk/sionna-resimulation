# T6: 검출 tap 기반 Range 관측식

실행 전 설계 메모다. `source_model.py`의 `SourceFFD.batch`는 이미 source complex direct spectrum을 Hann window / 4N IFFT / 실제 `O.first_path_batch`에 넣고, detector range를 `diag['native_range']`로 반환한다. 다만 실제 예측 벡터의 range는 `dist+B_OLD`로 대체한다. `src_range_model.py`는 앞 계산을 그대로 사용하여 range 행만 실제 detector 값으로 노출한다. s의 값·tap·Jacobian은 원본과 같다.

## 양자화와 Jacobian

정본 후보 `SRC_TAP`은 보간하지 않는다. 검출된 정수 tap의 range는 tap이 같으면 상수이고, 경계에서 점프한다. 따라서 올바른 active-cell range Jacobian은 0이다. `d+B_OLD`의 거리 미분을 이 관측식에 붙이면 수학적으로 다른 모델이 된다. 이 구현은 그렇게 하지 않는다.

이 선택에는 실제 재귀상의 중요한 제약이 있다. range 자체의 위치 민감도는 0이 되어, range가 상태를 직접 관측하는 기능을 잃는다. 상관 R의 off-diagonal 때문에 range innovation이 s 방향 gain을 거쳐 영향을 줄 수는 있다. 잔차 RMSE가 작다고 기존 POWER의 Range 정보를 그대로 보존한 것은 아니다. 재귀 결과가 악화되면 실패를 보존하며, 새 보간법으로 몰래 대체하지 않는다.

FD 검증은 x/y/yaw 각각 두 step에서 수행하고, tap 불변 stencil과 tap 전환 stencil을 모두 파일에 남긴다. 전환 stencil에서 수치 기울기가 크면 이는 정확한 정수 detector의 비미분성을 보여주므로 전역 미분 가능 PASS로 보고하지 않는다. 안정 셀에서 `|FD-J|≤1e-6`와 전역 claim은 따로 보고한다.

## 실행 입력·출력

`validate_native.py --source-root <restored source tree> --execution-root <bank/rf zip directory> --out <output>`를 사용한다. SourceFFD 의존 코드와 원본 bank, `BANK_MANIFEST.json`, `rf_frozen.zip`, P0_INPUT_MANIFEST가 필요하다. frozen LoS 관측과 truth는 평가에만 쓰며 predictor에는 상태 가설과 case만 들어간다. expected 9,519점은 전체 sequence이며 재귀 평가 t≥30초와 혼동하지 않는다.

출력은 `NATIVE_RESIDUALS.csv`, `RESIDUAL_GROUPS.csv`, `FD_STENCILS.csv`, `SUMMARY.json`, `MANIFEST.json`, `RESULTS_KO.md`다. source 파일·입력 archive/bank hash를 기록한다. 이 검증 runner는 P1 재학습이나 재귀 실행 완료를 주장하지 않는다. Mother의 공통 runtime은 `SourceTapRange(SourceFFD())`를 fit dataset과 recursive model 양쪽에 적용해야 한다. `B_REFIT_ONLY`는 train route의 LoS range−distance 평균으로만 적합한 별도 control이다.

## 주장하지 않는 것

정규화 Bayesian posterior, 독립 장면 일반화, 하드웨어 실증, detector residual 개선만으로 재귀 개선, 전환점에서의 미분 가능성을 주장하지 않는다.
