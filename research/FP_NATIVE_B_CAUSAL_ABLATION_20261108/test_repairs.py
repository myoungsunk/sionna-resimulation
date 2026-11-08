import tempfile,unittest,json,hashlib
from pathlib import Path
import numpy as np
from acquire_inputs import acquire,verify
from stage_inputs import copy_verified
from fp_ns_ablation import calc_one_step,pool,ARMS
from replay_evidence import signature

class Repairs(unittest.TestCase):
    def test_rejected_hypothetical_gain(self):
        H=np.array([[[1.,0,1.,0],[0,1.,2.,0]]]*2);P=np.array([np.eye(4)]*2);R=np.array([np.eye(2)*.5]*2)
        # Separate matrix inverse oracle, not implementation solve reuse.
        gain=P[0]@H[0].T@np.linalg.inv(H[0]@P[0]@H[0].T+R[0])
        K=np.array([gain,np.zeros((4,2))]);mask=np.array([True,False])
        tr=dict(H=H,Pprior=P,Reff=R,K=K,mask=mask)
        zs={'NN':np.zeros((2,2)),'BB':np.array([[.1,.2],[.1,.2]])}
        _,_,actualR,actualS,potentialR,potentialS,hyp=calc_one_step(tr,zs,{})
        np.testing.assert_allclose(hyp,np.array([gain]*2),atol=1e-14)
        np.testing.assert_allclose(actualR[1]+actualS[1],0)
        np.testing.assert_allclose(potentialR[1]+potentialS[1],gain@zs['BB'][1])
        self.assertGreater(abs(potentialS[1,2]),0)

    def test_fixed_pooled_mse_weighting(self):
        cases=[]
        for n,v in [(1,1.),(3,9.)]:
            c={'n':n}
            for field,scale in [('metrics',1),('metrics_fixed_mask',2)]:
                c[field]={a:dict(heading_mse_deg2=v*scale,xy_mse_m2=v*scale,mean_nees3=1.,pose95_coverage=.5,xy95_coverage=.5,heading95_coverage=.5,accepted=n) for a in ARMS}
            cases.append(c)
        result=pool(cases)
        self.assertEqual(result['metrics']['NN']['heading_mse_deg2'],7.)
        self.assertEqual(result['metrics_fixed_mask']['NN']['heading_mse_deg2'],14.)
        self.assertEqual(result['interactions_fixed_mask']['xy_mse_m2']['interaction'],0.)

    def test_download_resume_sha_and_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'source';src.write_bytes(b'PK-test-payload');out=root/'cache';out.mkdir()
            r=dict(asset_name='a.npz',size=src.stat().st_size,sha256=hashlib.sha256(src.read_bytes()).hexdigest(),download_url=src.as_uri())
            got=acquire(r,out);self.assertTrue(verify(got,r));self.assertEqual(acquire(r,out),got)
            dest=root/'staged.npz';copy_verified(got,dest,r['sha256']);copy_verified(got,dest,r['sha256'])
            dest.write_bytes(b'bad')
            with self.assertRaises(AssertionError):copy_verified(got,dest,r['sha256'])
            pointer=root/'pointer';pointer.write_bytes(b'version https://git-lfs.github.com/spec/v1\n')
            pr=dict(size=pointer.stat().st_size,sha256=hashlib.sha256(pointer.read_bytes()).hexdigest())
            self.assertFalse(verify(pointer,pr))

    def test_checkpoint_signature_rejects_changed_inputs(self):
        a={'z':np.zeros((2,2))};b={'z':np.ones((2,2))}
        self.assertNotEqual(signature(a,None,{}),signature(b,None,{}))
        self.assertNotEqual(signature(a,None,{}),signature(a,np.ones(2,bool),{}))
        self.assertNotEqual(signature(a,None,{}),signature(a,None,{'source':'changed'}))

if __name__=='__main__':unittest.main(verbosity=2)
