"""Same-prior distance/tie probe; no filter or candidate execution."""
import importlib.util,json,sys
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('A',sys.argv[1]); A=importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
out=Path('/runout'); result=[]
for route,i in [('R2',122),('R4',213),('R5',134)]:
    for runtime in ('base246','base253_oldinput'):
        with np.load(out/runtime/f'{route}_{A.BASE}.npz') as t:
            prior=t['prior'][i].copy(); rho=float(t['distance'][i])
        for delta in (0.,-1e-14,1e-14):
            nav=prior.copy(); nav[0]+=delta
            KO=A.KO; b=int(np.clip(np.searchsorted(KO.EDG,rho,side='right')-1,0,2)); B=KO.BINS[b]
            lx,ly,lp,nug=B['prm']; X=B['X']
            d=np.abs(X[:,0]-nav[0])/lx+np.abs(X[:,1]-nav[1])/ly+np.abs(KO.wrap(X[:,2]-nav[2]))/lp
            idx=np.argpartition(d,150)[:150]; dd=np.sort(d)
            result.append(dict(route=route,i=i,prior_source=runtime,delta_x=delta,prior=nav.tolist(),rho=rho,
                               selected=np.sort(idx).tolist(),cutoff=float(dd[149]),margin=float(dd[150]-dd[149]),
                               near_ties=int((np.abs(d-dd[149])<1e-12).sum()),mu_s=float(KO.krige_s(*nav[:3],rho))))
(out/f'KRIGING_PROBE_{np.__version__}.json').write_text(json.dumps(dict(numpy=np.__version__,rows=result),indent=2))
for x in result: print(x['route'],x['prior_source'],x['delta_x'],'margin',x['margin'],'ties',x['near_ties'],'mu_s',x['mu_s'])
