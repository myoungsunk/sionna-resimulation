# M5 HF-KI · Stage 0 구현 검사

mount 0°, 앵커 B, B0, Full RF, R2/R4/R5. 계획서 GitHub revision 033abcc7f2940bd8437ccbebd145d2f9f229730b.

σθ=0에서 동결 E0-LORO를, 고정 분산·kernel을 주입했을 때 R4 C1 KI를 재현했다. 검사 한도는 절대차 1e−10이다.

| 궤적 | E0-LORO 최대 절대차 | 독립 재계산 최대 절대차 | E0 수용 패킷 | 앵커 통과 |
|---|---:|---:|---:|---:|
| R2 | 0 | 1.82e-12 | 971/979 | 2 |
| R4 | 0 | 1.46e-11 | 728/742 | 1 |
| R5 | 0 | 1.36e-12 | 1384/1415 | 3 |

- C1 KI의 기준 trace 최대 절대차는 0, 독립 kernel 재계산 최대 절대차는 4.37e-11이다.
- 비영 σθ에서도 kernel·재귀를 재계산했다. 참값을 닮은 추가 입력이 trace에 영향을 주지 않았고 미래 입력을 바꿔도 처음 64행은 동일했다.
- seed 11–14에서 궤적별 online NPZ 12개를 검증했다. RF 패킷 z와 evaluator 격자는 공유하며, seed별 운동 입력은 B0 원래 생성식을 사용한다.
- 첫 실행에서 yaw wrap의 부동소수점 차이가 I_cell 절대차 2.48e−10로 증폭됐다. 이동·yaw를 별도로 검증하고 그 검사를 통과한 기록 좌표에서 독립 kernel 합을 계산하도록 수정했다. 허용차와 필터 식은 원 계약대로 적용했다. [첫 실행 기록](../../stage0/EXECUTION.json)

[동결 계약](RUN_CONTRACT.json) · [구현 검사](CHECKS.json) · [검증 기록](VERIFICATION.json)
