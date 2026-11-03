# DLP-R1B-CH4-001 / PREC-V1 — Native RT 정밀도 인터페이스 분리 검증

작성 2026-11-03. 상태: **NUMERICAL REPAIR CANDIDATE / SCIENCE HOLD**.

## 기존 검증 결과의 불변성

- 최초 고정 canary `[0,150,221,440,458,476,696,916]`, Native RF, `03_RF_CANARY_QA.json`, `08_QA_PARITY_AND_LIMITATIONS.json`은 **수정하지 않는다**.
- 원래 복소 상대오차 RMS는 `1.0051515145524099e-4 > 1e-4`로 **HOLD_RF_PARITY**다.
- `r1b_native.py`, SourceFFD `source_model.py`, EKF `h,H`, 4상태 `f,F,Q`, 거리/FP 관측기, FFD bank, 장면과 포트, `R0`는 변경하지 않는다.
- 합격 기준 `complex_relative_max=5e-4, complex_relative_rms=1e-4, s_max=2e-5, s_rmse=2e-6`, tap/port 불일치 0도 그대로 유지한다.

## 원인 분석: 단위 오류가 아니라 표현 정밀도 인터페이스 차이

Original SourceFFD 복소 채널 위상은 double-precision 원본 좌표 거리 `d64/c`를 쓴다. 저장된 Sionna-RT `raw.tau`는 모든 주파수에서 float32 왕복으로 동일하며, 좌표도 Mitsuba/DrJit 인터페이스를 통과한다. 기존 pose 440/458/476의 원본 `tau_native-d64/c = 3.900169068688608e-15 s`는 `~1.59e-4` 복소 채널 차이의 주된 성분이다.

숫자 변환 순서는 모든 pose에서 일치하지 않는다. 이는 **내부 DrJit 각 연산의 정확한 순서를 100% 복원했다는 증거가 아니며** 허용할 수 없는 위상/이득 적합 또는 Native tau 직접 대입 근거도 아니다.

## 수정안: 별도 순수-기하학 Native 표현 렌더러

오직 **복소 채널 parity 출력용**, 다음과 같이 원본 SourceFFD 물리 응답을 numeric representation에 렌더링한다.

```
d64      = norm(xyz64 - anchor64)
tau_ref  = d64/c
tau_repr = float32(norm(float64(float32(xyz64)) - float64(float32(anchor64)))/c)
H_repr(f)= H_source_physical(f) * exp[-j 2 pi f (tau_repr - tau_ref)]
```

입력은 **Source 모델의 원본 좌표와 FFD 채널만** 허용한다. Native H/지연, 실제 채널 잔차, GT 기반 보정, 데이터를 보고 맞춘 오프셋·위상·이득은 렌더러에 전달하지 않는다. `H_repr`을 EKF 관측 모델 `h,H`에 대입하지 않는다. LoS/Full의 signed `s`, 공통 FP, 수용 판정은 원본 관측기에서 재평가한다.

## 사전 지정 검증

1. **Legacy 8회 offline replay:** 원시 NPZ SHA 검사, V2 실패 결과 그대로 재계산, precision-rendered 복소 max/RMS, 편파차 max/RMS, tap/port, 모든 비유한 수 검사.
2. **Prospective independent pose selection before new RT:** `[75,305,610,809]` (기존 canary 8개와 겹치지 않음). 동일 C0/Anchor B, Full max-depth 3 / LoS max-depth 0, 257 bins, 원래 포트/검출기/원본 보정 0. 이 4개를 고정한 뒤에는 결과를 보고 표본을 변경하지 않는다.
3. **새 Native RT의 허용치:** 기존 V2 숫자 그대로 사용. 원본 V2 metric과 새 precision-rendered metric을 **둘 다** 남긴다. 새 결과가 실패하면 `PROSPECTIVE_NATIVE_NUMERIC_HOLD`; 성공해도 독립 과학 감사 전 원래 `HOLD_RF_PARITY`를 해제하지 않는다.
4. **회귀 보호:** SourceFFD 연속 `h,H` 및 EKF는 바뀌지 않아야 하며 917 RF와 Heading/XY는 **NOT_RUN**이다.

## 산출물/결론 경계

재계산 결과 파일, GitHub Actions 로그·raw artifacts, byte hash, 프로세스/파이썬·Native solver 버전, 독립 검산까지 제시한다. `NUMERIC_BRIDGE_REPLAY_PASS` 또는 `PROSPECTIVE_NATIVE_NUMERIC_PASS`는 **numeric representation의 parity**만 의미한다. 과학적 결론 및 전체 RF/EKF 생산 재개는 proposer freeze, 분리된 auditor sign-off가 충족될 때만 가능하다.

추가 적용 없이 원본 full-band 수치 정합 FAIL 자체를 PASS라고 서술하지 않는다.
