"""Independent selection fixtures and same-prior perturbation regression."""
import importlib.util,json,sys
from pathlib import Path
import numpy as np
from kriging_stable import neighbor_indices,make_predictor

def test_neighbor_selection():
    np.testing.assert_array_equal(neighbor_indices([3.,0.,2.,1.],2),[1,3])
    np.testing.assert_array_equal(neighbor_indices([0.,1.+1e-15,1.,2.],2),[0,1])
    np.testing.assert_array_equal(neighbor_indices([0.,1.+1e-8,1.,2.],2),[0,2])
    np.testing.assert_array_equal(neighbor_indices([0.,0.,0.],3),[0,1,2])


def main():
    test_neighbor_selection()
    spec=importlib.util.spec_from_file_location('A',sys.argv[1]); A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)
    stable=make_predictor(A.KO); results=[]
    for route,i in [('R2',122),('R4',213),('R5',134)]:
        values=[]; sets=[]
        for source in ('base246','base253_oldinput'):
            with np.load(Path('/runout')/source/f'{route}_{A.BASE}.npz') as tr:
                nav=tr['prior'][i].copy(); rho=float(tr['distance'][i])
            for eps in (-1e-14,0.,1e-14):
                v=nav.copy();v[0]+=eps
                KO=A.KO;b=int(np.clip(np.searchsorted(KO.EDG,rho,side='right')-1,0,2));B=KO.BINS[b]
                lx,ly,lp,_=B['prm'];X=B['X']
                d=np.abs(X[:,0]-v[0])/lx+np.abs(X[:,1]-v[1])/ly+np.abs(KO.wrap(X[:,2]-v[2]))/lp
                sets.append(neighbor_indices(d));values.append(float(stable(*v[:3],rho)))
        assert all(np.array_equal(sets[0],s) for s in sets)
        assert np.ptp(values)<1e-12
        results.append(dict(route=route,i=i,all_neighbor_sets_equal=True,mu_s_range=float(np.ptp(values))))
    out=dict(status='PASS',numpy=np.__version__,fixtures=4,probes=results)
    Path(f'/runout/STABLE_TEST_{np.__version__}.json').write_text(json.dumps(out,indent=2))
    print(out,flush=True)


if __name__=='__main__':
    main()
