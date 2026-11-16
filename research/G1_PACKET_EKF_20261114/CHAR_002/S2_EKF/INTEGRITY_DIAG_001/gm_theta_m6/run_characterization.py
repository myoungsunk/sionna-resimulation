"""Freeze M6's inherited sources and perform K1′, K2, K4 and K5."""

import argparse
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
from traceback import format_exc

import numpy as np

ROOT = Path(__file__).resolve().parent
ART = ROOT.parent
M5 = ART / "G1_HFKI_M5_20261116"
PARENT = M5 / "attempt_02"
REPO = ART.parent / "g1_m5_pub_20261116"
PLAN = ("research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/"
        "INTEGRITY_DIAG_001/PLAN_M6_GM_THETA_STAGED_KO.md")
REV = "ff6f42144c78aa7805fd04abe6963aa55dc5d9b9"
POLICY = Path.home() / ".codex/research-governance"
EXPECTED_POLICY = {
    "COMMON_CONTRACT.md": "a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
    "ROLE_IMPLEMENTER.md": "2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da",
}

sys.path.insert(0, str(M5))
import run_hfki as m5


def check_records(node):
    if isinstance(node, dict):
        if {"path", "sha256"} <= node.keys():
            m5.checked(node)
        else:
            for value in node.values():
                check_records(value)
    elif isinstance(node, list):
        for value in node:
            check_records(value)


@contextmanager
def receipt(directory, stage):
    path = directory / "EXECUTION.json"
    if path.exists() or any(p.name != "RUN_CONTRACT.json" for p in directory.iterdir()):
        raise FileExistsError(f"Existing evidence {directory}")
    record = dict(study="G1-INT-001/M6", stage=stage, started_utc=m5.utc(),
                  command=[sys.executable, *sys.argv],
                  contract_sha256=m5.sha(directory / "RUN_CONTRACT.json"),
                  python=sys.version, numpy=np.__version__)
    try:
        yield record
        record.update(status="PASS_EXECUTION", exit_code=0)
    except BaseException as exc:
        record.update(status="FAIL_EXECUTION", exit_code=1, error=str(exc), traceback=format_exc())
        raise
    finally:
        record["finished_utc"] = m5.utc()
        record["outputs"] = {p.relative_to(directory).as_posix(): m5.sha(p)
                             for p in sorted(directory.rglob("*"))
                             if p.is_file() and p.name != "RUN_CONTRACT.json"}
        m5.write(path, record)


def verified_native(base, stage2_dir=PARENT / "stage2"):
    native, hashes = m5.model_env(base)
    expected = m5.read(stage2_dir / "EXECUTION.json")["native_source_hashes"]
    if hashes != expected:
        raise ValueError("SourceFFD native hash differs from M5 Stage 2")
    return native, hashes


def freeze(out):
    plan_bytes = subprocess.check_output(["git", "-C", str(REPO), "show", f"{REV}:{PLAN}"])
    if (REPO / PLAN).read_bytes() != plan_bytes:
        raise ValueError("Local plan differs from pushed revision")
    parents = {str(n): {name: m5.item(PARENT / f"stage{n}" / name)
                        for name in ("RUN_CONTRACT.json", "EXECUTION.json", "VERIFICATION.json")}
               for n in (0, 2, 3)}
    stage2 = m5.read(PARENT / "stage2/RUN_CONTRACT.json")
    stage3 = m5.read(PARENT / "stage3/RUN_CONTRACT.json")
    check_records(stage3["parents"])
    for rec in parents.values():
        success = m5.read(m5.checked(rec["EXECUTION.json"]))
        if success["exit_code"] != 0 or success["contract_sha256"] != rec["RUN_CONTRACT.json"]["sha256"]:
            raise ValueError("Parent did not execute from the recorded contract")
    for name, digest in EXPECTED_POLICY.items():
        m5.checked(dict(path=POLICY / name, sha256=digest))
    base = m5.bindings()
    sources = [m5.item(ROOT / name) for name in ("run_characterization.py", "characterize.py", "diagnostics.py")]
    sources += stage2["sources"]
    archive = {str(seed): {route: m5.output_of(PARENT / "stage3", f"seed{seed}/{route}_A0.npz")
                           for route in m5.ROUTES} for seed in range(10, 15)}
    a2 = {route: m5.output_of(PARENT / "stage2", f"{route}_A2_2.npz") for route in m5.ROUTES}
    lock = dict(study="G1-INT-001/M6", stage="characterization", role="IMPLEMENTER", frozen_utc=m5.utc(),
                classification="DIAGNOSTIC_ONLY", branch="research/g1-sweep-heading-floor-spec-20261113",
                plan=m5.item(REPO / PLAN) | dict(commit=REV), scope=stage2["scope"], parents=parents,
                governance=[m5.item(POLICY / name) for name in EXPECTED_POLICY], sources=sources,
                base=m5.item(m5.BASE), model_assets=stage2["model_assets"], cells=stage2["cells"],
                d3=stage2["d3"], online_packets=stage3["online_packets"], archived_a0=archive, archived_a2=a2,
                gate_counts=m5.COUNTS, crossings=m5.PASSES, parity_tolerance=1e-10,
                distance_bins_m=[0., 1.5, 3., 6., 10.],
                k1=dict(accepted_supported="primary", minimum_packets=30, minimum_10s_blocks=2,
                        g_rms_ratio_min=1.2, minimum_routes=2, minimum_distance_bins=2, fit="route-by-distance FE",
                        draws=1500, seed=20261115, block_seconds=10, weights="Exp(1) per route block",
                        hybrid_upper_limit=2.0),
                k2=dict(denominator_abs_min_rad_inverse=1., estimator="1.4826 times zero-referenced median absolute",
                        require_acceptance=False, dispersion_ratio_max=2.,
                        centering="D3-centered; retain signed b_eq centers in primary"),
                k4=dict(channel_order=["range", "range-conditional polarization"], half_window_s=10.),
                k5=dict(routes=["R2", "R5"], compare=["A0", "A2_2"], lead_s=5., block_s=10.),
                continuations={"G-T2/G-V": "SEALED", "S2′": "STOP", "Step 3": "HOLD"})
    check_records(lock)
    m5.cases_from(lock)
    verified_native(base)
    out.mkdir(parents=True, exist_ok=True)
    m5.write(out / "RUN_CONTRACT.json", lock)


def characterization_inputs(lock, frozen, native):
    from d3 import decompose
    from ks_diagnostics import WINDOW

    model, spec = native[2:]
    anchor = np.array(spec["anchor"][:2])
    data = {}
    agreement = {}
    for route, case in frozen.items():
        record = m5.arrays(m5.checked(lock["d3"][route]))
        packet, truth, baseline = (case[k] for k in ("packet", "truth", "baseline"))
        m5.grid_equal(packet, record)
        np.testing.assert_array_equal(baseline["mask"], record["mask"])
        t, arc, yaw = packet["t"], record["arc_m"], record["yaw_arc_rad"]
        truth_h, truth_j = model.batch(np.column_stack((truth, np.zeros(len(truth)))), spec)
        truth_eps = packet["z"] - packet["muMB"] - truth_h
        np.testing.assert_allclose(truth_eps, record["eps"], atol=1e-10, rtol=0.)
        parts = decompose(record["eps"], t, arc, yaw, WINDOW)
        np.testing.assert_array_equal(parts["support"], record["decomposition_support"])
        np.testing.assert_array_equal(parts["window_n"], record["window_n"])
        np.testing.assert_allclose(parts["slow"], record["slow"], atol=1e-12, rtol=0.)
        signed_ref = baseline["H"][:, 1, 2]
        integrated = np.r_[0., np.cumsum(signed_ref)]
        mean_ref = (integrated[parts["right"]] - integrated[parts["left"]]) / parts["window_n"]
        data[route] = dict(t=t, mask=record["mask"], g_truth=abs(truth_j[:, 1, 2]),
                           truth_distance=np.linalg.norm(truth[:, :2] - anchor, axis=1),
                           prior_distance=np.linalg.norm(baseline["prior"][:, :2] - anchor, axis=1),
                           a_ref=signed_ref, window_a_ref=mean_ref, slow_s=record["slow"][:, 1],
                           raw_s=record["eps"][:, 1], route_mean_s=float(record["route_mean"][1]),
                           support=record["decomposition_support"], arc=arc, yaw_arc=yaw,
                           pass_times=np.array([p["time_s"] for p in case["passages"]]))
        agreement[route] = dict(accepted=int(record["mask"].sum()), packets=len(t),
                                passage_count=len(case["passages"]), supported=int(parts["support"].sum()),
                                max_truth_eps_delta=float(abs(truth_eps - record["eps"]).max()),
                                max_slow_delta=float(abs(parts["slow"] - record["slow"]).max()))
    return data, agreement


def execute(out):
    from characterize import characterize
    from diagnostics import passage_budget, passage_comparison

    lock = m5.read(out / "RUN_CONTRACT.json")
    check_records(lock)
    with receipt(out, "characterization") as run:
        base = m5.bindings()
        native, run["native_source_hashes"] = verified_native(base)
        frozen = m5.cases_from(lock)
        data, agreement = characterization_inputs(lock, frozen, native)
        m5.write(out / "CHECKS.json", agreement)
        result = characterize(data)
        m5.write(out / "K1_PRIME_K2.json", result)
        print("K1′ and K2 complete", result["k1"]["verdict"], result["k2"]["verdict"], flush=True)
        baseline = {route: m5.arrays(record["path"]) for route, record in lock["archived_a0"]["10"].items()}
        a2 = {route: m5.arrays(record["path"]) for route, record in lock["archived_a2"].items()}
        for route in m5.ROUTES:
            for trace in (baseline[route], a2[route]):
                m5.grid_equal(frozen[route]["packet"], trace)
                np.testing.assert_array_equal(frozen[route]["baseline"]["mask"], trace["mask"])
        m5.write(out / "K4_BASELINE.json", passage_budget(frozen["R5"], baseline["R5"]))
        m5.write(out / "K5.json", {route: passage_comparison(frozen[route], baseline[route], a2[route])
                                  for route in ("R2", "R5")})
        print("K4 baseline and K5 complete", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    {"freeze": freeze, "run": execute}[args.command](args.out)


if __name__ == "__main__":
    main()
