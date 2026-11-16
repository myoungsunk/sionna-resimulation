"""Exact scalar AR ledger of entering btheta; no state counterfactual replay."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
M6 = ROOT.parent.parent / "G1_GM_THETA_M6_20261116/attempt_02"

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(name):
    with (ROOT/name).open(encoding="utf-8-sig") as stream: return list(csv.DictReader(stream))
def write(name,payload):
    with (ROOT/name).open("x",encoding="utf-8") as stream:
        json.dump(payload,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write("\n")

if __name__ == "__main__":
    write("MEMORY_SUPPLEMENT_CONTRACT.json",dict(root_contract_sha256=sha(ROOT.parent/"RUN_CONTRACT.json"),
        code_sha256=sha(__file__),scope="descriptive exact AR arithmetic and local-information quantiles only",
        thresholds_added=False,allowed_claim="direct scalar AR memory only; excludes carried pose and crosscovariance feedback"))
    entries=read("R5_NEAR_ENTRIES.csv"); timeline=read("R5_TIMELINE.csv")
    result=json.loads((ROOT/"RESULTS.json").read_text(encoding="utf-8"))
    output=[]; max_error=0.; source_hashes={}
    for seed in range(10,15):
        for arm in ("G1_LORO","G1_KI"):
            path=M6/("seed10" if seed==10 else "seed11_14")/f"seed{seed}/R5_{arm}.npz"
            source_hashes[str(path)]=sha(path)
            with np.load(path,allow_pickle=False) as packed:
                tr={key:packed[key] for key in ("t","alpha","b_theta","b_theta_prior","K_aug","nu")}
            U=np.einsum("ni,ni->n",tr["K_aug"][:,4],tr["nu"])
            for entry in [r for r in entries if int(r["seed"])==seed and r["arm"]==arm]:
                passage=int(entry["passage"]); cross=result["passages"][passage-1]["packet_index"]
                first=int(np.argmin(abs(tr["t"]-float(entry["entry_time_s"]))))
                memory=1.; updates=0.
                for i in range(first,cross+1):
                    if i>first: memory*=tr["alpha"][i];updates*=tr["alpha"][i]
                    updates+=U[i]
                incoming=memory*tr["b_theta_prior"][first]
                error=abs(incoming+updates-tr["b_theta"][cross]);max_error=max(max_error,float(error))
                selected=[r for r in timeline if int(r["seed"])==seed and r["arm"]==arm
                    and r["accepted"]=="1" and float(entry["episode_start_s"])<=float(r["t_s"])<=float(entry["episode_end_s"])]
                row=dict(seed=seed,arm=arm,passage=passage,entry_time_s=float(tr["t"][first]),cross_packet_time_s=float(tr["t"][cross]),
                    ar_memory_fraction=float(memory),entry_b_prior_deg=float(np.rad2deg(tr["b_theta_prior"][first])),
                    crossing_propagated_incoming_b_deg=float(np.rad2deg(incoming)),crossing_decayed_updates_deg=float(np.rad2deg(updates)),
                    crossing_b_posterior_deg=float(np.rad2deg(tr["b_theta"][cross])),ledger_error_rad=float(error))
                for key in ("local_y_loss_fraction","delta_jyy","nominal_jyy","marginal_jyy"):
                    vals=[float(r[key]) for r in selected]
                    for q in (50,95,100):row[f"near_{key}_p{q}"]=float(np.percentile(vals,q))
                output.append(row)
    assert max_error<1e-10
    with (ROOT/"R5_AR_MEMORY_AND_INFORMATION.csv").open("x",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(output[0]));writer.writeheader();writer.writerows(output)
    write("MEMORY_SUPPLEMENT_RECEIPT.json",dict(status="PASS",code_sha256=sha(__file__),
        contract_sha256=sha(ROOT/"MEMORY_SUPPLEMENT_CONTRACT.json"),inputs=source_hashes,
        table_sha256=sha(ROOT/"R5_AR_MEMORY_AND_INFORMATION.csv"),max_ar_ledger_error_rad=max_error,
        denominator="within-arm Jnom = H_eff^T R_actual^-1 H_eff, holding the archived Gaussian prior fixed; not E0 information or independent accumulated information"))
