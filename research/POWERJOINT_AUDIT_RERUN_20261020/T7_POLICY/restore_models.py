"""Restore exact trained model bytes committed as base64 JSON; never retrain."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--input',type=Path,default=Path(__file__).with_name('TRAINED_MODELS_BASE64.json'))
    args=parser.parse_args();payload=json.loads(args.input.read_text(encoding='utf-8'))
    args.out.mkdir(parents=True,exist_ok=True)
    for name,item in payload['models'].items():
        assert Path(name).name==name and name.endswith('.pkl')
        data=base64.b64decode(item['base64'],validate=True)
        assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
        target=args.out/name
        if target.exists():assert target.read_bytes()==data,'Refuse different existing model: '+name
        else:target.write_bytes(data)
    print(json.dumps(dict(restored=len(payload['models']),archive_sha256=payload['archive_sha256'])))

if __name__=='__main__':main()
