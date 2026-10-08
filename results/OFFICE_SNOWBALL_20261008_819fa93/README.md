# Snowball 사무실 전체 실행 결과 — PASS

`claude/office-e-layout`의 코드 `819fa93b152ca3cdf66297af09ff073880bd9d9b`를 Snowball KMS 계정에서 실행했다. **전체 35곳 계산과 출력 검증이 통과했다.**

| 항목 | 실측 결과 |
|---|---|
| 슬랩 | PASS, 단일 판 상대오차 최대 약 1.3e-5 < 1e-4 |
| 기하 LoS | 35곳 일치, 열림 25 / 막힘 10, 불일치 0 |
| 축소 시험 | 6곳 × 3 bin × yaw 19, valid 6, 종료 0 |
| 전체 | 35곳 × 257 bin × yaw 19, PathSolver 170,905회 |
| 완료 | 컨테이너 종료 0, RUN_STATUS COMPLETE/exit0, SWEEP_COMPLETE 존재 |
| 전체 재검증 | valid 35 / invalid 0, 누락·중복·예상 밖 출력 없음, 종료 0 |
| 계산 시간 | 2026-10-08 11:56:50–13:07:57 KST, 약 1시간 11분 |
| 자원 | 초기4 worker; 사용자 승인으로 CPU quota 및 스케줄러 병렬 한도64, 먼저 완료된4곳 보존 후 나머지31곳 동시 계산 |

환경은 Sionna RT 2.0.1, Mitsuba 3.8.0, Dr.Jit 1.3.1, NumPy 2.4.6, SciPy 1.17.1이다. 고정 image ID와 시작·종료 시각은 [EXECUTION_MANIFEST](evidence/EXECUTION_MANIFEST.json)에 있다. LP ±45° 뱅크 두 파일의 SHA는 기존 BANK_MANIFEST와 일치했다. [source manifest](evidence/office_source_manifest_819fa93.json)의 배포90개 파일은 Git 원본과 바이트 단위로 일치한다.

## 결과와 재현 근거

- [전체 VERIFY](full35_stride1/VERIFY.json), [상태](full35_stride1/RUN_STATUS.json), [요청](full35_stride1/RUN_REQUEST.json).
- `full35_stride1/office_x*_y*/`에 H.npy, receipt.json, SETUP_SNAPSHOT과 장면 PLY가 있다. H의 격자는 yaw19 × bin257 × 수신2포트 × 송신2포트이다.
- [슬랩](slab_check/SLAB_CHECK.json), [LoS](geom_check/GEOM_LOS_CHECK.json), `pilot_stride128_lf/`의 시험 결과.
- `source/results/`에 사용한 위치 목록, RUN_PLAN, 솔버 CONFIG와 BANK_MANIFEST를 보존했다.
- [전송 manifest](evidence/TRANSFER_MANIFEST.json)의 1,953개 파일 SHA를 회수 후 전부 대조했고 불일치가 없었다. 전송 묶음 SHA256: `5d328bdbb1e4886b7266aad93c1463dfd4ca77a48ef09a062bf0e27891379b2d`.

**원시 경로 NPZ 35개는 Git에 올리지 않았다.** Snowball `/home/KMS/OFFICE_SNOWBALL_20261008_819fa93/full35_stride1/`에 보존했다. 파일별 절대 위치·크기·SHA는 [RAW_NPZ_MANIFEST](evidence/RAW_NPZ_MANIFEST.json)에 있다. 원시 경로를 이용하는 검증을 다시 수행하려면 해당 NPZ가 필요하다.

재검증 명령은 고정 환경과 원격 원시 출력에서 다음과 같다.

```bash
/opt/rt-env/bin/python scripts/sweep_verify.py run --scenario office \
  --run-dir /work/full35_stride1 \
  --positions results/OFFICE_RUN_PLAN_20261008/positions_all.txt \
  --bin-stride 1 --expect-n 35
```

배포 초기에 Windows Git archive의 CRLF 때문에 셸 종료127과 위치 이름 검증 종료1이 있었다. 원본 LF를 복원하고 SHA 대조 후 새 시험 폴더에서 통과했다. 초기 실패 출력과 원시 데이터는 원격에 보존했으며 물리 모델이나 검증 기준을 완화하지 않았다. `evidence/REPORT_START.md`는 전체 실행 시작 당시의 기록이다.

이 PASS는 현재 가정한 사무실 형상·재질과 출력 계약에 대한 것이다. 책상은 윗판 한 장이며 서랍·옆판은 없다. 회절·산란은 꺼져 있다. 실제 사무실 측정과의 적합성, 결과 분석 및 NLoS 각도 모델의 적용은 이번 검증에서 확립하지 않았다.
