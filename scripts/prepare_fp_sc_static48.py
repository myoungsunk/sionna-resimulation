"""Prepare original 48 static waveform controls without running detection."""
from pathlib import Path
import argparse,json,platform,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from qclean_uwb.fp_sc.followup.contracts import sha256,write_json,verify_files
from qclean_uwb.fp_sc.followup.runner import code_paths
from qclean_uwb.fp_sc.followup.static_detection import load_static,validate_static_specs

def prepare(root,manifest_path,original_lock,out):
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(manifest_path.read_text());original=json.loads(original_lock.read_text())
    sources={r['path']:r['sha256'] for r in original['files'] if r['path'].endswith('FIELDS_AND_WINDOWS.npz')}
    assert len(sources)==24;verify_files(root,sources)
    specs={};locked=dict(manifest['input_files']);checks=[]
    for path in sorted(sources):
        condition=Path(path).parent.name
        with np.load(root/path,allow_pickle=False) as z:
            full=z['full_spectrum'];direct=z['direct_spectrum']
        for channel,observed in [('Full',full),('Native_LoS',direct)]:
            cid='STATIC_'+condition+'_'+channel;folder=out/cid;folder.mkdir()
            np.savez_compressed(folder/'online.npz',Hrf=observed)
            np.savez_compressed(folder/'evaluator.npz',reference_H=direct)
            spec=dict(condition_id=condition,channel=channel,online_npz=(folder/'online.npz').relative_to(root).as_posix(),
                      evaluator_npz=(folder/'evaluator.npz').relative_to(root).as_posix())
            for key in ('online_npz','evaluator_npz'):locked[spec[key]]=sha256(root/spec[key])
            online,ev=load_static(root,spec,locked)
            assert np.array_equal(online.spectrum,observed) and np.array_equal(ev.spectrum,direct)
            specs[cid]=spec;checks.append(dict(case_id=cid,source=path,source_sha256=sources[path],
                observed_exact=True,reference_exact=True,no_fake_time_prior_controls=True))
    manifest.update(static_cases=specs,expected_static_cases=48,input_files=locked,
        environment={'python':platform.python_version(),'numpy':np.__version__},
        code_files={p:sha256(root/p) for p in code_paths(root)},mapping_reviewed=False)
    validate_static_specs(root,manifest)
    write_json(out/'MANIFEST_PREP_ONLY.json',manifest)
    write_json(out/'NO_EXECUTION_APPROVAL.json',dict(execute_science=False,stages=[],E1_02_GO=False,E2_GO=False))
    write_json(out/'STATIC_PREPARATION.json',dict(status='PASS_STATIC48_FORMAT_ONLY',
        static_cases=48,dynamic_packets=6272,total_waveforms=6320,checks=checks,
        files={p.relative_to(out).as_posix():sha256(p) for p in out.rglob('*.npz')},
        real_detection_calls=0,real_select_calls=0,E1_02_started=False,E2_started=False))
    print('STATIC48_PREPARED_NO_DETECTION',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','manifest','original-lock','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();prepare(a.root.resolve(),a.manifest,a.original_lock,a.output.resolve())
