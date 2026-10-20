"""Run only after protocol commit. Synthetic engine interface parity, no RF claim."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'T1_MEMORY'))
from unit_tests import TestObservation
sys.path.insert(0,str(HERE.parent/'T1_MEMORY/vendor'))
sp=importlib.util.spec_from_file_location('policy_interface_engine',HERE.parent/'canonical_engine.py')
engine=importlib.util.module_from_spec(sp);sp.loader.exec_module(engine)


def main():
    n=16;t=np.arange(n)*.2;controls=dict(dt_s=np.full(n,.2),ds_odom=np.full(n,.02),dtheta_gyro=np.full(n,.001))
    initial=np.array([.2,.1,.02]);z=np.c_[np.full(n,.4),np.full(n,.1)]
    mu=np.zeros((n,2));C=np.repeat(np.diag([.02,.03])[None],n,axis=0);risk=np.zeros(n);model=TestObservation();case={'id':'SYNTHETIC_INTERFACE'}
    def run(spec,**kw):return engine.run(t,controls,initial,z,mu,C,risk,case,model,[spec],**kw)
    baseline=run(dict(name='POWER',base='power'))
    power=run(dict(name='POWER',base='power'),decision_provider=lambda *args:'POWER')
    comparisons=[('POWER_CALLBACK',baseline,power)]
    for action,spec in [('R0',dict(name='R0',base='r0')),('SKIP',dict(name='SKIP',base='power',skip_all=True))]:
        comparisons.append((action,run(spec),run(dict(name=action,base='power'),decision_provider=lambda *args,a=action:a)))
    comparisons.append(('INFLATE4',run(dict(name='INFLATE4',base='power'),parameter_provider=lambda i,x,s:(mu[i],C[i]*4)),
                        run(dict(name='INFLATE4',base='power'),decision_provider=lambda *args:'INFLATE4')))
    k=6
    segment=engine.run(t[k:],{name:value[k:] for name,value in controls.items()},initial,z[k:],mu[k:],C[k:],risk[k:],case,model,
       [dict(name='POWER',base='power')],initial_state4=baseline['prior'][k,0,:4],initial_cov=baseline['prior_cov'][k,0,:4,:4])
    comparisons.append(('PRIOR_RESTART', {name:value[k:] for name,value in baseline.items() if name in ('state','cov','accepted')},segment))
    for name,left,right in comparisons:
        delta=max(float(abs(left[key]-right[key]).max()) for key in ('state','cov'))
        gates=int(np.count_nonzero(left['accepted']!=right['accepted']))
        if delta>1e-10 or gates:raise RuntimeError((name,delta,gates))
        print(name,delta,gates,flush=True)


if __name__=='__main__':main()
