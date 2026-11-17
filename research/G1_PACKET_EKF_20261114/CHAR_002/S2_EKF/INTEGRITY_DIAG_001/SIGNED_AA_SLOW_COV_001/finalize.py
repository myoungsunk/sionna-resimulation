"""P5 reproducible aggregation. Never rewrite frozen P0/P1/P2/P3/P4 evidence."""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from scipy.stats import skew, kurtosis
import covariance_core_v2 as C
from p0_inputs_v2 import sha, put


def load(path): return json.loads(path.read_bytes())
def interval(v): return f"{v['mean']:+.6f} [{v['ci95'][0]:+.6f}, {v['ci95'][1]:+.6f}]"


def run(attempt):
    out = attempt/"p5"
    out.mkdir(exist_ok=False)
    specs = load(attempt/"p1_revision_02/SPLITS.json")
    support = load(attempt/"p1_revision_02/SUPPORT_FINAL.json")
    scores = load(attempt/"p3/HOLDOUT_SCORES.json")
    fits = load(attempt/"p3/FITS.json")
    contrasts = load(attempt/"p3/SIGN_CONTRAST.json")
    nulls = load(attempt/"p3/NULL_CONTROLS.json")
    supplemental = load(attempt/"supplemental/N4_PAIR_CONTROLS.json")
    ext = load(attempt/"p4/EXTERNAL_SCORES.json")
    ext_support = load(attempt/"p4/SUPPORT_EXTERNAL.json")
    assert load(attempt/"p3/P3_STATUS.json")["status"] == "EXECUTION_COMPLETE"
    checks = []
    for directory in [attempt, attempt/"p1", attempt/"p1_revision_02", attempt/"p3", attempt/"supplemental", attempt/"p4"]:
        for line in (directory/"SHA256SUMS").read_text().splitlines():
            expected, filename = line.split("  ", 1)
            assert sha(directory/filename) == expected, "FROZEN_OUTPUT_HASH_MISMATCH:"+filename
        checks.append(dict(check="frozen stage manifest", path=str(directory), passed=True))
    normalized, table, sign_rows, descriptive = {}, [], [], {}
    for route in ["R2", "R4", "R5"]:
        if not specs[route]["eligible_rho_bins"]:
            normalized[route] = dict(status="NO_SUPPORTED_FOLD", packets=0, independent_clusters=0,
                original_p3_serialization_note="R5 skipped fit; dictionary was not flushed after continue; original preserved; explicit n0 here")
            table.append(dict(route=route, status="NO_SUPPORTED_FOLD", packets=0, clusters=0))
            continue
        rows = scores[route]["component_scores"]
        got = C.cluster_ci(rows, specs[route]["bootstrap_revisit_groups"]["10"])
        expected = scores[route]["primary_and_block_sensitivity"]["10"]
        assert got == expected, "PAIRED_BOOTSTRAP_REAGGREGATION_MISMATCH"
        status = "SIGNED_ASSOCIATION_SUPPORTED" if (expected["delta10"]["ci95"][0] > 0 and expected["delta12"]["ci95"][0] > 0
            and contrasts[route]["raw"]["ci95"][0] > 0 and contrasts[route]["predicted_signed_contrast"] > 0
            and nulls[route]["status"] == "COMPUTED") else "INCONCLUSIVE"
        normalized[route] = dict(status=status, rho_m=[6, 10], packets=got["packets"], independent_clusters=got["groups"],
                                 scores=got, signed_contrast=contrasts[route], null_control_status=nulls[route]["status"],
                                 theta_rad2=fits[route]["models"]["S1"]["parameters"][1],
                                 equivalent_sigma_deg=float(np.degrees(np.sqrt(fits[route]["models"]["S1"]["parameters"][1]))))
        table.append(dict(route=route, status=status, packets=got["packets"], clusters=got["groups"],
                          S0=got["mean_scores"]["S0"], S1=got["mean_scores"]["S1"], S2=got["mean_scores"]["S2"],
                          delta10=got["delta10"]["mean"], delta10_lo=got["delta10"]["ci95"][0], delta10_hi=got["delta10"]["ci95"][1],
                          delta12=got["delta12"]["mean"], delta12_lo=got["delta12"]["ci95"][0], delta12_hi=got["delta12"]["ci95"][1]))
        for name in ["raw", "winsor_p99"]:
            v = contrasts[route][name]
            sign_rows.append(dict(route=route, kind=name, pairs=contrasts[route]["pairs"],
                expected=contrasts[route]["predicted_signed_contrast"], observed=v["difference"],
                lo=v["ci95"][0], hi=v["ci95"][1], valid_bootstrap=v["valid_bootstrap"], active_groups=v["active_groups"]))
        checks.append(dict(check="paired bootstrap exact reaggregation", route=route, passed=True))
    for route in ["R2", "R4", "R5"]:
        with np.load(attempt/f"P0_{route}.npz") as a:
            e = a["e_rf"]
            descriptive[route] = dict(n=len(e), mean=float(e.mean()), rms=float(np.sqrt(np.mean(e*e))),
                skew=float(skew(e)), excess_kurtosis=float(kurtosis(e)),
                abs_p99=float(np.quantile(abs(e), .99)), definition="noise-free physical RF, no evaluator/MB correction")
    columns = ["route", "status", "packets", "clusters", "S0", "S1", "S2", "delta10", "delta10_lo", "delta10_hi", "delta12", "delta12_lo", "delta12_hi"]
    with (out/"HOLDOUT_COMPARISON.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns); w.writeheader(); w.writerows(table)
    with (out/"SIGN_CONTRAST.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sign_rows[0])); w.writeheader(); w.writerows(sign_rows)
    put(out/"PRIMARY_SUMMARY.json", normalized); put(out/"RAW_RESIDUAL_DESCRIPTIVE.json", descriptive)
    # Explicit absence of a time field is checked in retrieved unsealed metadata.
    gt = Path("D:/SLAM_bot/artifacts/G1_SIGNED_AA_COV_20261117_GT1B")
    sample = load(gt/"SAMPLES.json"); man = load(gt/"MANIFEST.json")
    time_keys = sorted({k for row in sample for k in row if any(x in k.lower() for x in ["time", "stamp", "t_s"])})
    put(out/"GT1_TIME_SUPPORT_CHECK.json", dict(sample_time_keys=time_keys, manifest_time_keys=[k for k in man if "time" in k.lower()],
        sample_sha256=sha(gt/"SAMPLES.json"), manifest_sha256=sha(gt/"MANIFEST.json"),
        status="NO_VERIFIED_PHYSICAL_TIME_GRID", sequence_index_is_not_elapsed_seconds=True))
    assert not time_keys
    decision = dict(question_id="G1-INT-SIGNED-COV-001", scientific_verdict="INCONCLUSIVE",
        signed_association_supported_routes=[], route_status={r: normalized[r]["status"] for r in normalized},
        execution="P0-P4 completed with support-gated exclusions; P5 self-checks completed; see independent AUDIT_KO.md",
        adoption="NOT_ASSESSED; M7 unchanged", primary_scope="BLOCK_C B mount0, common supported rho6-10m only",
        reasons=["R2/R4 delta12 10s CI includes zero", "R2 signed contrast significantly opposite expected direction",
                 "R5 no supported LORO fold", "N2/N3 and temporal holdout not testable under frozen support rules"],
        allowed_claim="R4 common far-range support shows covariance extension predicts better than s-only; signed necessity unestablished",
        prohibited_claims=["physical yaw bias proved", "universal signed multipath structure", "M6 sigma2deg physically validated"],
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat())
    put(out/"DECISION.json", decision); put(out/"CHECKS.json", dict(passed=True, type="IMPLEMENTER_SELF_CHECK_NOT_INDEPENDENT_AUDIT", checks=checks))
    report = ["# Signed a_i a_j 느린 공분산 검증 결과", "",
        "**과학 판정: INCONCLUSIVE.** 이번 자료에서 signed heading 등가 공분산의 필요성을 입증하지 못했다. 실행·감사 상태와 모형 지지는 분리한다. 독립 감사 결과는 [AUDIT_KO.md](AUDIT_KO.md)에 기록한다.", "",
        "기준 계획은 `bd28eac6a0e235412bdced9f08505148191e39d2`. 기존 M7·G-T2/G-V 봉인·S2′ STOP·Step3 HOLD는 유지했다. RF 생성, EKF 재생, M7 모수 수정·채택은 하지 않았다.", "",
        "## 주 분석", "",
        "원시 noise-free Full O30−LoS O30와 실제 RF 생성 pose에서 구한 signed ∂s/∂ψ [s/rad]를 사용했다. donor 평균·모수만 학습했고 holdout 평균은 주 점수에 사용하지 않았다. S0=qK, S1=qK+θ diag(a)Kdiag(a), S2=qK+u diag(|a|)Kdiag(|a|). 점수는 높을수록 좋으며 nats/packet이다.", "",
        "10 s cluster 안의 앞/뒤 5 s×원본 시간 인덱스 짝/홀로 component를 고정했다. 모든 적격 packet은 정확히 한 번 쓰고 off-diagonal lag는 0.4–5 s 안이다. 2,000회 짝 bootstrap(seed20261116), 주 구간은 10 s이며 5/20 s는 보조다.", "",
        "| 궤적 | 공통 거리 | packet / cluster | S0 | S1 signed | S2 unsigned | Δ10 [95% CI] | Δ12 [95% CI] | 판정 |",
        "|---|---|---:|---:|---:|---:|---|---|---|"]
    for route in ["R2", "R4", "R5"]:
        d = normalized[route]
        if d["packets"]:
            v = d["scores"]; ms=v["mean_scores"]
            report.append(f"| {route} | 6–10 m | {d['packets']} / {d['independent_clusters']} | {ms['S0']:.6f} | {ms['S1']:.6f} | {ms['S2']:.6f} | {interval(v['delta10'])} | {interval(v['delta12'])} | INCONCLUSIVE |")
        else: report.append(f"| {route} | 없음 | 0 / 0 | — | — | — | — | — | NO_SUPPORTED_FOLD |")
    report += ["", "R4의 S0 대비 개선은 확인되지만 signed 대 unsigned 차이는 확인되지 않았다. R4 전체·근거리 또는 R5의 signed 구조로 일반화하지 않는다. pooled로 합쳐 지지 부족을 가리지 않는다.", "",
        "## Signed contrast와 반증 대조", "", "매칭한 양수 a_i a_j 쌍의 e_i e_j 평균에서 음수 쌍 평균을 뺀 값이다. 주 잔차는 donor 평균만 뺀다.", "",
        "| 궤적 | S1 예상 contrast | 실제 raw contrast [95% CI] | 유효 bootstrap / 시도 |",
        "|---|---:|---|---:|"]
    for r in ["R2", "R4"]:
        cc=contrasts[r]; v=cc["raw"]
        report.append(f"| {r} | {cc['predicted_signed_contrast']:+.6f} | {v['difference']:+.6f} [{v['ci95'][0]:+.6f}, {v['ci95'][1]:+.6f}] | {v['valid_bootstrap']} / 2000 |")
    report += ["", "R2는 예상과 반대 방향이며 donor p99 winsor에서도 유지된다. R4는 contrast CI가 0을 포함한다. 부호가 한쪽만 들어온 bootstrap draw는 contrast를 정의할 수 없어 무효로 기록했다. 유효 sign cluster는 R2 4개, R4 5개다.", "",
        "N2/N3는 양쪽 모두 `NO_PERMUTABLE_BLOCK_SUPPORT`, 시간 holdout도 세 궤적 모두 `NO_SUPPORTED_TEMPORAL_FOLD`다. 해당 검사가 통과했다고 표현하지 않는다. 보수적 층화·guard에서 지지가 사라진 결과이며 검사 규칙을 사후 완화하지 않았다.", "",
        "## 입력·수치·모수", "",
        "P0 관측 O30 독립 재계산 차이 0, tap 일치. SourceFFD–raw LoS 최대 s 차이는 R2 1.048e−5, R4 2.362e−6, R5 5.140e−6으로 사전 max1e−4 이내였다. 안정 구간의 ±0.1°/±0.01° 차분도 최대 정규화 오차 2.09e−5/2.10e−7로 문턱 이내다. 불연속점은 기록하며 공분산 자료에서 자동 제외하지 않았다.", "",
        "정확히 중복된 arc/yaw만 S0 예비 적합에서 축약한다. 중복 잔차가 다르거나 비중복 unique kernel이 near-singular면 중단한다. ε=1e−8 max(q0,1e−6)는 donor S0로 한 번 정하고 모든 모형에 공통 사용했다.", "",
        "| holdout | q (s²) | θ (rad²) | √θ (degree) | ε | θ=0 경계 |",
        "|---|---:|---:|---:|---:|---|"]
    for r in ["R2", "R4"]:
        ff=fits[r]; q,theta=ff["models"]["S1"]["parameters"]
        report.append(f"| {r} | {q:.7g} | {theta:.7g} | {np.degrees(np.sqrt(theta)):.3f} | {ff['epsilon']:.5g} | {ff['models']['S1']['theta_boundary']} |")
    report += ["", "이 raw RF 공분산 모수는 M6의 느린 성분 기반 σθ≈2°와 정의·적합 대상이 다르다. 수치가 물리 yaw bias의 표준편차임을 뜻하지 않는다. 모수 수는 S0/S3 1개, S1/S2 2개이며 in-sample 이득은 증거로 사용하지 않았다. Gaussian 가정·꼬리 통계는 RAW_RESIDUAL_DESCRIPTIVE.json, condition/Cholesky는 p3/HOLDOUT_SCORES.json에 남겼다.", "",
        "## 평활의 인공 상관·민감도", "", "동일 D3 알고리즘에 독립 백색 잡음을 통과시킨 200회 대조다. 수치는 평균 pair product/주변분산이며 Monte Carlo 구간을 RF 일반화 CI로 해석하지 않는다.", "",
        "| 궤적 | 원시 백색 | 겹치는 평활 창 | 비중첩 창 | 독립 백색 stream 교차 |", "|---|---:|---:|---:|---:|"]
    for r in ["R2", "R4", "R5"]:
        vv=supplemental[r]["statistics"]
        report.append(f"| {r} | {vv['raw_white']['mean']:.4f} | {vv['smoothed_overlap']['mean']:.4f} | {vv['smoothed_nonoverlap']['mean']:.4f} | {vv['cross_independent_white_stream']['mean']:.4f} |")
    report += ["", "따라서 D3 평활 잔차만으로 물리 상관을 입증할 수 없다. 주 분석은 평활하지 않은 원시 RF 잔차를 사용했다. D3 원본 slow/eps는 별도 정의로 비교하고 합치지 않았다. 고정 E0 gate 교집합·D3 지원 교집합·전체 g 민감도는 supplemental/FIXED_FIT_SENSITIVITIES.json, 고정 kernel 4조합·donor별 중심화·oracle holdout 중심화·winsor는 p3/SENSITIVITY.json에 전부 보고했다. 어느 결과도 주 모형 선택에 쓰지 않았다.", "",
        "## 별도 앵커·TEACH/REPEAT 지지", "",
        "앵커 A는 원본 Full/LoS·SourceFFD·미분을 다시 확인하고 B donor 모수를 동결 적용했다. A·R2/R5는 지원 부족이다. A·R4 176 packet/4 cluster에서 Δ10=+0.911546 [−0.037869,+1.860961], Δ12=−0.003090 [−0.006986,−0.001168]로 unsigned가 더 좋았다. 보조 이전 진단이며 B의 주 판정과 합치지 않는다.", "",
        "비봉인 G-T1_B 원본만 KMS 계정으로 읽어 확보하고 manifest SHA를 확인했다. 7,872개 원본 RF pose와 8,888개 protocol label row를 구분했다. TEACH/REPEAT·회전에서 양/음 감도는 존재하지만 elapsed-time 필드가 없어 0.4–5 s 쌍이나 독립 10 s cluster를 만들지 않았다. sequence_index를 초로 바꾸지 않았으며 기하 지원표만 게시했다. G-T2/G-V는 열지 않았다.", "",
        "## 수정 이력·감사·재현", "",
        "- attempt01은 RF JSON의 6자리 직렬화와 evaluator 원정밀도 차이를 1e−10으로 비교해 STOP했다. 원본과 실패 코드는 보존했다. 실제 RF 생성 좌표를 primary로 하고 round6 exact provenance를 검사하는 수정안만 감사 후 attempt02로 진행했다.",
        "- 초기 P1의 donor 간 매칭 오류는 감사가 발견했다. donor별 선매칭으로 수정하고 p1_revision_02를 새로 동결했다. 이전 파일은 보존했다.",
        "- 초기 P2의 작은 고유값 제거 범위를 exact duplicate로 제한하고 signed ML→heldout·rad/degree refit 검사를 추가했다. revision02 T00–T09와 실제 runner 정보 차단을 독립 재실행한 뒤에만 P3를 승인했다.",
        "- P3 원 JSON은 마지막 R5 continue 뒤 저장되지 않아 R5 key가 없다. 재생·적합을 다시 하지 않고 PRIMARY_SUMMARY.json과 CSV에 NO_SUPPORTED_FOLD, n=0을 명시했다. 원 JSON은 수정하지 않았다.",
        "", "검증 코드·동결 계약·배열·원본 입력 해시·단계 해시·명령은 같은 attempt와 상위 코드 폴더에 있다. Git 기준은 계획 commit이고 실행 코드는 새 파일 SHA로 고정했다. 실행·독립 감사 완료는 signed 가설 지지 또는 H3 채택을 뜻하지 않는다.", "",
        "허용 문구: **시험한 장면의 공통 원거리 지지에서 R4의 공분산 확장은 s-only보다 예측력이 높았으나, signed Jacobian 구조의 필요성은 확인되지 않았다. R2의 signed contrast는 예측과 반대였다.**", ""]
    (out/"REPORT_KO.md").write_text("\n".join(report), encoding="utf-8")
    put(out/"RUN_CONTRACT.json", dict(stage="P5_AGGREGATION_ONLY", implementation_sha256=sha(__file__),
        command=sys.argv, report_sha256=sha(out/"REPORT_KO.md"), original_p3_unchanged=True,
        git_plan_commit="bd28eac6a0e235412bdced9f08505148191e39d2", implementation_state="new uncommitted files bound by SHA, isolated detached worktree"))
    print("P5 aggregation complete: INCONCLUSIVE", flush=True)


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--attempt", type=Path, required=True); run(ap.parse_args().attempt)
