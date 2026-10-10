# DRIVE_SIM S0 보고 (base 정리, 환경 재현, 사전 등록, 시간 실측)

상태: **S0_DONE_WITH_FINDINGS**. S1 이후는 시작하지 않았다.

## 1. 결과 요약

| 항목 | 결과 |
|---|---|
| Base | `git merge c13797a` 완료(병합 커밋 `84094a4`, force push 없음) |
| 환경 | sionna-rt 2.0.1 / mitsuba 3.8.0 / drjit 1.3.1, `llvm_ad_mono_polarized`. 이 세션의 venv에서 재현(Snowball/KMS 불필요) |
| Bank | LFS로 `LP_plus45`, `LP_minus45` 실파일 확보. receipt SHA256이 `BANK_MANIFEST.json`과 일치(둘 다 True) |
| LoS check | 48/48 통과, 최대 상대 오차 **6.066984088847065e-07** — 브랜치 기록과 완전히 동일 |
| 기존 tests | corridor 관련 28개 통과 + 신규 9개 통과 |
| G1 (A안 재현성) | **threads=1: 저장 H와 비트 동일(오차 0.0)**. threads=4: 3.2e-6 → 원 임계값 1e-6 미달. `PREREG_AMENDMENTS.md` A1 |
| G3 `classify_paths` tol | float32 `tau`, 63경로 일정, 미매칭 0. 최대 잔차 x=7 1.9e-14 s, 코너 4곳(x=1/19, y=±0.7)에서 ≤2.2e-14 s → tol 5e-14 s는 2.3배 여유 |
| FP 규칙 영향 (44 position × 19 yaw, TX +45) | FP index가 바뀌는 비율 **10.9%**, \|Δs\|>1e-3인 pose **89/836**, 최대 \|Δs\| 0.176, 중앙값 0 (TX −45: 11.5%, 95/836, 최대 0.353) |
| 시간 실측 (이 머신, idle) | 단일 thread **0.142 s/call**(36.4 s/pose), 4 thread 0.103 s/call(1.4배만 빠름), 단일 thread 4개 병렬 각 ≈0.18 s/call → 처리량 **약 11.7 s/pose**. receipt의 0.2709 s/call은 다른 하드웨어/부하 조건으로 보이며 재현되지 않았다 |
| 사전 등록 | `PREREG.json`을 비교 결과를 보기 전에 커밋(`02009ca`) |
| Lever arm | 0으로 고정(PREREG), 값과 근거 기록 |

## 2. 비용표 갱신 (A안, 이 머신 기준)

pose당 ≈46 s core-time(4개 병렬 시). 궤적 1개 ≈1,070 pose → **≈13.8 core-h(wall ≈3.5 h, 4 core)**.
lateral 2 × 장착 offset 2 = 4 조합 → A안 전체 **≈55 core-h(wall ≈13.9 h)**. 이전 표(69.6 s/pose 기준 41 core-h/offset)는 receipt 시간 기준이었다. B안 수치는 여전히 미검증 추정.

## 3. 판단이 필요한 발견

1. **FP 규칙 변경은 무시할 수 없다.** 10.9%의 pose에서 FP index가 달라지고 89개에서 \|Δs\|>1e-3(사전 등록 `abs_ds_max`)이다. 새 규칙으로 만든 `s`를 기존 4-branch 결과와 섞어 비교하면 안 된다. parity와 LUT는 모두 새 규칙 기준으로 재계산한다(이미 계획).
2. **장착 offset 직관과 이상 곡선의 방향이 반대이다.** 이상적 `s=−cos 2(heading+mount)`에서 직진(heading 0°/180°)이고 mount 0°이면 안테나 yaw 0°라 `s=∓1`, 기울기 0이다. heading 5° 오차의 \|Δs\|=1−cos10°≈0.015로, 모델 불일치 σ_s≈0.09보다 훨씬 작아 passive로는 거의 안 보인다. mount 45°이면 \|Δs\|≈sin10°≈0.17로 약 11배 크다. 반대로 heading 45°로 달리면 mount 0°가 steep 쪽이다. 즉 s는 (heading+mount) mod 180°만 보므로 "직진은 0°가 유리"는 이상 곡선 예측과 반대다. 사용자 직관은 `PREREG.json`에 `H3_alt`로 기록했고, 양측 검정으로 가른다. 복도는 heading 0°/180°뿐이라 "45° 선을 따라 주행" 절반은 이 복도에서 검증할 수 없다(복도 폭 2.4 m).
3. 사용자 직관이 맞을 물리적 이유(예: mount 0°에서 한 포트 전력이 작아져 SNR이 오히려 유리하거나 다중경로 왜곡이 다름)가 있다면 SNR sweep에서 드러난다.

## 4. 변경/이동/미변경 (AGENTS.md Done)

- Files changed(추가): `scripts/drive_sim_s0_prereg.py`, `scripts/drive_sim_s0_reference_check.py`, `src/qclean_uwb/drivesim/{__init__,config}.py`, `src/qclean_uwb/features/fp_power.py`(함수 추가, 기존 함수 유지), `tests/test_drivesim_config.py`, `tests/test_fp_single_tx.py`, `results/DRIVE_SIM_20261007/**`.
- Files moved: 없음.
- Untouched: `corridor_sionna_run.py` 포함 base의 모든 기존 파일, 기존 results, `data/raw/`, `results/frozen/`, `reports/release/`.
- Checks run: pytest(위), `--los-check`, bank SHA, G1 비교, G3 tol, FP 영향 분석. AGENTS.md의 `scripts/00_inventory.py` 등 검증 스크립트는 이 repo에 존재하지 않아 실행하지 않았다.
- Generated artifacts: `PREREG.json`, `PREREG_AMENDMENTS.md`, `REFERENCE_CHECK.json`, `G3_TOL_CHECK.json`, `los_check/`, `pilot_t1/`, `pilot_t4/`, `timing/`, `thr1/`, `thr4/`, `g3_extremes/`. `thr*`, `pilot_t4`는 다른 작업과 겹쳐 시간 값이 오염됐으므로 시간 판단에는 `timing/`만 쓴다.
- 커밋하지 않은 파일: 경로 단위 `*_sweep.npz`(LFS 추적 대상, 이 환경에서 LFS 업로드 불가로 push가 거부됨). `.gitignore`에 추가했고 로컬에는 남아 있다. 재생성: `scripts/corridor_sionna_run.py`(receipt의 command 참조). G3 tol 수치는 `G3_TOL_CHECK.json`에 남겼다.
- Remaining risks: (a) B안은 아직 어떤 gate도 시도하지 않았다. (b) G1 임계값은 threads=1에서만 충족. (c) 이 머신과 receipt 시간이 2배 다른 이유는 확인하지 못했다(하드웨어 추정). (d) 새 FP 규칙 기반 parity 결과는 S2에서 처음 나온다.
- Next: S1 (truth 궤적 생성기) 승인 후 시작.
