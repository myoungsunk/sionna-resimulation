# 사용자 승인 B안 재시작

2026-10-07 사용자 지시에 따라 G3 허용치를 이번 재시작에 한해 2e-13 s로 변경하고 B안을 실행했다. 원래 5e-14 s의 lateral 0 strict FAIL(미매칭 6개)과 모든 기존 결과는 보존했다. 두 lateral은 기존 relaxed 기준에서 통과한다. 물리적 경로 유일성·동등성 또는 실패 원인이 반올림뿐이라는 주장은 확립하지 않았다.

기존 A 컨테이너를 중단하고 부분 결과를 보존했다. 저장된 trace를 사용해 원래 rf_b_apply.py를 실행했으며, 네 lateral×mount H 저장소 각각 1223 poses, 874 positions, missing=0, unusable=0, complete=true를 확인했다. H shape 및 유한값 검증도 통과했다. 새로운 RF trace 계산은 하지 않았다.

09:47 UTC에 lut_mismatch와 SNR calibration을 마치고 S6_experiments RUNNING을 확인했다. S6 조건은 --snr-db 30 10 --mismatch-sigma 0.18 --pos-process-std 0.01 --seeds 50 --nproc 4이다. 분석은 자동으로 이어 실행한다. S6 최종 결과/분석: MISSING (실행 중).

L1/L2 FAIL과 해당 임계값은 변경하지 않았다. S6는 진단 결과이며 production/scientific PASS가 아니다.

B_RESTART_AUTHORIZED_01a115bd.zip 및 JSON/manifest/실행 wrapper는 승인·재시작 근거다. raw H와 NPZ는 제외했다. 최초 컨테이너는 Python entrypoint 누락으로 시작되지 않았고, explicit Python entrypoint를 적용한 pipelineB2가 정상 실행된다.

ZIP SHA256: b27c32de95e3672c2544c690927b8094c2b9a901cc46c1cea90f91a86c9067d9
