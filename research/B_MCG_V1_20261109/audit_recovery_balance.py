#!/usr/bin/env python3
"""Exact channel-update balance at one fixed clean-return prior, evaluator only."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from evaluate_delivery import independent_joseph, read_npz, wrap


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--recovery",type=Path,required=True)
    parser.add_argument("--cause",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError("Immutable completed balance diagnostic")
    trace_path=args.recovery/"R4_A186_ACTIVE_RS_TAU2.npz"
    tr=read_npz(trace_path);k=26
    cause_path=args.cause/"RESULTS.json"
    cause=json.loads(cause_path.read_text())
    original=next(c for c in cause["cases"] if c["name"]=="ACTUAL_HISTORY")
    betas={"FULL":np.ones(2)}
    betas.update({f"TAU{int(c['tau'])}":np.asarray(c["beta"]) for c in original["decisions"]})
    prior_error=float(np.degrees(wrap(tr["prior"][k,2]-tr["truth"][k,2])))
    terms=[]
    update_args=[tr[name][k] for name in ("prior","Pprior","H","nu","Rbase")]
    for name,beta in betas.items():
        x,P,K,Reff,rows=independent_joseph(*update_args,beta,bool(tr["mask"][k]))
        channel=np.degrees(K[2]*tr["nu"][k])
        change=float(channel.sum())
        actual_change=float(np.degrees(wrap(x[2]-tr["prior"][k,2])))
        error=float(np.degrees(wrap(x[2]-tr["truth"][k,2])))
        assert abs(change-actual_change)<1e-11
        assert abs(prior_error+change-error)<1e-11
        terms.append({"arm":name,"beta":beta.tolist(),"K_heading_rows":K[2].tolist(),
            "nu_range_m_s_unitless":tr["nu"][k].tolist(),
            "range_heading_correction_deg":float(channel[0]),"s_heading_correction_deg":float(channel[1]),
            "net_heading_correction_deg":change,"heading_error_deg":error,"heading_loss_deg2":error**2,
            "heading_gain_vs_skip_deg2":prior_error**2-error**2})
    full=terms[0]
    for arm in terms:
        delta=arm["net_heading_correction_deg"]-full["net_heading_correction_deg"]
        loss_difference=arm["heading_loss_deg2"]-full["heading_loss_deg2"]
        identity=2*full["heading_error_deg"]*delta+delta**2
        assert abs(loss_difference-identity)<1e-10
        arm.update(heading_loss_minus_full_deg2=loss_difference,
                   heading_loss_difference_identity_error_deg2=abs(loss_difference-identity),
                   same_sample_good_gain_lost_ratio=max(loss_difference,0)/full["heading_gain_vs_skip_deg2"])
    result={"status":"PASS_EXACT_FIXED_PRIOR_CHANNEL_BALANCE","route":"R4","original_k":212,
        "episode_k":26,"absolute_t_s":float(tr["absolute_t"][k]),"prior_heading_error_deg":prior_error,
        "trace_sha256":sha(trace_path),"cause_result_sha256":sha(cause_path),
        "script_sha256":sha(__file__),"helper_sha256":sha(Path(__file__).with_name("evaluate_delivery.py")),
        "runtime_source_sha256":cause["runtime_code_sha256"],"arms":terms,
        "scope":"Same prior/P/H/nu/R; diagnostic channel decomposition of each changed full joint gain. Not isolated channel gains held fixed and not a recursive replay.",
        "interpretation":"Range and s heading corrections oppose one another. Unequal attenuation changes both joint gains; their small net beneficial correction can disappear or reverse. An improvement ratio can exceed 100 percent when the policy becomes worse than skipping."}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
