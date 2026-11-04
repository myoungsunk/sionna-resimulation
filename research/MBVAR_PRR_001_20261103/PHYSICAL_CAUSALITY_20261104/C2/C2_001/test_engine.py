"""Synthetic-only tests using frozen motion/update functions; no RF bank init."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import numpy as np
from engine import run,BRANCHES,RecursionFailure
from evaluate import score_states,baseline_score,window_score,integral,acf

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE/'PLAN.json').read_bytes())


def module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec);sys.modules[name] = result
    spec.loader.exec_module(result);return result


cache = Path(PLAN['cache'])
core = module('c2_test_motion',cache/'legacy/research/EKF4_RANGE_S_STAGED_20261014/core.py')
online = module('c2_test_online',cache/'provenance/online.py')
SPEC = dict(anchor=(1.,2.,2.65),robot_z_m=.45,mount_deg=0.)


class ToyObserver:
    H = np.array([[1.,.2,.1,0.],[.1,.2,.5,0.]])
    def batch(self,x,spec,return_diagnostics=False):
        h = x@self.H.T;H = np.repeat(self.H[None],len(x),axis=0)
        diag = dict(tap=np.zeros(len(x),int),cells=np.zeros((len(x),6),int),fp_margin=np.ones(len(x)))
        return (h,H,diag) if return_diagnostics else (h,H)


def fixture(n=18):
    controls = dict(ds=np.full(n,.04),gy=np.full(n,.009),dt=np.full(n,.2),x0=np.array([.1,.2,.3]))
    states = [np.r_[controls['x0'],0.]]
    for k in range(1,n):states.append(core.transition(states[-1],controls['ds'][k],controls['gy'][k],controls['dt'][k])[0])
    z = np.asarray(states)@ToyObserver.H.T
    full = dict(t=np.arange(n)*.2,pose_id=np.arange(n)+200,z=z.copy(),
        muMB=np.zeros((n,2)),muBASE=np.zeros((n,2)),R=np.repeat(np.array([[.0025,.0003],[.0003,.0036]])[None],n,axis=0),
        P0=np.diag([.03,.04,.02,.0001]),D=np.zeros(n))
    full['z'][3] += [2.,.7];full['z'][8] += [-1.5,-.6]
    los = {key:value.copy() for key,value in full.items()};los['z'] = z.copy();los['z'][5] += [0.,.8]
    baseline = online.replay(full,controls,'W0',core,ToyObserver(),SPEC)
    baseline.update(t=full['t'].copy(),pose_id=full['pose_id'].copy())
    x=np.r_[controls['x0'],0.];P=full['P0'].copy();bx=[];bp=[]
    for k in range(n):
        x,P = online.predict(core,x,P,k,controls)
        h,H=ToyObserver().batch(x[None],SPEC);h,H=h[0],H[0]
        v=full['z'][k]-h;S=H@P@H.T+full['R'][k]
        if v@np.linalg.solve(S,v)<=online.GATE:
            K=P@H.T@np.linalg.inv(S);x=x+K@v;x[2]=core.wrap(x[2])
            a=np.eye(4)-K@H;P=a@P@a.T+K@full['R'][k]@K.T;P=(P+P.T)*.5
        bx.append(x.copy());bp.append(P.copy())
    return full,los,controls,baseline,dict(BASE_x=np.array(bx),BASE_P=np.array(bp))


def snapshot(*dicts):
    return [[(key,hashlib.sha256(value.tobytes()).hexdigest()) for key,value in sorted(d.items())] for d in dicts]


class Tests(unittest.TestCase):
    def test_prefix_batch_and_own_history_against_original_from_t0(self):
        full,los,ctl,tr,base=fixture();before=snapshot(full,los,ctl,tr,base)
        windows=[dict(id='early',first_index=3,last_index=5),dict(id='late',first_index=8,last_index=10)]
        records,stats=run(core,online,ToyObserver(),SPEC,full,los,ctl,tr,base,windows)
        flips=0
        for window in windows:
            result=records[window['id']];start=window['first_index']
            for j,(mode,arm) in enumerate(BRANCHES):
                packet={key:value.copy() for key,value in full.items()}
                selection=slice(start,window['last_index']+1)
                if arm in ('LF','LL'):packet['z'][selection,0]=los['z'][selection,0]
                if arm in ('FL','LL'):packet['z'][selection,1]=los['z'][selection,1]
                ref=online.replay(packet,ctl,'W0',core,ToyObserver(),SPEC,fixed_mask=tr['mask'] if mode=='fixed' else None)
                for name in ('x','P','prior','Pprior','h','H','K','nu','mask'):
                    np.testing.assert_allclose(result[name][:,j],ref[name][start:],atol=1e-11,rtol=1e-11)
                np.testing.assert_allclose(result['R'][:,j],ref['Rvar'][start:],atol=1e-13,rtol=1e-13)
                np.testing.assert_allclose(result['rho'][:,j],ref['rho_before'][start:],atol=1e-13,rtol=1e-13)
                flips+=int(np.sum(result['mask'][:,j]!=tr['mask'][start:]))
            self.assertEqual(int(result['filled_rows']),len(full['t'])-start)
        self.assertGreater(flips,0);self.assertEqual(before,snapshot(full,los,ctl,tr,base))
        self.assertEqual(stats['MB_transitions'],sum(len(full['t'])-w['first_index'] for w in windows)*6)
        self.assertEqual(stats['BASE_transitions'],stats['MB_transitions']//2)

    def test_no_intervention_FF_parity(self):
        full,los,ctl,tr,base=fixture()
        result,stats=run(core,online,ToyObserver(),SPEC,full,los,ctl,tr,base,[],verify_ff=True)
        result=result['FF_VERIFY']
        for name in ('x','P','prior','Pprior','h','H','K','nu','mask'):
            np.testing.assert_allclose(result[name][:,0],tr[name],atol=1e-12,rtol=1e-12)
        np.testing.assert_allclose(result['BASE_x'][:,0],base['BASE_x'],atol=1e-12,rtol=1e-12)

    def test_time_zero_rejection_preserves_unwrapped_prior(self):
        full,los,ctl,tr,base=fixture();ctl['x0'][2]=4.;full['z'][0]=[100.,100.]
        tr=online.replay(full,ctl,'W0',core,ToyObserver(),SPEC);tr.update(t=full['t'],pose_id=full['pose_id'])
        result,_=run(core,online,ToyObserver(),SPEC,full,los,ctl,tr,base,[],verify_ff=True)
        self.assertFalse(result['FF_VERIFY']['mask'][0,0])
        self.assertEqual(result['FF_VERIFY']['x'][0,0,2],4.)
        np.testing.assert_allclose(result['FF_VERIFY']['x'][:,0],tr['x'],atol=1e-12,rtol=1e-12)

    def test_units_NEES_and_horizon_missingness(self):
        x=np.array([[[.1,.2,np.pi+.01,.003]]]);P=np.diag([.01,.04,.0001,1e-6])[None,None]
        truth=dict(truth=np.array([[0.,0.,-np.pi]]),bg=np.array(0.))
        values=score_states(x,P,truth)
        np.testing.assert_allclose(values['NEES3'],3.,atol=1e-11)
        np.testing.assert_allclose(values['NEES4'],12.,atol=1e-11)
        np.testing.assert_allclose(values['heading_deg'],np.degrees(.01),atol=1e-11)
        self.assertTrue(values['heading95'][0,0]);self.assertFalse(values['NEES4_upper95'][0,0])
        missing=score_states(x,P,dict(truth=truth['truth']))
        self.assertFalse(missing['NEES4_available']);self.assertTrue(np.isnan(missing['NEES4']).all())
        t=np.arange(0.,20.1,.2)
        self.assertAlmostEqual(integral(t,np.ones(len(t)),0.,10.,20.),10.)
        self.assertIsNone(integral(t[:-1],np.ones(len(t)-1),0.,10.,20.))
        self.assertEqual(acf(np.ones(12)),[None]*10)
        np.testing.assert_allclose(acf(np.arange(20.)),np.ones(10),atol=1e-14)
        with self.assertRaises(np.linalg.LinAlgError):score_states(x,-P,truth)

    def test_failure_preserves_partial_context_without_expansion(self):
        full,los,ctl,tr,base=fixture()
        class Bad(ToyObserver):
            def batch(self,x,spec,return_diagnostics=False):
                h,H,d=super().batch(x,spec,True);h[0,0]=np.nan;return h,H,d
        with self.assertRaises(RecursionFailure) as failure:
            run(core,online,Bad(),SPEC,full,los,ctl,tr,base,[dict(id='fail',first_index=3,last_index=5)])
        self.assertEqual(failure.exception.context['index'],3)
        self.assertEqual(int(failure.exception.partial['fail']['filled_rows']),0)

    def test_evaluator_pairs_modes_and_explicit_partial_horizons(self):
        full,los,ctl,tr,base=fixture(180)
        window=dict(id='end',first_index=160,last_index=162,start_s=32.,end_s=32.4)
        result,_=run(core,online,ToyObserver(),SPEC,full,los,ctl,tr,base,[window])
        truth=dict(truth=tr['x'][:,:3].copy(),bg=np.array(0.))
        h,H=ToyObserver().batch(tr['x'],SPEC)
        reference=dict(h=h,H=H,physical_delta=full['z']-los['z'],physical_delta_tap=np.zeros(180,int),
                       time_bin=np.floor(tr['t']).astype(int),distance_bin=np.arange(180)//5)
        values,rows,blocks,diag=window_score(result['end'],tr,baseline_score(tr,truth),truth,reference,window,'toy','B0',10)
        self.assertEqual(len(rows),6);self.assertEqual(len(diag),6);self.assertTrue(blocks)
        self.assertTrue(all(set(row)==set(rows[0]) for row in rows))
        for row in rows:
            self.assertTrue(row['I_heading_deg_0_2_deg_s_available'])
            self.assertEqual(row['I_heading_deg_0_2_deg_s_actual_packets'],11)
            self.assertFalse(row['I_heading_deg_2_5_deg_s_available'])
            self.assertIsNone(row['I_heading_deg_2_5_deg_s'])
            self.assertTrue(row['I_heading_deg_2_5_deg_s_unavailable_reason'])
            if row['mode']=='own':self.assertAlmostEqual(row['own_minus_fixed_primary_heading_deg_rmse'],0.,places=10)
        self.assertLess(np.abs(values['identity_error']).max(),1e-14)


if __name__=='__main__':unittest.main()
