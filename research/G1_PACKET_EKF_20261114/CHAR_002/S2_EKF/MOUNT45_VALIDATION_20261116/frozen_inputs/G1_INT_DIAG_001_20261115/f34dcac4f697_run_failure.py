"""Diagnostic-only attribution of the C4/C5 failures on B/B0, mount 0."""
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(STUDY))

from run_followup import (BASE_LOCK, COMMIT, DISTANCE_EDGES, LOCK_FILE, RESULT,
                          authenticate, averaged_feature, check_trace, load,
                          noise_for, now, read, read_setup, record, replay_augmented,
                          replay_ks, same_trace, scores_with_blocks, sha, write)

QUESTION = "G1-INT-001/KS-R2-R5-FAILURE"
LOCK = HERE / "RUN_CONTRACT.json"
OUT = HERE / "run_01"
C5 = STUDY / "run_01"
C4 = STUDY / "run_c4_retry_03"
ROUTES = ("R2", "R5")
BINS = ("near", "mid", "far")
C5_FILES = ("C5.json", *(f"C5_{route}_{arm}.npz"
                         for route in ROUTES for arm in ("distance", "conservative")))
C4_FILES = ("C4.json", "C4_R2_directional.npz")
RULES = {
    "scope": "Post-hoc DIAGNOSTIC_ONLY; B/B0 mount 0 seed 10, R2/R5. No model fit or adoption.",
    "fixed": "Existing data, E0-LORO-sigma_b reference, common frozen mask, dynamics and mean.",
    "C5_memory": "At each original k, independently suppress slow covariance memory (return V_l to white, preserve fast partition/history) and fast causal excess (empty history). Both off must agree with LORO.",
    "C5_distance": "Apply conservative k in exactly one existing prior distance bin at a time, and in all bins except one at a time; compare with both original endpoints.",
    "C4_R2": "Use frozen directional coefficients, replace with original C5 distance-only variance in exactly one of the three existing bins at a time.",
    "scoring": "Full original scoring grid, paired 5/10 s bootstrap, plus fixed 10 s and LORO-prior distance strata; truth only for scoring.",
    "interpretation": "Recomputed priors, gains and cap events are downstream effects of each intervention. Do not infer the physical source of the residuals.",
}


def freeze():
    prior = read(LOCK_FILE)
    authenticate(BASE_LOCK)
    receipts = ((C5, C5_FILES, "C5"), (C4, C4_FILES, None),
                (RESULT, ("FITTED_PARAMETERS.json",), None))
    inputs = [record(LOCK_FILE), record(BASE_LOCK), record(STUDY / "RUN_CONTRACT_C4_RETRY_03.json")]
    for directory, names, completed in receipts:
        receipt = read(directory / "EXECUTION.json")
        if completed and completed not in receipt["completed"]:
            raise ValueError(f"Missing completed {completed} stage")
        if not completed and receipt["status"] != "PASS_EXECUTION":
            raise ValueError(f"Execution unverified: {directory}")
        inputs.append(record(directory / "EXECUTION.json"))
        for name in names:
            entry = record(directory / name)
            if entry["sha256"] != receipt["outputs"][name]:
                raise ValueError(f"Input receipt mismatch: {name}")
            inputs.append(entry)
    write(LOCK, dict(question=QUESTION, base_commit=COMMIT, freeze_utc=now(),
                     source=record(Path(__file__)), rules=RULES, inputs=inputs,
                     governance=prior["governance"]))


def index(distance):
    return int(np.searchsorted(DISTANCE_EDGES, distance, side="right") - 1)


def lookups(params, route, ratio):
    distance = noise_for(params, route, "distance")

    def scaled(d, g, bins):
        fitted = distance(d, g)
        if fitted is not None and index(d) in bins:
            fitted = replace(fitted, slow=fitted.slow * ratio)
        return fitted

    def fast(d, g, bins):
        fitted = scaled(d, g, bins)
        return None if fitted is None else replace(fitted, slow=0.)

    return distance, scaled, fast


def r2_directional(distance, frozen, whiten_bin=None):
    coefficients = {row["bin"]: np.array(row["coef"])
                    for row in frozen["fits"]["R2"]["directional"] if "coef" in row}

    def lookup(d, H, P, R):
        fitted = distance(d, abs(float(H[1, 2])))
        b = index(d)
        if fitted is None or b not in coefficients:
            return None
        if b == whiten_bin:
            return fitted
        coef = coefficients[b]
        slow = float(coef[0] + averaged_feature(H, P, R, "directional") @ coef[1:])
        return replace(fitted, slow=slow)

    return lookup


def stratify(row, trace, baseline_distance):
    squared_heading, squared_xy = row[:, 0], row[:, 1]
    time = trace["t"] - trace["t"][0]
    seconds = np.floor(time / 10).astype(int)
    by_distance = np.searchsorted(DISTANCE_EDGES, baseline_distance, side="right") - 1
    accepted, supported = trace["mask"], trace["supported"]
    # Decompose the local mean update by measurement channel at each arm's own prior.
    correction = trace["K"][:, :3, :] * trace["nu"][:, None, :]
    local = np.stack([np.linalg.norm(correction[:, :2, :], axis=1) * 100,
                      np.abs(np.rad2deg(correction[:, 2, :]))], axis=1)

    def reduce(mask):
        update = mask & accepted
        usable = update & supported
        return dict(n=int(mask.sum()), accepted=int(update.sum()), supported=int(usable.sum()),
                    heading_rmse_deg=float(np.sqrt(squared_heading[mask].mean())),
                    xy_rmse_cm=float(np.sqrt(squared_xy[mask].mean())),
                    coverage=row[mask, 3:].mean(axis=0).tolist(),
                    update_mean_abs_xy_cm_heading_deg_by_channel=(
                        local[update].mean(axis=0).tolist() if update.any() else None),
                    slow_cap_fraction=float(np.mean(trace["V_l"][usable] > trace["V_l_op"][usable]))
                    if usable.any() else None)

    return dict(by_time_10s={str(i * 10): reduce(seconds == i) for i in np.unique(seconds)},
                by_same_reference_distance={str(i): reduce(by_distance == i)
                                            for i in np.unique(by_distance)})


def run():
    from functools import partial

    lock = read(LOCK)
    for entry in [lock["source"], *lock["inputs"], *lock["governance"]]:
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError(f"Frozen input changed: {entry['path']}")
    OUT.mkdir()
    receipt = dict(question=QUESTION, contract_sha256=sha(LOCK), base_commit=COMMIT,
                   command=sys.argv, start_utc=now(), status="FAIL_EXECUTION", exit_code=1)
    try:
        core, online, model, _, primary, cases, _, preflight = read_setup(authenticate(BASE_LOCK))
        from verify_s2 import from_trace

        env = core, online, model
        params = {route: {int(k): value for k, value in bins.items()}
                  for route, bins in read(RESULT / "FITTED_PARAMETERS.json").items()}
        donor = read(C5 / "C5.json")["donor_var"]
        c4 = read(C4 / "C4.json")
        result = {}
        for route in ROUTES:
            case = cases[route]
            loro, truth = case["loro"], primary[route]["truth"]
            replay = partial(replay_ks, case, *env)
            distance, scaled, fast = lookups(params, route, donor[route]["multiplier"])
            rows = {"LORO": from_trace(loro, truth)}
            strata, diagnostics, parity = {}, {}, {}
            baseline_d = np.linalg.norm(loro["prior"][:, :2] - np.array(case["spec"]["anchor"][:2]), axis=1)

            def save(label, trace, *, history=True, original=None):
                diagnostics[label] = check_trace(trace, case, history_enabled=history)
                if original is not None:
                    parity[label] = max(same_trace(trace, load(original)).values())
                rows[label] = from_trace(trace, truth)
                strata[label] = stratify(rows[label], trace, baseline_d)
                np.savez_compressed(OUT / f"{route}_{label}.npz", **trace)

            for label, bins in (("distance", ()), ("conservative", (0, 1, 2))):
                choose = partial(scaled, bins=bins)
                save(label, replay(choose), original=C5 / f"C5_{route}_{label}.npz")
                save(f"{label}_fast_only", replay(partial(fast, bins=bins)))
                save(f"{label}_slow_only", replay(choose, check_special="empty_history"), history=False)
                independent = replay(choose, check_special="independent")
                save(f"{label}_independent", independent, history=False)
                fields = {key: loro[key] for key in ("t", "pose_id", "mask", "x", "P", "prior", "Pprior")}
                parity[f"{label}_independent_to_LORO"] = max(same_trace(independent, fields).values())

            for i, name in enumerate(BINS):
                save(f"conservative_only_{name}", replay(partial(scaled, bins=(i,))))
                other = tuple(j for j in range(len(BINS)) if j != i)
                save(f"conservative_except_{name}", replay(partial(scaled, bins=other)))

            if route == "R2":
                directional = partial(r2_directional, distance, c4)
                save("directional", replay_augmented(case, env, directional()),
                     original=C4 / "C4_R2_directional.npz")
                for i, name in enumerate(BINS):
                    save(f"directional_distance_in_{name}",
                         replay_augmented(case, env, directional(whiten_bin=i)))

            contrasts = [(label, "LORO") for label in rows if label != "LORO"]
            contrasts += [(label, "distance") for label in rows if label.startswith("conservative")]
            contrasts += [(label, "directional") for label in rows if label.startswith("directional_distance")]
            scores = scores_with_blocks({route: rows}, {route: case["packet"]["t"]}, contrasts)
            result[route] = dict(scores=scores, strata=strata, checks=diagnostics, parity=parity)
            print(f"{route} complete, {len(rows) - 1} replays", flush=True)
        write(OUT / "RESULT.json", dict(preflight=preflight, by_route=result))
        receipt.update(status="PASS_EXECUTION", exit_code=0)
    except Exception as exc:
        receipt["error"] = repr(exc)
        raise
    finally:
        receipt["finish_utc"] = now()
        receipt["outputs"] = {p.name: sha(p) for p in sorted(OUT.iterdir())}
        write(OUT / "EXECUTION.json", receipt)


if __name__ == "__main__":
    if sys.argv[1:] == ["freeze"]:
        freeze()
    elif sys.argv[1:] == ["run"]:
        run()
    else:
        raise SystemExit("Use freeze or run")

