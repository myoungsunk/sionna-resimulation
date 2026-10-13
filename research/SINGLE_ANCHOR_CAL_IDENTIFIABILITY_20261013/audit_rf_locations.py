"""Read-only cross-branch source inventory; does not execute experiments."""
from pathlib import Path
import subprocess, json, hashlib, re, urllib.request, datetime
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'out/rf_location_addendum'
DATA='f1d6d9fc984feb2c9a3b5fba36ca9aaa31fbe933'
RF='ce38566d2183f6a76c349b4e39a2a000f27e542a'
PREFIX='research/LOS_RANGE_RECAL_20261012/'
BLOCK='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/'
DELIVERY='research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012/'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    OUT.mkdir(exist_ok=False)
    names=['r23_run.py','r23_gm_unit_test.py','gm_ekf.py','p3_common.py','p3_detector_candidates.py','R23_PREREG_KO.md','R23_RESULT_KO.md','out_p0_p5/R1/P0/P0_INPUT_MANIFEST.json','out_p0_p5/R1/P0/TRAIN_VAL_TEST_SITE_SPLIT.json','out_p0_p5/R1/P3/P3_FROZEN_MODEL.json','out_p0_p5/R1/P3/P3_FREEZE_ADDENDUM.json','out_p0_p5/R1/P3/P3_MODEL_CANDIDATES.json','out_p0_p5/R1/P3/P3_VALIDATION_PAIRED.csv','out_p0_p5/R1/P3/P3_LEAKAGE_TESTS.json','out_p0_p5/R1/RUN_MANIFEST.json']
    sources={}
    for name in names:
        b=git('show',DATA+':'+PREFIX+name)
        dest=OUT/'references'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
        sources[PREFIX+name]={'commit':DATA,'sha256':sha(b),'bytes':len(b)}
    inventory=[]
    for commit,path in [(RF,BLOCK),(DATA,DELIVERY)]:
        for line in git('ls-tree','-r',commit,path).decode().splitlines():
            meta,p=line.split('\t',1)
            if re.fullmatch(r'(?:H_(?:LoS_)?R[245]_a[AB]_m(?:0|45)|freqs_hz)\.npy',p.rsplit('/',1)[-1]):
                inventory.append({'commit':commit,'path':p,'blob':meta.split()[-1],'bytes_verified':False})
    freq=git('show',RF+':'+BLOCK+'freqs_hz.npy')
    (OUT/'freqs_hz.npy').write_bytes(freq)
    fhash=sha(freq)
    model=json.loads((OUT/'references/out_p0_p5/R1/P3/P3_FROZEN_MODEL.json').read_text())
    add=json.loads((OUT/'references/out_p0_p5/R1/P3/P3_FREEZE_ADDENDUM.json').read_text())
    checks={'frozen_model_sha_matches':sources[PREFIX+'out_p0_p5/R1/P3/P3_FROZEN_MODEL.json']['sha256']==add['frozen_model_sha256'],
            'fitting_script_sha_matches':sources[PREFIX+'p3_detector_candidates.py']['sha256']==add['code_sha256']['p3_detector_candidates.py'],
            'current_common_sha_matches_addendum':sources[PREFIX+'p3_common.py']['sha256']==add['code_sha256']['p3_common.py'],
            'current_common_is_fit_time_bytes':sources[PREFIX+'p3_common.py']['sha256']==model['code_sha256']['p3_common.py']}
    release={}
    try:
        url='https://api.github.com/repos/myoungsunk/sionna-resimulation/releases/tags/v01b-r-los-h-m45-20261012'
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'I0-provenance-audit'}),timeout=20) as r: raw=json.load(r)
        release={'url':raw['html_url'],'tag':raw['tag_name'],'assets':[{'name':x['name'],'bytes':x['size'],'url':x['browser_download_url'],'digest':x.get('digest')} for x in raw['assets']], 'asset_bytes_downloaded':False}
    except Exception as e: release={'metadata_status':'UNVERIFIED','error':str(e)}
    result={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources':sources,'channel_inventory':inventory,'frequency_sha256':fhash,'frequency_bytes':len(freq),'checks':checks,'release':release,'H_sha_verification':'User reports 12/12 Full and 7/7 tracked LoS match P0; not independently rehashed in this location audit','historical_execution_binding':'INCONCLUSIVE: R23 result lacks command and input hashes','I1':'NOT_RUN'}
    (OUT/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'frequency_sha256':fhash,'channels':len(inventory),'release':release}))
if __name__=='__main__':main()
