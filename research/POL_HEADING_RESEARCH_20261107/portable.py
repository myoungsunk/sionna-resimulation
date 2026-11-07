"""Relocation adapter; archived experiment code and results remain unchanged."""
import argparse,hashlib,json,sys,shutil,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(p):return str(p).replace(chr(92),'/').casefold()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['verify','tests','replay-v3']);parser.add_argument('--output',type=Path);args=parser.parse_args()
 manifest=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
 for r in manifest:assert digest(ROOT/r['path'])==r['sha256'],r['path']
 if args.action=='verify':print(f'PASS: {len(manifest)} archived files match source hashes');return
 if args.output is None:parser.error('--output is required; use a new empty directory outside experiments/')
 output=args.output.resolve();protected=(ROOT/'experiments').resolve()
 if output==protected or protected in output.parents:parser.error('output must not be inside archived experiments')
 output.mkdir(parents=True,exist_ok=False)
 archive=ROOT/'experiments/POL_HEADING_VAR_20261106_v3';sys.path.insert(0,str(archive));import run_heading as m
 m.e.OLD=ROOT/'inputs/original_run';m.BASE=output
 lookup={norm(r['source']):ROOT/r['path'] for r in manifest}
 def relocated_sha(path):return digest(lookup.get(norm(path),Path(path)))
 m.sha=relocated_sha
 for name in ['INPUT_HASHES.json','EXTRA_HASHES.json']:shutil.copy2(archive/name,output/name)
 if args.action=='tests':
  m.tests();runpy.run_path(str(archive/'topology_tests.py'),run_name='__main__')
 else:
  runpy.run_path(str(archive/'campaign.py'),run_name='__main__')
 print('Completed:',output)
if __name__=='__main__':main()
