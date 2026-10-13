"""Frozen dense single-tap candidate. No oracle or data-fitted parameters."""
from d10_d14_core import *
from d10_d14_core import extract_cir_methods as original_extract
METHODS=('W0_FP','DENSE_SINGLE')

def extract_cir_methods(cir, *, fp_index, config=None, template=None):
    vals,e=original_extract(cir,fp_index=fp_index,config=config,template=template)
    h=np.asarray(cir,complex); n=len(h)//4
    # Coarse CIR is a 4N transform of N frequency bins. Retain those bins.
    fine=np.fft.ifft(np.fft.fft(h,axis=0)[:n],n=16*n,axis=0)*4
    bound=64*np.finfo(float).eps*max(1.,np.log2(len(fine)))*np.max(abs(h))
    if np.max(abs(fine[::4]-h))>bound:raise RuntimeError('Dense/coarse grid mismatch')
    k=e['window_begin'];port=e['selected_reference_rx'];threshold=.3*np.max(abs(h[:,port]))
    lo=max(0,k-1)*4;hi=k*4
    if k>0 and abs(fine[lo,port])<threshold<=abs(fine[hi,port]):
        q=lo+int(np.flatnonzero(abs(fine[lo:hi+1,port])>=threshold)[0])
    else:q=hi
    e=dict(e,window_begin=q/4,window_end_exclusive=q/4+.25,window_width_taps=.25)
    return {'W0_FP':vals['W0_FP'],'DENSE_SINGLE':signed_power_ratio(abs(fine[q])**2)},e

from d10_d14_core import stage_finish as old_stage_finish

def stage_finish(out,stage,files,*,config,evidence=None,warnings=None):
    old_stage_finish(out,stage,files,config=config,evidence=evidence,warnings=warnings)
    p=Path(out)/(stage+'_MANIFEST.json');j=json.loads(p.read_text('utf8'))
    j['candidate']='DENSE_SINGLE_FIXED_16N_LOCAL_CROSSING'
    j['script_sha256'].update({f.name:file_sha(f) for f in Path(__file__).parent.glob('d15*.py')})
    save_json(p,j)
