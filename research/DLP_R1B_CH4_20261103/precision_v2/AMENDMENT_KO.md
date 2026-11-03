# DLP-R1B-CH4-001 / PREC-V2 — Sionna 2.0.1 연산식 직접 복원

PREC-V1 8개 재검증과 새 4개 예비 검증을 관찰하기 전, 공식 **Sionna RT v2.0.1** 소스를 검토해 V2 연산을 고정한다.

원본: https://github.com/NVlabs/sionna-rt/blob/v2.0.1/src/sionna/rt/path_solvers/field_calculator.py

직접경로에서는 `vertex=target`, `prev_vertex=source`이며 아래 지연 계산을 그대로 사용한다.

```python
ki_world = mi.Vector3f(vertex - prev_vertex)
path_length = dr.norm(ki_world)
tau = path_length * dr.rcp(speed_of_light)
```

`mi.Float` 및 `drjit`의 native 계산 순서를 그대로 따라, **source 좌표만으로** 계산한 `tau_render`를 사용한다. 기존 SourceFFD complex physical channel을 수치 표현으로 렌더링한다.

```math
H_{repr}(f)=H_{SourceFFD}(f)\exp[-j2\pi f(\tau_{render}-d_{64}/c)].
```

- Native에서 저장된 `tau_native`는 **오직 예측 이후 검산**할 때만 사용한다.
- phase/gain fit, native tau oracle, GT 보정, old data overwrite, threshold relaxation 금지.
- 원래 V2 HOLD 및 기존 FFD/SourceFFD `h,H`·EKF 변경 불가.
- 사전 숫자 기준은 PREC-V1과 동일: 복소 max ≤5e−4, RMS ≤1e−4, 편파차 max ≤2e−5, RMS ≤2e−6, tap/port 불일치 0.
- V2 old 8 raw replay 통과와 prospective 4 raw replay는 **수치 정합 증거**일 뿐, 별도의 과학적 승인 또는 917 pose/full EKF 결과가 아니다.
- V2 실행은 기존 Native를 새로 돌리지 않으며, source-only delay와 저장된 Native delay 사이의 정확 일치 여부는 별도 보고한다.

PREC-V1의 float32 입출력 근사 표현을 교체하는 이유는 동결 규칙을 결과에 맞추기 위해서가 아니라, **코드로 확인한 실제 Sionna 지연 산술 순서를 재현하기 위해서**다. 기존 결과는 모두 append-only 보존한다.
