import numpy as np
from d6_d9_common import OBS
from d15_dense_core import extract_cir_methods

def test_proportional_ports():
    n=257;h=np.ones((1,n,2),complex);h[:,:,1]*=.5
    c=OBS.cir_batch(h);fp=OBS.first_path_batch(c,1.95e6)
    v,e=extract_cir_methods(c[0],fp_index=int(fp['index'][0]))
    assert abs(v['DENSE_SINGLE']-.6)<1e-12

def test_against_direct_frequency_padding():
    rng=np.random.default_rng(19);n=257
    for _ in range(12):
        h=rng.normal(size=(n,2))+1j*rng.normal(size=(n,2))
        c=OBS.cir_batch(h[None])[0];fp=OBS.first_path_batch(c[None],1.95e6)
        v,e=extract_cir_methods(c,fp_index=int(fp['index'][0]))
        w=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
        f=np.fft.ifft(h*w[:,None],n=16*n,axis=0)*4*n
        q=round(e['window_begin']*4);p=abs(f[q])**2
        assert abs(v['DENSE_SINGLE']-(p[0]-p[1])/p.sum())<1e-12
        assert abs(v['W0_FP']-fp['s'][0])<1e-12
