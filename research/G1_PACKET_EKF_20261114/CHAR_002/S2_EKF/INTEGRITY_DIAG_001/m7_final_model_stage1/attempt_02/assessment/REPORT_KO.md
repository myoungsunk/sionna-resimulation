# M7 Stage 1 검증 결과

20개 seed는 같은 RF 실현을 공유합니다. RF·환경 일반화의 독립 검증이 아닙니다.

주 판정은 B0와 Q가 일치하는 L2입니다. Q 불일치 stress와 고정 mask 대조는 보고 전용입니다.

| 조건 | gate | arm | 무결성 | 정확도 | 동시 | mirror | 판정 |
|---|---|---|---:|---:|---:|---:|---|
| B0 | own | H0 | 1/20 | 0/20 | 0/20 | 59 | FAIL |
| B0 | own | H1 | 1/20 | 0/20 | 0/20 | 51 | FAIL |
| B0 | own | H2 | 0/20 | 20/20 | 0/20 | 4 | FAIL |
| B0 | own | H3 | 12/20 | 15/20 | 12/20 | 11 | FAIL |
| B0 | own | H4 | 0/20 | 1/20 | 0/20 | 15 | FAIL |
| B0 | own | H5 | 0/20 | 3/20 | 0/20 | 5 | FAIL |
| B0 | own | H5P | 0/20 | 7/20 | 0/20 | 13 | FAIL |
| B0 | fixed | H0 | 0/5 | 0/5 | 0/5 | 11 | REPORT_ONLY |
| B0 | fixed | H1 | 0/5 | 0/5 | 0/5 | 15 | REPORT_ONLY |
| B0 | fixed | H2 | 0/5 | 5/5 | 0/5 | 1 | REPORT_ONLY |
| B0 | fixed | H3 | 3/5 | 3/5 | 3/5 | 2 | REPORT_ONLY |
| B0 | fixed | H4 | 0/5 | 0/5 | 0/5 | 4 | REPORT_ONLY |
| B0 | fixed | H5 | 0/5 | 0/5 | 0/5 | 1 | REPORT_ONLY |
| B0 | fixed | H5P | 0/5 | 1/5 | 0/5 | 4 | REPORT_ONLY |
| L2_GYRO_ARW | own | H0 | 1/20 | 0/20 | 0/20 | 58 | FAIL |
| L2_GYRO_ARW | own | H1 | 1/20 | 0/20 | 0/20 | 50 | FAIL |
| L2_GYRO_ARW | own | H2 | 0/20 | 20/20 | 0/20 | 4 | FAIL |
| L2_GYRO_ARW | own | H3 | 12/20 | 14/20 | 11/20 | 10 | FAIL |
| L2_GYRO_ARW | own | H4 | 0/20 | 1/20 | 0/20 | 16 | FAIL |
| L2_GYRO_ARW | own | H5 | 0/20 | 3/20 | 0/20 | 5 | FAIL |
| L2_GYRO_ARW | own | H5P | 2/20 | 6/20 | 2/20 | 13 | FAIL |
| L2_GYRO_ARW | fixed | H0 | 0/5 | 0/5 | 0/5 | 10 | REPORT_ONLY |
| L2_GYRO_ARW | fixed | H1 | 0/5 | 0/5 | 0/5 | 16 | REPORT_ONLY |
| L2_GYRO_ARW | fixed | H2 | 0/5 | 5/5 | 0/5 | 1 | REPORT_ONLY |
| L2_GYRO_ARW | fixed | H3 | 3/5 | 3/5 | 3/5 | 2 | REPORT_ONLY |
| L2_GYRO_ARW | fixed | H4 | 0/5 | 0/5 | 0/5 | 5 | REPORT_ONLY |
| L2_GYRO_ARW | fixed | H5 | 0/5 | 0/5 | 0/5 | 1 | REPORT_ONLY |
| L2_GYRO_ARW | fixed | H5P | 1/5 | 1/5 | 1/5 | 4 | REPORT_ONLY |
| L2_GYRO_ARW_Q_B0_STRESS | own | H0 | 1/20 | 0/20 | 0/20 | 58 | REPORT_ONLY |
| L2_GYRO_ARW_Q_B0_STRESS | own | H1 | 1/20 | 0/20 | 0/20 | 50 | REPORT_ONLY |
| L2_GYRO_ARW_Q_B0_STRESS | own | H2 | 0/20 | 20/20 | 0/20 | 4 | REPORT_ONLY |
| L2_GYRO_ARW_Q_B0_STRESS | own | H3 | 8/20 | 13/20 | 7/20 | 11 | REPORT_ONLY |
| L2_GYRO_ARW_Q_B0_STRESS | own | H4 | 0/20 | 1/20 | 0/20 | 13 | REPORT_ONLY |
| L2_GYRO_ARW_Q_B0_STRESS | own | H5 | 0/20 | 1/20 | 0/20 | 5 | REPORT_ONLY |
| L2_GYRO_ARW_Q_B0_STRESS | own | H5P | 0/20 | 6/20 | 0/20 | 13 | REPORT_ONLY |

H5는 GM 몫을 뺀 잔여 q_s를 사용하므로 H5 실패만으로 b_θ 필요성을 주장할 수 없습니다. H5′를 함께 봅니다.

seed 10–14와 진단에 사용하지 않은 seed 15–29를 COUNTS_SUBSETS.csv에 별도 집계했습니다. 기존 기준은 완화하지 않았습니다.

본 결과는 실행·구현 검사와 수치 판정이며, 독립 감사 완료나 모델 채택을 뜻하지 않습니다.
