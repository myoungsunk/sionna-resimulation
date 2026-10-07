# PREREG 수정 기록 (S0)

원본 `PREREG.json`(커밋 `02009ca`)은 수정하지 않는다. 변경은 이 파일에만 추가한다.

## A1 — G1은 production 설정(`--threads 1`)에서 판정한다 (명확화, 완화 아님)

- 원 문구: G1 "H 상대 오차 ≤ 1e-6". thread 수는 명시하지 않았다.
- 관측(`REFERENCE_CHECK.json`, 같은 position x7.0_y0.0, yaw 0/50°):
  - `--threads 1`: 저장 H와 **오차 0.0**(비트 동일, 65 bin × 2 yaw).
  - `--threads 4`: pose별 상대 오차 3.2e-6, bin별 최대 1.2e-5 → **원 임계값 1e-6 미달(FAIL)**. 원인 추정: 병렬 reduction 순서(float32 비결합성).
- 조치: production A안은 기존 scan 방식대로 단일 thread 프로세스 4개 병렬(`corridor_scan2_run.sh`)이므로 G1은 `--threads 1`에서 판정한다. 임계값 1e-6은 그대로 두고, `--threads 4`는 production에서 쓰지 않으며 FAIL 결과를 그대로 기록한다.
