"""Additional input-barrier checks with disk reads disabled in the online replay."""

import argparse
import builtins
from contextlib import ExitStack
import io
from pathlib import Path
from unittest.mock import patch

import numpy as np

from run_characterization import ROOT, check_records, m5, receipt, verified_native
from run_replay import online_inputs, schedule, setup, tested


def compare_fields(actual, expected, fields, take):
    errors = {}
    for name in fields:
        a, b = actual[name][take], expected[name][take]
        np.testing.assert_allclose(a, b, atol=1e-10, rtol=0., err_msg=name)
        errors[name] = float(abs(a.astype(float) - b.astype(float)).max())
    return errors


def run(out, directory):
    spec, lock, base, cases = setup(out)
    native, hashes = verified_native(base)
    from gm_replay import replay

    directory.mkdir(parents=True, exist_ok=True)
    m5.write(directory / "RUN_CONTRACT.json", dict(
        stage="additional_information_barrier", frozen_utc=m5.utc(), source=m5.item(Path(__file__)),
        replay=m5.item(out / "RUN_CONTRACT.json"),
        rules=dict(probe=20, retained_prefix_packets=25,
                   current_z_delta=[.2, -.1], future_changes=["z", "ds", "gy", "dt", "R", "muMB"],
                   denied_reads=["builtins.open", "io.open", "numpy.load"], tolerance=1e-10)))
    with receipt(directory, "additional_information_barrier") as execution:
        execution["native_source_hashes"] = hashes
        results = {}
        for row in spec["variants"]:
            route, name = row["route"], row["name"]
            case = cases[10][route]
            kwargs = row["kw"].copy()
            if kwargs["arm"] in ("G4", "G5psi", "G5y"):
                kwargs.update(schedule(lock, route, case)[1])
            packet, controls, baseline = online_inputs(case, native)[:3]
            stop, probe = min(25, len(packet["t"])), 20
            raw = {k: (v[:stop].copy() if k not in ("x0", "P0") else v.copy()) for k, v in packet.items()}
            active = {k: v[:stop] for k, v in controls.items()}
            fixed = {k: baseline[k][:stop] for k in ("mask", "Reff")}
            for key in ("a2_variance", "near"):
                if key in kwargs:
                    kwargs[key] = kwargs[key][:stop]
            reads = []

            def denied(*args, **unused):
                reads.append(str(args[0]))
                raise RuntimeError("Disk access attempted in the online replay")

            def check():
                with ExitStack() as stack:
                    for target in ("builtins.open", "io.open", "numpy.load"):
                        stack.enter_context(patch(target, denied))
                    reference = replay(raw, active, fixed, *native, **kwargs)
                    current = {k: v.copy() for k, v in raw.items()}
                    current["z"][probe] += np.array([.2, -.1])
                    perturbed_current = replay(current, active, fixed, *native, **kwargs)
                    fields = ("prior", "Pprior", "a", "alpha", "beta", "R_ref", "Reff")
                    current_errors = compare_fields(perturbed_current, reference, fields, probe)
                    future = {k: v.copy() for k, v in raw.items()}
                    future["z"][probe + 1:] += np.array([.1, -.2])
                    future["ds"][probe + 1:] += .03
                    future["gy"][probe + 1:] += .05
                    future["dt"][probe + 1:] *= 1.1
                    future["R"][probe + 1:] *= 1.2
                    future["muMB"][probe + 1:] += .04
                    future_controls = {k: future[k] for k in active}
                    changed = replay(future, future_controls, fixed, *native, **kwargs)
                    fields += ("x", "P", "h", "H", "K", "nu", "S", "mask")
                    suffix_errors = compare_fields(changed, reference, fields, slice(0, probe + 1))
                if reads:
                    raise ValueError("Disk reads were attempted")
                return dict(status="PASS", current=current_errors, future=suffix_errors,
                            disk_read_attempts=0, prefix_packets=probe + 1)

            tested(results, f"{route}/{name}", check)
        m5.write(directory / "CHECKS.json", results)
        print("Supplemental barrier", sum(r["status"] == "PASS" for r in results.values()),
              "/", len(results), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    run(args.replay, args.out)
