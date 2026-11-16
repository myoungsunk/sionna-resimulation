"""Check a KS execution receipt and reaggregate saved replay traces."""

import argparse
from pathlib import Path

import numpy as np

from run_ks import BASE, ROUTES, STAGES, STRUCT, authenticate, dump, read, sha, verify_file


def same(actual, expected):
    np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=1e-12)


def score_replay(out, file, truth, expected, ref_mask):
    from metrics_s2 import _summarize
    from verify_s2 import from_trace

    with np.load(out / file, allow_pickle=False) as trace:
        np.testing.assert_array_equal(trace["mask"], ref_mask)
        rows = from_trace({k: trace[k] for k in ("x", "P")}, truth)
    actual = _summarize(rows)
    for key in actual:
        same(actual[key], expected[key])
    return rows


def verify(contract, folder, destination):
    lock = authenticate(contract)
    receipt = read(folder / "EXECUTION.json")
    if (receipt["status"] != "PASS_EXECUTION" or receipt["exit_code"] != 0 or
            receipt["contract_sha256"] != sha(contract) or tuple(receipt["completed_stages"]) != STAGES):
        raise ValueError("Incomplete or unauthenticated run")
    if set(receipt["outputs"]) != {p.name for p in folder.iterdir() if p.is_file() and p.name != "EXECUTION.json"}:
        raise ValueError("Execution output manifest incomplete")
    for name, digest in receipt["outputs"].items():
        verify_file({"path": str(folder / name), "sha256": digest})

    from run_structure import authenticate as structure_auth, cases_from

    structure, _ = structure_auth()
    routes = cases_from(structure)
    from metrics_s2 import _moving_block_indices, _summarize
    from verify_s2 import from_trace
    from d0_d5 import bind

    base = read(BASE)
    truth = {cell["route"]: bind(cell)[1] for cell in base["cells"] if cell["anchor"] == "B" and cell["bias"] == "B0"}
    transfer = read(folder / "V8.json")
    if {(row["fold"], row["bin_index"]) for row in transfer["rows"]} != {(r, b) for r in ROUTES for b in range(3)}:
        raise ValueError("Missing V8 rows")
    for item in transfer["rows"]:
        if item["fold"] in item["donors"] or set(item["donors"]) != set(ROUTES) - {item["fold"]}:
            raise ValueError("V8 holdout leakage")
        if item["ratio"] is not None:
            same(item["ratio"], item["prediction"] / item["measured"])
            same(item["capped_prediction_ratio"], item["capped_prediction"] / item["measured"])
            if item["capped_prediction"] > item["prediction"] + 1e-12:
                raise ValueError("V8 capped-g sensitivity overflow")

    oracle = read(folder / "V3.json")
    r4 = routes["R4"]
    indices = _moving_block_indices(r4["packet"]["t"], 10, 1500, np.random.default_rng(20261115))
    point = oracle["scores"]["point"]["R4"]
    baseline_rows = from_trace(r4["loro"], truth["R4"])
    for key, value in _summarize(baseline_rows).items():
        same(value, point["LORO"][key])
    for arm, decision in oracle["decisions"].items():
        file = f"V3_{arm}.npz"
        rows = score_replay(folder, file, truth["R4"], point[arm], r4["mask"])
        same(np.quantile(np.take(rows[:, 5], indices).mean(axis=1), [.025, .975]), decision["heading95_ci95"])
        with np.load(folder / file, allow_pickle=False) as trace:
            supported = trace["supported"] & trace["mask"]
            clipped = (trace["V_l"] > trace["V_l_capped"]) & supported
            count, capped_count = int(supported.sum()), int(clipped.sum())
            source = oracle["clipping"][arm]
            same([count, capped_count], [source["supported"], source["clipped"]])
            if count:
                same(capped_count / count, source["fraction"])
                expected = trace["V_l"] if arm == "a_prime" else trace["V_l_capped"]
                same(trace["V_l_op"][supported], expected[supported])
            if arm == "a":
                triggered = count > 0 and capped_count / count > .10
                if triggered != oracle["a_prime_executed"] or triggered != ("a_prime" in oracle["decisions"]):
                    raise ValueError("V3 conditional oracle trigger mismatch")

    v9 = read(folder / "V9.json")["scores"]["point"]
    for route in ("R2", "R5"):
        case = routes[route]
        for arm in ("SC", "GM", "FIXED_GAIN"):
            score_replay(folder, f"V9_{route}_{arm}.npz", truth[route], v9[route][arm], case["mask"])
        with np.load(folder / f"V9_{route}_FIXED_GAIN.npz", allow_pickle=False) as trace:
            same(trace["x"], case["loro"]["x"])

    d6 = read(folder / "D6.json")
    for route in ROUTES:
        base_mask = routes[route]["mask"]
        for name in ("native", "13.8", "all_valid"):
            with np.load(folder / f"D6_{route}_{name}.npz", allow_pickle=False) as trace:
                summary = d6["mask_diagnostics"][route][name]
                same((trace["mask"].sum(), (trace["mask"] != base_mask).sum()), (summary["accepted"], summary["changed"]))
                for arm in ("E0", "LORO"):
                    expected = d6["scores"]["point"][route][f"{arm}_{name}"]
                    for key, value in _summarize(trace[arm]).items():
                        same(value, expected[key])

    stage = read(folder / "KS.json")
    entrance = {key: read(folder / f"{key}.json")["status"] for key in ("V8", "V1", "V2")}
    entrance.update({f"V3_{arm}": oracle["decisions"][arm]["status"] for arm in ("a", "c")})
    if set(entrance.values()) != {"PASS"}:
        if stage != dict(status="STOP_NOT_ADMITTED", entrance_gates=entrance) or any(folder.glob("KS_R*.npz")):
            raise ValueError("KS admission was not respected")
    else:
        if stage["status"] != "EXECUTED":
            raise ValueError("KS admitted but missing")
        for route in ROUTES:
            for arm in ("KS", "KI"):
                score_replay(folder, f"KS_{route}_{arm}.npz", truth[route],
                             stage["scores"]["point"][route][arm], routes[route]["mask"])
    dump(destination, dict(status="PASS_REAGGREGATION", role="IMPLEMENTER_SELF_CHECK",
                           verifier_sha256=sha(Path(__file__)), contract_sha256=sha(contract),
                           execution_sha256=sha(folder / "EXECUTION.json"), verified_outputs=len(receipt["outputs"]),
                           v8_rows=len(transfer["rows"]), v3_arms=list(oracle["decisions"]),
                           v9_traces=6, d6_gate_traces=9, entrance=entrance, KS=stage["status"]))


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--contract", required=True, type=Path)
    args.add_argument("--run", required=True, type=Path)
    args.add_argument("--out", required=True, type=Path)
    config = args.parse_args()
    verify(config.contract, config.run, config.out)
