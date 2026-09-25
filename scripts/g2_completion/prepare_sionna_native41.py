"""Prepare additive native-Sionna inputs, preserving canonical geometry/banks."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from rt_cp_uwb_py.g2_relocated_inputs import RelocatedInputs,sha
from rt_cp_uwb_py.c1_c3_geometry import panel_corners

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    prior=ROOT/'results/SIONNA_G2_SCOPED41_V3_20260925_01a0d6e5'
    old=json.loads((prior/'CONFIG.json').read_text());feed=RelocatedInputs(old['input_root'],old['geometry_root'])
    bank=Path(old['bank_root']);bm=json.loads((bank/'BANK_MANIFEST.json').read_text())
    geometry=Path(old['geometry_root']);mf=geometry/'SCENE_MESH_MANIFEST.json';manifest=json.loads(mf.read_text())
    rows=[];dynamic={}
    for r in feed.rows:
        row={k:r[k] for k in ['link_id','scene_id','tx','rx','frame','tx_rotation','rx_rotation'] if k in r}
        for k in ['tx_rotation','rx_rotation']:row[k]=row[k].tolist()
        frame=r.get('frame_record');obj=frame['physical'].get('object') if frame else None
        if obj:
            pts=panel_corners(obj['panel']);name='dynamic/'+r['link_id']+'.ply';row['dynamic_panel']=name
            dynamic[name]='\n'.join(['ply','format ascii 1.0','element vertex 4','property float x','property float y','property float z','element face 2','property list uchar int vertex_indices','end_header']+[' '.join(format(x,'.17g') for x in v) for v in pts]+['3 0 1 2','3 0 2 3'])+'\n'
        rows.append(row)
    config=dict(rows=rows,ports=bm['ports'],bank_sha256=bm['npz_sha256'],noise=old['noise'],detector=old['detector'],
                solver=dict(max_depth=3,samples_per_src=100000,max_num_paths_per_src=1000000,synthetic_array=True,los=True,
                            specular_reflection=True,refraction=True,diffraction=False,edge_diffraction=False,diffuse_reflection=False,seed=20260924),
                backend='unmodified Sionna RT 2.0.1 PathSolver and FieldCalculator',
                model='native single-layer air-slab-air; no volume TRT extension',
                ideal_material_mapping={'PEC':'native ITU metal 1 mm','EPS4_LOSSLESS':'native RadioMaterial epsilon_r=4 with manifest thickness'},
                exclusions=['diffraction','diffuse scattering'],search_completeness_claim=False,
                bank_root=str(bank),geometry_root=str(geometry),classification='RD/HB deferred by user')
    (a.out/'CONFIG.json').write_text(json.dumps(config,indent=2),encoding='utf8')
    hashes=dict(feed.inputs);hashes[str(mf)]=sha(mf);hashes[str(prior/'CONFIG.json')]=sha(prior/'CONFIG.json')
    for name,h in bm['npz_sha256'].items():
        assert sha(bank/name)==h;hashes[str(bank/name)]=h
    script=ROOT/'scripts/g2_completion/sionna_native_runtime.py'
    hashes[str(script)]=sha(script);hashes[str(Path(__file__).resolve())]=sha(Path(__file__))
    with zipfile.ZipFile(a.out/'INPUTS.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.write(a.out/'CONFIG.json','CONFIG.json');z.write(mf,'SCENE_MESH_MANIFEST.json');z.write(script,script.name)
        selected={r['scene_id'] for r in rows}
        for scene in manifest['scenes']:
            if scene['scene_id'] not in selected:continue
            for m in scene['materials']:
                p=geometry/m['mesh'];assert sha(p)==m['sha256'];hashes[str(p)]=m['sha256'];z.write(p,m['mesh'])
        for name,data in dynamic.items():z.writestr(name,data)
    (a.out/'INPUT_MANIFEST.json').write_text(json.dumps(dict(inputs=hashes,command=sys.argv,config_sha256=sha(a.out/'CONFIG.json'),payload_sha256=sha(a.out/'INPUTS.zip')),indent=2))
    print(json.dumps(dict(rows=len(rows),scenes=len(selected),dynamic_panels=len(dynamic),inputs=len(hashes))))

if __name__=='__main__':main()
