"""Extend verified S2 preservation with pagination for 105 label artifacts."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
 t=(HERE.parent/'S2_N2_GEOMETRY/preserve_outputs.py').read_text().replace('S2','S3').replace('s2','s3')
 t=t.replace("metas=api(s,f'actions/runs/{rid}/artifacts',params={'per_page':100})['artifacts'];assert metas","metas=[];page=1\n  while True:\n   chunk=api(s,f'actions/runs/{rid}/artifacts',params={'per_page':100,'page':page})['artifacts'];metas+=chunk\n   if len(chunk)<100:break\n   page+=1\n  assert metas")
 t=t.replace("jobs=api(s,f'actions/runs/{rid}/jobs',params={'per_page':100})['jobs']","jobs=[];page=1\n  while True:\n   chunk=api(s,f'actions/runs/{rid}/jobs',params={'per_page':100,'page':page})['jobs'];jobs+=chunk\n   if len(chunk)<100:break\n   page+=1")
 t=t.replace("assert len(records)>=16,'EXPECTED_TRAIN_PLUS_FIRST9_PLUS_RETRY6'","assert records,'NO_EXISTING_ARTIFACTS_TO_PRESERVE'\n if all(r['conclusion']=='success' for r in runs):assert len(records)>=115,'EXPECTED_105_LABELS_PLUS_MODEL_PLUS_9_EVALUATION'\n # Failed/skipped runs still get a durable receipt for every available artifact.")
 t=t.replace('deadline=time.monotonic()+7200','deadline=time.monotonic()+21600')
 (HERE/'preserve_outputs.py').write_text(t)
if __name__=='__main__':main()
