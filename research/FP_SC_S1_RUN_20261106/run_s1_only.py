"""Authorized six-case S1 orchestration only; frozen science code unchanged."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
import sys, json, ctypes, datetime, pathlib, traceback, subprocess
root=pathlib.Path(__file__).resolve().parents[2]
os.chdir(root)
sys.path[:0]=[str(root/'src'),str(root/'scripts')]
import fp_sc_vab_shadow_stages as stages
out=pathlib.Path(__file__).resolve().parent
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.GetCurrentProcess.restype=ctypes.c_void_p
handle=kernel.GetCurrentProcess()
allowed=ctypes.c_size_t();system=ctypes.c_size_t()
kernel.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
kernel.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
assert kernel.GetProcessAffinityMask(handle,ctypes.byref(allowed),ctypes.byref(system))
bits=[1<<i for i in range(allowed.value.bit_length()) if allowed.value&(1<<i)][:3]
assert kernel.SetProcessAffinityMask(handle,sum(bits))
receipt=dict(scope='S1_ONLY_SIX_CASES',start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    implementation_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    affinity_mask=sum(bits),logical_cores=len(bits),blas_threads=1,status='RUNNING',cases=[])
def save():stages.write_json(out/'BATCH_RECEIPT.json',receipt)
save()
try:
    for manifest in sorted((root/'research/FP_SC_S1_PREPARATION_20261106/FINAL_002').glob('*_S1_MANIFEST.json')):
        stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
        if stop and pathlib.Path(stop).exists():raise RuntimeError('STOP_REQUESTED')
        m=json.loads(manifest.read_text())
        assert m['stage']=='S1_SHADOW_SELECT'
        cid=m['case_id']
        print('START',cid,datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
        r=stages.run(manifest,out/'APPROVALS'/f'{cid}.json',out/'RESULTS'/cid)
        receipt['cases'].append(r);save()
        print('COMPLETE',cid,r['row_count'],flush=True)
    assert len(receipt['cases'])==6
    receipt['status']='COMPLETE_TECHNICAL_ONLY'
except Exception:
    receipt['status']='FAILED_PRESERVED';receipt['error']=traceback.format_exc()
    raise
finally:
    receipt['end']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
