# DLP-R1B-CH4-001 — 복소 채널 지연 정밀도 불일치 수정·재검증 최종 보고

**작성일:** 2026-11-03  
**판정:** `NUMERICAL_PRECISION_PARITY_VERIFIED_12_POSES` / **과학적 승인 및 P1 생산 실행은 미승인**  
**원본 상태:** 기존 V2 `HOLD_RF_PARITY` **불변**  
**대상:** R1 `y0.35/Tnone`, Anchor B `(10,0,2.65)` m, tag z `0.45` m, mount 0°, 257-bin Native LoS/Full.  

## 1. 검증된 원인과 수정

원래 SourceFFD `physical_h_col`의 위상은 원본 좌표의 double-precision 기하거리 `d64/c`를 사용하나, Native RT 2.0.1의 직접파 지연은 Mitsuba/DrJit의 다음 산술을 사용한다.

```python
ki_world = mi.Vector3f(vertex - prev_vertex)
path_length = dr.norm(ki_world)
tau = path_length * dr.rcp(speed_of_light)
```

원전: https://github.com/NVlabs/sionna-rt/blob/v2.0.1/src/sionna/rt/path_solvers/field_calculator.py

기존 8개에서 최대 `3.900169068688608e-15 s` (약 3.9 fs) 차이가 생기고 회전 구간의 `~1.59e-4` 복소 상대오차를 유발했다. 정합 **전용** 렌더러는 Source 좌표로만 Native와 동일한 `tau_rt`를 계산하여

```math
H_{RT-repr}(f) = H_{SourceFFD}(f) exp[-j 2π f (tau_rt - d64/c)]
```

를 생성한다. Native `tau`나 H를 수정 계산에 주입하지 않고, 표본 삭제/phase-gain fit/재학습/임계값 완화를 수행하지 않았다. 실제 FFD/물리 편파 응답과 EKF 온라인 관측모델 `h,H`는 **변경하지 않았다**.

## 2. 재검증 수치: 8개 원본 및 4개 새로운 Native pose

동결된 복소 상대오차 RMS 허용치: `<= 1e-4`. 복소 최대 `<=5e-4`, signed 편파차 RMSE `<=2e-6`, 최대 `<=2e-5`, first-tap/port mismatch 0.

| 결과 | 원래 SourceFFD–Native 복소 RMS | 수정 후 V2 복소 RMS | V2 최대 상대오차 | Native tau 완전 일치 | 결과 |
|---|---:|---:|---:|---:|---|
| 기존 8개 (0,150,221,440,458,476,696,916) | 1.0051515145524099e-4 | **4.911678562479378e-7** | 7.1294878847295e-7 | **8/8 ×257 bins** | 수치 PASS |
| 신규 4개 (75,305,610,809) | 4.250422255292953e-5 | **4.0564451832149803e-7** | 5.223530133212291e-7 | **4/4 ×257 bins** | 수치 PASS |

기존 8개 원래 복소 RMS의 **원래 과학 게이트 실패**를 삭제·수정하지 않는다. 모든 12개 pose의 Source 좌표 기반 DrJit 지연과 저장 Native LoS 지연은 각 257개 주파수 bin에서 정확히 같았다. 총 **3,084개 pose–bin 지연 비교**다. 단, 이 12개로 공간 전체의 완전한 동등성을 주장하지 않는다.

신규 4개 V2 수정 결과의 signed 편파차 RMS는 `1.6172854925009117e-7`, 최대는 `2.4278088850415713e-7`, tap/port mismatch는 `0/0`이다. 별도 구현으로 원시 `a,tau`부터 LoS/Full `H`를 재구성한 최대 절대오차는 `0`이다.

신규 pose별 V2 복소 상대오차:
- 75: `5.223530133212291e-7`
- 305: `2.4556343201846843e-7`
- 610: `4.962773471036223e-7`
- 809: `2.8061472886941317e-7`

신규 4개는 기존 8개 검증 pose 밖에서 **사전에 고정**했으며, Native Full/LoS의 실제 PathSolver를 `4×257×2=2,056`회 신규 호출했다. 이 새 RF에서 원래 SourceFFD도 복소 RMS `4.250422255292953e-5`로 해당 4개 표본의 허용치를 통과했다. 차이는 수치 정합을 더 정확하게 만든다는 점이지 새 4개에서 원래 실패가 있었다는 뜻이 아니다.

## 3. 실행 근거와 독립 재검산

- [기존 8개 DrJit V2 검증 PASS — Actions #41600953304](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41600953304), 실행 SHA `cd33dd0e3e0858ac277c73e24e5afcfe45ba0059`.
- [신규 4개 실제 Native RF 생산 + V1 검사 PASS — Actions #41599666331](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41599666331), 실행 SHA `f08a376a01ff2be1cd749a6a0d691b2414b2a65f`.
- [신규 4개 V2 구현 검사 + 별도 산술 감사 PASS — Actions #41604842904](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41604842904), 실행 SHA `8ccf53ce3e1c3115f465ce64f2ec02f4bea8b23c`.
- [원본 신규 4개 Native artifact #13214412546](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41599666331/artifacts/13214412546). `pose_0075/0305/0610/0809.npz`, JSON, 실행 로그 포함.
- [최종 V2 QA/독립 감사 artifact #13216280531](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41604842904/artifacts/13216280531). `V2_PROSPECTIVE_4_NUMERICAL_QA.json`, `INDEPENDENT_V2_4_RAW_AUDIT.json`, `SUMMARY_RECEIPT.json`.
- 독립 산술 검산은 별도 코드/프로세스에서 계산하였으나 **동일한 DrJit/Mitsuba 수치 라이브러리를 재사용**한다. 별도 사람의 독립 과학적 승인 서명과는 다르다.

전달 ZIP 기반 신규 RF와 감사 Actions artifact의 보존 정책은 **30일**이다. 2026-12-03 이후 자동 삭제될 수 있으므로 장기 연구 기록을 위해서는 별도 해시 고정 영속 보존이 필요하다.

## 4. 잘못된 CI 검증 두 차례의 처리

이전 V2 신규 4개 교차검증에서 발생한 두 번의 workflow 실패는 과학 정합 실패가 아니다.
1. 초기 실행 #41604404981: V2 수정값을 독립 V1 근사식의 RMS와 동등하다고 비교하는 검사 배선 오류. V2 복소 RMS `4.056445e-7` 자체는 PASS.
2. 재검사 #41604691769: 독립 V2 구현 계산도 PASS였으나 GitHub Actions 내 임베디드 Python 줄바꿈 이스케이프 오류로 최종 receipt 작성 실패.
3. 수정 실행 **#41604842904 최종 PASS**, V2 구현 및 독립 V2 산술 결과가 일치하고 artifact 보존 PASS.

실패 실행의 로그는 삭제하거나 은폐하지 않는다.

## 5. 과학적 승인 경계 / 다음 단계

현재 **검증 완료**는 `SourceFFD ↔ Native RT`의 **복소 지연 정밀도 표현 문제**에 한정된다.

- 기존 frozen 8개 V2 실패 수치와 계약 `HOLD_RF_PARITY`는 불변으로 보존한다.
- 현재 수정은 독립 `precision_v2/solver_matched_delay.py`의 **정합 평가용 렌더러**이며 원래 `r1b_native.py`, SourceFFD `source_model.py`, EKF를 덮어쓰지 않는다.
- 새 표현 변경을 과학계약 amendment로 승인하고 별도 감사/통합 사전 검증이 완료되기 전까지 **P1 전체 917 pose RF**, **P2 전체 경로 관측오차 분석**, **P3 4-state EKF replay**는 NOT_RUN / SCIENCE HOLD.
- 논문에서는 `수치 정밀도 원인 분석 및 정합 검증`으로 인용할 수 있으나 `R1의 LoS–Full 위치/헤딩 성능 검증 완료`로 인용할 수 없다.
