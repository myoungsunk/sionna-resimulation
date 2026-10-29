# RA2-a~e 실증 감사 기록 — 2026-10-29

**상태:** TECHNICAL_SOURCE_REPLAY_PASS / NEGATIVE_QA_REQUIRES_FINAL_CONFIRM / INDEPENDENT_AUDIT_PENDING.
**역할:** PROPOSER → IMPLEMENTER → AUDITOR 문서·검산 절차를 분리했지만 같은 세션의 SELF_REVIEW_ONLY. 연구 승인 아님.

## 고정 출처 (RA2-a)
- 조사 원소스 `9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13`.
- 현재 실험 근거 `f100a983cc389fcdef073592a254add61e7115da`.
- 원 RF 원본은 `results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/FULL_RF/H_<case>.npy`.
- 같은 BLOCK_C의 `<case>/SAMPLES.json`, `results/DRIVE_SIM_20261007/S1/routes/timeline_<R>_Tnone.csv`.
- CONTROL packet: `research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL/<case>_B0.npz`의 LFS 원본, 해시 직접 확인.
- FFD 주파수축: `LP_plus45_bank.npz`, sha256 `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b`.
- 7개 H SHA와 CONTROL SHA는 실행 코드 `ra2_readonly_lineage.py`의 사전 상수로 동결.
- 관측 조건: TX=0, 257 bins, Hann, 1028-tap IFFT ×257, stronger RX peak의 30% leading-edge, `s=(P1-P2)/(P1+P2)`, `r=c tap/(1028 Δf)`. 중간 계산에 원 관측 구현의 함수를 호출하지 않음.
- 허용차: `max|Δs|<=1e-12`, `max|Δr|<=1e-9 m`; H/blob SHA와 packet/control SHA는 비트 단위 일치.

## 실행 (RA2-b,c)
[GitHub Actions run #40847329404](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40847329404), SHA `12cce1b3a16d755331d8cbbb944314494646a0e8`; receipt artifact `ra2-lineage-receipt-40847329404`.

| case | 원 H/SAMPLES 수 | timeline/packet 수 | max |Δs| | max |Δr| (m) | 원 H SHA · control SHA |
|---|---:|---:|---:|---:|---|
| R2_aA_m0 | 1,303 | 979 | 2.22e−16 | 3.55e−15 | MATCH · MATCH |
| R2_aB_m0 | 1,303 | 979 | 2.22e−16 | 3.55e−15 | MATCH · MATCH |
| R2_aA_m45 | 1,303 | 979 | 1.21e−16 | 3.55e−15 | MATCH · MATCH |
| R4_aA_m0 | 922 | 742 | 1.11e−16 | 3.55e−15 | MATCH · MATCH |
| R4_aB_m0 | 922 | 742 | 2.22e−16 | 1.78e−15 | MATCH · MATCH |
| R5_aA_m0 | 1,883 | 1,415 | 2.22e−16 | 3.55e−15 | MATCH · MATCH |
| R5_aB_m0 | 1,883 | 1,415 | 2.22e−16 | 3.55e−15 | MATCH · MATCH |

총 packet-조건 7,251개(동일 R2/R4/R5 항목의 별도 anchor/mount 관측은 서로 다른 채널이므로 각각 계수). 원 H에서 `SAMPLES`는 추가 probe 자세를 포함하고, CONTROL은 원 timeline row만 사용한다. 독립 환경/독립 RF 시뮬레이션 수가 아니라 단순한 감사 packet 수이다.

## 오류주입 (RA2-d)
초기 run #40846941134, #40847032432는 **음성 fixture 자체의 코드 오류**로 실패했으며 유지. 수정한 #40847116193에서는 중복·정렬·빈 행·누락 4개의 음성 검사 통과. 추가 SHA 위조/포트 반전/시간 이동/0분모 검사는 별도 신규 커밋 `4b1743429ac4ca89abcd6b6c32b77bd5564d16a8`에서 추가, 최종 실행 확인 필요. `run #40847329404` 성공만으로 이 추가 4개가 성공했다고 소급 주장하지 않음. 향후 실제 데이터에서 H 파일 교체, port flip, 행 누락 시 반드시 fail-closed인지도 확인 필요.

## 원인과 수정 여부 (RA2-e)
- **관측 추출 오류가 현재 점수 차이의 원인이라는 가설**: 7개 모든 원본 case에서 원 H→r,s→packet parity가 사실상 기계정밀도로 맞으므로 이 구간의 오류는 **지지되지 않음**.
- 반면 `H` 자체의 반사/회절 물리, generator float precision, path continuity, `μ` 모델 적합, MB_VAR의 이전 posterior/현재 prior 분산 조회 시점 차이, gate 운영 방식은 이 시험에 의해 검증되지 않음.
- **기존 BB/MB_VAR 결과 재실행**: H→packet 경로만으로는 불필요. 분산 조회 시점/예측 모델/다른 코드 비교는 RA3~RA4 계약에 따라 canary R4-B/R5-A 우선, 변화 시 28조건 비교. 기존 결과는 불변으로 보존.
- **독립 감사 승인**: 보류. 별도 auditor가 표본 무작위/최악 packet을 독립 구현으로 재계산하고 원본 출력 해시를 검증해야 함.
- **G3**: strict 26건이 `H` 물리학에 미치는 영향은 별개. 상세 `G3_ROOT_CAUSE_AUDIT.md` 참조.

본 문서 자체는 후속 결과 증거의 색인이다. 새 가설의 확증 결과가 아니다.
