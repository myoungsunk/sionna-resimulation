"""Where and how do replays diverge? For each pair (A-B kernel, A-C ulp input noise) and each run whose state differs by >1e-10 anywhere:
first divergence step, whether any gate status (odom/range/s applied/rejected) differs at or before it, and the horizontal distance to the anchor at that step."""
import json,collections
from pathlib import Path
import numpy as np
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');OUT=Path(__file__).resolve().parents[1]/'out_div'
ANCH={'aA':4.0,'aB':10.0};POSE={r:np.load(S/f'g7/job_pub/OUTPUT/MOTION_{r}_legacy-euler.npz')['pose'] for r in ('R2','R4','R5')}
res={}
for other in 'BC':
    cat=collections.Counter();dist=[];per_case=collections.Counter();per_arm=collections.Counter();flips_total=0
    for f in sorted((S/'div_A').glob('*.npz')):
        a=np.load(f);b=np.load(S/f'div_{other}'/f.name);ok=a['completed']&b['completed']
        dif=np.nanmax(np.abs(a['est']-b['est']),axis=1);dif[~ok]=0;idx=np.where(dif>1e-10)[0]
        if len(idx)==0:continue
        k0=int(idx[0]);fl=np.zeros(len(dif),bool)
        for key in ('odom_status','range_status','s_status'):fl|=(a[key]!=b[key])
        fi=np.where(fl)[0]
        c='no_status_flip_in_run' if len(fi)==0 else ('flip_at_or_before_first_divergence' if fi[0]<=k0 else 'flip_after_numeric_drift')
        cat[c]+=1;case=f.name.split('_d')[0];r=case[:2];an=ANCH[case.split('_')[1]]
        p=POSE[r][k0];dist.append(float(np.hypot(p[0]-an,p[1])));per_case[case]+=1;per_arm[f.stem.split('_')[-1]]+=1
    res[f'A_vs_{other}']=dict(n_runs_state_diff_gt_1em10=int(sum(cat.values())),category=dict(cat),per_case=dict(per_case),per_arm=dict(per_arm),
        horizontal_distance_to_anchor_at_first_divergence_m=dict(min=min(dist),p25=float(np.percentile(dist,25)),median=float(np.median(dist)),p75=float(np.percentile(dist,75)),max=max(dist)))
    print(other,json.dumps(res[f'A_vs_{other}']))
json.dump(res,open(OUT/'g7_div_location.json','w'),indent=1)
