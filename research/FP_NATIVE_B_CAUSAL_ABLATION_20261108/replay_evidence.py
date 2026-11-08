"""Atomic per-arm checkpoints for the unmodified pinned W0 replay."""
import hashlib,json,os
from pathlib import Path
import numpy as np

def signature(packet,mask,source_hashes):
    h=hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode())
    for name in sorted(packet):
        a=np.ascontiguousarray(packet[name]);h.update(name.encode());h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.tobytes())
    if mask is not None:h.update(np.asarray(mask,bool).tobytes())
    return h.hexdigest()

def replay_checkpoint(path,packet,controls,core,online,model,spec,hashes,mask=None):
    sig=signature(packet,mask,hashes)
    if path.exists():
        with np.load(path,allow_pickle=False) as z:
            assert str(z['input_signature'])==sig,('CHECKPOINT_INPUT_MISMATCH',str(path))
            result={k:z[k] for k in z.files if k!='input_signature'}
        assert len(result['x'])==len(packet['t'])
        print('REUSE_VERIFIED_ARM',path.name,flush=True)
        return result
    tr=online.replay(packet,controls,'W0',core,model,spec,fixed_mask=mask)
    assert all(np.isfinite(v).all() for v in tr.values())
    assert np.linalg.eigvalsh(tr['P']).min()>-1e-12
    path.parent.mkdir(parents=True,exist_ok=True)
    partial=path.with_suffix('.part')
    with partial.open('wb') as f:np.savez_compressed(f,**tr,input_signature=sig)
    os.replace(partial,path)
    print('ARM_CHECKPOINT',path.name,flush=True)
    return tr

def baseline_parity(case,on,nn,bb,archived):
    errors={}
    for key in ['prior','Pprior','h','H','K','Reff','mask']:
        expected=on['trace_'+key];actual=nn[key]
        assert actual.shape==expected.shape
        err=float(np.max(abs(actual.astype(float)-expected.astype(float))/np.maximum(1.,abs(expected.astype(float)))))
        errors['NN_'+key]=err
        assert err<=1e-10,(case,'NATIVE_REPLAY_MISMATCH',key,err)
    # Input archives contain priors and gain, not trace_x/trace_P. Reconstruct
    # their posterior independently with the stored Joseph-update ingredients.
    nu=on['z']-on['trace_h']-on['muMB']
    x=on['trace_prior']+np.einsum('nij,nj->ni',on['trace_K'],nu)
    x[:,2]=(x[:,2]+np.pi)%(2*np.pi)-np.pi
    A=np.eye(4)[None]-on['trace_K']@on['trace_H']
    P=A@on['trace_Pprior']@A.transpose(0,2,1)+on['trace_K']@on['trace_Reff']@on['trace_K'].transpose(0,2,1)
    for key,expected in [('x',x),('P',P)]:
        err=float(np.max(abs(nn[key]-expected)/np.maximum(1.,abs(expected))))
        errors['NN_'+key]=err
        assert err<=1e-10,(case,'NATIVE_RECONSTRUCTED_POSTERIOR_MISMATCH',key,err)
    with np.load(archived,allow_pickle=False) as old:
        for key,target in [('x','x'),('P','P'),('prior','prior'),('Pprior','Pprior'),('h','h'),('H','H'),('K','K'),('Reff','R'),('mask','accepted')]:
            expected=old[target][:,0];actual=bb[key]
            assert actual.shape==expected.shape
            err=float(np.max(abs(actual.astype(float)-expected.astype(float))/np.maximum(1.,abs(expected.astype(float)))))
            errors['BB_'+key]=err
            assert err<=1e-10,(case,'B_REPLAY_MISMATCH',key,err)
    assert np.array_equal(nn['mask'],on['trace_mask'])
    return errors
