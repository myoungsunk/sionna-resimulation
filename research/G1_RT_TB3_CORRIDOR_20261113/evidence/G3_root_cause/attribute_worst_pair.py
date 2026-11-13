"""Attribute the worst paired 400k-reference discrepancy by path membership."""
import json
import sys
from pathlib import Path

import numpy as np

from qclean_uwb.drivesim import pattern_apply as p
from qclean_uwb.drivesim.rf_store import h_for_antenna_yaws, load_banks, load_trace
from qclean_uwb.features.fp_power import signed_s_single_tx
from run_tb3_g1_pilot import sha, write

base, run, out = map(Path, sys.argv[1:])
gate = run / "EVALUATION/analysis/G3.json"
worst = json.loads(gate.read_text())["pooled"]["worst_by_abs_ds"][0]
case, tag, yaw = (worst[k] for k in ("case", "tag", "yaw_deg"))
paths = {
    "old_dense": base / "output" / case / "bin_by_bin" / f"{tag}_trace.npz",
    "prod": base / "output" / case / "node_interpolation" / f"{tag}_trace.npz",
    "new_dense": run / "output" / case / "bin_by_bin" / f"{tag}_trace.npz",
}
traces = {k: load_trace(v) for k, v in paths.items()}
dense = traces["new_dense"]
direction = p.path_directions(*dense["ang"])
banks = load_banks()
freqs = banks[0].freqs_hz
scores = {k: float(signed_s_single_tx(h_for_antenna_yaws(t, banks, [yaw])[0], freqs)[0])
          for k, t in traces.items()}
comparisons = {}
for key in ("old_dense", "prod"):
    t = traces[key]
    matched, extra = p.match_partial(dense["tau"], direction, t["tau"], p.path_directions(*t["ang"]))
    new_indices = np.flatnonzero(matched < 0)
    amp = np.linalg.norm(dense["jones"], axis=(2, 3))
    rel = amp / np.maximum(np.linalg.norm(amp, axis=1, keepdims=True), 1e-300)
    keep = np.flatnonzero(matched >= 0)
    filtered = dense | dict(jones=dense["jones"][:, keep], tau=dense["tau"][keep],
                            ang=dense["ang"][:, keep], present=dense["present"][:, keep])
    s = float(signed_s_single_tx(h_for_antenna_yaws(filtered, banks, [yaw])[0], freqs)[0])
    comparisons[key] = dict(
        path_count=len(t["tau"]), dense_only=[
            dict(path_index=int(i), tau_ns=float(dense["tau"][i] * 1e9),
                 present_bins=int(dense["present"][:, i].sum()), peak_rel_jones=float(rel[:, i].max()))
            for i in new_indices
        ],
        old_only=[dict(path_index=int(i), tau_ns=float(t["tau"][i] * 1e9)) for i in extra],
        signed_s_reference_shared_paths=s, abs_ds_after_removing_dense_only=abs(s-scores[key]))
old = traces["old_dense"]
indices, extra = p.match_partial(dense["tau"], direction, old["tau"], p.path_directions(*old["ang"]))
if np.any(indices < 0) or len(extra):
    raise ValueError("Expected equal union path membership")
old_present = old["present"][:, indices]
new_present = dense["present"]
aligned = old["jones"][:, indices]
delta = np.linalg.norm(dense["jones"] - aligned, axis=(2, 3))
paths_disagree = np.flatnonzero(np.any(old_present != new_present, axis=0))
replaced = dense["jones"].copy()
replaced[:, paths_disagree] = aligned[:, paths_disagree]
s_replace = float(signed_s_single_tx(
    h_for_antenna_yaws(dense | dict(jones=replaced), banks, [yaw])[0], freqs)[0])
frequency_comparison = dict(
    path_masks=[dict(path_index=int(i), old_path_index=int(indices[i]), delay_ns=float(dense["tau"][i] * 1e9),
                     absent_100k=np.flatnonzero(~old_present[:, i]).tolist(),
                     absent_400k=np.flatnonzero(~new_present[:, i]).tolist()) for i in paths_disagree],
    max_absolute_jones_delta_both_present=float(delta[old_present & new_present].max()),
    abs_ds_after_replacing_disagreeing_paths=abs(s_replace - scores["prod"]))
write(out, dict(frequency_comparison=frequency_comparison, kind="POST_HOC_PATH_MEMBERSHIP_ATTRIBUTION", worst=worst, score=scores,
                revalidation_sha256=sha(gate), trace_sha256={k: sha(v) for k,v in paths.items()},
                reference_path_count=len(dense["tau"]), comparisons=comparisons))
