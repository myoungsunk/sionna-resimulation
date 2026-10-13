"""Postprocess raw distribution differences; never change frozen run gates."""
from pathlib import Path
import json
import numpy as np
from repair_short_range import IndependentOneStep

H=Path(__file__).resolve().parent
O=H/'out/i2_short_range_kernel_01'

def features(x):
    return np.column_stack((x[:,0],np.sin(x[:,1]),np.cos(x[:,1]),x[:,2:]))

def cloud(name):
    with np.load(O/name,allow_pickle=False) as f:
        return f['samples'],f['weights']

def main():
    receipt=json.loads((O/'EXECUTION_RECEIPT.json').read_text())
    assert receipt['exit_code']==0
    results=[]
    for case in ('SYNTHETIC','R2','R4'):
        inp=json.loads((O/f'{case}_INPUT.json').read_text())
        model=IndependentOneStep({k:np.array(v) for k,v in inp['public'].items()},inp['config'])
        outcome=json.loads((O/f'{case}_RESULT.json').read_text())
        x,w=cloud(f'{case}_QMC_19_0.npz')
        grid=[]
        for col in features(x).T:
            order=np.argsort(col)
            grid.append(np.interp(np.arange(.01,1,.01),np.cumsum(w[order]),col[order]))
        threshold=np.array(outcome['hpd_threshold'])
        def measure(x,w):
            cdf=[]
            for j,col in enumerate(features(x).T):
                order=np.argsort(col)
                cumulative=np.r_[0.,np.cumsum(w[order])]
                cdf.append(cumulative[np.searchsorted(col[order],grid[j],side='right')])
            density=model.full(x)
            return np.array(cdf),np.array([w[density>=q].sum() for q in threshold])
        reference=[measure(*cloud(f'{case}_QMC_19_{r}.npz')) for r in (1,2,3)]
        pf=[measure(*cloud(f'{case}_PF_{r}.npz')) for r in range(4)]
        with np.load(O/f'{case}_BATCH.npz',allow_pickle=False) as f:
            batch=[measure(a,np.full(len(a),1/len(a))) for a in f['samples']]
        refcdf=np.mean([a for a,b in reference],axis=0)
        refhpd=np.mean([b for a,b in reference],axis=0)
        item=dict(case=case,reference_hpd_masses=refhpd.tolist(),reference_cdf=refcdf.tolist(),methods={})
        for method,clouds in [('PF',pf),('BATCH',batch)]:
            cdf=np.mean([a for a,b in clouds],axis=0)
            hpd=np.mean([b for a,b in clouds],axis=0)
            item['methods'][method]=dict(raw_max_cdf_difference=float(np.max(abs(cdf-refcdf))),
                hpd_masses=hpd.tolist(),raw_hpd_mass_difference=(hpd-refhpd).tolist(),cdf=cdf.tolist(),
                frozen_mc_upper=outcome['simultaneous'][method])
        results.append(item)
    (O/'RAW_DISTRIBUTION_COMPARISON.json').write_text(json.dumps(dict(
        purpose='descriptive decomposition of already frozen comparisons; no new gate or threshold',
        cases=results),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps([dict(case=r['case'],raw_cdf={k:v['raw_max_cdf_difference'] for k,v in r['methods'].items()},
                          hpd={k:v['hpd_masses'] for k,v in r['methods'].items()}) for r in results],indent=2))

if __name__=='__main__':
    main()
