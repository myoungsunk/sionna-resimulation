"""Gate control-flow regression with synthetic scorer; not scientific validation."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np


def main():
    source = Path(__file__).with_name("run_far_kriging_ab.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "report_one")
    routes = ("R2", "R4", "R5")
    arms = ("H2", "H2S", "BASE", "FAR")
    metrics = tuple("metric" + str(i) for i in range(5))
    trace = dict(t=np.arange(2), pose_id=np.arange(2), distance=np.array([4., 8.]))
    packet = lambda *a, **kw: trace
    score = {r: {a: {m: 1. for m in metrics} for a in arms} for r in (*routes, "pooled")}
    ns = dict(np=np, ROUTES=routes, BASE="BASE", FAR="FAR", PAIR_PARAMS=metrics, ZERO={},
        C=NS(packet=packet, TRUTH={r: {"truth": None} for r in routes},
             R7=NS(replay=packet), m7_kwargs=lambda *a: {}),
        M=NS(replay_m8=packet, ARM_MODES={"F2": {}}),
        KO=NS(make_fn=lambda *a, **kw: None),
        S=NS(score=lambda *a, **kw: {"point": score}),
        baseline_packet=packet, static_policy_check=lambda *a: None)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "gate_control_flow", "exec"), ns)
    B = {f"{r}/{k}": 0 for r in routes for k in ("mu_r", "mu_s", "Rrr", "Rss")}
    published = {("B0", 30, a, r): {m: 1. for m in metrics}
                 for r in (*routes, "pooled") for a in arms[:3]}
    published["B0", 30, "BASE", "R2"][metrics[0]] = 2.
    def call(**kwargs):
        return ns["report_one"]("B0", 30, None, (None, None, None), B, {}, published, **kwargs)
    def fails(expected, **kwargs):
        try:
            call(**kwargs)
        except RuntimeError as e:
            assert expected in str(e)
        else:
            raise AssertionError("Expected fail-closed behavior")
    fails("PARITY_FAIL")
    d = call(allow_baseline_mismatch=True)
    assert not d["frozen_parity_pass"] and d["frozen_parity_max_abs"] == 1.
    assert len(d["frozen_parity_checks"]) == 60
    assert sum(not row["passed"] for row in d["frozen_parity_checks"]) == 1
    score["R2"]["BASE"][metrics[0]] = float("nan")
    fails("NONFINITE_BASELINE", allow_baseline_mismatch=True)
    score["R2"]["BASE"][metrics[0]] = 1.
    del published["B0", 30, "H2", "R2"]
    fails("missing frozen POINT_B", allow_baseline_mismatch=True)
    print("PASS: strict default; explicit mismatch records 60 checks; nonfinite and missing still stop")


if __name__ == "__main__":
    main()
