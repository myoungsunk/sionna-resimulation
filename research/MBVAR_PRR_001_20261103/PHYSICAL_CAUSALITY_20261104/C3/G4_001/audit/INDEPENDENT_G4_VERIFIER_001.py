"""Independent G4 retained-result verifier. No production physics/adapter imports, RT, EKF or training."""
import argparse,csv,datetime,hashlib,importlib.metadata,json,os,pathlib,platform,subprocess,sys
EXPECTED_REVISION='1c1decaa8ae43dcd5119596943b499f9b495d338'
EXPECTED_RUN='8c1a6cc7-6349-46de-9bb8-f1e35164a99d'
EXPECTED_RESOURCE='90cf5373-c502-4027-b2c3-add2fcedba35'
def read(p):return json.loads(pathlib.Path(p).read_bytes())
def sha(p):
    with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,message):
    if not ok:raise AssertionError(message)
def scalar(actual,expected,name,tol=1e-12):
    require(np.isfinite(actual) and np.isfinite(expected) and abs(float(actual)-float(expected))<=tol,name)
def array(actual,expected,name):
    actual=np.asarray(actual);expected=np.asarray(expected)
    require(actual.shape==expected.shape and np.isfinite(actual).all() and np.isfinite(expected).all(),name+' shape/finite')
    error=actual-expected;den=float(np.linalg.norm(expected));peak=float(np.max(abs(expected)))
    erel=float(np.linalg.norm(error));emax=float(np.max(abs(error)))
    require(erel<=1e-28+1e-8*den and emax<=1e-28+1e-8*peak,name+' numerical')
    maximum_array_relative[0]=max(maximum_array_relative[0],erel/den if den else 0.)
def table(p):return list(csv.DictReader(pathlib.Path(p).open(newline='',encoding='utf8')))
def compare_row(actual,expected,label):
    require(set(actual)==set(expected),label+' columns')
    for k,v in expected.items():
        if isinstance(v,(int,np.integer)):require(int(actual[k])==int(v),label+' '+k)
        elif isinstance(v,(float,np.floating)):
            tol=1e-28+1e-8*abs(v) if any(t in k for t in ('power','allocated','cross','denominator')) else 1e-12
            scalar(float(actual[k]),v,label+' '+k,tol)
        else:require(actual[k]==v,label+' '+k)
def signed(v):
    power=abs(v)**2;den=float(power.sum());require(np.isfinite(power).all() and den>0,'undefined polarization')
    return float((power[0]-power[1])/den),den,power
def detector(c):
    mag=abs(c);rx=int(np.max(mag,axis=0).argmax());peak=float(mag[:,rx].max())
    require(np.isfinite(mag).all() and peak>0,'undefined detector')
    tap=int(np.flatnonzero(mag[:,rx]>=.3*peak)[0]);s,den,power=signed(c[tap])
    return dict(tap=tap,rx=rx,s=s,denominator=den,power=power.tolist(),range_m=tap*299792458./(1028*1950000.))
def branch(d,i):return dict(tap=int(d['tap'][i]),strong_port=int(d['strong_port'][i]),cells=d['cells'][i].tolist())
def cir(h):return fft.ifft(np.asarray(h,np.complex128)*np.hanning(257)[:,None],n=1028,axis=-2)*257
def validate_host(root):
    h=read(root/'logs/analysis_001.json');m=read(root/'logs/analysis_001_managed_finish.json')['processes']
    require(h['exit_code']==0 and h['managed_run']==EXPECTED_RUN and h['managed_resource']==EXPECTED_RESOURCE,'host identity/exit')
    rows=[v for v in m if v['id']==EXPECTED_RESOURCE];require(len(rows)==1,'managed resource')
    v=rows[0];require(v['creator']==EXPECTED_RUN and v['exit_code']==0 and v['termination']=='natural' and v['ref_count']==0,'natural completion')
    require(all(v[k]['state']=='absent' for k in ('actual_process','actual_supervisor','job')),'termination absence')
    require(any(x['run_id']==EXPECTED_RUN and x['ownership']=='released' for x in v['owners']),'released ownership')
    return h
def main(root,output):
    global np,fft,maximum_array_relative
    require(not output.exists(),'fresh verifier output required')
    plan=read(root/'PLAN.json');lock=read(root/'INPUT_LOCK.json');go=read(root/plan['go_file']);out=root/'RUN_001'
    m=read(out/'MANIFEST.json')
    require(m['status']=='G4_ANALYSIS_PASS_PENDING_INDEPENDENT_AUDIT','terminal complete before scientific audit')
    require(m['completed_conditions']==24 and m['completed_pairs']==36 and m['source_model_initializations']==1,'result counts')
    require(m['new_RT_calls']==m['new_training_runs']==m['new_EKF_runs']==0 and m['G3_original_clean_execution_acceptance'] is False,'scope')
    require(m['code_revision']==EXPECTED_REVISION,'immutable run code revision');host=validate_host(root)
    bindings={n:sha(root/n) for n in plan['bound_files']}
    require(go['schema']=='C3_G4_GO_V1' and go['decision']=='GO' and go['bindings_sha256']==bindings==m['bindings_sha256'],'GO code bindings')
    require((go['conditions'],go['pairs'],go['new_RT_calls'],go['output'])==(24,36,0,'RUN_001'),'GO scope')
    require(m['go_sha256']==sha(root/plan['go_file']),'manifest GO')
    for k in ('spec_audit','code_audit'):
        require(go[k+'_sha256']==sha(root/plan[k]),'gate receipt SHA')
    repo=root.parents[4]
    for n in [*plan['bound_files'],plan['go_file'],plan['spec_audit'],plan['code_audit']]:
        gitdata=subprocess.check_output(['git','-C',str(repo),'show',EXPECTED_REVISION+':'+(root/n).relative_to(repo).as_posix()])
        require(gitdata==(root/n).read_bytes(),'published code bytes '+n)
    checked=0
    def entry(v):
        nonlocal checked
        p=pathlib.Path(v['path']);require(p.stat().st_size==v['size'] and sha(p)==v['sha256'],'input '+str(p));checked+=1
    for k in ('contracts','source_model_dependencies','banks','governance'):
        for v in lock[k].values():entry(v)
    entry(lock['c1b_input_lock']);entry(lock['diagnostics'])
    for control in lock['actual_yaw_read_only'].values():
        for v in control.values():entry(v)
    expected=[('SM2_'+c['id']+'_Y'+str(i),c['id'],c['xyz'],y,i) for c in plan['coordinates'] for i,y in enumerate([0.,180.,35.7,-35.7])]
    require([tuple(r[k] for k in ('id','coordinate','xyz','yaw_deg','yaw_index')) for r in lock['conditions']]==expected,'exact24 order')
    for row in lock['conditions']:
        for v in row['files'].values():entry(v)
        raw=pathlib.Path(row['files']['RAW.npz']['path']);capture=raw.parent.parent
        ri=read(capture/'ARTIFACT_HASHES.json') if capture.name=='CANARY_002' else read(root.parent/'G3_001/audit/RECOVERED_ROOT_ARTIFACT_HASHES_001.json')
        ci=read(raw.parent/'ARTIFACT_HASHES.json')
        for n in ('RAW.npz','MANIFEST.json','QA.json'):
            require(ci[n]==row['files'][n]['sha256']==ri[(raw.parent/n).relative_to(capture).as_posix()],'accepted RAW index')
    require(read(root.parent/'G3_001/audit/C3_G3_RETAINED_DATA_RESULT_AUDIT_RESULT.json')['original_clean_execution_acceptance'] is False,'G3 forced preserved')
    index=read(out/'ARTIFACT_HASHES.json');actual_files={p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file() and p.name!='ARTIFACT_HASHES.json'}
    require(set(index)==actual_files and len(index)==103,'complete output inventory')
    for n,h in index.items():require(sha(out/n)==h,'output artifact '+n)
    require((out/'FAILURES.jsonl').stat().st_size==0,'no failed results')
    env=read(pathlib.Path(lock['source_model_cache'])/'provenance/ENV_LOCK.json')
    require(sys.version==env['python'] and platform.platform()==env['os'],'runtime Python/OS')
    require({n:importlib.metadata.version(n) for n in env['packages']}==env['packages'],'runtime packages')
    require(sha(sys.executable)==plan['python_executable_sha256'] and all(os.environ.get(n)=='1' for n in env['threads']),'runtime executable/threads')
    import numpy as _np
    from scipy import fft as _fft
    np=_np;fft=_fft;maximum_array_relative=[0.]
    from threadpoolctl import threadpool_info
    cache=pathlib.Path(lock['source_model_cache']);legacy=cache/'legacy'
    sys.path[:0]=[str(legacy/'research/FFD_P0P3_20261016'),str(legacy/'research/EKF4_RANGE_S_STAGED_20261014'),str(legacy/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
    from source_model import SourceFFD
    from qclean_uwb.drivesim.pattern_apply import Bank
    imported={}
    for name in ['source_model','p0_initial','p3_rf_adapter4','qclean_uwb','qclean_uwb.drivesim','qclean_uwb.scenarios','qclean_uwb.drivesim.pattern_apply','qclean_uwb.drivesim.observation','qclean_uwb.drivesim.hs_lut','qclean_uwb.scenarios.corridor']:
        p=pathlib.Path(sys.modules[name].__file__).resolve();n=p.relative_to(cache).as_posix()
        require(sha(p)==lock['source_model_dependencies'][n]['sha256'],'actual model import '+name)
        require(m['model_imports'][name]['sha256']==sha(p) and pathlib.Path(m['model_imports'][name]['path']).resolve()==p,'manifest import')
        imported[name]=dict(path=str(p),sha256=sha(p))
    banks=[]
    for n in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
        with np.load(lock['banks'][n]['path'],allow_pickle=False) as z:banks.append(Bank(dict(z)))
    model=SourceFFD(banks=banks)
    pools=threadpool_info();require(pools and all(v['num_threads']==1 for v in pools),'actual BLAS1')
    records=read(out/'CONDITIONS.json');summaries=table(out/'CONDITIONS.csv')
    require(len(records)==len(summaries)==24,'condition outputs')
    expected_summaries=[];group_total=surface_total=0;smooth=undefined=0;max_identity=0.;max_fd_error=0.
    for row,record,summary in zip(lock['conditions'],records,summaries):
        cid=row['id'];folder=out/cid;require(read(folder/'RESULT.json')==record and record['condition_id']==cid,'record identity')
        require(all(record[k]==row[k] for k in ('coordinate','xyz','yaw_deg','yaw_index')),'record condition')
        require(record['raw_sha256']==row['files']['RAW.npz']['sha256'],'record RAW provenance')
        with np.load(row['files']['RAW.npz']['path'],allow_pickle=False) as z:a=dict(z)
        labels=a['group_labels'].tolist();fields=np.zeros((len(labels),257,2),np.complex128);counts=np.zeros((len(labels),257),np.int32)
        require(a['original_field'].dtype==np.complex64 and a['legacy_group_fields'].dtype==np.complex128,'retained precision')
        require(np.array_equal(a['frequencies_hz'],6250400000.+1950000.*np.arange(257)),'frequency')
        for fi in range(257):
            for j in range(int(a['offsets'][fi]),int(a['offsets'][fi+1])):
                gi=int(a['source_group'][j]);fields[gi,fi]+=a['original_field'][j];counts[gi,fi]+=1
        require(np.array_equal(fields,a['legacy_group_fields']) and np.array_equal(fields.sum(0),a['legacy_native_full']),'exact raw legacy replay')
        require(np.array_equal(counts,a['group_count']) and np.array_equal(counts==0,a['group_missing']),'counts missing')
        direct=labels.index('DIRECT');require(direct==int(a['direct_group']),'DIRECT group')
        h=fields.sum(0);gc=cir(fields);c=cir(h);los=gc[direct];dc=detector(c);dl=detector(los)
        same=signed(c[dl['tap']])[0];fixed=same-dl['s'];selector=dc['s']-same;emp=dc['s']-dl['s']
        physical=record['physical'];det=physical['detector'];require(physical['groups']==len(labels) and len(physical['power_closure'])==2,'physical denominators')
        for name,expected_d in [('full',dc),('los',dl)]:
            for k in ('tap','rx'):require(det[name][k]==expected_d[k],'detector branch')
            for k in ('s','range_m'):scalar(det[name][k],expected_d[k],'detector '+k)
            array(det[name]['power'],expected_d['power'],'detector power');scalar(det[name]['denominator'],expected_d['denominator'],'detector denominator',1e-28+1e-8*expected_d['denominator'])
        for k,v in [('e_mp',emp),('same_los_tap',fixed),('detector_choice',selector),('delta_range_m',dc['range_m']-dl['range_m'])]:scalar(det[k],v,'decomposition '+k)
        identity=abs(emp-fixed-selector);require(identity<=1e-12 and det['identity_error']<=1e-12,'identity');max_identity=max(max_identity,identity)
        for v in physical['cir_closure'].values():require(0<=v['Erel']<=1e-8 and 0<=v['Emax']<=1e-8,'saved CIR closure')
        array(gc.sum(0),c,'independent scipy CIR closure')
        reflections=[i for i,n in enumerate(labels) if i!=direct and n!='INVALID'];surfaces={}
        for i in reflections:
            for surface in {x[0] for x in json.loads(labels[i])}:surfaces.setdefault(surface,set()).add(i)
        expected_groups=[];expected_surfaces=[];windows=[];powers=[];crosses=[]
        with np.load(folder/'FIELDS_AND_WINDOWS.npz',allow_pickle=False) as z:saved=dict(z)
        for k,v in [('full_spectrum',h),('direct_spectrum',fields[direct]),('reflected_spectrum',h-fields[direct]),('full_cir',c),('direct_cir',los),('reflected_cir',c-los),('full_power',abs(c)**2),('direct_power',abs(los)**2),('reflected_power',abs(c-los)**2)]:array(saved[k],v,k)
        require(saved['group_labels'].tolist()==labels,'group labels')
        for ti,(ref,tap) in enumerate([('fpFull',dc['tap']),('fpLoS',dl['tap'])]):
            ix=(tap+np.arange(-4,5))%1028;windows.append(ix);v=gc[:,tap];individual=abs(v)**2;cross=2*(v[:,None,:]*v[None,:,:].conj()).real
            for i in range(len(labels)):cross[i,i]=0
            powers.append(individual);crosses.append(cross)
            predicted=individual.sum(0)+np.array([np.triu(cross[:,:,r],1).sum() for r in range(2)])
            actual=abs(c[tap])**2;array(predicted,actual,'coherent power')
            baseline=signed(c[tap])[0];q=gc[reflections,tap].sum(0);allocation_total=np.zeros(2)
            for i in reflections:
                removed=c-gc[i];sv,den,power=signed(removed[tap]);rd=detector(removed)
                direct_cross=2*(los[tap].conj()*v[i]).real;allocated=direct_cross+(v[i].conj()*q).real;allocation_total+=allocated
                expected_groups.append(dict(group_id=i,group_label=labels[i],tap_ref=ref,tap=tap,group_plus_power=individual[i,0],group_minus_power=individual[i,1],direct_cross_plus=direct_cross[0],direct_cross_minus=direct_cross[1],allocated_plus=allocated[0],allocated_minus=allocated[1],removed_s_fixed=sv,delta_s_fixed=baseline-sv,removed_denominator=den,removed_plus_power=power[0],removed_minus_power=power[1],removed_detected_tap=rd['tap'],removed_s_redetected=rd['s'],delta_s_redetected=dc['s']-rd['s']))
            target=abs(c[tap])**2-abs(los[tap])**2
            require(np.all(abs(allocation_total-target)<=1e-28+1e-8*actual),'coherent allocation')
            pc=physical['power_closure'][ti];require(pc['tap_ref']==ref,'closure reference')
            array(pc['full_power'],actual,'closure saved power');array(pc['individual_plus_cross'],predicted,'closure saved prediction')
            require(np.all(abs(np.asarray(pc['residual']))<=1e-28+1e-8*actual) and np.all(abs(np.asarray(pc['allocation_residual']))<=1e-28+1e-8*actual),'saved closure residual bounds')
            for surface,indices in sorted(surfaces.items()):
                ii=sorted(indices);removed=c-gc[ii].sum(0);sv,den,power=signed(removed[tap]);rd=detector(removed)
                expected_surfaces.append(dict(surface=surface,removed_group_indices=json.dumps(ii),removed_group_count=len(ii),tap_ref=ref,tap=tap,removed_s_fixed=sv,delta_s_fixed=baseline-sv,removed_denominator=den,removed_plus_power=power[0],removed_minus_power=power[1],removed_detected_tap=rd['tap'],removed_s_redetected=rd['s'],delta_s_redetected=dc['s']-rd['s']))
        ix=np.stack(windows);require(np.array_equal(saved['window_indices'],ix),'window wrap indices')
        for k,v in [('group_windows',np.stack([gc[:,i] for i in ix])),('full_windows',c[ix]),('direct_windows',los[ix]),('reflected_windows',(c-los)[ix]),('individual_power_center',np.stack(powers)),('pair_cross_center',np.stack(crosses))]:array(saved[k],v,k)
        for filename,expected_rows in [('GROUP_REMOVAL.csv',expected_groups),('SURFACE_REMOVAL.csv',expected_surfaces)]:
            rows=table(folder/filename);require(len(rows)==len(expected_rows),'removal row count')
            for rr,ee in zip(rows,expected_rows):compare_row(rr,ee,filename)
        group_total+=len(expected_groups);surface_total+=len(expected_surfaces)
        state=np.array([row['xyz'][0],row['xyz'][1],np.deg2rad(row['yaw_deg']),0.]);case=dict(anchor=plan['anchor'],robot_z_m=.45,mount_deg=0.)
        hh,jj,dd=model.batch(state[None],case,gradient=True,return_diagnostics=True);model_record=record['model'];hp=float(jj[0,1,2]);base=branch(dd,0)
        require(model_record['state']==state.tolist() and model_record['base_branch']==base,'model input/branch')
        for k,v in [('h_s',hh[0,1]),('h_range',hh[0,0]),('Hpsi_s_per_rad',hp),('Hpsi_s_per_deg',hp*np.pi/180),('model_native_range',dd['native_range'][0]),('model_fp_margin',dd['fp_margin'][0])]:scalar(model_record[k],v,'model '+k)
        require(len(model_record['fd_checks'])==2,'both FD steps retained')
        flags=[]
        for eps,record_fd in zip([1e-5,5e-6],model_record['fd_checks']):
            xx=np.repeat(state[None],2,axis=0);xx[:,2]+=[-eps,eps]
            yy,_,dg=model.batch(xx,case,gradient=False,return_diagnostics=True);minus=branch(dg,0);plus=branch(dg,1);same_branch=minus==base==plus
            fd=float((yy[1,1]-yy[0,1])/(2*eps));error=abs(fd-hp);tol=1e-6+1e-4*abs(hp)
            require(record_fd['eps_rad']==eps and record_fd['minus_state']==xx[0].tolist() and record_fd['plus_state']==xx[1].tolist(),'FD state/step')
            require(record_fd['minus_branch']==minus and record_fd['plus_branch']==plus and record_fd['same_branch']==same_branch,'FD branches')
            for k,v in [('minus_h_s',yy[0,1]),('plus_h_s',yy[1,1]),('finite_difference_s_per_rad',fd),('absolute_error',error),('tolerance',tol)]:scalar(record_fd[k],v,'FD '+k)
            require(record_fd['status']==('VERIFIED_SMOOTH' if same_branch else 'UNDEFINED_BRANCH_CHANGE'),'FD status')
            if same_branch:require(error<=tol,'FD tolerance');max_fd_error=max(max_fd_error,error)
            flags.append(same_branch)
        status='VERIFIED_SMOOTH' if all(flags) else 'UNDEFINED_BRANCH_CHANGE';require(model_record['derivative_status']==status,'model derivative status')
        smooth+=int(all(flags));undefined+=int(not all(flags))
        expected_summary=dict(condition_id=cid,coordinate=row['coordinate'],yaw_deg=row['yaw_deg'],sFull=dc['s'],sLoS=dl['s'],eMP=emp,fixed=fixed,selector=selector,tapFull=dc['tap'],tapLoS=dl['tap'],rangeFull=dc['range_m'],rangeLoS=dl['range_m'],delta_range=dc['range_m']-dl['range_m'],Full_plus_power=dc['power'][0],Full_minus_power=dc['power'][1],LoS_plus_power=dl['power'][0],LoS_minus_power=dl['power'][1],h_s=float(hh[0,1]),Hpsi_s_per_rad=hp,Hpsi_s_per_deg=hp*np.pi/180,derivative_status=status,model_minus_LoS=float(hh[0,1])-dl['s'])
        compare_row(summary,expected_summary,'condition summary');expected_summaries.append(expected_summary)
        print('INDEPENDENT_G4_CONDITION',cid,status,flush=True)
    require((m['smooth_conditions'],m['undefined_branch_conditions'])==(smooth,undefined),'derivative denominators')
    numeric=['sFull','sLoS','eMP','fixed','selector','tapFull','tapLoS','rangeFull','rangeLoS','delta_range','Full_plus_power','Full_minus_power','LoS_plus_power','LoS_minus_power','h_s','Hpsi_s_per_rad','Hpsi_s_per_deg']
    pairs=read(out/'YAW_PAIRS.json');csv_pairs=table(out/'YAW_PAIRS.csv');require(len(pairs)==len(csv_pairs)==36,'pair count')
    pi=0
    for coordinate in plan['coordinates']:
        group=[r for r in expected_summaries if r['coordinate']==coordinate['id']];require(len(group)==4,'coordinate denominator')
        for i in range(4):
            for j in range(i+1,4):
                a,b=group[i],group[j];expected_pair=dict(coordinate=coordinate['id'],first_id=a['condition_id'],second_id=b['condition_id'],first_yaw_deg=a['yaw_deg'],second_yaw_deg=b['yaw_deg'],delta_convention='second-minus-first')
                expected_pair.update({'delta_'+k:b[k]-a[k] for k in numeric})
                residual=abs(expected_pair['delta_sFull']-expected_pair['delta_sLoS']-expected_pair['delta_fixed']-expected_pair['delta_selector']);require(residual<=1e-12,'pair identity')
                expected_pair['decomposition_residual']=residual
                compare_row(pairs[pi],expected_pair,'JSON pair');compare_row(csv_pairs[pi],expected_pair,'CSV pair');pi+=1
    controls=read(out/'READ_ONLY_CONTROLS.json');require(controls['controls']==lock['actual_yaw_read_only'],'controls excluded provenance')
    result=dict(schema='C3_G4_INDEPENDENT_VERIFIER_V1',decision='ACCEPT',scope='C3_G4_SELECTED_24_STORED_CHANNELS_AND_36_WITHIN_COORDINATE_CONTRASTS',published_code_revision=EXPECTED_REVISION,bindings_sha256=bindings,go_sha256=sha(root/plan['go_file']),source_sha256=sha(__file__),input_lock_sha256=sha(root/'INPUT_LOCK.json'),artifact_hashes_sha256=sha(out/'ARTIFACT_HASHES.json'),manifest_sha256=sha(out/'MANIFEST.json'),host_receipt_sha256=sha(root/'logs/analysis_001.json'),managed_receipt_sha256=sha(root/'logs/analysis_001_managed_finish.json'),counts=dict(conditions=24,coordinate_blocks=6,yaw_pairs=36,raw_frequency_bins=6168,group_removal_rows=group_total,surface_removal_rows=surface_total,source_model_center_states=24,source_model_endpoint_states=96,smooth_conditions=smooth,undefined_branch_conditions=undefined,hashed_input_entries=checked,indexed_output_artifacts=len(index)),maximum_errors=dict(array_relative=maximum_array_relative[0],decomposition_abs=max_identity,smooth_FD_absolute=max_fd_error),independent_observer='SciPy FFT and independent scalar matrix/selector/replay; original source API directly, no production physics/adapter import',actual_imports=imported,runtime=dict(python=sys.version,packages={n:importlib.metadata.version(n) for n in env['packages']},threadpools=pools),prior_G3_original_execution_status='FORCED_AFTER20',prior_G3_original_clean_execution_acceptance=False,activities=dict(new_RT_calls=0,new_training_runs=0,new_EKF_runs=0,independent_source_model_initializations=1,production_code_calls=0),claim_boundary='Selected six fixed coordinates/four yaws; stored-path removals are offline interventions; source Hpsi is not a physical RT yaw derivative or Fisher information; no EKF/adoption/latency conclusion',adoption='NO_GO',realtime='HOLD',required_correction=[],timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes((json.dumps(result,indent=2,allow_nan=False)+'\n').encode())
    print('C3_G4_INDEPENDENT_RESULT',json.dumps(result,allow_nan=False),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=pathlib.Path);parser.add_argument('output',type=pathlib.Path);args=parser.parse_args()
    main(args.root.resolve(),args.output.resolve())
