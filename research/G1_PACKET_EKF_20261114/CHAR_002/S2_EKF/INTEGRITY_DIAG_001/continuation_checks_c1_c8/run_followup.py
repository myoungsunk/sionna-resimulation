"""C1-C6 follow-up for the frozen KS transfer diagnostic."""
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import scipy
from scipy.optimize import nnls


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "continuation_ks"
RESULT = PREVIOUS / "run_03"
BASE_LOCK = PREVIOUS / "RUN_CONTRACT_RETRY_03.json"
GIT = HERE.parent.parent.parent / "g1_int_diag001_publication_20261115"
COMMIT = "8305058bcea6a0e29b45675ea148bfa0ee85aa0c"
sys.path.insert(0, str(PREVIOUS))

from run_ks import ROUTES, authenticate, noise_for, read_setup
from ks_diagnostics import COVERAGE, RMSE, scores_with_blocks, v3_status
from ks_fit import DISTANCE_EDGES, MIN_VARIANCE, _indices, _prepare, _support
from ks_replay import (KI_MAX_PACKETS, _augmented_prior, _augmented_update, _common_step,
                       _geometry, _kernel_extra, _partition, _trace, check_trace,
                       clipping_summary, replay_ks)

SCALES = (.25, .5, .75, 1., 1.5, 2., 4.)
LENGTHS = (.5, 1., 2., 4.)
BASE_VARIANTS = {"a": "oracle", "b": "distance", "c": "sensitivity_matched_distance_length"}
FEATURES = ("norm_full", "norm_xy", "directional")
BASE_TRACES = ("a", "b", "c", "a_prime")
TOLERANCE = 1e-10
LOCK_FILE = HERE / "RUN_CONTRACT_C1_C6.json"
RULES = {
    "C1": "Freeze V3(a) realized per-packet V_l_op, fast inflation and mask. KI adds frozen slow causal excess to matched marginal. WHITE adds V_l_op to frozen V3(a) Reff. WHITE_REF adds V_l_op to contemporaneous R_ref as literal additive variance control.",
    "C2": {"multipliers": SCALES, "policies": ("cap", "uncap"), "fixed": "original V3(a) lengths and fast parameters; log requested and applied variance and caps", "criterion": "original V3 (a) criterion, tested grid only, no new V8 criterion"},
    "C3": {"fixed_controls": "cross a/c requested variance and a/c lengths in both directions, pure g^2 allocation from own a sill normalized on V3(a) E0-LORO D3 eligible g^2 in own distance bin", "common_lengths_m": LENGTHS, "series": ("a", "c"), "cap": "all comparisons capped as originals"},
    "C6": "NIS <= native 9.210340371976184 at candidate own prior with augmented S and its own accepted history. Compare a/c at fixed/own gate. Peak reference is each fixed variant and LORO, local maxima of absolute heading error above its trajectory 90th percentile. Record differences for all original rejections and own changes, nearest peak time and counts within 1 s.",
    "C5": "For each holdout compute one multiplier max across distance bins of larger/smaller centered slow D3 donor variance with original support and minimum variance. Multiply original distance-only donor estimate, use distance-only donor lengths and fixed E0 mask, cap as original. Compare to k=1. Apply the frozen plan section 5 criteria as diagnostic; any failed or unsupported condition triggers C4/C7 investigations, no KS admission reset.",
    "C4": {"trigger": "C5 does not pass", "strict_variants": FEATURES, "fit": "separate two-donor NNLS per distance bin using centered squared D3 slow target and equal donor weight; keep distance-only length and all other parameters", "scalars": "full squared norm of [H_x*1m,H_y*1m,H_yaw*1rad] and squared XY norm; directional three terms H_j^2 P_jj / R_ref_ss in yaw,x,y order, no cross terms; intercept for each", "scope": "same fold/packet/support and original V8 thresholds; all preregistered variants reported; no selection or adoption"},
    "bootstrap": "original KS 1500 draws with paired 5 and 10 s blocks on full grids, seed 20261115",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def record(path):
    return {"path": str(path), "sha256": sha(path)}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")


def load(path):
    with np.load(path, allow_pickle=False) as archive:
        return {field: archive[field] for field in archive.files}


def same_trace(actual, expected):
    errors = {}
    for name in expected:
        a, b = actual[name], expected[name]
        if b.dtype.kind in "biu":
            np.testing.assert_array_equal(a, b)
        else:
            np.testing.assert_allclose(a, b, rtol=0., atol=TOLERANCE, err_msg=name)
            errors[name] = float(np.max(np.abs(a - b)))
    return errors


def freeze():
    parent = authenticate(BASE_LOCK)
    receipt = read(RESULT / "EXECUTION.json")
    if receipt["status"] != "PASS_EXECUTION" or receipt["contract_sha256"] != sha(BASE_LOCK):
        raise ValueError("Invalid parent execution")
    files = ["FITTED_PARAMETERS.json", "V8.json", "V3.json", *[f"V3_{a}.npz" for a in BASE_TRACES]]
    inputs = [record(BASE_LOCK), record(RESULT / "EXECUTION.json"), record(PREVIOUS / "PLAN_FROZEN.md")]
    for name in files:
        entry = record(RESULT / name)
        if entry["sha256"] != receipt["outputs"][name]:
            raise ValueError(f"Changed parent execution output: {name}")
        inputs.append(entry)
    git_head = subprocess.check_output(["git", "-C", str(GIT), "rev-parse", "HEAD"], text=True).strip()
    if git_head != COMMIT:
        raise ValueError("Publication checkout revision changed")
    write(LOCK_FILE, dict(question="G1-INT-001/KS-C1-C6", role="IMPLEMENTER",
                         base_commit=COMMIT, frozen_utc=now(), source=record(Path(__file__)),
                         governance=parent["governance"], inputs=inputs, rules=RULES))


def artifact_score(rows, times, contrasts):
    return scores_with_blocks(rows, times, contrasts, blocks=(5, 10))


def r4_scores(rows, time, pairs):
    scores = artifact_score({"R4": rows}, {"R4": time}, pairs)
    return scores


def counterfactual_white(case, env, source, variant):
    core, online, model = env
    packet = case["packet"]
    x, P = packet["x0"].copy(), packet["P0"].copy()
    steps = []
    for i, accepted in enumerate(case["mask"]):
        prior, Pprior, h, H, _, rho_before, rho_prior, sigma, R = _geometry(case, *env, x, P, i)
        Reff = R.copy()
        applied = source["V_l_op"][i]
        if variant == "WHITE_REF":
            Reff[1, 1] += applied
        else:
            Reff = source["Reff"][i].copy()
            Reff[1, 1] += applied
            if variant == "KI":
                Reff[1, 1] += source["causal"][i, 1]
        innovation = packet["z"][i] - h - packet["muMB"][i]
        x, P, K, S = online.joseph(prior, Pprior, H, innovation, Reff, accepted, 1.)
        steps.append(_common_step(x, P, prior, Pprior, h, H, K, Reff, innovation, S,
                                  sigma, rho_before, rho_prior, R))
    trace = _trace(case, steps)
    trace["same_V_l_op_as_a"] = source["V_l_op"].copy()
    return trace


def replay_augmented(case, env, lookup, *, own_gate=False):
    """Preserve the original KS update and enable own NIS / additional online features."""
    core, online, model = env
    packet, controls = case["packet"], case["controls"]
    x, P = packet["x0"].copy(), packet["P0"].copy()
    augmented = np.eye(5)
    augmented[:4, :4] = P
    hazard, inverse_lengths = np.zeros(2), np.zeros(2)
    history = deque(maxlen=KI_MAX_PACKETS)
    arc = 0.
    mask, steps = [], []
    for i, fixed in enumerate(case["mask"]):
        prior, Pprior, h, H, F, rho_before, d, sigma_b, R = _geometry(case, *env, x, P, i)
        fitted = lookup(d, H, Pprior, R)
        white, fast, slow, capped, fallback = _partition(R[1, 1], fitted, False)
        if fitted is not None:
            inverse_lengths = 1. / np.array([fitted.ell_fast, fitted.ell_slow])
        travel = abs(float(controls["ds"][i])) if i else 0.
        arc += travel
        increment = travel * inverse_lengths
        hazard += increment
        comp = np.array([fast, slow])
        t = float(packet["t"][i])
        causal = _kernel_extra(history, t, hazard, comp)
        history_n = len(history)
        Reff = R.copy()
        Reff[1, 1] = white + fast + causal[0]
        innovation = packet["z"][i] - h - packet["muMB"][i]
        alpha = np.array([np.exp(-increment[1])])
        predicted = _augmented_prior(augmented, Pprior, F, alpha)
        D = np.array([[0.], [math.sqrt(slow)]])
        J = np.column_stack((H, D))
        preS = (J @ predicted) @ J.T + Reff
        nis = float(innovation @ np.linalg.solve((preS + preS.T) * .5, innovation))
        accepted = bool(nis <= online.GATE) if own_gate else bool(fixed)
        if accepted:
            history.append((t, hazard.copy(), comp))
        state, augmented, gain, S = _augmented_update(
            np.r_[prior, 0.], predicted, J, innovation, Reff, accepted, core.wrap
        )
        x, P, K = state[:4], augmented[:4, :4], gain[:4]
        step = _common_step(x, P, prior, Pprior, h, H, K, Reff, innovation, S,
                            sigma_b, rho_before, d, R)
        step.update(sensitivity=abs(float(H[1, 2])), arc=arc, hazard=hazard.copy(),
                    history_n=history_n, causal=causal, W_op=white,
                    V_f=0. if fitted is None else fitted.fast, V_f_op=fast,
                    V_l=0. if fitted is None else fitted.slow, V_l_capped=capped, V_l_op=slow,
                    supported=fitted is not None, white_fallback=fallback,
                    P_aug=augmented, Pprior_aug=predicted, K_aug=gain, D=D, alpha=alpha,
                    u_mean=state[4:], nis=nis)
        steps.append(step)
        mask.append(accepted)
    return _trace(case | {"mask": np.asarray(mask, dtype=bool)}, steps)


def averaged_feature(H, P, R, name):
    j = H[..., 1, :3]
    if name == "directional":
        values = j**2 * np.diagonal(P, axis1=-2, axis2=-1)[..., :3] / R[..., 1, 1, None]
        return values[..., (2, 0, 1)]
    width = 3 if name == "norm_full" else 2
    return np.sum(j[..., :width]**2, axis=-1)[..., None]


def acceptance(score, labels):
    points = score["point"]
    bounds = score["blocks"]["10"]["by_group"]["pooled"]
    result = {}
    for arm in labels:
        per_route = {
            route: dict(coverage=all(points[route][arm][m] >= .75 for m in COVERAGE),
                        accuracy=all(points[route][arm][m] <= 1.25 * points[route]["LORO"][m] for m in RMSE))
            for route in ROUTES
        }
        pooled = points["pooled"][arm]
        gates = dict(
            points=all(pooled[m] >= .90 for m in ("pose95_coverage", "heading95_coverage")),
            nees=1.5 <= pooled["mean_nees3"] <= 6.,
            accuracy=all(pooled[m] <= 1.10 * points["pooled"]["LORO"][m] for m in RMSE),
            ci=all(bounds["absolute_ci95"][arm][m][0] >= .80 for m in ("pose95_coverage", "heading95_coverage")),
        )
        passed = all(gates.values()) and all(all(row.values()) for row in per_route.values())
        status = "INCONCLUSIVE" if bounds["reference_only"] else "PASS" if passed else "FAIL"
        result[arm] = dict(status=status, route=per_route, pooled=gates)
    return result


def gate_events(case, truth, fixed, own):
    from scipy.signal import find_peaks
    time = fixed["t"]
    changed = (fixed["mask"] != own["mask"])
    physical = lambda trace: np.abs(np.rad2deg(np.angle(np.exp(1j * (trace["x"][:, 2] - truth[:, 2])))))
    errors = {variant: physical(trace) for variant, trace in
              (("fixed", fixed), ("own", own), ("LORO", case["loro"]))}
    peak_sets = {k: find_peaks(v, height=np.quantile(v, .9))[0] for k, v in errors.items()}
    def timing(index, peaks):
        if not len(peaks):
            return None
        nearest = peaks[np.argmin(np.abs(time[peaks] - time[index]))]
        return float(time[index] - time[nearest])
    events = []
    for i in np.flatnonzero(~fixed["mask"] | changed):
        events.append(dict(index=int(i), pose_id=int(fixed["pose_id"][i]), time_s=float(time[i]),
                           elapsed_s=float(time[i] - time[0]), fixed=bool(fixed["mask"][i]),
                           own=bool(own["mask"][i]), own_nis=float(own["nis"][i]),
                           heading_abs_deg={k: float(v[i]) for k, v in errors.items()},
                           signed_seconds_from_nearest_peak={k: timing(i, p) for k, p in peak_sets.items()}))
    coupling = {k: sum(timing(i, p) is not None and abs(timing(i, p)) <= 1.
                       for i in np.flatnonzero(~fixed["mask"])) for k, p in peak_sets.items()}
    return dict(n_fixed=int(fixed["mask"].sum()), n_own=int(own["mask"].sum()),
                restored=int(np.sum(~fixed["mask"] & own["mask"])),
                lost=int(np.sum(fixed["mask"] & ~own["mask"])), original_rejections_near_peaks=coupling,
                peak_time_s={k: time[v].tolist() for k, v in peak_sets.items()}, events=events)


def run(folder):
    contract = read(LOCK_FILE)
    if contract["source"]["sha256"] != sha(Path(__file__)):
        raise ValueError("Follow-up code changed after freeze")
    for entry in contract["inputs"] + contract["governance"]:
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError(f"Frozen input changed: {entry['path']}")
    folder.mkdir(exist_ok=False)
    report = dict(question=contract["question"], contract_sha256=sha(LOCK_FILE),
                  base_commit=COMMIT, start_utc=now(), command=sys.argv,
                  python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                  completed=[], status="RUNNING")
    try:
        parent = authenticate(BASE_LOCK)
        core, online, model, _, primary, case, fit, preflight = read_setup(parent)
        env = core, online, model
        from verify_s2 import from_trace
        params = {route: {int(k): v for k, v in entries.items()}
                  for route, entries in read(RESULT / "FITTED_PARAMETERS.json").items()}
        base_traces = {arm: load(RESULT / f"V3_{arm}.npz") for arm in BASE_TRACES}
        truth = {r: primary[r]["truth"] for r in ROUTES}
        time = {r: case[r]["packet"]["t"] for r in ROUTES}
        prepared = {f: {r: _prepare(fit[f][r]) for r in ROUTES} for f in ROUTES}
        r4 = case["R4"]
        r4_truth = truth["R4"]
        choices = {k: noise_for(params, "R4", variant) for k, variant in BASE_VARIANTS.items()}
        r4_rows = {"LORO": from_trace(r4["loro"], r4_truth)}
        r4_rows.update({a: from_trace(base_traces[a], r4_truth) for a in BASE_TRACES})
        check_summaries = {}
        clip = {}
        def trace_out(stage, label, trace, route="R4"):
            validated = check_trace(trace, case[route] | {"mask": trace["mask"]})
            key = f"{stage}_{route}_{label}"
            check_summaries[key] = validated
            if "V_l" in trace:
                clip[key] = clipping_summary(trace)
            np.savez_compressed(folder / f"{key}.npz", **trace)
            return from_trace(trace, truth[route])
        def complete(stage, payload):
            write(folder / f"{stage}.json", payload)
            report["completed"].append(stage)
            print(stage, "complete", flush=True)
        parity = same_trace(replay_ks(r4, *env, choices["a"]), base_traces["a"])
        complete("PREFLIGHT", dict(read_setup=preflight, original_a_replay_parity=parity))

        rows = {a: r4_rows[a] for a in ("LORO", "a")}
        for name in ("KI", "WHITE", "WHITE_REF"):
            trace = counterfactual_white(r4, env, base_traces["a"], name)
            expect = base_traces["a"]["Reff"][:, 1, 1].copy()
            if name == "WHITE_REF":
                expect = trace["R_ref"][:, 1, 1].copy()
            expect += base_traces["a"]["V_l_op"]
            if name == "KI":
                expect += base_traces["a"]["causal"][:, 1]
            np.testing.assert_array_equal(trace["Reff"][:, 1, 1], expect)
            rows[name] = trace_out("C1", name, trace)
        complete("C1", r4_scores(rows, time["R4"], [(a, "a") for a in ("KI", "WHITE", "WHITE_REF")]))

        def scale_noise(d, g, quantity, variant="a"):
            fitted = choices[variant](d, g)
            return None if fitted is None else replace(fitted, slow=fitted.slow * quantity)
        rows = {a: r4_rows[a] for a in ("LORO", "a", "a_prime")}
        scales = {}
        for uncapped in (False, True):
            cap = "uncap" if uncapped else "cap"
            for k in SCALES:
                name = f"{cap}_{k:g}"
                scales[name] = dict(k=k, cap=cap)
                if k == 1.:
                    trace = base_traces["a_prime" if uncapped else "a"]
                else:
                    trace = replay_ks(r4, *env, partial(scale_noise, quantity=k), uncap_slow=uncapped)
                rows[name] = trace_out("C2", name, trace)
                stats = clip[f"C2_R4_{name}"]
                scales[name].update(clipping=stats)
        scores = r4_scores(rows, time["R4"], [(label, "a") for label in scales])
        for label, stats in scales.items():
            reference = scales[f'{stats["cap"]}_1']["clipping"]["mean_applied"]
            stats["mean_applied_over_k1"] = stats["clipping"]["mean_applied"] / reference
            stats["v3"] = v3_status(scores, label, stats["clipping"]["supported"])
        complete("C2", dict(scores=scores, arms=scales))

        focus = prepared["R4"]["R4"]
        g2_ref = {b: float(np.mean(focus["g"][_indices(focus, b)]**2)) for b in range(3)}
        def cross(d, g, variance, length):
            v, l = choices[variance](d, g), choices[length](d, g)
            return None if v is None or l is None else replace(v, ell_slow=l.ell_slow)
        def allocate(d, g):
            fitted = choices["a"](d, g)
            bin_index = int(np.searchsorted(DISTANCE_EDGES, d, side="right") - 1)
            return None if fitted is None else replace(fitted, slow=fitted.slow * g**2 / g2_ref[bin_index])
        def common_length(d, g, choice, length):
            fitted = choices[choice](d, g)
            return None if fitted is None else replace(fitted, ell_slow=length)
        rows = {a: r4_rows[a] for a in ("LORO", "a", "b", "c")}
        variants = {"c_oracle_length": partial(cross, variance="c", length="a"),
                    "a_donor_length": partial(cross, variance="a", length="c"),
                    "a_g2_allocation": allocate}
        variants.update({f"{kind}_ell_{length:g}": partial(common_length, choice=kind, length=length)
                         for kind in ("a", "c") for length in LENGTHS})
        for name, noise in variants.items():
            trace = replay_ks(r4, *env, noise)
            rows[name] = trace_out("C3", name, trace)
        pairs = [(label, ref) for label in variants for ref in ("a", "c")]
        complete("C3", dict(g2_normalization=g2_ref, scores=r4_scores(rows, time["R4"], pairs),
                           clipping={k: v for k, v in clip.items() if k.startswith("C3_")}))

        rows = {a: r4_rows[a] for a in ("LORO", "a", "c")}
        events, parity = {}, {}
        for arm in ("a", "c"):
            def as_aug(d, H, P, R):
                return choices[arm](d, abs(float(H[1, 2])))
            fixed = base_traces[arm]
            parity[arm] = same_trace(replay_augmented(r4, env, as_aug), fixed)
            own = replay_augmented(r4, env, as_aug, own_gate=True)
            np.testing.assert_array_equal(own["mask"], own["nis"] <= online.GATE)
            rows[f"{arm}_own"] = trace_out("C6", f"{arm}_own", own)
            events[arm] = gate_events(r4, r4_truth, fixed, own)
        complete("C6", dict(scores=r4_scores(rows, time["R4"], [("a_own", "a"), ("c_own", "c")]),
                           events=events, fixed_path_parity=parity))

        rows, donor_var = {}, {}
        for route in ROUTES:
            arms = {"LORO": from_trace(case[route]["loro"], truth[route])}
            donors = tuple(x for x in ROUTES if x != route)
            ratios, bins = [], []
            for b in range(3):
                values = {}
                for donor in donors:
                    prep = prepared[route][donor]
                    idx = _indices(prep, b)
                    if _support(prep, idx)["supported"]:
                        values[donor] = float(np.var(prep["parts"]["slow"][idx, 1]))
                if len(values) == 2 and min(values.values()) > MIN_VARIANCE:
                    ratios.append(max(values.values()) / min(values.values()))
                bins.append(dict(bin=b, variance=values, ratio=ratios[-1] if len(values) == 2 and min(values.values()) > MIN_VARIANCE else None))
            if len(ratios) != 3:
                raise ValueError(f"Missing conservative multiplier donor support for {route}")
            k = max(ratios)
            donor_var[route] = dict(multiplier=k, distances=bins)
            choose = noise_for(params, route, "distance")
            def amplified(d, g):
                fitted = choose(d, g)
                return None if fitted is None else replace(fitted, slow=fitted.slow * k)
            for name, noise in (("distance", choose), ("conservative", amplified)):
                trace = replay_ks(case[route], *env, noise)
                arms[name] = trace_out("C5", name, trace, route)
            rows[route] = arms
        score = artifact_score(rows, time, [("distance", "LORO"), ("conservative", "LORO"), ("conservative", "distance")])
        decision = acceptance(score, ("distance", "conservative"))
        complete("C5", dict(donor_var=donor_var, scores=score, disposition=decision,
                           clipping={k: v for k, v in clip.items() if k.startswith("C5_")}))
        if decision["conservative"]["status"] != "PASS":
            study_c4(folder, complete, trace_out, case, fit, time, truth, prepared, params, env)
        write(folder / "CHECKS.json", dict(covariance_gate=check_summaries, clipping=clip))
        report.update(status="PASS_EXECUTION", exit_code=0)
    except BaseException as exc:
        report.update(status="FAIL_EXECUTION", exit_code=1, error=repr(exc))
        raise
    finally:
        report.update(finish_utc=now(), outputs={p.name: sha(p) for p in sorted(folder.iterdir()) if p.is_file()})
        write(folder / "EXECUTION.json", report)


def study_c4(folder, complete, trace_out, case, fit, time, truth, prepared, params, env):
    from run_ks import D23
    from verify_s2 import from_trace
    rows, fits = {}, {}
    for route in ROUTES:
        prior = {route: case[route]["loro"]}
        donors = tuple(r for r in ROUTES if r != route)
        for donor in donors:
            prior[donor] = load(D23 / "d2" / f"M3_{route}_donor_{donor}.npz")
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
    complete("C4", dict(fits=fits, scores=score, disposition=acceptance(score, FEATURES)))


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze()
    elif sys.argv[1] == "run":
        run(Path(sys.argv[2]).resolve())
    else:
        raise SystemExit("Use freeze or run OUT")
