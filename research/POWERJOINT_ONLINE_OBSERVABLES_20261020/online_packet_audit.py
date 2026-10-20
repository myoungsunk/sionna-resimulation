#!/usr/bin/env python3
"""Full-only online-candidate indicators; offline GT used only for scoring/episode identity.
No LoS H, GT pose, prior GT error, future samples, or cross-port coherent phase is
accepted by online_features(). Both receive ports must nevertheless be time/power
calibrated. Simulation batch pairing is not evidence of hardware acquisition.
No new RF generation, EKF replay, policy fitting or test-set tuning.
"""
from pathlib import Path
import argparse,csv,json,hashlib
import numpy as np

F=257;DF=1950000.;C0=299792458.;WIN=np.hanning(F)
SPEC=[('C01','A','x_m',16,21,1,5.393),('C01','B','x_m',16,21,1,4.340),('C01','A','x_m',10,16,1,-3.079),('C02','A','x_m',4,10,1,1.775),('C03','A','x_m',1,4,1,.767),('C03','A','x_m',4,10,1,-3.115),('C03','B','x_m',10,16,1,.610),('C03','B','x_m',10,16,2,.537),('O02','O0','y_m',4,8,1,-4.330),('O03','O0','y_m',4,8,1,1.798),('O03','O0','y_m',4,8,2,-15.347),('O03','O0','y_m',0,4,2,-14.462)]
ANCHORS={'A':(4.,0.,2.65),'B':(10.,0.,2.65),'O0':(5.,2.2,2.65)}
PORTS={'C01':['A','B'],'C02':['A','B'],'C03':['A','B'],'O01':['O0'],'O02':['O0'],'O03':['O0']}
TINY=np.finfo(float).tiny

def cir(h,L=4):
    h=np.asarray(h);assert h.ndim==3 and h.shape[1:]==(257,2)
    # *L keeps amplitude scaling fixed across zero-padding factors; no new information.
    return np.fft.ifft(h*WIN[None,:,None],n=L*F,axis=1)*(L*F)

def detect(c,q=.3):
    a=abs(c);n=len(c);b=a.max(axis=1).argmax(axis=1)
    v=a[np.arange(n),:,b];peak=v.max(axis=1);valid=peak>1e-16
    idx=(v>=q*peak[:,None]).argmax(axis=1)
    return idx,b,valid

def pol_power(p):
    return (p[...,0]-p[...,1])/np.maximum(p.sum(axis=-1),TINY)

def window_power(power,idx,width):
    n,nt,_=power.shape;offset=idx[:,None]+np.arange(width)[None,:]
    okay=offset<nt;ix=np.minimum(offset,nt-1)
    return power[np.arange(n)[:,None],ix]*okay[:,:,None],okay.all(axis=1)

def online_features(h):
    """Single currently received Full two-port H only, no truth or historical future.
    Features are functions of per-port |CIR|^2; independent unknown port phase
    rotations cancel. Common gain invariance is unit-tested. H-to-CIR here stands
    in for readout of the measured CIR; changing hardware front-end needs QA.
    """
    h=np.asarray(h,np.complex128);assert np.isfinite(h).all()
    c=cir(h,4);p=abs(c)**2;idx,b,valid=detect(c);n=len(h);ii=np.arange(n);dt=1e9/(4*F*DF)
    sf=pol_power(p[ii,idx]);width4=int(np.ceil(4/dt));width16=int(np.ceil(16/dt));width40=int(np.ceil(40/dt))
    a4,ok4=window_power(p,idx,width4);a16,ok16=window_power(p,idx,width16);a40,ok40=window_power(p,idx,width40)
    e4=a4.sum(axis=(1,2));e40=a40.sum(axis=(1,2));e16=a16.sum(axis=(1,2))
    s4=pol_power(a4.sum(axis=1));s16=pol_power(a16.sum(axis=1))
    pt=a16.sum(axis=2);w=pt/np.maximum(e16[:,None],TINY);st=pol_power(a16);smean=(w*st).sum(axis=1)
    std_s=np.sqrt(np.maximum(0,(w*(st-smean[:,None])**2).sum(axis=1)))
    tp=np.arange(width40)*dt;wp=a40.sum(axis=2)/np.maximum(e40[:,None],TINY);mean=(wp*tp).sum(axis=1)
    spread=np.sqrt(np.maximum(0,(wp*(tp-mean[:,None])**2).sum(axis=1)))
    maxoff=a40.sum(axis=2).argmax(axis=1)
    # Envelope-shape similarity, not cross-port complex Jones alignment.
    u=a16[:,:,0];v=a16[:,:,1]
    align=(u*v).sum(axis=1)/np.maximum(np.sqrt((u*u).sum(axis=1)*(v*v).sum(axis=1)),TINY)
    det=[];ss=[]
    for q in (.2,.3,.4):
        iq,_,_=detect(c,q);det.append(iq*dt);ss.append(pol_power(p[ii,iq]))
    f=dict(s_full=sf,abs_s_full=abs(sf),saturation_full=abs(sf)>.95,
        pol_fp_vs_early4_abs=abs(sf-s4),pol_early4_vs16_abs=abs(s4-s16),pol_delay_std16=std_s,
        late_energy_fraction40=1-e4/np.maximum(e40,TINY),delay_spread40_ns=spread,
        peak_minus_detected_fp_ns=maxoff*dt,port_envelope_mismatch16=1-align,
        detector_time_span_ns=np.ptp(det,axis=0),detector_pol_span=np.ptp(ss,axis=0),
        valid_feature=valid&ok4&ok16&ok40,estimated_fp_ns=idx*dt)
    for k,x in f.items():
        assert len(x)==n and np.isfinite(x[f['valid_feature']]).all(),k
    return f

def timing_eval(h,l,xyz,anchor):
    """No values in this function enter online_features.
    Geometric d/c is an offline reference, not complete receiver/antenna calibrated
    arrival truth. No-direct frames are excluded from direct-reference errors.
    """
    n=len(h);out={};geom=np.linalg.norm(xyz-np.asarray(anchor)[None,:],axis=1)/C0*1e9
    for factor in (4,16):
        a=cir(h,factor);b=cir(l,factor);ia,_,va=detect(a);ib,_,vb=detect(b);dt=1e9/(factor*F*DF)
        out['fp_full_'+str(factor)+'_ns']=ia*dt;out['fp_los_'+str(factor)+'_ns']=ib*dt
        out['full_minus_los_'+str(factor)+'_ns']=(ia-ib)*dt
        out['full_minus_geom_'+str(factor)+'_ns']=ia*dt-geom
        out['los_minus_geom_'+str(factor)+'_ns']=ib*dt-geom
        out['s_full_'+str(factor)]=pol_power(abs(a[np.arange(n),ia])**2)
        out['s_los_'+str(factor)]=pol_power(abs(b[np.arange(n),ib])**2)
        out['direct_reference_valid']=va&vb
    out['geom_ns']=geom
    return out

def unit_tests():
    rng=np.random.default_rng(20261020);h=rng.normal(size=(5,F,2))+1j*rng.normal(size=(5,F,2))
    a=online_features(h);b=online_features(h*np.exp(1j*np.array([.83,-1.13]))[None,None,:]*2.5)
    for k in a:
        assert np.allclose(a[k],b[k],rtol=1e-10,atol=1e-10),('phase/gain',k)
    f=np.arange(F)*DF;delay=18.23e-9;u=np.exp(-2j*np.pi*f*delay)[None,:,None]*np.array([1.,.5])[None,None,:]
    a=online_features(u)
    for k in ['pol_fp_vs_early4_abs','pol_early4_vs16_abs','pol_delay_std16','port_envelope_mismatch16','detector_pol_span']:
        assert np.max(abs(a[k]))<1e-10,('single proportional path',k,a[k])
    pure=[]
    for fac in [4,8,16,32,64]:
        ix,_,_=detect(cir(u,fac));delta=1e9/(fac*F*DF)
        pure.append({'factor':fac,'tap_spacing_ns':delta,'detected_minus_geom_ns':float(ix[0]*delta-delay*1e9)})
    return {'phase_independent_per_port':'PASS','common_gain_invariance':'PASS','single_path_constant_port_ratio':'PASS','synthetic_single_path_leading_edge_bias':pure,'is_hardware_test':False}

def runmask(mask):
    diff=np.diff(np.r_[False,mask,False].astype(int));return list(zip(np.flatnonzero(diff==1),np.flatnonzero(diff==-1)))

def write_csv(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)

def finite_stat(a,op='median'):
    a=np.asarray(a,float);a=a[np.isfinite(a)]
    if not len(a):return None
    if op=='rms':return float(np.sqrt(np.mean(a*a)))
    if op=='mean':return float(np.mean(a))
    return float(np.median(a))

def run(source,out,route):
    out.mkdir(parents=True,exist_ok=True);base=source/route;assert base.exists(),base
    unit=unit_tests();events=[];timing=[];allrows=[];provenance=[];casecounts={}
    for anchor in PORTS[route]:
        batches=sorted((base/'BATCHES').glob(route+'_'+anchor+'_M45_FULL_P*'));assert batches,(route,anchor)
        meta=[];features=[];offline=[]
        for batch in batches:
            f=batch/'H_FULL.npy';l=batch/'H_DIRECT_LOS.npy'
            hh=np.load(f,allow_pickle=False);ll=np.load(l,allow_pickle=False);assert hh.shape==ll.shape and hh.shape[1:]==(F,2,2)
            po=base/'BATCH_POSES'/(batch.name+'.csv')
            with po.open(newline='') as z:rows=list(csv.DictReader(z))
            assert len(rows)==len(hh)
            xyz=np.array([[float(x['x_m']),float(x['y_m']),float(x.get('z_m',.45))] for x in rows])
            feat=online_features(hh[:,:,:,0]);ev=timing_eval(hh[:,:,:,0],ll[:,:,:,0],xyz,ANCHORS[anchor])
            features.append(feat);offline.append(ev);meta+=rows
            provenance.append({'full':str(f),'full_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'los_eval_only_sha256':hashlib.sha256(l.read_bytes()).hexdigest(),'pose_sha256':hashlib.sha256(po.read_bytes()).hexdigest()})
        fe={k:np.concatenate([x[k] for x in features]) for k in features[0]};ev={k:np.concatenate([x[k] for x in offline]) for k in offline[0]}
        t=np.array([float(x['t_s']) for x in meta]);assert np.all(np.diff(t)>0);casecounts[anchor]=len(t)
        for i,row in enumerate(meta):
            rr={'route':route,'anchor':anchor,'pose_id':row.get('pose_id',i),'t_s':float(t[i])}
            rr.update({k:(bool(v[i]) if v.dtype==bool else float(v[i])) for k,v in fe.items()})
            allrows.append(rr)
        for a,an,c,lo,hi,v,eff in SPEC:
            if a!=route or an!=anchor:continue
            coord=np.array([float(x[c]) for x in meta]);segments=runmask((coord>=lo)&(coord<hi));assert len(segments)>=v
            start,end=segments[v-1];pick=np.zeros(len(t),bool);pick[start:end]=True;good=pick&fe['valid_feature']
            event={'route':route,'anchor':anchor,'coordinate':c,'low':lo,'high':hi,'visit':v,'n':end-start,'valid_features':int(good.sum()),'t_start_s':float(t[start]),'t_end_s':float(t[end-1]),'historical_skip_gain_deg':eff,'skip_reference_replayed_now':False}
            for k in fe:
                if k=='valid_feature':continue
                event[k+'_median']=finite_stat(fe[k][good]);event[k+'_mean']=finite_stat(fe[k][good],'mean')
            events.append(event)
            g=pick&ev['direct_reference_valid'];diag={k:event[k] for k in ['route','anchor','low','high','visit','n','t_start_s','t_end_s']};diag['n_direct_valid']=int(g.sum())
            for fac in [4,16]:
                for f in ['full_minus_los','full_minus_geom','los_minus_geom']:
                    x=ev[f+'_'+str(fac)+'_ns'][g]
                    diag[f+'_'+str(fac)+'_rms_ns']=finite_stat(x,'rms');diag[f+'_'+str(fac)+'_mean_ns']=finite_stat(x,'mean')
                diag['delta_s_'+str(fac)+'_rms']=finite_stat((ev['s_full_'+str(fac)]-ev['s_los_'+str(fac)])[g],'rms')
            timing.append(diag)
        # Entire case timing is scored only on explicit valid direct LoS reference.
        g=ev['direct_reference_valid'];diag={'route':route,'anchor':anchor,'scope':'ALL_CASE','n':len(t),'n_direct_valid':int(g.sum())}
        for fac in [4,16]:
            for f in ['full_minus_los','full_minus_geom','los_minus_geom']:
                x=ev[f+'_'+str(fac)+'_ns'][g];diag[f+'_'+str(fac)+'_rms_ns']=finite_stat(x,'rms');diag[f+'_'+str(fac)+'_mean_ns']=finite_stat(x,'mean')
        timing.append(diag)
    write_csv(out/(route+'_ONLINE_PACKETS.csv'),allrows);write_csv(out/(route+'_ONLINE_EVENTS.csv'),events);write_csv(out/(route+'_FP_TIMING_EVAL.csv'),timing)
    result={'route':route,'case_counts':casecounts,'total_packets':len(allrows),'n_paired_events':len(events),'unit_checks':unit,'source_files':provenance,'online_predictors_input':'current Full only; independent-port phase invariant powers; LoS,GT and ray paths EXCLUDED','offline_labels':'prior fixed-episode RF-skip effects, not refit or replayed','window_ns':[4,16,40],'new_EKF_runs':0,'new_Sionna_runs':0,'hardware_synchronization_and_noise':'NOT_VERIFIED','firstpath_true_reference_limit':'d/c geometric reference plus Direct-LoS detector diagnostic, not raw-ray group-delay ground truth; blocked excluded'}
    (out/(route+'_AUDIT.json')).write_text(json.dumps(result,indent=2)+'\n')
    print('ONLINE_ROUTE_PASS',route,json.dumps(result['case_counts']),len(events),flush=True)
    for e in events:
        print('ONLINE_EVENT',json.dumps({k:e[k] for k in ['route','anchor','low','high','visit','n','historical_skip_gain_deg','pol_fp_vs_early4_abs_median','pol_delay_std16_median','late_energy_fraction40_median','detector_pol_span_median','abs_s_full_median']}),flush=True)
    for e in timing:
        print('TIMING_EVAL',json.dumps(e),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('output');ap.add_argument('route');x=ap.parse_args();run(Path(x.source),Path(x.output),x.route)
