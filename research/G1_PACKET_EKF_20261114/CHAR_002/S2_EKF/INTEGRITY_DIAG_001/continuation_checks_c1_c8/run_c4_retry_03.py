"""Resume the preregistered C4 with exact donor prior/covariance reconstruction."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

from run_followup import (HERE, BASE_LOCK, RESULT, ROUTES, FEATURES, LOCK_FILE, DISTANCE_EDGES, MIN_VARIANCE,
                          authenticate, read_setup, record, read, sha, write, now, load, same_trace,
                          noise_for, _prepare, _indices, _support, averaged_feature, replay_augmented,
                          check_trace, clipping_summary, artifact_score, acceptance)


PREVIOUS = HERE / "run_01"
RETRY_LOCK = HERE / "RUN_CONTRACT_C4_RETRY_03.json"


def previous_experiment():
    contract = read(LOCK_FILE)
    receipt = read(PREVIOUS / "EXECUTION.json")
    if (receipt["contract_sha256"] != sha(LOCK_FILE) or receipt["status"] != "FAIL_EXECUTION"
            or receipt["completed"] != ["PREFLIGHT", "C1", "C2", "C3", "C6", "C5"]
            or receipt["error"] != "KeyError('H')"):
        raise ValueError("Wrong prior execution for this retry")
    for name, expected in receipt["outputs"].items():
        if sha(PREVIOUS / name) != expected:
            raise ValueError(f"Changed prior evidence: {name}")
    if read(PREVIOUS / "C5.json")["disposition"]["conservative"]["status"] == "PASS":
        raise ValueError("C4 was not triggered")
    if sha(HERE / "run_followup.py") != contract["source"]["sha256"]:
        raise ValueError("Prior source changed")
    return contract, receipt


def freeze():
    contract, _ = previous_experiment()
    previous_retry = HERE / "run_c4_retry" / "EXECUTION.json"
    first_retry = read(previous_retry)
    old_retry_lock = HERE / "RUN_CONTRACT_C4_RETRY.json"
    if (first_retry["status"] != "FAIL_EXECUTION" or first_retry["error"] != "KeyError('t')"
            or first_retry["retry_contract_sha256"] != sha(old_retry_lock)):
        raise ValueError("Unexpected first C4 retry")
    previous_retry_02 = HERE / "run_c4_retry_02" / "EXECUTION.json"
    retry_02 = read(previous_retry_02)
    retry_lock_02 = HERE / "RUN_CONTRACT_C4_RETRY_02.json"
    if (retry_02["status"] != "FAIL_EXECUTION" or not retry_02["error"].startswith("NameError")
            or retry_02["retry_contract_sha256"] != sha(retry_lock_02)):
        raise ValueError("Unexpected second C4 retry")
    inputs = [record(previous_retry_02), record(retry_lock_02), record(HERE / "run_c4_retry_02.py"),
              record(LOCK_FILE), record(PREVIOUS / "EXECUTION.json"), record(Path(__file__)),
              record(previous_retry), record(old_retry_lock), record(HERE / "run_c4_retry.py")]
    write(RETRY_LOCK, dict(question=contract["question"], role="IMPLEMENTER", frozen_utc=now(),
                           inputs=inputs, original_rules=contract["rules"]["C4"],
                           correction="Replay donor under holdout's E0-LORO sigma table to reconstruct H and Pprior. Verify frozen M3 prior, Reff, mask, t, pose_id and g parity before fitting. Attach immutable online packet t/pose_id explicitly, as replay_sigma returns scored states without these packet identity fields. Import dataclasses.replace explicitly in retry module."))


def execute(out):
    previous_experiment()
    lock = read(RETRY_LOCK)
    for binding in lock["inputs"]:
        if sha(binding["path"]) != binding["sha256"]:
            raise ValueError("Retry input changed")
    receipt = dict(question=lock["question"], retry_contract_sha256=sha(RETRY_LOCK), start_utc=now(), command=sys.argv)
    out.mkdir(exist_ok=False)
    try:
        core, online, model, _, primary, case, fit, preflight = read_setup(authenticate(BASE_LOCK))
        from verify_s2 import from_trace
        env = core, online, model
        params = {f: {int(k): v for k, v in rows.items()} for f, rows in read(RESULT / "FITTED_PARAMETERS.json").items()}
        truth = {r: primary[r]["truth"] for r in ROUTES}
        time = {r: case[r]["packet"]["t"] for r in ROUTES}
        prepared = {f: {r: _prepare(fit[f][r]) for r in ROUTES} for f in ROUTES}
        checks = {}
        def complete(stage, payload):
            write(out / f"{stage}.json", payload)
        def trace_out(stage, arm, trace, route):
            label = f"{stage}_{route}_{arm}"
            checks[label] = check_trace(trace, case[route]) | {"clipping": clipping_summary(trace)}
            np.savez_compressed(out / f"{label}.npz", **trace)
            return from_trace(trace, truth[route])
        study_c4(complete, trace_out, case, fit, time, truth, prepared, params, env)
        write(out / "CHECKS.json", dict(donor_preflight=preflight, replay=checks))
        receipt.update(status="PASS_EXECUTION", exit_code=0)
        print("C4 complete", flush=True)
    except BaseException as exc:
        receipt.update(status="FAIL_EXECUTION", exit_code=1, error=repr(exc))
        raise
    finally:
        receipt.update(end_utc=now(), outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()})
        write(out / "EXECUTION.json", receipt)


def study_c4(complete, trace_out, case, fit, time, truth, prepared, params, env):
    from d0_d5 import replay_sigma
    from run_ks import D23
    core, online, model = env
    donor_checks = {}
    from verify_s2 import from_trace
    rows, fits = {}, {}
    for route in ROUTES:
        prior = {route: case[route]["loro"]}
        donors = tuple(r for r in ROUTES if r != route)
        for donor in donors:
            bound = case[donor]
            computed = replay_sigma(bound["packet"], bound["controls"], bound["mask"],
                                    core, online, model, bound["spec"], case[route]["table"])
            frozen = load(D23 / "d2" / f"M3_{route}_donor_{donor}.npz")
            computed.update(t=bound["packet"]["t"], pose_id=bound["packet"]["pose_id"])
            fields = ("prior", "Reff", "mask", "t", "pose_id")
            donor_checks[f"{route}_{donor}"] = same_trace(computed, {k: frozen[k] for k in fields})
            np.testing.assert_allclose(np.abs(computed["H"][:, 1, 2]), fit[route][donor]["g"], rtol=0., atol=1e-10)
            prior[donor] = computed
        arms = {"LORO": from_trace(case[route]["loro"], truth[route])}
        fits[route] = {}
        for name in FEATURES:
            design = {r: averaged_feature(a["H"], a["Pprior"], a["Reff"], name) for r, a in prior.items()}
            estimates, bins = {}, []
            for b in range(3):
                samples, targets, listed = [], [], {}
                for donor in donors:
                    prep = prepared[route][donor]
                    idx = _indices(prep, b)
                    listed[donor] = _support(prep, idx)
                    if not listed[donor]["supported"]:
                        continue
                    slow = prep["parts"]["slow"][idx, 1]
                    normalizer = np.sqrt(len(idx))
                    samples.append(np.c_[np.ones(len(idx)), design[donor][idx]] / normalizer)
                    targets.append((slow - slow.mean())**2 / normalizer)
                focus = prepared[route][route]
                idx = _indices(focus, b)
                listed[route] = _support(focus, idx)
                row = dict(bin=b, support=listed, status="INCONCLUSIVE")
                if len(samples) == 2 and listed[route]["supported"]:
                    X = np.concatenate(samples)
                    Y = np.concatenate(targets)
                    rank = int(np.linalg.matrix_rank(X))
                    row["rank"] = rank
                    if rank == X.shape[1]:
                        coef, _ = nnls(X, Y)
                        estimates[b] = coef
                        values = design[route][idx]
                        obs = float(np.var(focus["parts"]["slow"][idx, 1]))
                        pred = float(coef[0] + (values @ coef[1:]).mean())
                        donor_max = np.stack([design[r][_indices(prepared[route][r], b)].max(axis=0) for r in donors]).max(axis=0)
                        extrap = float(np.mean(np.any(values > donor_max, axis=1)))
                        ratio = pred / obs if obs > MIN_VARIANCE else None
                        status = ("INCONCLUSIVE" if ratio is None else "FAIL" if not .5 <= ratio <= 2.
                                  else "EXTRAPOLATION_PASS" if extrap > .5 else "PASS")
                        row.update(coef=coef.tolist(), predicted=pred, measured=obs, ratio=ratio,
                                   donor_feature_max=donor_max.tolist(), exceed_fraction=extrap, status=status)
                bins.append(row)
            fits[route][name] = bins
            baseline = noise_for(params, route, "distance")
            def lookup(d, H, P, R):
                fitted = baseline(d, abs(float(H[1, 2])))
                k = int(np.searchsorted(DISTANCE_EDGES, d, side="right") - 1)
                if fitted is None or k not in estimates:
                    return None
                coef = estimates[k]
                slow = float(coef[0] + averaged_feature(H, P, R, name) @ coef[1:])
                return replace(fitted, slow=slow)
            trace = replay_augmented(case[route], env, lookup)
            np.testing.assert_array_equal(trace["mask"], case[route]["mask"])
            arms[name] = trace_out("C4", name, trace, route)
        rows[route] = arms
    score = artifact_score(rows, time, [(name, "LORO") for name in FEATURES])
    complete("C4", dict(fits=fits, scores=score, disposition=acceptance(score, FEATURES),
                        frozen_donor_parity=donor_checks))


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze()
    else:
        execute(Path(sys.argv[2]).resolve())
