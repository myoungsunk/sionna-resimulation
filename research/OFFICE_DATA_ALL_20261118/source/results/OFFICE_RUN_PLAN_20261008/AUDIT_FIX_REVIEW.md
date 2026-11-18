# R1–R3 수정 및 전체 코드 재감사 — 2026-10-08

판정: **기존 네 지적과 재감사 R1–R3의 코드 차단 사항 해소. 오프라인 범위 조건부 수용. 전체 테스트 PASS 또는 Snowball RF PASS는 아님.**

기준 커밋은 `808ea6f64455dc9adb8a166e9d41bf5099fc625a`이다. 별도 로컬 복제 `D:/SLAM_bot/OFFICE_FIX_REAUDIT_20261008`의 미커밋 변경을 검토했다. 기존 감사본과 연구 결과는 보존했다. 동일 작업자가 수정 후 재검토했으며 별도 독립 심사자가 수행한 감사로 표현하지 않는다.

## 수정

| 지적 | 변경 및 재검증 |
|---|---|
| R1 경로 무결성 | counts/offsets 정수·비음수·시작 0·단조·bin-major 계약, 계수/지연/interaction/object 배열 차원과 형식, 계수·지연 유한값과 지연 비음수 검사. 모든 호출의 경로 합으로 H를 재구성한다. H.npy와 NPZ H는 같은 저장값이므로 정확한 일치를 요구한다. |
| R2 slab_check | 명시적 부속 폴더 목록에 slab_check를 추가했다. geom_check와 함께 존재하는 출력 배치에서 실제 실행 스크립트가 완료와 재개 모두 exit 0을 반환했다. 예상 밖 위치 폴더는 여전히 거절한다. |
| R3 포트·좌표 | LP_plus45/LP_minus45 순서, H_layout의 RX/TX 축 및 offsets 순서, setup.robot_position(x,y)의 수신 3D 좌표를 검사한다. 복도 감사에도 같은 좌표 계약을 연결했다. |

경로 재구성 허용오차는 포트별 `sum(abs(a)) * (2*eps32 + 8*max(1,N)*eps_sum)`이다. 첫 항은 저장 complex64 계수 양자화, 둘째는 합산 반올림을 고려한다. 고정 절대 허용오차를 쓰지 않아 작은 채널의 상대적으로 큰 손상을 숨기지 않는다. 지연 dtype과 위상 계산식은 생산 러너와 동일하게 유지한다. 정상 fixture는 비영 지연·주파수별 위상과 실제 경로 합으로 H를 생성하며, 양자화 전 H와 양자화 후 계수의 허용 범위를 검사한다.

## 기존 네 지적의 재점검

- **이중 슬랩:** OfficeSetup의 RF objects는 물리 슬랩당 판 한 장이다. boxes는 충돌/시각화용이며 RF LoS도 판과의 선분 교차를 쓴다. 해당 형상·PLY·슬랩 해석식 회귀가 통과했다. 실제 Sionna 슬랩 재실행은 하지 않았다.
- **불완전 출력:** 이전 A/B 재현, 새 R1/R3 손상 사례, stride 불일치, LoS 불일치, 누락·중복·초과 위치를 차단한다. complex64 저장, float32 지연, 명시적으로 허용된 옛 복도 objects_cat 누락은 회귀 검사로 구분한다.
- **receipt-only 재개:** 두 불완전 폴더를 보존하고 다시 실행을 시도한다. 실패 runner에서 exit 1, 완료 표식 없음. 합성 정상 출력은 실제 shell에서 재검증 후 건너뛴다.
- **종료코드:** 실패 1, 다른 요청 2, 정상 완료·재개 0을 실제 shell로 확인했다. deadline 미완료 분기의 코드를 검토했으나 이번에 그 분기를 실행하지 않았다.

## 실행 증거와 전체 테스트의 한계

- 최종 `pytest -q tests -k 'not run_script' -p no:cacheprovider`: **104 passed, 3 failed, 1 skipped, 3 deselected**.
- 실패 세 건은 `test_g2_scoped_channel.py`가 참조하는 `results/SIONNA_G2_P1_SIMPLE_CONTRACT_20260924_01a0d1b0/POWER_NOISE_CONTRACT.json`이 저장소에 없어서 발생했다. 수정하지 않은 원본 808ea6f에서도 동일한 세 건이 실패하고 나머지 한 건은 통과했다. 누락된 연구 계약은 추정해 만들지 않았다.
- skip 한 건은 Sionna 설치를 요구한다. 제외한 shell 테스트 세 건은 실제 bank 대신 주파수만 든 고립된 합성 bank와 false runner로 독립 재현했다. 추가로 정상 완료·재개를 같은 shell에서 검증했다. 합성 출력에는 실제 안테나/RF 증거가 없다.
- 증거 폴더: `D:/SLAM_bot/artifacts/OFFICE_FIX_REAUDIT_20261008/`. `TEST_RESULTS.json`, `full.log`, `baseline_missing_contract.log`, `SHELL_PROBES.json`, `COMPLETION_PROBES.json`, `FIX_MANIFEST.json`, `FIX.patch`를 참조한다.
- 기존 복도 원시 출력 102곳과 저장 H의 비트 일치, 사무실 35곳 Sionna LoS, 6곳 RF pilot은 이번에 재현하지 않았다. RF 호출 0회. 책상 윗판 가정과 재질/회절 조건은 변경하지 않았다.

## 변경 범위와 다음 단계

변경 소스는 `src/qclean_uwb/runcheck.py`, `scripts/sweep_verify.py`, `scripts/corridor_audit.py`, `tests/test_runcheck.py`이다. 이 대응 보고서를 추가했다. 파일 이동·삭제, 원본 수정, 커밋·푸시, 원격 실행은 하지 않았다.

수정된 코드에 한해서 R1–R3 차단 사항은 해소됐다. 전체 저장소 테스트 통과가 필요한 게이트에는 누락 계약 파일 복구와 재검사가 남는다. Snowball 검증에는 이 수정본의 정확한 소스 식별 및 전달, 실제 bank와 고정 Sionna 환경 확인 후 README의 슬랩 → LoS → pilot 순서가 필요하다. 기존 GitHub 808ea6f에는 이번 수정이 아직 반영되지 않았다.
