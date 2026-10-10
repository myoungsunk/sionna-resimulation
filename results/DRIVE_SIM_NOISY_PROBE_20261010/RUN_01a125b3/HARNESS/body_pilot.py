import body_controls as C
import json,time
C.OUT=C.J/'BODY_PILOT';C.OUT.mkdir(exist_ok=False);start=time.time();case='R2_aA_m0';groups=C.casepack(case)[3]
for gi in range(len(groups)):
 rows=C.one((case,gi,0,0,30))
 if rows[0]['status']=='NO_EVALUATION_PRIOR':continue
 assert len(rows)==6 and all(r['status']=='COMPLETED' for r in rows),rows
 C.J.joinpath('BODY_PILOT_STATUS.json').write_text(json.dumps({'state':'COMPLETED','station':gi,'rows':rows,'seconds':time.time()-start,'purpose':'logging/finite/guard pilot only; not statistical evidence'},indent=2));print(json.dumps(rows),flush=True);break
else:raise ValueError('no original evaluation prior available')
