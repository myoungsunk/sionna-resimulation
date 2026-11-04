"""Run frozen receiver diagnostics on a single QA-passed raw capture."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from diagnostics import evaluate
from producer import load_diagnostics


def main(capture, out):
    receipt=json.loads((capture/'MANIFEST.json').read_bytes())
    raw=capture/'RAW.npz'
    if receipt['status']!='PASS':
        raise ValueError('raw capture has not passed reconstruction')
    if hashlib.sha256(raw.read_bytes()).hexdigest()!=receipt['raw_sha256']:
        raise ValueError('raw SHA256 mismatch')
    out.mkdir(parents=True,exist_ok=False)
    result=evaluate(out,**load_diagnostics(raw))
    for channel in ('full','los'):
        if result['native'][channel]['tap']!=result['archive'][channel]['tap']:
            raise ValueError('native and archived tap differ; stop for review')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}
    (out/'DERIVED_MANIFEST.json').write_text(json.dumps(dict(case=receipt['case'],pose_id=receipt['pose']['pose_id'],
        source_raw=receipt['raw_sha256'],diagnostics_sha256=hashlib.sha256(Path(__file__).with_name('diagnostics.py').read_bytes()).hexdigest(),
        output_hashes=hashes),indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('capture',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    main(args.capture,args.output)
