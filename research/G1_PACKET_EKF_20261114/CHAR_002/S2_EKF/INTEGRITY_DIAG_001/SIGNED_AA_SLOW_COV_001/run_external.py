"""P4 separate anchor A and unsealed G-T1_B support, frozen B fits only."""
import argparse
import datetime as dt
import json
from pathlib import Path
import numpy as np
import covariance_core_v2 as C
from p0_inputs_v2 import RAW, put, sha, load_source, independent_o30, quant
from p1_design_v2 import base_valid, in_envelope, bin_ids, supported_pairs, components
from run_covariance import blocks, paired_report


def extract(model, observation, full, los, truth, spec):
    arrays = {"truth": truth}; chunks = {k: [] for k in ["s_full", "s_los", "a_truth", "source_s"]}
    errors = {s: [] for s in [.1, .01]}; stable = {s: [] for s in [.1, .01]}; taps = []
    for start in range(0, len(truth), 64):
        end = min(start+64, len(truth)); x = truth[start:end]
        h, H, diag = model.batch(x, spec, gradient=True, return_diagnostics=True)
        chunks["source_s"].append(h[:, 1]); chunks["a_truth"].append(H[:, 1, 2])
        for name, source in [("s_full", full), ("s_los", los)]:
            s, tap, cir = independent_o30(source[start:end, :, :, 0])
            ref = observation.first_path_batch(cir, model.freqs[1]-model.freqs[0])
            assert np.array_equal(tap, ref["index"]) and abs(s-ref["s"]).max() <= 1e-12
            chunks[name].append(s)
            if name == "s_los": taps.append(tap != diag["tap"])
        for step in [.1, .01]:
            delta = np.zeros_like(x); delta[:, 2] = np.radians(step)
            hm, _, dm = model.batch(x-delta, spec, gradient=False, return_diagnostics=True)
            hp, _, dp = model.batch(x+delta, spec, gradient=False, return_diagnostics=True)
            good = np.ones(len(x), bool)
            for name in ["tap", "strong_port", "cells"]:
                good &= ((dm[name] == diag[name]) & (dp[name] == diag[name])).reshape(len(x), -1).all(axis=1)
            stable[step].append(good)
            errors[step].append(abs((hp[:, 1]-hm[:, 1])/(2*np.radians(step))-H[:, 1, 2])/np.maximum(1, abs(H[:, 1, 2])))
    arrays.update({k: np.concatenate(v) for k, v in chunks.items()})
    arrays["e_rf"] = arrays["s_full"]-arrays["s_los"]
    parity = quant(abs(arrays["source_s"]-arrays["s_los"]))
    check = dict(parity=parity, tap_mismatches=int(np.concatenate(taps).sum()), FD={})
    passed = parity["max"] <= 1e-4 and check["tap_mismatches"] == 0
    for step, tolerance in [(.1, 1e-4), (.01, 1e-5)]:
        good, err = np.concatenate(stable[step]), np.concatenate(errors[step])
        passed = passed and bool(good.any() and err[good].max() <= tolerance)
        check["FD"][str(step)] = dict(stable=int(good.sum()), nonsmooth=int((~good).sum()), stable_error=quant(err[good]))
    check["passed"] = bool(passed)
    arrays["rho_m"] = np.linalg.norm(truth[:, :2]-np.array(spec["anchor"][:2]), axis=1)
    arrays["arc_m"] = np.r_[0., np.cumsum(np.linalg.norm(np.diff(truth[:, :2], axis=0), axis=1))]
    arrays["yaw_arc_rad"] = np.r_[0., np.cumsum(abs((np.diff(truth[:, 2])+np.pi)%(2*np.pi)-np.pi))]
    return arrays, check


def run(attempt, gt1):
    out = attempt/"p4"
    out.mkdir(exist_ok=False)
    contract = dict(stage="P4_DIAGNOSTIC_ONLY", timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        implementation_sha256=sha(__file__),
        scope="anchor A timed R2/R4/R5; unsealed G-T1_B geometry, unique original RF poses only",
        fits="primary B donor fits fixed; no external residual fits or recentering; no primary decision changes",
        GT1="set/repeat labels do not make reused RF poses independent; no invented times; no temporal score without a verified unique chronological grid",
        parity_and_FD="same max1e-4 LoS/tap exact and FD0.1deg1e-4/0.01deg1e-5 gates as P0; case fails closed",
        sealed="G-T2/G-V never opened")
    put(out/"RUN_CONTRACT.json", contract)
    model, observation, source_hashes = load_source()
    cases = json.loads((RAW/"CASES.json").read_bytes())
    fits = json.loads((attempt/"p3/FITS.json").read_bytes())
    splits = json.loads((attempt/"p1_revision_02/SPLITS.json").read_bytes())
    support, scores, hashes = {}, {}, {}
    for route in ["R2", "R4", "R5"]:
        meta = next(x for x in cases if x["case"] == route+"_aA_m0")
        pfull, plos, ppose = RAW/"FULL_RF"/f"H_{route}_aA_m0.npy", RAW/f"H_LoS_{route}_aA_m0.npy", RAW/f"{route}_aA_m0/SAMPLES.json"
        for p in [pfull, plos, ppose]: hashes[str(p)] = sha(p)
        assert hashes[str(pfull)] == meta["input_H_sha256"] and hashes[str(plos)] == meta["H_sha256"]
        assert hashes[str(ppose)] == meta["samples_sha256"]
        poses = {p["pose_id"]: p for p in json.loads(ppose.read_bytes())}
        with np.load(attempt/f"P0_{route}.npz") as ref: t, pid = ref["t"], ref["pose_id"]
        truth = np.array([[poses[k]["x"], poses[k]["y"], np.radians(poses[k]["yaw_body_deg"])] for k in pid])
        full, los = np.load(pfull, mmap_mode="r")[pid], np.load(plos, mmap_mode="r")[pid]
        d, check = extract(model, observation, full, los, truth, dict(anchor=meta["anchor_xyz"], robot_z_m=meta["robot_z"], mount_deg=0))
        d.update(t=t, pose_id=pid)
        np.savez_compressed(out/f"A_{route}.npz", **d)
        key = "A_"+route
        if not check["passed"]:
            support[key] = dict(status="UNSUPPORTED_INPUT", checks=check); scores[key] = dict(status="NOT_SCORED_INPUT_GATE"); continue
        split = splits[route]
        mask = base_valid(d) & in_envelope(d, split["donor_envelope"])
        _, _, _, table = supported_pairs(d, mask)
        eligible = [b for b in split["eligible_rho_bins"] if table[b]["status"] == "SUPPORT_AVAILABLE"]
        support[key] = dict(status="SUPPORT_AVAILABLE" if eligible else "NO_SUPPORTED_EXTERNAL_FOLD", checks=check,
            bins=table, eligible_bins=eligible, common_envelope_packets=int(mask.sum()), primary_decision=False)
        if eligible and route in fits:
            mask &= np.isin(bin_ids(d), eligible)
            rr, nn = C.score_models(blocks(d, components(d, mask), fits[route]["donor_mean"]), fits[route])
            scores[key] = dict(status="DESCRIPTIVE_TRANSFER_ONLY", scores=paired_report(rr, d, split), numerics=nn,
                               mean_from="B donor only", no_anchor_fit=True)
        else: scores[key] = dict(status="NO_SUPPORTED_EXTERNAL_FOLD", packets=0)
        print(key, support[key]["status"], flush=True)
    manifest = json.loads((gt1/"MANIFEST.json").read_bytes())
    for filename, key in [("H_full.npy", "full_H_sha256"), ("H_LoS.npy", "los_H_sha256")]:
        hashes[str(gt1/filename)] = sha(gt1/filename)
        assert hashes[str(gt1/filename)] == manifest[key], "GT1_ORIGINAL_RF_HASH_MISMATCH"
    pose_rows = json.loads((gt1/"rf_poses.json").read_bytes())
    scene = json.loads((gt1/"SCENE_ENTRY.json").read_bytes())
    truth = np.array([[p["x"], p["y"], np.radians(p["yaw_body_deg"])] for p in pose_rows])
    d, check = extract(model, observation, np.load(gt1/"H_full.npy", mmap_mode="r"), np.load(gt1/"H_LoS.npy", mmap_mode="r"),
        truth, dict(anchor=scene["anchors_xyz_m"]["B"], robot_z_m=scene["rx_z_m"], mount_deg=manifest["mount_deg"]))
    np.savez_compressed(out/"GT1_B_GEOMETRY.npz", **d)
    samples = json.loads((gt1/"SAMPLES.json").read_bytes())
    groups = {}
    for row in samples:
        groups.setdefault((row.get("set", ""), row.get("motion", "")), set()).add(row["pose_id"])
    table = []
    for (label, motion), ids in sorted(groups.items()):
        ii = np.array(sorted(ids), int); a = d["a_truth"][ii]
        table.append(dict(set=label, motion=motion, unique_RF_poses=len(ii), positive=int((a >= .1).sum()),
                          negative=int((a <= -.1).sum()), abs_a=quant(abs(a)), raw_e=quant(d["e_rf"][ii])))
    support["GT1_B"] = dict(status="GEOMETRY_ONLY_NO_VERIFIED_CHRONOLOGICAL_GRID" if check["passed"] else "UNSUPPORTED_INPUT",
        unique_original_RF_poses=len(truth), sample_label_rows=len(samples), groups=table, checks=check,
        pair_temporal_support="NOT_ESTABLISHED; no synthetic clock assigned", no_shared_primary_p_value=True)
    scores["GT1_B"] = dict(status="NOT_SCORED_NO_VERIFIED_TIMED_GRID", reason="TEACH/REPEAT and yaw sweep labels can reuse RF poses; geometry support does not supply independent10s clusters")
    for filename in ["MANIFEST.json", "rf_poses.json", "SAMPLES.json", "SCENE_ENTRY.json"]: hashes[str(gt1/filename)] = sha(gt1/filename)
    put(out/"SUPPORT_EXTERNAL.json", support); put(out/"EXTERNAL_SCORES.json", scores); put(out/"SOURCE_HASHES.json", hashes)
    put(out/"STATUS.json", dict(status="EXECUTION_COMPLETE_WITH_SUPPORT_GATES", primary_scope_unchanged=True))
    (out/"SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file() and p.name != "SHA256SUMS"), encoding="utf-8")
    print("External support complete", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--attempt", type=Path, required=True); ap.add_argument("--gt1", type=Path, required=True)
    args = ap.parse_args(); run(args.attempt, args.gt1)
