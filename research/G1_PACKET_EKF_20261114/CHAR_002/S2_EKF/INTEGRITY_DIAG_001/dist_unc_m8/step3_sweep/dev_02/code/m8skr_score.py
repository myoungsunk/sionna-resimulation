"""M8 scoring: same pinned scorer functions and assess rules as M7 score_comparison, arm set H0-H3 + F0-F2."""
import numpy as np, m7_score
from m7_assess import COVERAGE, assess_group, assess_seed, bias_metrics
ARMS8=("H0","H1","H2","H3","F2SK","F2SKR","F2SKRW"); ROUTES=("R2","R4","R5"); PASSES={"R2":2,"R4":1,"R5":3}
def score8(seed,condition,mode,traces,truth,times,*,from_trace,scores_with_blocks,branch_metrics):
    rows,branches,endpoints={},{},{}
    for route in ROUTES:
        t,ref=np.asarray(times[route]),np.asarray(truth[route]); rows[route],branches[route],endpoints[route]={},{},{}
        for arm in ARMS8:
            tr=traces[route][arm]; assert np.array_equal(tr["t"],t)
            assert str(np.asarray(tr["metadata_condition"]).item())==condition
            row=np.asarray(from_trace(tr,ref)); assert row.shape==(len(t),6) and np.isfinite(row).all()
            rows[route][arm]=row
            br=branch_metrics(tr,ref,t); assert len(br["passages"])==PASSES[route]
            branches[route][arm]=br
            end=np.asarray(tr["x"])[-1,:3]-ref[-1]; hd=np.degrees((end[2]+np.pi)%(2*np.pi)-np.pi)
            endpoints[route][arm]=dict(heading_signed_deg=float(hd),xy_error_cm=float(100*np.linalg.norm(end[:2])))
    pairs=[(a,"H2") for a in ARMS8 if a!="H2"]+[(a,b) for a in ARMS8[2:] for b in ("H0","H1")]
    pairs+=[("F2SKR","F2SK"),("F2SKRW","F2SK"),("F2SKRW","F2SKR")]
    sc=scores_with_blocks(rows,times,list(dict.fromkeys(pairs)),blocks=(5,10,20))
    point,b10=sc["point"],sc["blocks"]["10"]; assessed={}
    for arm in ARMS8:
        groups={}
        for g in (*ROUTES,"pooled"):
            ci=b10["by_group"][g]; lower={m:ci["absolute_ci95"][arm][m][0] for m in COVERAGE}; pooled=g=="pooled"
            mir=sum(branches[r][arm]["mirror_fail_count"] for r in ROUTES) if pooled else branches[g][arm]["mirror_fail_count"]
            blocks=min(b10["full_blocks"].values()) if pooled else b10["full_blocks"][g]
            groups[g]=assess_group(point[g][arm],lower,point[g]["H2"],pooled=pooled,effective_blocks=blocks,
                                   reference_only=bool(ci["reference_only"]),mirror_fail=mir)
        assessed[arm]=assess_seed(seed,groups)
    paired={k:v for k,v in b10.items() if k not in("by_group","full_blocks")}
    return dict(seed=seed,condition=condition,mode=mode,point=point,
                ci10={g:b10["by_group"][g] for g in (*ROUTES,"pooled")},
                passages={r:{a:[{k:v for k,v in p.items() if not isinstance(v,(list,dict))} for p in branches[r][a]["passages"]] for a in ARMS8} for r in ROUTES},
                mirror={r:{a:branches[r][a]["mirror_fail_count"] for a in ARMS8} for r in ROUTES},
                endpoint=endpoints,seed_assessments=assessed)
