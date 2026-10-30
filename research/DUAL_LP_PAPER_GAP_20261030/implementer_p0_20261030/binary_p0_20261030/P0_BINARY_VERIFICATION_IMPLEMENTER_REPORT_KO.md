# DLP-EKF-GAPS-001 — 구현자 P0 원본 바이너리 검증 결과 (2026-10-30)

**상태: `P0_PARTIAL_LARGE_BINARY_PENDING` — 신뢰할 수 있는 소형 자산 전수 검사 PASS / 대형 파일 당일 직접 재해시 미완료 / 과거 검증 로그·Git blob 동일성 유지.** 과학적 결과 승인이나 독립 감사가 아니다.

## 권한·범위
- role: IMPLEMENTER, phase: P0_BINARY_READONLY.
- base immutable SHA: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`, proposer HEAD: `5f0a4ac5259210dca8aa866ed887b7117c080aad`.
- 기존 계약은 DRAFT이며 P1–P5, RT, EKF replay, 임의 source 모델 변경, 3-D/M2 선택은 허가되지 않았다.
- 이번 실행은 Github 원본의 읽기 전용 출처/바이트/샘플/시간 키 검증 및 새 증거 문서 append-only 커밋만 수행.

## 이번 세션의 실측 재검증

| 대상 | SHA256 실제 바이트 재계산 | 구조 검증 |
|---|---|---|
| SAMPLES.json 7개 | **7/7 PASS** | 1303/922/1883 poses, 중복 없음 |
| timeline_R2/R4/R5_Tnone.csv 3개 | **3/3 PASS** | 979/742/1415 timestamps, 역행 없음 |
| freqs_hz.npy | **1/1 PASS** | dtype <f8; (257,); 6.2504–6.7496 GHz, step 1.95MHz |
| 원본 sensor/filter/observer/routes/trajectory Python 7개 | **7/7 PASS** | 원래 소스 SHA와 모두 동일 |
| LUT metadata, sensor neutral config, lineage 4개 | **6/6 PASS** | 기존 명시 SHA는 일치; SHA가 없던 lineage 4개는 실제 SHA 새로 생성 |
| 대형 C0 FULL H 7개 + LoS H 7개 + legacy LUT 1개 | **0/15 NOT REHASHED TODAY** | 기존 Actions(2026-10-13) 39/39 SHA/NPY/pose PASS, 현재 원본 Git blob SHA·bytes 39/39 동일 |

**소형 자산 당일 직접 해시: 24/24 PASS, 원본 39개 전체에서 24개.** GitHub Contents API 대형 바이너리 반환 제한 및 대용량 bank 다운로드 이후 작업 컨테이너 장애 때문에, 15개 대형 파일의 당일 직접 SHA 계산은 수행하지 못했다. 그 때문에 `P0 COMPLETE`를 선언하지 않는다.

### 실제 pose/time 수치
- R2: 979 Tnone 시점 ↔ 1303 RF poses, missing 0, max |Δx|≈4.9982e-7m.
- R4: 742 ↔ 922, missing 0, max |Δx|≈4.9920e-7m.
- R5: 1415 ↔ 1883, missing 0, max |Δx|≈4.9995e-7m.
- 모든 route: max |Δyaw|≈4.82285e-7°, 중복/시간 역행 없음. 각 route의 7 C0 case가 공유하는 SAMPLES SHA를 7개 모두 별도 재해시했다.

## 선행 전체-바이너리 증거의 상태
- Actions [38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521): 기존 `p0_verify_inputs.py` 실행 기록에서 **39개 SHA256/shape/pose PASS, error_count=0**. 원천 Git blob SHA와 크기는 이번 Git tree 검사에서 39/39 일치했음. 이를 당일 재실행이라고 부르지 않는다.
- 동일 Actions 원래 아카이브 artifact 11782748118 ZIP **SHA256 88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63**, 2026-10-30 파일 복사 후 직접 재해시 **PASS**; 포함 14 파생 r,s trace NPZ + summary/receipt, **원본 H 아님**. 보존 만료 예정 2026-11-12 UTC.
- Actions [38875080492](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38875080492): LP±45 FFD bank 두 파일 247727983/247743979 bytes, 각 SHA256 **Actions 당시 PASS**. 당일 두 Git LFS 포인터의 object SHA·크기를 원래 `SOURCE_BANK_RECEIPT`와 대조해 2/2 일치. 495473098-byte artifact 12034154094는 접근 가능하나 당일 ZIP 해시 검산 및 NPZ 내부 검산은 컨테이너 오류로 **NOT_COMPLETED**. 해당 Actions artifact 보존 만료 예정 2026-11-15 UTC. 이걸 새 `.ffd` 원시 export 확인으로 혼동하지 말 것.

## G4 재판정 — R4/R5 mount45 **이미 생성된 이력 확인**
기존 Snowball S2 H-store 12개 중 C0에 들어온 7개 Full H SHA 문자열은 **7/7 정확히 같음**. 네 R4/R5 Mount45 S2 생성 manifest의 **입력 pose SHA256도 현재 C0 SAMPLES와 4/4 일치**.
- `R4_aA_m45`: N=922, original pose SHA match, Full H expected SHA256 `5eabb1e44677bdf82630cdf9eea43cad729af2459b9b790d246310d62b725724`, raw complex H **NOT RECOVERED**.
- `R4_aB_m45`: N=922, original pose SHA match, Full H expected SHA256 `3f76d713edccf90ed1d20c8e0f65064add3ca5c5340b56d11c1f391ca81c791d`, raw complex H **NOT RECOVERED**.
- `R5_aA_m45`: N=1883, original pose SHA match, Full H expected SHA256 `1e2c2f36c8d4945e3868c418875b6f08e459c669bcdad981318daf4521ecfbc2`, raw complex H **NOT RECOVERED**.
- `R5_aB_m45`: N=1883, original pose SHA match, Full H expected SHA256 `8f0d87f213a04d6861d6de12f557ce5ce4ae2ba369b9c94e49496bc4f3e154e9`, raw complex H **NOT RECOVERED**.

과거 Snowball README는 보존 패키지에서 H/NPZ 바이너리를 제외했다고 명시. 현재 조회된 해당 브랜치/기본 원본에는 4개 복소 H payload가 없고 manifest + S6 CSV가 있다. 즉 **원본 존재 이력/관측 키 동일계열은 확인되나 실제 현재 파일 접근/LoS 대응/새 해시는 미확인**. 신규 RF부터 재생성하지 말 것.

## G2/G3 및 비교 가능성
- G2: EKF3 range-only는 3state one-step, Range-only 6state full recursive 구현/과거 출력 존재. 같은 C0, 4state, 동일 f/F/Q, initial/gate, scalar range-only full-recursive trace는 아직 **UNCONFIRMED**.
- G3: `rt_cp_uwb_py/localization.py`는 ≥3-anchor known-Z WLS와 **2state** range update helper 제공; frozen C0 RF가 A/B뿐이므로 ≥3-anchor 실제 연속·동시 RF 관측이 확보되었다는 증거 아님.
- G1: 원본 패킷과 이전 source는 교차 참조 가능하나 SourceFFD vs legacy LUT, continuous range bridge vs detector likelihood의 동치는 P0 원본 해시만으로 증명되지 않는다.
- M2와 3-D는 RESERVED; Office는 본문 C0 원본 통계에 혼합하지 않음.

## 남은 P0 및 명시적 중단
1. **R4/R5 Mount45 Full H 원본 복구/직접 해시 및 native LoS H 유무 조회**; 원본이 없으면 G4 optional limitation으로 보존.
2. **C0 H 14개/legacy LUT 직접 재해시 및 H→CIR→tap→r,s 짝지음**. 2026-10-13 전수 검증은 강한 기존 증거지만 이번 세션 계산으로 승격하지 않음.
3. **FFD NPZ 2개 당일 직접 해시** 및 source raw availability 검토(기존 Actions 증거 별도 보존).
4. 검증 가능한 원본이 모인 후 P0 정합 결과와 미해결 질문을 제안자에게 이관; FROZEN+감사 없이 P1/P2/P3/P4 미실행.

**변경:** 새 증거 파일만 P0 출력 경로에 추가. 기존 `data/raw`, original C0 H, FFD bank/LFS, 원래 기록, main, MBVAR/POL-XCORR 불변. 과학 PASS 미발행.
