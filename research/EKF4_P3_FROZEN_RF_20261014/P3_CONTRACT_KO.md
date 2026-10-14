# P3 — 동결 실제 RF 입력 39개 해시/형상 사전감사와 적격성 검증

이 단계는 **P2의 과학적 가설 지지 여부와 무관한 RF 입력 적격성 감사**다. 원본 소스 P0 manifest `research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json`을 `32ee990b0d9d...`에서 고정한다.

실행 전 stdlib-only `p3_frozen_inputs.py audit`가 manifest Git blob SHA1 `8bf216cf606f5e3c11139cacbf42f15a44556feb`, P3 코드·workflow AST와 총 39 assets 목록을 확인하고 `GO/HOLD` 영수증을 남긴다. **그다음** 해당 assets만 sparse checkout하여 실제 39개 SHA256, 크기 및 `.npy` shape를 검사한다. 실제 RF H/LoS/FFT/frequency/LUT/timeline/archived sensor sources 전부 보존한다. 입출력 해시/runner/step failures 별도 보존.

**직접 결정:** RF 파일·관측 모델 연결이 유효하면 P4 공동 모델 어댑터 구현이 가능하다. source SHA mismatch/shape mismatch로 얻은 데이터에는 RF 성능 수치를 붙이지 않는다.

P3 성공은 *데이터 적격성*만 의미한다. 원본 재생 결과와 4-state P4 수치 갱신, P5 reference, P6 반복 추정 성능 또는 generalization PASS와 같지 않다. `P2_FULL`의 synthetic 결과를 RF 물리학의 입력 적격성과 혼동하지 않는다. 사용자가 요청한 audit-first 원칙으로, 코드는 GitHub-hosted Actions에서만 실행한다.
