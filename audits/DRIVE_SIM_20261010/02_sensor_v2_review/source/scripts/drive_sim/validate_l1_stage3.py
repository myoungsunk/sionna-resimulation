"""Additive, CPU-only L1 replay and bounded diagnostics; never rebuilds a LUT."""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys, time, itertools, importlib.util
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from qclean_uwb.drivesim import hs_lut as L, observation as O
from qclean_uwb.drivesim.rf_store import load_banks
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION

OUT = ROOT / 'results/DRIVE_SIM_L1_STAGE3_20261008'
OLD = ROOT / 'results/DRIVE_SIM_20261007/SNOWBALL_RUNS/01a11582/final_B_20261007T1017Z/S4'
RAW = Path('D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/selected_raw')
REV = '1b9cf190244f91d0097a82106a02ec1dd5f53220'
def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''): h.update(b)
    return h.hexdigest()
def write(name, x):
    (OUT/name).write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False,
        default=lambda v:v.item() if isinstance(v,np.generic) else v.tolist()), encoding='utf-8')
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)

def prepare():
    assert not (OUT/'PLAN.json').exists(), 'Do not overwrite frozen plan'
    inputs = OUT/'inputs'
    for name in ('hs_lut_2deg.npy','hs_lut_meta.json','freqs_hz.npy'):
        (inputs/name).write_bytes((RAW/name).read_bytes())
    (inputs/'hs_lut_manifest.json').write_bytes((OLD/'hs_lut_manifest.json').read_bytes())
    manpath = ROOT/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json'
    (inputs/'BANK_MANIFEST.json').write_bytes(manpath.read_bytes())
    expected = json.loads(manpath.read_text())['npz_sha256']
    for name in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
        assert digest(inputs/name)==expected[name], name
    assert digest(inputs/'hs_lut_2deg.npy')==json.loads((OLD/'hs_lut_manifest.json').read_text())['outputs'][0]['sha256']
    src = ['scripts/drive_sim/build_hs_lut.py','src/qclean_uwb/drivesim/hs_lut.py','src/qclean_uwb/drivesim/observation.py','src/qclean_uwb/drivesim/pattern_apply.py','src/qclean_uwb/drivesim/rf_store.py','src/qclean_uwb/features/fp_power.py','src/qclean_uwb/scenarios/corridor.py']
    snapshots=OUT/'source'; snapshots.mkdir()
    for p in src:
        (snapshots/Path(p).name).write_bytes((ROOT/p).read_bytes())
        (snapshots/(Path(p).stem+'_original.py')).write_bytes(git('show', REV+':'+p))
    (OUT/'SOURCE_DIFF.patch').write_bytes(git('diff', REV, 'HEAD','--',*src))
    (OUT/'GIT_STATUS_BEFORE.txt').write_bytes(git('status','--short'))
    protected = {str(p.relative_to(ROOT)):digest(p) for folder in ('src','scripts','tests','configs') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    for p in (ROOT/'results/DRIVE_SIM_20261007').rglob('*'):
        if p.is_file(): protected[str(p.relative_to(ROOT))]=digest(p)
    for name in ('OUTPUT_MANIFEST.json','FINAL_REPORT_KO.md'):
        p=ROOT/'results/SENSOR_V2_STAGE2_20261008'/name
        protected[str(p.relative_to(ROOT))]=digest(p)
    write('PROTECTED_BEFORE.json',protected)
    rng=np.random.default_rng(20261007)
    pts=np.column_stack([rng.uniform(5,85,500),rng.uniform(-180,180,500),rng.uniform(-180,180,500)])
    np.save(OUT/'SAMPLES_500.npy',pts)
    np.savetxt(OUT/'SAMPLES_500.csv', np.column_stack([np.arange(500),pts]), delimiter=',',header='sample_id,theta_deg,phi_tx_deg,phi_rx_deg',comments='')
    shape={}
    for p in inputs.glob('*.npz'):
        with np.load(p,allow_pickle=False) as z:
            shape[p.name]={k:dict(shape=list(z[k].shape),dtype=str(z[k].dtype)) for k in z.files}
    write('PLAN.json',dict(head=git('rev-parse','HEAD').decode().strip(),branch=git('branch','--show-current').decode().strip(),original_revision=REV,
        source_hashes={p:digest(ROOT/p) for p in src},inputs={p.name:dict(sha256=digest(p),bytes=p.stat().st_size) for p in inputs.iterdir()},bank_schema=shape,
        sample_sha256=digest(OUT/'SAMPLES_500.npy'),seed=20261007,n=500,sampling='Three sequential rng.uniform vectors: theta [5,85], phi_tx [-180,180], phi_rx [-180,180]',
        original_thresholds=dict(max=0.01,median=0.001),options=dict(distance_m=10,tx=0,ports=['LP_plus45','LP_minus45'],window='symmetric Hann N',padding='4N tail zero padding',ifft='ifft * N',leading_edge_amplitude=0.3,detection_threshold=0,noise=None,delay='index/(4N*df)',ratio='(P1-P2)/(P1+P2)'),
        diagnostic=dict(selection='top 5 absolute errors; stable sample_id tie break; no sample exclusion',sweep='each angle separately +/-2 degrees, 0.05 deg spacing (81 points), 5*3*81=1215',corners='8 corners for every original point, cached duplicates; max 4000',seam='theta20,50,80; phi other -73,17,123; either azimuth +/-180 around +/-0.001 degree',pole='theta 0,0.001,89.999,90; azimuths -180,-90,0,90',fixed_tap='center sample index, diagnostic only',max_unique_los=6500,independent='raw-bank bilinear fields, explicit Cartesian matrices, NumPy Hann/IFFT and ratio; independent eight-weight interpolation',tolerances=dict(grid=1e-10,independent_s=1e-10,interpolation=1e-12,periodicity=1e-10)),
        restrictions=['no LUT rebuild','no Sionna','no RF solver','no filter','no tuning'],python=sys.version,numpy=np.__version__))
    print('PREPARED',json.dumps(shape))

def independent_h(banks,pt):
    # Separate implementation: no Bank.sample, field_world, los_h, observe or HsLut call.
    th,tx,rx=np.deg2rad(pt)
    d=np.array([np.sin(th)*np.cos(tx),-np.sin(th)*np.sin(tx),-np.cos(th)])
    yaw=np.arctan2(-d[1],-d[0])-rx
    c,s=np.cos(yaw),np.sin(yaw)
    rotations=[np.diag([1.,-1.,-1.]),np.array([[c,-s,0],[s,c,0],[0,0,1.]])]
    def field(b,R,direction):
        local=R.T@direction
        t=np.arccos(np.clip(local[2],-1,1)); p=np.arctan2(local[1],local[0])
        u=np.clip((t-b.theta[0])/(b.theta[1]-b.theta[0]),0,b.nt-1)
        v=np.clip(((p-b.phi[0])%(2*np.pi))/(b.phi[1]-b.phi[0]),0,b.np-1)
        i=min(int(np.floor(u)),b.nt-2); j=min(int(np.floor(v)),b.np-2); a=u-i; q=v-j
        fields=[]
        for e in (b.e_theta,b.e_phi): fields.append((1-a)*(1-q)*e[:,i,j]+(1-a)*q*e[:,i,j+1]+a*(1-q)*e[:,i+1,j]+a*q*e[:,i+1,j+1])
        basis=np.array([[np.cos(t)*np.cos(p),-np.sin(p)],[np.cos(t)*np.sin(p),np.cos(p)],[-np.sin(t),0.]])
        return np.sqrt(2*np.pi/376.730313668)*(np.stack(fields,axis=1)@basis.T)@R.T
    txfield=field(banks[0],rotations[0],d)
    rxfield=[field(b,rotations[1],-d) for b in banks]
    f=banks[0].freqs_hz
    return np.column_stack([np.sum(e*txfield,axis=1) for e in rxfield])*(299792458/f/(4*np.pi*10)*np.exp(-2j*np.pi*f*10/299792458))[:,None]

def weights(pt):
    t=np.clip(pt[0]/2,0,45-1e-9); a=(pt[1]+180)/2; b=(pt[2]+180)/2
    base=np.floor([t,a,b]).astype(int); frac=np.array([t,a,b])-base
    inds=[]; ws=[]
    for bits in itertools.product((0,1),repeat=3):
        ix=base+bits; ix[1:]%=180
        inds.append(tuple(ix)); ws.append(float(np.prod([frac[j] if bits[j] else 1-frac[j] for j in range(3)])))
    return inds,np.array(ws)

def run():
    assert not (OUT/'RESULT.json').exists(), 'No overwrites'
    plan=json.loads((OUT/'PLAN.json').read_text(encoding='utf-8')); start=time.perf_counter()
    for p,h in plan['source_hashes'].items(): assert digest(ROOT/p)==h
    for name,row in plan['inputs'].items(): assert digest(OUT/'inputs'/name)==row['sha256']
    banks=load_banks(OUT/'inputs'); f=banks[0].freqs_hz
    assert np.array_equal(f,np.load(OUT/'inputs/freqs_hz.npy'))
    S=np.load(OUT/'inputs/hs_lut_2deg.npy'); meta=json.loads((OUT/'inputs/hs_lut_meta.json').read_text())
    assert S.shape==(46,180,180) and np.isfinite(S).all()
    lut=L.HsLut(dict(s=S,theta_deg=meta['meta']['theta_deg'],phi_deg=np.arange(-180,180,2)))
    spec=importlib.util.spec_from_file_location('original_l1',OUT/'source/hs_lut_original.py'); old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    pts=np.load(OUT/'SAMPLES_500.npy'); assert len(np.unique(pts,axis=0))==500
    cache={}; hs=[]; cirs=[]; rows=[]; checks=[]
    def calc(p):
        p=np.asarray(p,float); key=tuple(p)
        if key in cache:return cache[key]
        assert len(rows)<6500
        th,ph=np.deg2rad(p[:2]); dw=ANCHOR_ROTATION@np.array([np.sin(th)*np.cos(ph),np.sin(th)*np.sin(ph),np.cos(th)])
        yaw=np.rad2deg(np.arctan2(-dw[1],-dw[0]))-p[2]
        h=L.los_h(banks,dw,yaw)[:,:,0]; cir=O.cir_batch(h[None])[0]; obs=O.first_path_batch(cir[None],float(f[1]-f[0])); idx=int(obs['index'][0])
        independent_cir=np.fft.ifft(h*np.hanning(len(f))[:,None],n=4*len(f),axis=0)*len(f)
        strongest=np.argmax(np.max(np.abs(independent_cir),axis=0)); mag=np.abs(independent_cir[:,strongest]); ix=int(np.flatnonzero(mag>=0.3*mag.max())[0])
        power=abs(independent_cir[ix])**2; si=(power[0]-power[1])/power.sum()
        assert ix==idx
        il,ws=weights(p); interp=float(sum(w*S[q] for q,w in zip(il,ws)))
        row=dict(id=len(rows),angles=p.tolist(),s_direct=float(obs['s'][0]),s_lut=float(lut(*p)),index=idx,power=obs['power'][0].tolist(),strongest_rx=int(strongest),peak=float(obs['peak'][0]),cell=[list(q) for q in il],weights=ws.tolist(),s_independent_ratio=float(si),s_independent_interp=interp)
        row['delta']=row['s_lut']-row['s_direct']; rows.append(row);hs.append(h);cirs.append(cir); cache[key]=row
        return row
    main=[]
    for i,p in enumerate(pts):
        row=calc(p); main.append(dict(sample_id=i,**row))
        ih=independent_h(banks,p); ic=np.fft.ifft(ih*np.hanning(len(f))[:,None],n=4*len(f),axis=0)*len(f)
        branch=np.argmax(np.max(abs(ic),axis=0)); mag=abs(ic[:,branch]);ix=int(np.flatnonzero(mag>=.3*mag.max())[0]);pw=abs(ic[ix])**2; si=float((pw[0]-pw[1])/sum(pw))
        checks.append(dict(sample_id=i,h_abs_max=float(np.max(abs(ih-hs[row['id']]))),s_abs=float(abs(si-row['s_direct'])),index_match=ix==row['index'],original_s_abs=float(abs(old.los_s_direct(banks,*p)-row['s_direct']))))
    err=np.abs([r['delta'] for r in main]); top=np.argsort(-err,kind='stable')[:5].tolist()
    write('SELECTED_DIAGNOSTICS.json',dict(rule=plan['diagnostic']['selection'],sample_ids=top,sweeps=plan['diagnostic']['sweep']))
    corners=[]
    for i,p in enumerate(pts):
        inds,ws=weights(p); center=main[i]; idx=center['index']; vertex=[]; fixed=[]
        for ix in inds:
            r=calc([2*ix[0],-180+2*ix[1],-180+2*ix[2]]); vertex.append(r)
            pw=abs(cirs[r['id']][idx])**2;fixed.append(float((pw[0]-pw[1])/pw.sum()))
        smooth=float(ws@fixed-center['s_direct']); selection=float(center['s_lut']-ws@fixed)
        corners.append(dict(sample_id=i,vertex_ids=[r['id'] for r in vertex],vertex_indices=[r['index'] for r in vertex],center_index=idx,all_same_index=all(r['index']==idx for r in vertex),grid_error_max=max(abs(r['delta']) for r in vertex),fixed_s_vertices=fixed,smooth_fixed_tap_error=smooth,selection_component=selection,decomposition_residual=float(center['delta']-smooth-selection)))
    sweeps=[]
    for i in top:
        p=pts[i]; tap=main[i]['index']
        for axis in range(3):
            group=[]
            for offset in np.linspace(-2,2,81):
                q=p.copy();q[axis]+=offset;r=calc(q);pw=abs(cirs[r['id']][tap])**2
                il,ws=weights(q); fixed_v=[]
                # Sweep fixed direct ratio isolates selection; original LUT always retained.
                group.append(dict(offset=float(offset),id=r['id'],fixed_tap=tap,s_fixed=float((pw[0]-pw[1])/pw.sum())))
            sweeps.append(dict(sample_id=i,axis=axis,points=group))
    boundaries=[]
    for th,other,axis in itertools.product((20.,50.,80.),(-73.,17.,123.),(1,2)):
        for val in (-180.001,-180.,-179.999,179.999,180.,180.001):
            p=np.array([th,other,other]);p[axis]=val;r=calc(p);q=p.copy();q[axis]+=360;pair=calc(q)
            boundaries.append(dict(type='wrap',id=r['id'],pair_id=pair['id'],direct_period_error=abs(r['s_direct']-pair['s_direct']),lut_period_error=abs(r['s_lut']-pair['s_lut'])))
    for th,tx,rx in itertools.product((0.,.001,89.999,90.),(-180.,-90.,0.,90.),(-180.,-90.,0.,90.)):
        r=calc([th,tx,rx]);boundaries.append(dict(type='pole_endpoint',id=r['id']))
    allsame=np.array([r['all_same_index'] for r in corners]); original=meta['gate_L1_interpolation']
    result=dict(gate=dict(max=float(err.max()),median=float(np.median(err)),n=500,n_gt_01=int(sum(err>.01)),n_gt_003=int(sum(err>.003)),passed=bool(err.max()<=.01 and np.median(err)<=.001)),original_gate=original,
        reproduction_difference=dict(max=float(err.max()-original['max']),median=float(np.median(err)-original['median'])),top_ids=top,
        same_index_cells=dict(n=int(allsame.sum()),max_error=float(err[allsame].max()),n_gt_01=int(sum(err[allsame]>.01))),mixed_index_cells=dict(n=int((~allsame).sum()),max_error=float(err[~allsame].max()),n_gt_01=int(sum(err[~allsame]>.01))),
        finite_all=all(np.isfinite([r['s_direct'],r['s_lut'],*r['power']]).all() for r in rows),unique_original_samples=500,missing_original_samples=0,
        grid_error_max=max(c['grid_error_max'] for c in corners),independent_h_error_max=max(x['h_abs_max'] for x in checks),independent_s_error_max=max(x['s_abs'] for x in checks),independent_indices_all=all(x['index_match'] for x in checks),original_current_s_error_max=max(x['original_s_abs'] for x in checks),
        independent_interp_error_max=max(abs(r['s_lut']-r['s_independent_interp']) for r in rows),independent_ratio_error_max=max(abs(r['s_direct']-r['s_independent_ratio']) for r in rows),
        wrap_direct_period_max=max(x['direct_period_error'] for x in boundaries if x['type']=='wrap'),wrap_lut_period_max=max(x['lut_period_error'] for x in boundaries if x['type']=='wrap'),
        n_unique_los=len(rows),elapsed_s=time.perf_counter()-start,scientific_PASS=False,F01='OPEN',F02='OPEN',correction_applied=False)
    for name,data in [('SAMPLES_RESULTS.json',main),('ALL_POINTS.json',rows),('CELL_DECOMPOSITION.json',corners),('SWEEPS.json',sweeps),('BOUNDARIES.json',boundaries),('INDEPENDENT_CHECKS.json',checks)]:write(name,data)
    np.savez_compressed(OUT/'RAW_CHANNEL_CIR.npz',H_tx0=np.array(hs),CIR_tx0=np.array(cirs),frequencies_hz=f,angles=np.array([r['angles'] for r in rows]))
    write('RESULT.json',result); print(json.dumps(result,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run']);args=ap.parse_args()
    prepare() if args.mode=='prepare' else run()
