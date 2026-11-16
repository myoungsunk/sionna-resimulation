
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

art = Path("D:/SLAM_bot/artifacts")
diag = art / "G1_INT_DIAG_001_20261115"
stage = art / "G1_HFKI_M5_20261116/attempt_02/stage2"
contract = json.loads((stage / "RUN_CONTRACT.json").read_bytes())
receipt = json.loads((stage / "EXECUTION.json").read_bytes())
assert receipt["contract_sha256"] == hashlib.sha256((stage / "RUN_CONTRACT.json").read_bytes()).hexdigest()
base = json.loads((diag / "RUN_CONTRACT.json").read_bytes())
sys.path[:0] = [str(diag / "continuation_ks"), str(diag / "continuation_d2_d3"),
                str(art / "G1_EXPOSURE_M1_M4_20261116"), base["s2"], str(Path(base["native"]) / "src")]
from exposure_score import branch_metrics, _gates
from ks_diagnostics import boot_indices, BOOTSTRAP_SEED, scores_with_blocks
from qclean_uwb.fp_sc.e0_baseline import load_original_model, SPEC
from replay_s2 import validate_trace
from verify_s2 import from_trace

def checked(path, digest):
    payload = Path(path).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == digest, path
    return payload

def arrays(rec):
    from io import BytesIO
    with np.load(BytesIO(checked(rec["path"], rec["sha256"])), allow_pickle=False) as data:
        return {k: data[k] for k in data.files}

cell = next(cell for cell in contract["cells"] if cell["route"] == "R5")
p, ev, baseline, gate = (arrays(cell[key]) for key in ("online", "evaluator", "loro_trace", "fixed_gate_trace"))
native = Path(base["native"])
core, online, model, hashes = load_original_model(native)
for key, rec in contract["model_assets"].items():
    checked(rec["path"], rec["sha256"])
assert SPEC == dict(anchor=(10., 0., 2.65), robot_z_m=.45, mount_deg=0.)
t, truth = p["t"], ev["truth"]
mask, ref = baseline["mask"], baseline["Reff"]
assert (len(t), int(mask.sum())) == (1415, 1384)
for other in (ev, baseline, gate):
    for key in ("t", "pose_id"):
        np.testing.assert_array_equal(p[key], other[key])
np.testing.assert_array_equal(mask, gate["mask"])
rho = np.linalg.norm(baseline["prior"][:, :2] - np.asarray(SPEC["anchor"][:2]), axis=1)
near = rho < 3.
far = ~near
nav = ("x", "P", "prior", "Pprior", "h", "H", "Reff", "K", "nu", "S")
identity = np.eye(4)
none = np.zeros(len(t), dtype=bool)

def replay(schedule, protect=none, axis=None, weaken=False):
    x, P = p["x0"].copy(), p["P0"].copy()
    rows = []
    for i, accepted in enumerate(mask):
        prior, pp = online.predict(core, x, P, i, p)
        h, H = (array[0] for array in model.batch(prior[None], SPEC))
        nu = p["z"][i] - h - p["muMB"][i]
        R = ref[i] if protect[i] and (axis is None or weaken) else schedule[i]
        x, P, K, S = online.joseph(prior, pp, H, nu, R, accepted, 1.)
        if protect[i] and accepted and axis is not None:
            # Isolate the s contribution conditional on the range innovation.
            # Its coefficient on nu_s equals the corresponding column of joint K.
            _, _, K0, S0 = online.joseph(prior, pp, H, nu, schedule[i] if weaken else ref[i], True, 1.)
            alpha = S[1, 0] / S[0, 0]
            assert S[1,0] == S0[1,0] and S[0,0] == S0[0,0]
            k = K[axis, 1]
            K[axis, 1] = K0[axis, 1]
            K[axis, 0] -= (K[axis, 1] - k) * alpha
            x = prior + K @ nu
            x[2] = (x[2] + np.pi) % (2*np.pi) - np.pi
            A = identity - K @ H
            P = A @ pp @ A.T + K @ R @ K.T
            P = (P + P.T) * .5
        rows.append((x, P, prior, pp, h, H, R, K, nu, S))
    trace = {name: np.stack(col) for name, col in zip(nav, zip(*rows), strict=True)}
    trace["mask"] = mask.copy()
    validate_trace(trace)
    np.testing.assert_array_equal(trace["x"][~mask], trace["prior"][~mask])
    np.testing.assert_array_equal(trace["P"][~mask], trace["Pprior"][~mask])
    return trace

def parity(a, b):
    for key in nav:
        np.testing.assert_allclose(a[key], b[key], atol=1e-10, rtol=0, err_msg=key)
    np.testing.assert_array_equal(a["mask"], b["mask"])
    return max(float(abs(a[k] - b[k]).max()) for k in nav)

def rms(v):
    return float(np.sqrt(np.square(v).mean()))

model_label = "A2_4"
name = f"R5_{model_label}.npz"
archived = arrays({"path": stage / name, "sha256": receipt["outputs"][name]})
for key in ("t", "pose_id"):
    np.testing.assert_array_equal(archived[key], p[key])
schedule = archived["Reff"]
np.testing.assert_array_equal(schedule[:, 0], ref[:, 0])
np.testing.assert_array_equal(schedule[:, 1, 0], ref[:, 1, 0])
assert np.all(schedule[:, 1, 1] >= ref[:, 1, 1])
all_replayed = replay(schedule)
result = {"model": model_label, "parity_all": parity(all_replayed, archived)}
base_check = replay(ref) if model_label == "A2_4" else baseline
result["parity_base"] = parity(base_check, baseline)
traces = {"BASE": base_check, "ALL": all_replayed,
          "NEAR": replay(schedule, near), "FAR": replay(schedule, far)}
for label, region in (("NEAR", near), ("FAR", far)):
    np.testing.assert_array_equal(traces[label]["Reff"][region], ref[region])
    np.testing.assert_array_equal(traces[label]["Reff"][~region], schedule[~region])
for axis_name, axis in (("Y", 1), ("PSI", 2)):
    entry = replay(schedule, near, axis, weaken=True)
    np.testing.assert_array_equal(entry["Reff"], traces["NEAR"]["Reff"])
    before = np.flatnonzero(near & mask)[0]
    np.testing.assert_array_equal(entry["prior"][before], traces["NEAR"]["prior"][before])
    allowed = np.arange(4) != axis
    np.testing.assert_array_equal(entry["K"][before, allowed], traces["NEAR"]["K"][before, allowed])
    np.testing.assert_array_equal(entry["K"][before, axis], traces["ALL"]["K"][before, axis])
    traces[f"WEAK_{axis_name}"] = entry

rows = {name: from_trace(trace, truth) for name, trace in traces.items()}
contrasts = [(label, "ALL") for label in traces if label not in ("BASE", "ALL")]
contrasts.append(("NEAR", "FAR"))
contrasts.extend((name, "NEAR") for name in ("WEAK_Y", "WEAK_PSI"))
contrasts.append(("WEAK_Y","WEAK_PSI"))
scores = scores_with_blocks({"R5": rows}, {"R5": t}, contrasts, blocks=(10,))
point = scores["point"]["R5"]
blocks = scores["blocks"]["10"]["by_group"]["R5"]
idx, full_blocks = boot_indices(t, 10, np.random.default_rng(BOOTSTRAP_SEED))
result["full_blocks_10s"] = full_blocks
result["region"] = {r: {"packets": int(selector.sum()), "accepted": int((selector & mask).sum()),
                        "last_first_s": [float(t[selector][0]), float(t[selector][-1])]}
                    for r, selector in (("near", near), ("far", far))}
result["region"]["rho_min_max"] = [float(rho.min()), float(rho.max())]
squared_y = {label: np.square((trace["x"][:, 1] - truth[:, 1])*100.) for label, trace in traces.items()}
result["arms"] = {}
for label, trace in traces.items():
    if not label.startswith("WEAK_"):
        continue
    branch = branch_metrics(trace, truth, t)
    yerr = (trace["x"][:, 1] - truth[:, 1])*100.
    crossings = branch["passages"]
    window = (t >= crossings[0]["time_s"] - 5.) & (t < crossings[0]["time_s"])
    update_window = window & mask
    near_before = near & (t < crossings[0]["time_s"])
    improvement = _gates(point, blocks, label, False, branch["mirror_fail_count"])
    cond_nu = trace["nu"][:, 1] - (trace["S"][:, 1, 0] / trace["S"][:, 0, 0])*trace["nu"][:, 0]
    result["arms"][label] = dict(point[label], y_cm=rms(yerr),
        y_cm_near=rms(yerr[near]), y_cm_far=rms(yerr[far]),
        near_before_first_pass_y_cm=rms(yerr[near_before]), pre_first_y_cm=rms(yerr[window]),
        conditional_s_update_first5s_y_cm=rms(100*trace["K"][update_window,1,1]*cond_nu[update_window]),
        conditional_s_update_first5s_psi_deg=rms(np.rad2deg(trace["K"][update_window,2,1]*cond_nu[update_window])),
        crossings=[{"t_s": row["time_s"], "mirror_longest_s": row["longest_mirror_duration_s"],
                    "first_mirror_run": row["mirror_runs"][0] if row["mirror_runs"] else None}
                   for row in crossings],
        mirror=branch["mirror_fail_count"], integrity=improvement["integrity_ok"],
        accuracy=improvement["accuracy_ok"], heading95_ci=blocks["absolute_ci95"][label]["heading95_coverage"])
result["paired10s"] = {}
for label, ref_label in contrasts:
    if not label.startswith("WEAK_"):
        continue
    key = f"{label}-{ref_label}"
    diff_y = np.sqrt(squared_y[label][idx].mean(axis=1)) - np.sqrt(squared_y[ref_label][idx].mean(axis=1))
    measures = blocks["paired_ci95"][key]
    result["paired10s"][key] = dict(y_rmse_cm=np.quantile(diff_y, [.025,.975]).tolist(),
        **{m: measures[m] for m in ("xy_rmse_cm", "heading_rmse_deg", "heading95_coverage")})
def compact(number):
    if isinstance(number, float):
        return round(number, 6)
    if isinstance(number, list):
        return [compact(value) for value in number]
    if isinstance(number, dict):
        return {key: compact(value) for key, value in number.items()}
    return number
print(json.dumps(compact(result), ensure_ascii=True), flush=True)
