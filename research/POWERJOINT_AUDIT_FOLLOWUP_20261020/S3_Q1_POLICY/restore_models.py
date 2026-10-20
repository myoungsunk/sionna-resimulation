"""Use only the verified model artifact of this S3 training run."""
import argparse,json
from pathlib import Path
from train import get_artifacts,restore_artifact
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();items=[x for x in get_artifacts(a.run) if x['name'].startswith('powerjoint-s3-models-')];assert len(items)==1
 receipt=restore_artifact(items[0],a.out);models=list(a.out.rglob('MODELS.json'));assert len(models)==1
 man=json.loads((models[0].parent/'MANIFEST.json').read_text());assert man['technical']=='TECHNICAL_PASS' and man['stage']=='train'
 (a.out/'MODEL_ARTIFACT_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
 # Deliberately known flat path for subsequent workflow argument.
 assert models[0]==a.out/'MODELS.json','EXPECTED_FLAT_MODEL_ARTIFACT'
if __name__=='__main__':main()
