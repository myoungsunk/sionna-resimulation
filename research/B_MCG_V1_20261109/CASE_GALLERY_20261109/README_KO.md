# B-MCG v1 — 506개 사례 케이스북 (2026-11-09)

## 시작

1. `B_MCG_506_CASES_INTERACTIVE_20261109.html`을 브라우저에서 열면 506개 추천 사례와 **전체 3,136개 원시 주행 시점에 대한 직접 k 조회**가 가능합니다. (두 보정 strata에서 비교)
2. 좌측에서 `실제 감쇠 23건` 버튼을 누르면 실제 intervention의 모든 사례를 볼 수 있습니다.
3. 경로/보정/분류 검색, 시점 직접 이동, 전후 시간창 길이 변경, 케이스별 고유 `#route|stratum|k` 링크가 지원됩니다.
4. 그래프: GT·OFF·ON·IMU/DR의 XY 궤적, heading, gyro 대 GT yaw rate, Full/LoS `s`와 모델, range, 실제 오차, 가드 β와 score, CIR FP 주변 왜곡 지표입니다.
5. `B_MCG_CASE_GALLERY_20261109/CASEBOOK_REPORT_KO.md`: 분석 결론과 실제 개입 23건의 개별 손익. `CASE_BY_CASE_506_KO.md`: 506개 전체 목록.
6. `B_MCG_CASE_GALLERY_20261109/panels/`: 48개 대표 사례에 대한 8패널 독립 PNG; 23개 실제 개입은 모두 포함됐습니다.

## 데이터/코드

- `CASE_CATALOG.csv`: 506개 선택 사례 (각 사례의 경로·시간·원인 분류·감쇠·손익·참값).
- `FULL_ENRICHED_6272.csv`: 3,136 주행 시점 × 보정 strata 2개, 총 6,272개 저장 필터·IMU·RF·평가 행.
- `PRIMARY_R[2,4,5]_RF_CIR_FEATURES.csv`: source PRIMARY_3136의 경로별 CIR/s/Full-LoS 요약.
- `analyze_cases.py`: 결과 입력·control 역산·인과 대비·사례 발굴/감사 코드.
- `build_gallery.py`: 오프라인 self-contained Plotly 케이스북 생성.
- `export_panels.py`: 48개 독립 PNG 생성.
- `make_reports.py`: 연구 보고서와 전체 케이스 정적 색인 생성.
- `CASE_AUDIT.json`, `PANEL_MANIFEST.json`, `SHA256.json`: 무결성·출처 및 평가 제한.

## 과학적 주의

- **컴퓨터가 새 RF 또는 B-MCG 필터를 실행한 결과가 아닙니다.** GitHub Actions #42600632209가 실행한 저장된 state/prior/observation/RF 기록과 이전 Full/LoS 비교 결과를 재산술해 연결했습니다.
- **IMU gy / odom ds는 원본 NPZ 직접 조회가 아니라 원본 predictor 역산 값입니다.** 4스트림 parity를 확인했으나, 실제 하드웨어 raw IMU 센서 출력과 동일시해서는 안 됩니다.
- **GT-aligned DR은 첫 시점에만 GT로 정렬한 사후 시각화**입니다. 온라인 B-MCG는 참값, clean CIR, Full-LoS error에 접근하지 않았습니다.
- **COMPATIBLE은 정확/LoS 판정이 아닙니다.** `UNKNOWN`은 정답 미판정입니다. 같은-prior 손익은 RF 단독 원인이라는 인과 증거가 아닙니다.
- **원본 복소 CIR samples는 이 저장소에 포함돼 있지 않으며, CIR 그림은 원본 데이터를 통한 요약 특징의 시간 추적입니다.** FP 주변 위상/복소 sample별 자세한 원인을 확인하려면 pinned 원본 CFR를 다시 열어야 합니다.
- 506개는 사후 진단을 위한 선택 사례입니다. 미지 환경·seed에 대한 독립 검증 결과가 아니며, 운영 채택 보류를 바꾸지 않습니다.

Source GitHub: https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209  
Original code: https://github.com/myoungsunk/sionna-resimulation/tree/61ad3da300fdf5c235c60c7f23c04696c07b2e59/research/B_MCG_V1_20261109  
