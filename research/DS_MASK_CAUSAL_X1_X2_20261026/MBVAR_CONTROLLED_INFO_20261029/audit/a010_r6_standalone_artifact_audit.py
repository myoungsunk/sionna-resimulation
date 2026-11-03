"""A010 R6 standalone arithmetic check. SELF_REVIEW_ONLY, technical evidence.
Never import implementation modules, never run DEV3, HOLDOUT2 or physical RT.
Validates original S1V5 900/901 zip+arrays, 7-array optimizer receipt digests,
saved full C10/NEES4; optional archived DEV2 K1/K2 & original GEN 48 arrays.
Does NOT independently rerun the nonlinear solver/Hessian.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile
import numpy as np

SMOKE_ARTIFACT_SHA = "e227582fb99e26e8d943404b409d33b37a72acaba8ee757443ccff141f9b239b"
CANON_SHA = "316efcc04946197cbb5c10417e3b6bfca3e4e8f5e4d3433535dfbba09b7bb9f3"
NEW_DEV2_A_SHA = "3eaddbed37eddbe13572b74925ff67057fb0490e5dbd403d9370d666242b2fcc"
NEW_DEV2_B_SHA = "0ba7f8ed0b7d9a0ebd5ad14fd7c327337b2ad77f086a845cc77e1f85cecdc98c"
SMOKE_SOURCE_SHA = "6733fb52510e7f4687a8f117f6a01e22b703538e"
DEV2_SOURCE_SHA = "ecb6d58199e8fd47d50ba54696b5fbe4b054ee0d"
SEVEN = ("z", "x0", "ds_m", "gy_m", "Sigma_model", "dts", "taps")
DREF = np.array([.02, .02, np.deg2rad(.25), np.deg2rad(.01)])

def sha(b):
    return hashlib.sha256(b).hexdigest()

def arr_sha(a):
    a = np.ascontiguousarray(a)
    return sha(a.dtype.str.encode() + str(a.shape).encode() + a.tobytes())

def fail(code):
    raise ValueError(code)

def check(test, code):
    if not test:
        fail(code)

def jl(z, p):
    return json.loads(z.read(p))

def csv_rows(z, p):
    return list(csv.DictReader(io.StringIO(z.read(p).decode())))

def keys(r):
    return tuple(str(r[k]) for k in ("field", "role", "cell", "sensor_seed", "arm"))

def matrix(row):
    p = np.zeros((4, 4))
    for i in range(4):
        for j in range(i, 4):
            p[i, j] = p[j, i] = float(row[f"C10rot_{i}{j}"])
    return p

def wrap(x):
    return math.atan2(math.sin(x), math.cos(x))

def nees_from_truth(row, truth, anchor):
    error = np.asarray(truth[-1], dtype=float) - np.array(
        [float(row[f"xend_{i}"]) for i in range(4)])
    error[2] = wrap(float(error[2]))
    u = np.asarray(truth[-1, :2], float) - anchor
    u /= np.linalg.norm(u)
    t = np.eye(4)
    t[0, :2] = u
    t[1, :2] = [-u[1], u[0]]
    e = t @ error
    p = matrix(row)
    check(np.isfinite(p).all() and np.linalg.eigvalsh(p)[0] > 0, "ERR_R6_NONSPD_C10")
    return float(np.linalg.norm(np.linalg.solve(np.linalg.cholesky(p), e)) ** 2)

def read_generator(gen):
    """48 original A010-P0 archived arrays; additional ledger diagnostic rows aren't ZIP members."""
    gen = Path(gen)
    mani = json.loads((gen / "MANIFEST.json").read_text())
    expected = mani["output_sha256"]
    for name, digest in expected.items():
        check(sha((gen / name).read_bytes()) == digest, "ERR_R6_GEN_OUTPUT_SHA_" + name)
    zdata = (gen / "A010_CANONICAL_INPUTS.zip").read_bytes()
    check(sha(zdata) == CANON_SHA, "ERR_R6_GEN_CANON_SHA")
    with zipfile.ZipFile(io.BytesIO(zdata)) as z:
        check(z.namelist() == ["canonical.npz"], "ERR_R6_GEN_ZIP_MEMBERS")
        with np.load(io.BytesIO(z.read("canonical.npz")), allow_pickle=False) as v:
            arrays = {k:np.array(v[k]) for k in v.files}
    rows = list(csv.DictReader((gen / "A010_INPUT_CANONICAL_SHA.csv").open()))
    checked = set()
    for row in rows:
        if row["array"] in ("z_S1V3_receipt", "Sigma_model_fp_check"):
            continue
        k = row["case"]+"|"+row["array"]
        check(k in arrays and k not in checked, "ERR_R6_GEN_ARRAY_KEY")
        a = arrays[k]
        check(arr_sha(a) == row["sha256"], "ERR_R6_GEN_ARRAY_SHA_"+k)
        check(a.dtype.str == row["dtype"] and a.shape == ast.literal_eval(row["shape"]),
              "ERR_R6_GEN_ARRAY_SCHEMA_"+k)
        checked.add(k)
    check(checked == set(arrays) and len(checked) == 48, "ERR_R6_GEN_48_ARRAYS")
    return arrays, dict(n_arrays_rehashed=48,
                        canonical_zip_sha256=sha(zdata),
                        manifest_sha256=sha((gen/"MANIFEST.json").read_bytes()))

def verify_smoke(path, anchor):
    path = Path(path)
    check(sha(path.read_bytes()) == SMOKE_ARTIFACT_SHA, "ERR_R6_OUTER_ARTIFACT_SHA")
    details, fields, arrs, counts = [], {}, {}, 0
    with zipfile.ZipFile(path) as z:
        check(len(z.namelist()) == len(set(z.namelist())), "ERR_R6_OUTER_DUPLICATE")
        m = jl(z, "e2e/s1agg/MANIFEST.json")
        check(m["source_git_sha"] == SMOKE_SOURCE_SHA, "ERR_R6_SOURCE_SHA")
        for f in (900, 901):
            filename = f"S1V5_INPUTS_SMOKE_{f}.zip"
            blob = z.read("e2e/s1agg/" + filename)
            idx = jl(z, f"e2e/s1agg/S1V5_INPUT_HASHES_SMOKE_{f}.json")
            check(sha(blob) == idx["zip_sha256"] == m["output_sha256"][filename],
                  "ERR_R6_RECEIPT_ZIP_SHA")
            with zipfile.ZipFile(io.BytesIO(blob)) as iz:
                names = iz.namelist()
                check(len(names) == len(set(names)), "ERR_R6_RECEIPT_DUPLICATE")
                check({n[:-4] for n in names} == set(idx["array_sha256"]), "ERR_R6_RECEIPT_KEYSET")
                for key in sorted(idx["array_sha256"]):
                    v = np.load(io.BytesIO(iz.read(key + ".npy")), allow_pickle=False)
                    check(arr_sha(v) == idx["array_sha256"][key], "ERR_R6_ARRAY_SHA")
                    check(v.dtype.str == idx["array_dtype"][key]
                          and list(v.shape) == idx["array_shape"][key], "ERR_R6_ARRAY_SCHEMA")
                    if v.dtype.kind in "fiu":
                        check(np.isfinite(v).all(), "ERR_R6_ARRAY_NONFINITE")
                    check(key.split("|")[1 if key.startswith(("MAT|","TRUTH|")) else 0] == str(f),
                          "ERR_R6_FIELD_LEAK")
                    arrs[key] = v
                    counts += 1
            fields[str(f)] = dict(n_arrays=len(idx["array_sha256"]),
                                  zip_sha256=sha(blob))
        check(counts == 256, "ERR_R6_ARRAY_COUNT")
        s1 = csv_rows(z, "e2e/s1agg/S1V5_RESULTS_SMOKE.csv")
        c3 = csv_rows(z, "e2e/c3agg/C3V5_ROWS.csv")
        check(len(s1) == 44 and len(c3) == 10, "ERR_R6_SMOKE_ROWS")
        check(len({keys(x) for x in s1}) == 44 and len({keys(x) for x in c3}) == 10,
              "ERR_R6_DUPLICATE_KEYS")
        s1map = {keys(x):x for x in s1}
        for r in c3:
            k = keys(r)
            check(k in s1map, "ERR_R6_MISSING_SOURCE_ROW")
            f, role, cell, seed, arm = k
            base = "|".join((f, role, cell, seed))
            truth_key = "|".join(("TRUTH", f, role, cell))
            actual = dict(z=arrs[base+"|z"], x0=arrs[base+"|x0"],
                ds_m=arrs[base+"|ds_m"], gy_m=arrs[base+"|gy_m"],
                Sigma_model=arrs["MAT|"+f+"|"+role+"|"+cell+"|"+arm+"|Sig_model"],
                dts=arrs[truth_key+"|dts"], taps=arrs[base+"|taps"])
            h = {name:arr_sha(actual[name]) for name in SEVEN}
            digest = sha(json.dumps(h, sort_keys=True).encode())
            check(digest == r["OPTIMIZER_BOUNDARY_INPUT_SHA"], "ERR_R6_CALL_BOUNDARY_DIGEST")
            check(str(r["OPTIMIZER_BOUNDARY_EXACT"]).lower()=="true" and
                  int(r["OPTIMIZER_BOUNDARY_ARRAYS_CHECKED"])==7,
                  "ERR_R6_CALL_BOUNDARY_RECORDED")
            p, q = matrix(r), matrix(s1map[k])
            check(np.isfinite(p).all() and np.linalg.eigvalsh(p)[0]>0, "ERR_R6_C10_SPD")
            natural = np.sqrt(np.maximum(np.diag(p),np.diag(q)))
            c10_rel=float(np.max(np.abs(p-q)/(natural[:,None]*natural[None,:])))
            delta=float(max(abs(float(r["xend_"+str(j)])-float(s1map[k]["xend_"+str(j)]))
                            for j in range(4)))
            cost=float(abs(float(r["cost"])-float(s1map[k]["cost"])))
            nees=nees_from_truth(r, arrs[truth_key+"|Xtrue"], anchor)
            ndiff=float(abs(nees-float(r["nees4_C10"])))
            check(c10_rel<=1e-3 and delta<=1e-6 and cost<=1e-6 and ndiff<=1e-7,
                  "ERR_R6_S1_C3_NUMERIC_MISMATCH")
            details.append(dict(key="|".join(k), c10_min_eig=float(np.linalg.eigvalsh(p)[0]),
                nees4_recomputed=nees, abs_nees_diff=ndiff, full_c10_natural_rel=c10_rel,
                max_state_diff=delta, cost_diff=cost, input_sha=digest))
        stat = jl(z, "e2e/c3agg/C3V5_STATUS.json")
        cov = stat["criteria"]["rows"]["registered_key_set"]
        check(cov["n_expected"]==72 and cov["n_missing_keys"]==62
              and cov["n_duplicate_keys"]==0 and stat["status"]=="FAIL"
              and stat["G5_NUMERIC_REPLAY"]["status"]=="FAIL"
              and not stat["science_release_allowed"], "ERR_R6_SCIENCE_UNAUTHORISED")
    return dict(outer_zip_sha256=sha(path.read_bytes()),fields=fields,
        n_original_arrays_rehashed=counts,n_optimizer_input_digests_rederived=len(details),
        c3_replay_rows=len(details),max_nees4_abs_diff=max(x["abs_nees_diff"] for x in details),
        max_c10_natural_rel=max(x["full_c10_natural_rel"] for x in details),
        max_cost_abs_diff=max(x["cost_diff"] for x in details),
        s1_rows=44, c3_rows=10, registered_c3=72, missing_c3=62, rows=details)

def verify_two_runner(a, b, canon, anchor):
    output={}
    rows=[]
    for path,dig,label in ((a,NEW_DEV2_A_SHA,"a"), (b,NEW_DEV2_B_SHA,"b")):
        path=Path(path)
        check(sha(path.read_bytes())==dig,"ERR_R6_DEV2_ZIP_DIGEST_"+label)
        with zipfile.ZipFile(path) as zz:
            r=jl(zz,"REPLAY_RECEIPT.json")
        check(r["source_git_sha"]==DEV2_SOURCE_SHA and
              r["input_sha256"]==CANON_SHA and
              r["allowed_cases"]==["K1","K2"],"ERR_R6_DEV2_SOURCE_SCOPE")
        for x in r["rows"]:
            p=matrix(x)
            check(np.linalg.eigvalsh(p)[0]>0,"ERR_R6_DEV2_SPD")
            true=canon[x["case"]+"|Xtrue"]
            n=nees_from_truth(x,true,anchor)
            check(abs(n-float(x["nees4_C10"]))<=1e-7,"ERR_R6_DEV2_NEES")
        rows.append(r)
        output[label]=dict(boot_id=r["runner_boot_id"],runner_id=r["runner_id"],
                           source_sha=r["source_git_sha"],n_rows=len(r["rows"]))
    aa, bb=rows
    check(aa["runner_boot_id"]!=bb["runner_boot_id"],"ERR_R6_SINGLE_VM")
    check(aa["source_code_sha256"]==bb["source_code_sha256"] and
          aa["input_evidence"]==bb["input_evidence"],"ERR_R6_SOURCE_MISMATCH")
    metrics=[]
    for x,y in zip(aa["rows"],bb["rows"]):
        check(x["case"]==y["case"],"ERR_R6_K1K2_KEYSET")
        d=np.array([float(x["xend_"+str(j)])-float(y["xend_"+str(j)])
                    for j in range(4)])
        d[2]=wrap(d[2])
        state=float(np.max(np.abs(d)/DREF))
        C,D=matrix(x),matrix(y)
        n=np.sqrt(np.maximum(np.diag(C),np.diag(D)))
        full=float(np.max(np.abs(C-D)/(n[:,None]*n[None,:])))
        cost=abs(float(x["cost"])-float(y["cost"]))
        check(state<=1e-6 and full<=1e-3 and cost<=1e-6 and
              x["n_alt_ambiguous"]==y["n_alt_ambiguous"] and
              x["class_v31"]==y["class_v31"] and x["ms_best_k"]==y["ms_best_k"],
              "ERR_R6_DEV2_NUMERIC")
        metrics.append(dict(case=x["case"],dref=state,c10_rel=full,cost_abs_diff=cost,
                            n_ambiguous_starts=x["n_alt_ambiguous"]))
    return dict(runners=output,n_cases=2,checks=metrics,science_claim="TECHNICAL_REPLAY_ONLY")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--smoke-zip",required=True)
    ap.add_argument("--generator-root",required=True)
    ap.add_argument("--plan-parameters",required=True)
    ap.add_argument("--runner-a",required=True)
    ap.add_argument("--runner-b",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    world=json.loads(Path(args.plan_parameters).read_text())["world"]
    anchor=np.asarray(world["anchors"]["A"][:2],float)
    canon,gen=read_generator(args.generator_root)
    smoke=verify_smoke(args.smoke_zip,anchor)
    dev2=verify_two_runner(args.runner_a,args.runner_b,canon,anchor)
    out=dict(schema="A010_R6_STANDALONE_ARITHMETIC_V1",
        status="ARITHMETIC_EVIDENCE_VERIFIED",subject_sha=SMOKE_SOURCE_SHA,
        dev2_sha=DEV2_SOURCE_SHA,GEN=gen,SMOKE=smoke,DEV2=dev2,
        mathematical_independence="No import of S1V5/C3V5/AV helper; independent NumPy Cholesky and bytes digests",
        limit="NOT nonlinear solver/Hessian re-derivation; NOT an independent human auditor signature",
        role="SELF_REVIEW_ONLY",independent_auditor_signed=False,
        science_frozen=False,dev3="NO-GO",holdout2="NO-GO",rt="NO-GO")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("A010_R6_STANDALONE_ARITHMETIC_PASS",len(canon),smoke["n_original_arrays_rehashed"],smoke["n_optimizer_input_digests_rederived"],len(dev2["checks"]))
if __name__=="__main__":
    main()
