# TARGETS 재현성 대조 자료 (F5)

- `TARGETS.jsonl.gz`: 정본 `00_inputs_R3/TARGETS.jsonl`을 결정론적 gzip(mtime 0)으로 압축한 파일. 압축을 풀면 SHA256이 `10fc60b3ea49a1995f0ef94fc7c44aefd44219dfebeaa93fe4ee5d62976146e6`(00_inputs_R3/CONFIG.json의 `targets_sha256`)이다. LFS 업로드가 이 세션에서 거부되어 일반 git 객체로 저장했다.
- `TARGETS_FIELD_DIGESTS.json`: 파일 전체 SHA, 그리고 필드별 digest(165,009행 전체에 대한 필드 값의 canonical JSON)이다. `pose.value`는 POSES.json의 회전행렬 값이다.

재생성 환경에서 수행할 작업:

```powershell
py -3.10 scripts/g2_completion/targets_fingerprint.py <재생성>/TARGETS.jsonl --poses <재생성>/POSES.json --out FP_WIN.json
# FP_WIN.json의 field_sha256을 TARGETS_FIELD_DIGESTS.json과 비교해 어느 필드가 다른지 확인한다
py -3.10 -c "import gzip,shutil;shutil.copyfileobj(gzip.open('TARGETS.jsonl.gz'),open('TARGETS_CANON.jsonl','wb'))"
py -3.10 scripts/g2_completion/targets_fingerprint.py TARGETS_CANON.jsonl --compare <재생성>/TARGETS.jsonl --out DIFF.json
```

`DIFF.json`의 `fields`는 필드별로 다른 행 수, 차이 종류(float/value/missing), 최대 절대차, 최대 ulp를 기록한다.

- 모든 차이가 수 ulp 수준의 float 표현 차이이고 identity·좌표·frame·판재 필드가 같다면, 원인은 수치 표현이다.
- 그 밖의 차이는 실질적인 입력 변경으로 본다.

두 경우 모두 해시를 임의로 갱신하거나 기준을 완화하지 않고 판단 근거를 기록한다.

이 환경(Linux, Python 3.11, numpy 2.4.6)에서는 이격 계산이 chunk 크기와 관계없이 비트 단위로 동일했고, 자세 계산도 같은 프로세스 안에서 결정론적이었다. 교차 플랫폼 차이는 이 환경에서 재현할 수 없어 원인은 미확정이다.
