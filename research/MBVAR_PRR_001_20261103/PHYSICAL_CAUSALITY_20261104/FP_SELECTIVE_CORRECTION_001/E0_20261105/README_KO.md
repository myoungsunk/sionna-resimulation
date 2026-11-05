# FP-SC-001 E0 — 정의·입력·기준선 재현

최신 사용자 지시(“계획대로, 구현 - 실행 - 깃허브 푸시하도록”)에 따라 E0를 구현한다. 원 제안서는 옆 `PROPOSER_20261105` 폴더에 원본 바이트 그대로 보존한다.

## 실행 범위

- 공개 sensor seed10, R2/R4/R5 × B0/L2 × Full/Native-LoS 12개 원본 W0 조건.
- 3,136개 pose의 Full/LoS clean RF와 원래 관측·거리 정의·상태 prior를 구분한다.
- G4 24개 정지 조건의 원시 spectrum/CIR와 실제 SourceFFD 모델을 재현한다.
- 2≤d<16m, 1mm 간격 14,000개의 이상적 flat-spectrum 직접파로 검출거리 mapping을 점검한다. 새 RT는 없다.

## 해석과 통제

`SourceFFD.h_r=geometry+B_OLD`와 양자화된 `native_range`는 다른 값이다. 보정거리는 원래 convention에 따라 `z_r−mu_r−B_OLD`로 정의하며, clean RF 재추출값과 원래 packet 값을 따로 보존한다. 원래 RF가 clean임은 소스 계보와 r/s 수치 parity가 모두 확인된 경우에만 확정한다. 센서 noise seed와 RF-noise seed를 혼용하지 않는다.

모든 실행은 코드·입력·환경·계약의 SHA 검증 후 시작하며 새 결과 폴더만 만든다. 실행자의 합성 시험, 같은 세션의 별도 검토자, 별도 산술 재계산의 범위를 구분한다. 외부 독립감사 ACCEPT를 부여하지 않는다. E0 완료 및 다음 단계 판정은 실행 후 `RESULTS_KO.md`와 `STAGE_VERDICT.json`에 기록한다.

## 재현 명령

`RUN_MANIFEST.json`에 실제 명령과 code/input/contract SHA를 기록한다. `scripts/fp_sc_acquire_inputs.py`는 기존 public LFS payload를 원 OID·크기로 검증하며, 다른 실제 payload를 덮어쓰지 않는다. 이 E0 폴더의 작은 출력 NPZ/JSONL은 일반 Git 객체로 보존한다.
