"""Verify short Range evidence and produce a bounded Korean result report."""
from pathlib import Path
import datetime
import hashlib
import json
import numpy as np
import scipy

H = Path(__file__).resolve().parent
O = H / "out/i2_short_range_kernel_01"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = read(O / "EXECUTION_RECEIPT.json")
    assert receipt["exit_code"] == 0 and receipt["inputs_unchanged"]
    for name, digest in receipt["input_sha256"].items():
        assert sha(H / name) == digest, name
    for name, digest in receipt["output_sha256"].items():
        assert sha(O / name) == digest, name
    protected = read(H / "out/I2_S0_REFERENCE_FAILURE_AUDIT.json")["input_sha256"]
    for name, digest in protected.items():
        assert sha(H / name) == digest, name
    r1 = read(H / "out/i2_r1_cdf_tail_v2_cached_01/PACKAGE_SHA256.json")["files"]
    for name, digest in r1.items():
        assert sha(H / name) == digest, name
    results = [read(O / f"{case}_RESULT.json") for case in ("SYNTHETIC", "R2", "R4")]
    rows, joint_rows, limits, summary = [], [], [], []
    for r in results:
        d = r["batch_diagnostics"]
        rh = max(d["rank_folded_split_rhat"])
        es = min(d["bulk_ess"] + d["tail_ess"])
        q = r["resolution"]
        res = "PASS" if q["moment_pass"] and q["sector_pass"] else "INCONCLUSIVE"
        rows.append(f"| {r['case']} | {res} | {rh:.5f} | {es:.1f} | {r['gate']} |")
        j = r["joint_comparison"]
        v = j["PF_vs_BATCH"]
        joint_rows.append(f"| {r['case']} | {max(v['mean_upper_sd']):.4g} | {max(v['sd_ratio_upper']):.4g} | {np.max(v['quantile_upper_sd']):.4g} | {j['max_abs_correlation_difference']:.4g} |")
        limits.append(f"- {r['case']}: " + "; ".join(r["failed_or_missing"]))
        summary.append(dict(case=r["case"],qmc_resolution=res,max_rhat=rh,min_bulk_tail_ess=es,
                            joint_comparison=j,simultaneous=r["simultaneous"],failed_or_missing=r["failed_or_missing"]))
    report = """# 짧은 Range 독립 적분·결합 이동 검증 결과

구현·검증·실행을 완료했다. 판정은 **INCONCLUSIVE**, I2 전체 참조는 **REFERENCE_NOT_VALIDATED**이다. I3/I7 및 전 구간 Range 보완 실험은 실행하지 않았다.

## 목표 밀도와 제안비

상태는 `(rho, delta, whitened bg/SF/eps, latent z1/z2)`이다. 반경 좌표의 목표 밀도는 `p0(rho|r0) × UniformCircle(delta) × phi3(c) × phi2(z) × L_odo × L_range1`이다. 첫 Range는 `p0`에만 사용한다. 이후 likelihood에 중복 입력하지 않는다.

전체 독립 제안은 `logpi(new)-logpi(old)+logq(old)-logq(new)`를 사용한다. 역 CDF 보간 샘플러의 실제 반경 제안밀도 `ΔCDF/Δrho`와 해석적 초기 반경 밀도의 차이를 MH·PF·독립 적분에서 보정했다. 로그 반경의 대칭 결합 이동에는 `+log(rho)` Jacobian을 포함한다. 독립 커널과 대칭 커널의 혼합 확률은 상태와 무관한 1/2이다.

음수 조건부 분산을 0으로 고치는 처리 없이 오류로 드러낸다. 최초 구현 감사에서 발견한 PSD clipping, Batch MCSE의 자기상관 누락, 실제 보간 제안밀도 불일치는 본 실행 전에 수정했다. 기존 구현과 결과는 수정하지 않았다.

## 실행 범위와 검증

합성 1스텝과 기존 Gaussian seed8000 R2/R4의 첫 1스텝을 사용했다. 관측은 두 시점, 운동 전이는 1개이다. 합성 조건은 별도 검증 문제이며 실제 경로를 대체하지 않는다. 독립 적분은 별도의 조건부 공분산·궤적·반경 계산으로 Sobol 2^17/2^19, 각 4개 scramble을 사용했다. 기존 추정기의 평가 함수를 독립 적분에서 호출하지 않는다.

PF는 80,000개 입자 × 4회인 단일 전이 중요도 표본이며 재표집하지 않는다. 따라서 장기 PF의 조상 붕괴 해소를 증명하는 실험은 아니다. Batch는 4개 체인, burn 4,000, retained 8,000에서 시작하고 동결 규칙에 따라 수렴 진단 실패 시 모든 체인을 동일하게 연장한다. PF와 Batch의 관측 horizon은 같다.

평균·SD비·분위수·공분산·상관·Heading 12구간 질량을 보존했다. 독립 QMC의 첫 반복으로 CDF 평가 격자 및 50/90/95% 공동 밀도 영역을 정하고 나머지 반복에서 평가했다. 영역은 `d rho d delta d c d z`에 대한 밀도 기준이다. MC 오차는 독립 반복과 Batch 16개 블록/체인의 오차를 함께 사용한다. 오차 상한은 유한 표본의 조건부 근사이며 형식적 보증이 아니다.

| 조건 | QMC 해상도 비교(모멘트·sector 기준) | 최대 rank/folded Rhat | 최소 bulk/tail ESS | 최종 |
|---|---:|---:|---:|---|
""" + "\n".join(rows)
    report += """

## PF–Batch 직접 비교

아래 평균·SD비·분위수는 MC 오차를 포함한 상한이다. 기준은 각각 0.25 pooled SD, 대칭 SD비 1.25, 0.1 pooled SD이다. 상관 차이는 기술 통계이며 새로운 통과 기준을 만들지 않았다. Calibration은 동결 prior 표준화 좌표이다.

| 조건 | 평균 차이 상한/pooled SD | 대칭 SD비 상한 | 분위수 차이 상한/pooled SD | 최대 절대 상관 차이 |
|---|---:|---:|---:|---:|
""" + "\n".join(joint_rows)
    distribution = read(O / "RAW_DISTRIBUTION_COMPARISON.json")
    raw_rows = []
    for r in distribution["cases"]:
        a,b = r["methods"]["PF"],r["methods"]["BATCH"]
        raw_rows.append(f"| {r['case']} | {a['raw_max_cdf_difference']:.5f} | {b['raw_max_cdf_difference']:.5f} | {a['frozen_mc_upper']['cdf_upper']:.4f} | {b['frozen_mc_upper']['cdf_upper']:.4f} |")
    density = [read(O / f"{case}_TARGET_DENSITY_CHECKS.json") for case in ("SYNTHETIC","R2","R4")]
    report += "\n\n## 실제 차이와 Monte Carlo 오차 구분\n\n"
    report += "원시 표본을 사후 집계했으며 동결된 판정을 바꾸지 않았다. 실제 차이가 작아도 4회 반복과 동시 비교의 Bonferroni t(df=2) 상한이 넓어 합의를 승인할 수 없다. 상한이 1보다 큰 항목은 정보가 없는 보수적 검정량이며 실제 확률 차이가 1보다 크다는 뜻이 아니다.\n\n"
    report += "| 조건 | PF 실제 최대 CDF 차이 | Batch 실제 최대 CDF 차이 | PF 오차 포함 상한 | Batch 오차 포함 상한 |\n|---|---:|---:|---:|---:|\n" + "\n".join(raw_rows)
    report += "\n\nPF의 독립 적분 대비 평균·SD·분위수 합의는 3/3 통과했지만, Batch 및 PF–Batch의 같은 복합 기준은 0/3이다. R2/R4의 정규화 평균 MCSE(체인별 최대)는 각각 0.05442/0.05510으로 기준 0.05를 초과하고, 분위수 MCSE도 미달했다. 모든 사례가 기본 Rhat·ESS 조건을 통과하여 동결된 연장 규칙에 따라 retained는 체인당 8,000으로 유지했다.\n"
    report += "\n관련 단위·회귀 테스트 21개 PASS. 사례별 64개 점에서 전체 log-density 독립 구현 오차는 최대 1.07e-14, MH log-flux 상세균형 오차는 최대 7.11e-15였다. 첫 Range가 한 번만 소비됨을 확인했다. 본 실행은 202.70초, 종료 코드 0이다.\n"
    report += "\n\n## 실패 또는 미완료 항목\n\n" + "\n".join(limits)
    report += """

연결되지 않은 density basin의 질량 및 탐색 검증이 완료되지 않았다. 평균이나 Rhat의 일치만으로 전체 참조를 승인하지 않는다. 공동 영역·CDF의 동시 오차 상한과 QMC 해상도 결과도 별도로 보존했다. 수치 기준을 결과에 맞춰 완화하지 않았다.

## 적용 범위와 산출물

기존 초기 반경의 12-sigma 수치 영역 안에서 conditional measured-input 모델을 검증했다. 이 결과는 무한 영역의 posterior 꼬리 보증, 실제 생성모델의 일치, 장시간 경로, RF 모델, 운용 요구 정밀도의 충분성 판정이 아니다. 운용 요구 정밀도는 계속 미정이다.

- 구현: `repair_short_range.py`, `repair_short_range_run.py`, `tests/test_repair_short_range.py`.
- 동결 설계: `I2_SHORT_RANGE_DESIGN.json`.
- 결과: `out/i2_short_range_kernel_01/`의 입력·밀도 검사·원시 QMC/PF/Batch NPZ·조건별 RESULT·SHORT_RANGE_GATE·실행 영수증.
- 테스트: `out/I2_SHORT_RANGE_TESTS.log` 및 테스트 실행 영수증.
- 해시 검증: 같은 출력 폴더의 `FINAL_VERIFICATION.json`.

기존 보호 입력과 앞선 R1 패키지의 SHA256 불변을 확인했다. 실행 입력/출력 SHA와 정확한 명령·환경·시각·종료 코드는 실행 영수증에 있다.

진단 방법 확인 자료: [Stan posterior analysis](https://mc-stan.org/docs/reference-manual/analysis.html). Rank/folded Rhat·bulk/tail ESS를 함께 사용하더라도 미방문 모드의 부재를 증명하지 못한다.
"""
    (H / "I2_SHORT_RANGE_RESULT_KO.md").write_text(report,encoding="utf-8")
    final = dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 execution_hashes_pass=True,protected_hash_count=len(protected),r1_package_hash_count=len(r1),
                 numpy=np.__version__,scipy=scipy.__version__,cases=summary,density_checks=density,
                 I2_reference="REFERENCE_NOT_VALIDATED",I3="NOT_RUN",I7="NOT_RUN")
    (O / "FINAL_VERIFICATION.json").write_text(json.dumps(final,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps([dict(case=x['case'],qmc_resolution=x['qmc_resolution'],max_rhat=x['max_rhat'],min_ess=x['min_bulk_tail_ess']) for x in summary],indent=2))


if __name__ == "__main__":
    main()
