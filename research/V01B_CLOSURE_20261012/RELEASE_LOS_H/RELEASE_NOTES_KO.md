# V01b-R LoS H 5종 — GitHub Release 패키지

## 상태: **업로드 미완료 (이 세션에서는 Release를 만들 수 없음)**
이 세션의 GitHub 도구는 Release 조회(`list_releases`, `get_release_by_tag`)만 지원하고 생성·에셋 업로드 도구가 없다. 파일을 repo에 커밋하는 방법(`create_or_update_file`)은 “Git 원본/LFS 정책을 바꾸지 않는다”는 지시에 어긋나므로 사용하지 않았다. 아래 절차로 사용자가 올려 주시면, 다운로드 후 재검증을 제가 수행한다.

## 에셋 (총 113.7 MB, 5개) — 세션 scratchpad `release_pkg/`에 준비됨
| 파일 | SHA256 | shape |
|---|---|---|
| H_LoS_R2_aB_m45.npy | 7046e0a8dc0eb21950f5d1d2d1876059c6311851d731b2b62e4a7a8317cb9831 | (1303,257,2,2) c128 |
| H_LoS_R4_aA_m45.npy | 86e9a22728b664541a75413a4751264494600a3b654c297f48654c047c8fe516 | (922,257,2,2) c128 |
| H_LoS_R4_aB_m45.npy | 8515d1e0e0383b607c51078f88485e460a780a78de608fe20a706f919fb0fb8f | (922,257,2,2) c128 |
| H_LoS_R5_aA_m45.npy | 848059092382e1a45ddbc2e0b01b0b31259236dee3d82733d7ab96a9e27a7136 | (1883,257,2,2) c128 |
| H_LoS_R5_aB_m45.npy | a4406847a98b5d58a75e1927bc106815d956fa15b062fa6095e08ef008c115a0 | (1883,257,2,2) c128 |

전체 SHA256은 `SHA256SUMS.txt`, 필드(경로, 앵커, mount, rf_poses SHA, 생성 절차)는 `RELEASE_MANIFEST.json`. 행 i = `rf_poses_<route>.json`의 `pose_id` i.

## 업로드 (예시)
```
gh release create v01b-r-los-h-m45-20261012 --repo myoungsunk/sionna-resimulation \
  --title "V01b-R LoS H (legacy mount-45, 5 cases)" --notes-file RELEASE_NOTES_KO.md \
  H_LoS_R2_aB_m45.npy H_LoS_R4_aA_m45.npy H_LoS_R4_aB_m45.npy H_LoS_R5_aA_m45.npy H_LoS_R5_aB_m45.npy SHA256SUMS.txt RELEASE_MANIFEST.json
```
(npy 파일은 scratchpad `release_pkg/`에 있으며 이 세션이 끝나면 사라진다 — 필요하면 같은 파일을 trace 5세트에서 `g5_d.py`의 LoS 블록으로 재생성할 수 있고, 결과는 비트 단위로 동일해야 한다.)

## 다운로드 후 재검증
```
python -I verify_release.py --dir <다운로드 폴더> --poses-dir <rf_poses_R*.json 폴더> \
       [--src <qclean_uwb src> --traces-root <trace 세트 상위 폴더> --rows 40]
```
- 단계 1: SHA256(SHA256SUMS·manifest 일치), bytes, dtype, shape, finite, 행 수 == pose 수, rf_poses SHA, pose_id 연속.
- 단계 2(선택): trace에서 행을 재생성해 에셋과 비교 + 인접 행과 다름을 확인(포즈 순서 오류 검출).

## 사전 리허설 (업로드 전 로컬 복사본으로 수행한 결과)
단계 1·2 모두 5/5 PASS. 단계 2는 40행/파일, 재생성-에셋 상대오차 0.0(비트 동일), 인접 행과의 최소 상대차 2.6e-2 ~ 8.5e-2. **이것은 실제 Release 다운로드 검증이 아니다.** Release 업로드 후 실제 다운로드본으로 다시 수행해야 이 항목이 닫힌다.
