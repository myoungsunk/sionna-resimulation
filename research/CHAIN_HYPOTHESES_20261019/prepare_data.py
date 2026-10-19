"""Read frozen RF, train only on held-route complements, and emit numerical inputs."""
from pathlib import Path
import argparse,json,io,zipfile
import numpy as np
import pandas as pd
from runtime import load,write_json
from training import train_all


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',required=True);ap.add_argument('--inputs',required=True);args=ap.parse_args()
    work=Path(args.work);inp=Path(args.inputs);rt=load(work);root=rt['root'];model=rt['model']
    manifest=json.loads((root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
    cases={c['id']:c for c in manifest['cases']}
    frames=[];cache={};checks=[]
    with zipfile.ZipFile(inp/'n4b.zip') as z:
        nm=next(n for n in z.namelist() if n.endswith('N4B_OOF_PREDICTIONS.csv.gz'))
        archived=pd.read_csv(io.BytesIO(z.read(nm)),compression='gzip')
    old=archived[archived.model=='R0'].set_index(['case','pose_id'])
    for cid,meta in cases.items():
        s=pd.DataFrame(json.loads((root/meta['samples_path']).read_text()))
        truth=np.column_stack([s.x,s.y,np.radians(s.yaw_body_deg)])
        pred=[];jac=[]
        for i in range(0,len(s),64):
            h,H=model.batch(truth[i:i+64],meta);pred.append(h);jac.append(H)
        pred=np.concatenate(pred);jac=np.concatenate(jac)
        cache[cid]={'h':pred,'H':jac,'truth':truth,'samples':s}
        for ch,pathkey in [('full','full_path'),('los','los_path')]:
            H=np.load(root/meta[pathkey],mmap_mode='r');parts=[]
            for i in range(0,len(H),64):parts.append(pd.DataFrame(rt['extract'](H[i:i+64,:,:,0],model.freqs)))
            q=pd.concat(parts,ignore_index=True)
            q['case']=cid;q['route']=cid[:2];q['channel']=ch;q['pose_id']=s.pose_id.to_numpy()
            q['x_eval']=s.x;q['y_eval']=s.y;q['yaw_rad']=truth[:,2]
            q['mount_feature']=meta['mount_deg']/45.;q['anchor_x_feature']=meta['anchor'][0]/10.
            q['e_r']=q.range_m-pred[:,0];q['e_s']=q.s_fp-pred[:,1];q['s_model']=pred[:,1]
            q['fp_tap']=q.tap;q['strong_port']=q.branch;q['gpsi']=jac[:,1,2]
            dx=s.x-meta['anchor'][0];dy=s.y-meta['anchor'][1]
            q['distance']=np.sqrt(dx*dx+dy*dy+(meta['robot_z_m']-meta['anchor'][2])**2)
            q['relative_yaw']=(truth[:,2]+np.radians(meta['mount_deg'])-np.arctan2(-dy,-dx)+np.pi)%(2*np.pi)-np.pi
            frames.append(q)
        ref=old.loc[cid];obs=frames[-2].set_index('pose_id').loc[ref.index]
        check={'case':cid,'n':len(s),'old_observer_r_max':float(abs(obs.range_m-ref.range_m).max()),'old_observer_s_max':float(abs(obs.s_fp-ref.s_fp).max()),'source_native_s_rmse':float(np.sqrt(np.mean(frames[-1].e_s**2)))}
        checks.append(check);print('INPUT_PARITY',check,flush=True)
    allq=pd.concat(frames,ignore_index=True)
    pol,cfg,density,risk=train_all(rt,allq,{c:v['H'] for c,v in cache.items()})
    allq.to_csv(work/'SOURCE_PACKET_FEATURES.csv.gz',index=False)
    write_json(work/'FIT_CONFIG.json',cfg);write_json(work/'CASES.json',cases)
    pd.DataFrame(checks).to_csv(work/'DATA_QA.csv',index=False)
    pd.DataFrame(density).to_csv(work/'DENSITY_DIAGNOSTICS.csv',index=False)
    pd.DataFrame(risk).to_csv(work/'RISK_DIAGNOSTICS.csv',index=False)
    los=allq[allq.channel=='los'].set_index(['case','pose_id'])
    with zipfile.ZipFile(inp/'rf.zip') as z:
        manifest=json.loads(z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
        for rec in manifest['per_case']:
            cid,ch=rec['case'],rec['channel']
            with np.load(io.BytesIO(z.read('P2_OUT/'+rec['trace_file'])),allow_pickle=False) as a:
                t=a['t_s'].copy();ids=a['pose_id'].copy();truth=a['truth_for_offline_scoring_only'].copy();obs=np.column_stack([a['z_r_m'],a['z_s']])
            p=pol[(cid,ch)];q=p['q'];ix=pd.Index(q.pose_id).get_indexer(ids)
            if np.any(ix<0):raise RuntimeError('Missing original pose in new packet data')
            l=los.loc[[(cid,int(k)) for k in ids]]
            payload={'t':t,'pose_id':ids,'truth':truth,'z':obs,'z_los':l[['range_m','s_fp']].to_numpy(),'h_truth':cache[cid]['h'][ids],'H_truth':cache[cid]['H'][ids]}
            for k in ['mu','R','mu_rich','R_rich','risk','utility']:payload[k]=p[k][ix]
            for k in rt['features']+['relative_yaw','distance','gpsi','fp_tap','strong_port']:payload['feature_'+k]=q.iloc[ix][k].to_numpy()
            for level in ['B0','L0','L1','L2']:
                controls,x0=rt['controls'](t,truth,level)
                for k,v in controls.items():payload[level+'_'+k]=v
                payload[level+'_x0']=x0
            np.savez_compressed(work/(cid+'_'+ch+'.npz'),**payload)
    print('PREPARED',len(allq),'source labels;',len(pol),'RF case/channel packets',flush=True)

if __name__=='__main__':main()
