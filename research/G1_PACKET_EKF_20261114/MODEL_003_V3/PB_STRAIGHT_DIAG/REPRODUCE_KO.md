# P-B 직진 진단 재현

**DIAGNOSTIC_ONLY · S2′ STOP (FULL_6) · Step 3 보류**

Git LFS가 설치된 체크아웃에서 이 폴더로 이동한다. 파일의 원본 바이트는 SHA-256 검증을 위해 유지한다. 표와 그림을 다시 생성할 때는 이 폴더의 복사본에서 아래 명령을 실행한다. 집계에는 NumPy, 그림에는 Matplotlib이 필요하다.

```bash
sha256sum -c SHA256SUMS
python -X utf8 summarize_pb.py .
python -X utf8 plot_pb.py .
```

집계는 동결 체크포인트 63개와 패킷 재생 12개의 파일을 검증한다. 패킷 재생은 동결 G-T1 입력, 관측 모델, 패턴 뱅크, Docker 이미지와 기존 S3 체크포인트를 읽었다. 같은 Snowball 환경에서 재생하려면 기존 실행 산출물이 없는 새 폴더에 `launch_pb.sh`, `pb_trace.py`, `PLAN.md`를 복사한 뒤 `bash launch_pb.sh`를 실행한다. 실제 실행 인자는 [COMMAND.txt](COMMAND.txt)와 [container_input.sh](container_input.sh), 입력 해시와 봉인 검사는 [INPUT_CHECK.log](INPUT_CHECK.log), [SEAL_BEFORE.log](SEAL_BEFORE.log), [SEAL_AFTER.log](SEAL_AFTER.log)에 있다.

[보고서](REPORT_KO.md) · [재생 로그](execution.log) · [파일 해시](SHA256SUMS)
