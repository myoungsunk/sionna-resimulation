"""Pre-GO synthetic mathematics and frozen-input checks; no actual RF analysis/model init."""
import copy, importlib.util, json, unittest
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_info
import authority as A
import physics as P
import model_adapter as M

PLAN=A.read(A.HERE/'PLAN.json'); LOCK=A.read(A.HERE/'INPUT_LOCK.json')
spec=importlib.util.spec_from_file_location('frozen_diagnostics',LOCK['diagnostics']['path'])
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)

def synthetic():
    # Two coherent groups with analytically known constructive/destructive port powers.
    envelope=np.ones(257,np.float32);envelope[128]=2
    raw=(envelope[:,None,None]*np.array([[1,2],[.5j,-.25]],np.complex64)[None,:,:]).reshape(-1,2)
    fields=np.zeros((2,257,2),np.complex128)
    fields[0]=raw.reshape(257,2,2)[:,0];fields[1]=raw.reshape(257,2,2)[:,1]
    return dict(group_labels=np.array(['DIRECT','[["wall",0],["wall",1]]']),
        direct_group=np.array(0),legacy_group_fields=fields,legacy_native_full=fields.sum(0),
        frequencies_hz=6250400000.+1950000.*np.arange(257),original_field=raw,
        source_group=np.tile([0,1],257),offsets=np.arange(258)*2,
        group_count=np.ones((2,257),np.int32),group_missing=np.zeros((2,257),bool))

class Toy:
    def __init__(self,wrong=False,change=False):self.wrong=wrong;self.change=change;self.calls=0
    def batch(self,x,case,gradient,return_diagnostics):
        self.calls+=1
        assert case==dict(anchor=PLAN['anchor'],robot_z_m=.45,mount_deg=0)
        y=x[:,2];h=np.column_stack([np.ones(len(x)),np.sin(y)])
        J=np.zeros((len(x),2,4));J[:,1,2]=np.cos(y)+(1 if self.wrong else 0)
        cells=np.zeros((len(x),6),int)
        if self.change:cells[:,0]=(y>np.deg2rad(35.7)).astype(int)
        d=dict(tap=np.ones(len(x),int),strong_port=np.zeros(len(x),int),cells=cells,
               native_range=np.ones(len(x)),fp_margin=np.ones(len(x)))
        return h,J,d

class Preflight(unittest.TestCase):
    def test_frozen_inputs_runtime_and_blas(self):
        A.verify_scope(PLAN,LOCK); A.verify_inputs(LOCK); A.runtime(PLAN,LOCK)
        pools=threadpool_info();self.assertTrue(pools)
        self.assertTrue(all(p['num_threads']==1 for p in pools))
    def test_scope_negatives(self):
        for key,value in [('fd_steps_rad',[1e-4,5e-5]),('mount_deg',1),('fd_abs_tol',1e-3),('anchor',[10,0,2.7]),('pairwise_contrasts',[])]:
            p=copy.deepcopy(PLAN);p[key]=value
            with self.assertRaises(ValueError):A.verify_scope(p,LOCK)
        for mutation in ('missing','duplicate','yaw','order'):
            l=copy.deepcopy(LOCK)
            if mutation=='missing':l['conditions'].pop()
            if mutation=='duplicate':l['conditions'][-1]=l['conditions'][0]
            if mutation=='yaw':l['conditions'][0]['yaw_deg']=1
            if mutation=='order':l['conditions'].reverse()
            with self.assertRaises(ValueError):A.verify_scope(PLAN,l)
    def test_go_missing_or_forged(self):
        with self.assertRaises(ValueError):A.check_go(PLAN,{})
    def test_fft_against_direct_dft(self):
        h=np.column_stack([np.arange(257)/257+1j*.1,np.ones(257)*(.2-.1j)])
        taps=np.array([0,1,37,1027])
        expected=np.exp(2j*np.pi*taps[:,None]*np.arange(257)[None,:]/1028)@(h*np.hanning(257)[:,None])*257/1028
        np.testing.assert_allclose(D.cir(h)[taps],expected,atol=2e-12,rtol=1e-12)
    def test_selector_amplitude_ties_and_zero(self):
        c=np.zeros((1028,2),complex);c[2]=.4;c[7]=1
        d=D.detect(c,1950000.)
        self.assertEqual((d['tap'],d['rx']),(2,0)) # .4 < sqrt(.3), discriminates power threshold.
        self.assertEqual(d['s'],0.)
        with self.assertRaises(ValueError):D.detect(c*0,1950000.)
        with self.assertRaises(ValueError):P.signed(D,np.zeros(2))
    def test_signed_port_swap(self):
        v=np.array([3+4j,2j]);self.assertAlmostEqual(P.signed(D,v)[0],21/29)
        self.assertAlmostEqual(P.signed(D,v[::-1])[0],-21/29)
    def test_coherent_power_surface_union_and_wrap(self):
        result,arrays,groups,surfaces=P.analyze(synthetic(),D,PLAN)
        envelope=np.ones(257,np.float32);envelope[128]=2
        scale=((np.hanning(257)*envelope).sum()*257/1028)**2
        np.testing.assert_allclose(arrays['full_power'][0],scale*np.array([1.25,3.0625]),rtol=1e-14)
        np.testing.assert_allclose(arrays['pair_cross_center'][0,0,1],scale*np.array([0.,-1.]),atol=1e-12)
        self.assertEqual(arrays['window_indices'][0].tolist(),[1024,1025,1026,1027,0,1,2,3,4])
        self.assertEqual(len(surfaces),2)
        for row in surfaces:
            self.assertEqual(row['removed_group_indices'],'[1]');self.assertEqual(row['removed_group_count'],1)
            self.assertAlmostEqual(row['removed_s_fixed'],-.6)
        self.assertLessEqual(result['detector']['identity_error'],1e-12)
    def test_replay_negatives(self):
        for mutation in ('freq','field','count','missing','group','offset','nan','direct'):
            a=synthetic()
            if mutation=='freq':a['frequencies_hz'][0]+=1
            if mutation=='field':a['legacy_group_fields'][1,0,0]+=1
            if mutation=='count':a['group_count'][0,0]+=1
            if mutation=='missing':a['group_missing'][0,0]=True
            if mutation=='group':a['source_group'][0]=2
            if mutation=='offset':a['offsets'][1]=0
            if mutation=='nan':a['original_field'][0,0]=np.nan
            if mutation=='direct':a['direct_group']=1
            with self.assertRaises(ValueError):P.replay(a)
    def test_cir_zero_tails_and_closure_mutation(self):
        a=synthetic();a['original_field']=np.tile(np.array([[1,2],[.5j,-.25]],np.complex64),(257,1))
        a['legacy_group_fields'][0]=[1,2];a['legacy_group_fields'][1]=[.5j,-.25]
        a['legacy_native_full']=a['legacy_group_fields'].sum(0)
        result,_,_,_=P.analyze(a,D,PLAN)
        self.assertLess(result['cir_closure']['joint']['Emax'],1e-8)
        c=D.cir(a['legacy_native_full']);bad=c.copy();bad[0,0]+=.01
        with self.assertRaises(ValueError):P.complex_closure(bad,c,1e-8)
        with self.assertRaises(ValueError):P.complex_closure(c*0,c*0,1e-8)
    def test_derivative_units_steps_and_bad_jacobian(self):
        row=dict(id='toy',xyz=[5,.3,.45],yaw_deg=35.7)
        toy=Toy();v=M.evaluate(toy,row,PLAN)
        self.assertEqual(toy.calls,3);self.assertEqual(v['derivative_status'],'VERIFIED_SMOOTH')
        self.assertAlmostEqual(v['state'][2],35.7*np.pi/180)
        self.assertAlmostEqual(v['Hpsi_s_per_deg'],np.cos(35.7*np.pi/180)*np.pi/180)
        self.assertEqual([c['eps_rad'] for c in v['fd_checks']],[1e-5,5e-6])
        with self.assertRaises(ValueError):M.evaluate(Toy(wrong=True),row,PLAN)
        v=M.evaluate(Toy(change=True),row,PLAN)
        self.assertEqual(v['derivative_status'],'UNDEFINED_BRANCH_CHANGE')
        self.assertFalse(any(c['same_branch'] for c in v['fd_checks']))

if __name__=='__main__':unittest.main(verbosity=2)
