# Mount +45° 검증 결과와 재현 자료

[검증 보고서](CHECKLIST_STATUS_KO.md)에는 B·B0, B·L2와 앵커 A의 결과 및 진입 판정이 있다. 데이터 범위는 R2·R4·R5, seed 10이다. 앵커 A의 R4·R5는 동결 MB_VAR 보정이 확인되지 않아 관측 패킷과 evaluator까지 생성했다.

| 자료 | 위치 |
|---|---|
| 0°·+45° DR 및 E0–E5 비교 | [MOUNT_0_VS_45_S2.csv](MOUNT_0_VS_45_S2.csv) |
| 0°·+45° SC·KI 비교 | [MOUNT_0_VS_45_STRUCTURE.csv](MOUNT_0_VS_45_STRUCTURE.csv) |
| 0°·+45° B·L2 비교 | [MOUNT_0_VS_45_L2.csv](MOUNT_0_VS_45_L2.csv) |
| 관측식과 TEACH/REPEAT | [관측식 계약](OBSERVER_CONTRACT.json) · [학습 계약](training/RUN_CONTRACT.json) · [G-T1 학습 RF 출처](guarded_gt1/RETRIEVAL.json) |
| 동결 계약과 실행 명령 | [DR·E0–E5](comparison/RUN_CONTRACT.json) · [D0–D3·M3](diagnostics/RUN_CONTRACT.json) · [SC·KI](structure/RUN_CONTRACT.json) · [D4](d4/RUN_CONTRACT.json) |
| 후속 진단 계약 | [V1–V9·D6](ks/RUN_CONTRACT.json) · [C1–C6](followup/RUN_CONTRACT.json) · [C7](c7/RUN_CONTRACT.json) · [C8](c8/RUN_CONTRACT.json) · [R2/R5 실패 대조](r2_r5/RUN_CONTRACT.json) |
| B·L2 및 앵커 A | [L2 계약](l2/RUN_CONTRACT.json) · [L2 패킷](l2/packets/) · [A 계약](anchor_a_final/RUN_CONTRACT.json) · [A 패킷과 trace](anchor_a_final/execution/) |
| 파일 출처와 해시 | [이전 입력 대응표](FROZEN_INPUTS_INDEX.json) · [게시 파일 SHA-256](PUBLICATION_MANIFEST.json) |
| +45° B·B0 원본 | [기존 online/evaluator·E0 parity](../MOUNT45_B0_20261116/) |

## 검증과 재생

Git LFS로 `.npz`, `.npy`, `.gz` 데이터를 내려받은 뒤 이 폴더에서 Python 3.11 이상으로 파일을 확인한다.

```powershell
git lfs pull --include="research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/**"
python -B verify_publication.py
```

[verify_publication.py](verify_publication.py)는 이 폴더의 파일 SHA-256, 보고서 링크, 성공한 실행 16개의 출력 해시와 앵커 A의 중단 기록을 확인한다. 실행 코드와 기존 수치 재현 코드는 이 폴더 및 아래 하위 폴더에 있다. 동결 시점 작업 경로는 계약과 실행 기록에 그대로 남아 있다. 원래 배치를 복원할 때 [이전 입력 대응표](FROZEN_INPUTS_INDEX.json)의 `workspace_relative`와 `path`를 대조한다. `repository` 경로는 저장소 루트 기준이며, `bundled` 경로는 이 폴더 기준이다. 재생은 동결 계약과 각 실행 기록의 명령 및 Python 환경을 따른다.

게시 파일 검증은 실행 기록과 데이터 무결성 확인이다. C8 수치 재생은 동일 호스트에서 수행했다.
