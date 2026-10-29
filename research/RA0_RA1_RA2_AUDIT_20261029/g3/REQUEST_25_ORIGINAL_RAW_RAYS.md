# G3 잔여 25 ray 근본 원인 확정을 위한 최소 원본 데이터 요청

상태: `BLOCKED_25_ORIGINAL_RAW_TAU` — 원본 23개 위치 receipt/SHA와 모두 연결됨. 2026-10-29 기준 GitHub 저장소 및 원 final/snapshot 압축본, 연결된 Google Drive의 관련 파일명 검색에서 해당 23개 원 trace NPZ를 확보하지 못함.

## 사용자가 제공할 파일: 단일 ZIP 1개

2026-10-07 Snowball 원본 작업의 `SNOWBALL_ROUTES_01a11669` / job root에서, **아래 파일을 원형 그대로** 묶어 전달해 주세요.

- **정확한 원본 `*_trace.npz` 23개**, 그룹별 R2_aB 1개 · R4_aA 3개 · R4_aB 3개 · R5_aA 9개 · R5_aB 7개.
- **각 NPZ에 대응하는 `*_trace_receipt.json` 23개**. 총 46개 파일. Receipt는 과거 SHA-256 고정 자료와 비트 일치해야 합니다.
- 원래 폴더 구조 `results/S2/traces_<route>_a<anchor>/<tag>_trace.npz` 및 `..._trace_receipt.json` 유지.
- 전체 `5,630` 위치를 다시 업로드할 필요는 없습니다. 정상 R2_aA 그룹 925개는 이미 별도 저장돼 있습니다.
- 원본 `H_*.npy`, `SAMPLES_*.json`, 두 FFD bank, original timeline, 7개 CONTROL은 이미 GitHub 자료로 확보되어 있으므로 추가 업로드가 필요하지 않습니다.

**23개 exact original_relpath**는 [SHA 고정 원장](G3_23_ORIGINAL_SOURCE_LOCK.json)의 `items[].original_relpath`, `items[].expected_original_receipt_sha256`를 따르십시오. 해당 문서는 다음 URL에서도 열 수 있습니다.
https://github.com/myoungsunk/sionna-resimulation/blob/audit/ra4-factorial-g3-precision-20261029/research/RA0_RA1_RA2_AUDIT_20261029/g3/G3_23_ORIGINAL_SOURCE_LOCK.json

예시:
```text
results/S2/traces_R2_aB/x18.7383_y0.0235_trace.npz
results/S2/traces_R2_aB/x18.7383_y0.0235_trace_receipt.json
results/S2/traces_R4_aA/x14.6758_y0.0748_trace.npz
results/S2/traces_R4_aA/x14.6758_y0.0748_trace_receipt.json
...
```

필수 내부 배열/메타: `tau`(ray별 지연), `jones`(frequency/node별 Jones response), `ang`, `node_bins/node_freq_hz`, `present`, `x,y`, `status`, 해당 receipt의 `n_paths`, source config/hash. 포트 순서와 주파수축은 원본에서 변경하지 마십시오.

### 직접 ZIP 생성 권장

원래 job root로 이동한 다음 **다음 명령**을 실행하면 됩니다. 두 번째 인자에 본 감사 폴더의 원장 `G3_23_ORIGINAL_SOURCE_LOCK.json` 경로를 지정하세요.

```python package_g3_23.py /path/to/SNOWBALL_ROUTES_01a11669 /path/to/G3_23_ORIGINAL_SOURCE_LOCK.json
```

패키징 스크립트는 [package_g3_23.py](package_g3_23.py). 23개 raw + 23개 receipt, SHA 목록을 확인하고 `G3_ORIGINAL_23_TRACE_PAIRS.zip`을 생성하며 누락 시 중단합니다. ZIP을 이 대화에 업로드해 주세요.

## 확보 시 실행할 확정 절차

1. 원 receipt SHA 23/23 검증, 각 `tau`/포트/주파수/지오메트리 검사.
2. raw image candidate와 merged class 지연을 각각 재계산해 25개 ray의 원인을 `CLASS_TIE`, `SOURCE_NUMERIC`, `GEOMETRY_OR_SOLVER`, `UNRESOLVED`로 개별 분류. float32 final cast가 아닌 내부 누적 수치는 별도 비교.
3. **실제 H 재합성 parity**: 원 NPZ + bank + 고정 FFD solver configuration으로 257-bin/2×2 복소 H를 처음부터 재조립해 기존 H의 해당 row와 비교.
4. 경로 물리 결함이 확정된 경우에만 24 trace 위치 국소 수정 후보를 **새 파일**로 생성, raw/first-path `r,s,tap` 변화 확인.
5. packet 변화가 실질적으로 있는 case만 **첫 변경 시점 이후**의 BB/MB_VAR 원래 필터, 필요시 각 gate arm을 재실행. 전역 solver 버그이면 전체 H 변화 스캔을 별도 단계로 확장.

## 원본 데이터가 없을 때

- 원 위치에 대한 pinned Sionna RT 재실행은 *재현성/수치 모델 시험용*으로 진행할 수 있지만 이는 **2026-10-07 원본 tau 자료가 아닙니다**.
- 이 경우 우선 제공해야 할 것은 원 solver 및 scene 실행 환경 `sionna-rt, mitsuba, drjit` 버전, 17+추가 node 설정, 원 `rf_b_trace.py` commit, scene/material 설정, 원 FFD bank SHA와 하드웨어/미쓰바 variant입니다. 은행·코드는 이미 공개 소스에서 확인 가능하므로 원 런타임 기록만 있으면 시작할 수 있습니다.
- 새 RT와 저장 H가 달라질 경우 해당 차이가 original bug인지 재현환경 차이인지 추가로 확인해야 합니다. 
