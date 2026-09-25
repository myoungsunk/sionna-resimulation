"""Manifest-bound consumer for channels produced by unmodified Sionna RT."""
import hashlib
import json
from pathlib import Path
import numpy as np


def sum_native_paths(coefficients,delays_s,frequency_hz):
    """Apply carrier phase to native a/tau, explicitly in complex128."""
    a=np.asarray(coefficients,np.complex128);tau=np.asarray(delays_s,np.float64)
    if a.ndim!=3 or tau.shape!=(a.shape[-1],) or not np.isfinite(a).all() or not np.isfinite(tau).all():
        raise ValueError('INVALID_NATIVE_COEFFICIENTS_OR_DELAYS')
    return np.sum(a*np.exp(-2j*np.pi*float(frequency_hz)*tau)[None,None,:],axis=-1)


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def load_native_link(root,link_id):
    root=Path(root).resolve();manifest=json.loads((root/'MANIFEST.json').read_text())
    def checked(name):
        p=root/name
        if p.resolve().parent!=root or name not in manifest['outputs']:
            raise ValueError('UNMANIFESTED_NATIVE_OUTPUT')
        if file_sha(p)!=manifest['outputs'][name]:raise ValueError('NATIVE_OUTPUT_SHA_MISMATCH')
        return p
    status=json.loads(checked('STATUS.json').read_text())
    if status['backend']!='Sionna RT 2.0.1' or status['status']!='NATIVE_PIPELINE_COMPUTED':
        raise ValueError('NATIVE_BACKEND_NOT_COMPLETE')
    rows=json.loads(checked('PRODUCTION_INPUTS.json').read_text())
    matches=[r for r in rows if r['link_id']==link_id]
    if len(matches)!=1:raise ValueError('NATIVE_LINK_NOT_UNIQUE')
    row=matches[0];detail=json.loads(checked(link_id+'_RESULT.json').read_text())
    with np.load(checked(link_id+'_CHANNEL.npz')) as z:data={k:z[k] for k in z.files}
    if detail['tx']!=row['tx'] or detail['rx']!=row['rx']:raise ValueError('NATIVE_COORDINATE_MISMATCH')
    np.testing.assert_array_equal(data['tx_m'],row['tx']);np.testing.assert_array_equal(data['rx_m'],row['rx'])
    return dict(input=row,result=detail,channel=data)
