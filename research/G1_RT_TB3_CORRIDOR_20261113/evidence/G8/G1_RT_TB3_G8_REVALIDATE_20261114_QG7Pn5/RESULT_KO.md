# G1-RT-TB3-002 G8 재검증

Snowball에서 G-T1 × 앵커 A의 동일한 P001–P003 TEACH·REPEAT RF pose 332개를 F1으로 다시 계산했다. RF pose 표와 기존 G1 `H_LoS.npy`의 SHA를 확인했다. 판정은 복소 원소별 최대 상대 오차 < 1 × 10⁻⁶이며 기준 원소가 0일 때 재합성 값도 0이어야 한다. [초기 G8 기록](../G1_RT_TB3_G8_20261114T082240Z_qOhMGz/RESULT_KO.md).

## 원인 확인

- 기존 G1 단정밀도 위상을 배정밀도로 계산하면 포트 계수의 최대 상대 차이 7.17925 × 10⁻⁶가 남았다. 저장된 TX/RX 각도와 delay는 같았고, 보간이 없는 17개 노드의 최대 차이도 6.92553 × 10⁻⁶였다. LoS Jones 항을 자유공간 해석식으로 바꾸면 여전히 5.45358 × 10⁻⁶가 남았다. [각도·Jones 대조](../G1_RT_TB3_G8_REVALIDATE_20261114_xUMt2d/ATTRIBUTION.json).
- 332 pose의 4개 bin에서 Sionna의 방향·기저·채널 내적을 사용하고 FFD 격자 산술만 NumPy 방식으로 바꿨을 때 포트 계수가 최대 6.56165 × 10⁻⁶ 변했다. Sionna는 FFD 값을 스케일 적용 후 float32로 저장하고 보간한다. Method B는 NumPy에서 보간한 뒤 스케일하며, 안테나 방향과 기저 변환에도 다른 연산 경로를 사용한다. [FFD 산술 대조](../G1_RT_TB3_G8_REVALIDATE_20261114_xUMt2d/BANK_ARITHMETIC.json).
- 첫 수정안은 Sionna의 개별 연산을 조합해 적용했다. 배정밀도 기준 최대 오차 2.38772 × 10⁻⁶로 미통과했다. 최종 수정안은 F1 trace가 발견한 직선 경로에 Sionna 2.0.1의 `FieldCalculator`를 통째로 적용했다. 257 bin 전체에서 기존 G1 LoS 포트 계수와 지연을 비트 단위로 재현했다. [첫 수정안 결과](../G1_RT_TB3_G8_REVALIDATE_20261114_xUMt2d/output/G8.json) · [계수·지연 대조](VERIFICATION.json).

## 최종 판정

| 비교 기준 | 복소 원소 | 최대 상대 오차 | 판정 |
| --- | ---: | ---: | --- |
| 같은 G1 `PATHS_LoS`의 원래 계수·지연에 배정밀도 위상을 적용한 `H_LoS` | 341,296 | 0 | PASS |
| 같은 F1 trace에서 계산한 LoS | 341,296 | 0 | PASS |
| 기존 단정밀도 위상이 저장된 G1 파일 원본 | 341,296 | 2.99922 × 10⁻⁵ | FAIL |

G1 기준의 계수·지연·pose·주파수는 원본을 그대로 사용한다. 기준의 위상 계산 정밀도를 수정한 재검증이며, 첫 파일럿과 G1 파일 원본의 판정도 기록했다. F1은 6개 XY 위치에서 solver를 102회 호출했다. LoS 전계 계산에는 추가 경로 탐색이 없었다. near 경로 664개의 기하·메타데이터 및 반사 경로 계수는 초기 G8과 비트 단위로 같았다. H의 변경 중 LoS 항 교체로 설명되는 부분을 제외한 최대 절대차는 7.46 × 10⁻¹⁸이다. 소요 시간 272.52초. [G8 결과](output/G8.json) · [실행 manifest](output/RUN_MANIFEST.json).

원본 배열과 NPZ는 Snowball `/home/KMS/G1_RT_TB3_G8_REVALIDATE_20261114_QG7Pn5/output`에 보관했다. 파일럿 범위에서만 검증했다. [체크섬](SHA256.txt).
