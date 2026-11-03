"""A010 R5 prefreeze implementation: fail-closed terminal precision and
field-block *registered* H/CAL alternative-conclusion sensitivity.

No solver modifications, no truth-start in operational mode choice. This
technical module does not authorize scientific freeze, DEV3, HOLDOUT2, or RT.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent.parent
SPEC_FILE=ROOT/"contracts/AMENDMENT-010-R5-PROPOSER-SPEC-V1.json"
STARTS=("psi-3","psi-2","psi-1","psi+0","psi+1","psi+2","psi+3","x+1","y+1")
SOLS=("E",)+STARTS
STATES=("rad","tan","psi","bg")
ROWKEY=("field","role","cell","sensor_seed","arm")
# Frozen SCIENCE_SPEC/A003 and A010 v2 role/cell/arm universe.
# These are NOT inferred from observed rows, or an entire missing H4 arm would
# silently suppress registered hypotheses instead of failing closed.
LH_PRIMARY=("LOWCORR","POSE_HIGH")
LH_CELLS=("LOWCORR","POSE_HIGH","TIME_1","TIME_5","POSE_HIGH_C03")
RV_CELLS=("LOWCORR","POSE_HIGH","TIME_HIGH_5")
XMODEL_CELLS=("POSE_HIGH","TIME_HIGH_5")
REGISTERED_HYPOTHESIS_COUNTS={"H1":8,"H2":2,"H3":4,"CAL":8,"H4":8,"H4_REPRO":32}
REGISTERED_HYPOTHESIS_COUNT=62



def spec_with_sha(path=SPEC_FILE):
    path=Path(path)
    data=path.read_bytes()
    cfg=json.loads(data)
    if (cfg.get("schema")!="MBVAR_A010_R5_PROPOSER_POLICY_FINAL_V1" or
        cfg.get("decision")!="FINAL_PRE_FREEZE" or
        cfg.get("scientific_execution_authorized") is not False or
        cfg.get("diagnostic_starts")!=list(STARTS) or
        cfg.get("polish",{}).get("cost_descent_tol_chi2")!=.001 or
        cfg["polish"].get("max_steps")!=30 or
        cfg["field_sensitivity"].get("field_bootstrap_B")!=4000 or
        cfg["field_sensitivity"].get("field_bootstrap_seed")!=20261029 or
        cfg["ambiguous"]["absolute_cost_gap_chi2_lte"]!=1 or
        cfg["ambiguous"]["end_state_dref_gt"]!=2 or
        cfg.get("a010_science_frozen") is not False):
        raise ValueError("ERR_R5_PROPOSER_SPEC_MISMATCH")
    return cfg,hashlib.sha256(data).hexdigest()


def finite(*args):
    try:
        return bool(args and all(np.isfinite(np.asarray(x,dtype=float)).all()
                                 for x in args))
    except (ValueError,TypeError,OverflowError):
        return False


def _terminal_bool(value):
    """Deserialize CSV round-trip bool without Python's bool("False") trap.

    Unknown/missing encodings never default to a successful certificate.
    """
    if isinstance(value,(bool,np.bool_)):
        return bool(value)
    if isinstance(value,str) and value in ("True","False"):
        return value=="True"
    return None


def _terminal_end_state(value):
    """Require exactly four finite state scalars from live arrays or CSV JSON."""
    if isinstance(value,str):
        try:
            value=json.loads(value)
        except (ValueError,TypeError):
            return None
    try:
        a=np.asarray(value,dtype=np.float64)
    except (ValueError,TypeError,OverflowError):
        return None
    return a if a.shape==(4,) and np.isfinite(a).all() else None


def _terminal_steps(value,max_steps):
    try:
        n=float(value)
    except (TypeError,ValueError,OverflowError):
        return None
    if not math.isfinite(n) or n!=int(n) or not (0<=n<=max_steps):
        return None
    return int(n)


def validate_terminals(records,cfg,required=SOLS):
    """Exact E'+9 nonoracle terminal certificate, both live and CSV replay.

    A failed CSV schema/cap/descent check yields UNRESOLVED_PRECISION.
    Neither textual "False" nor stringified 4D state is implicitly coerced
    to a misleading truth value. This is stricter than the original schema.
    """
    records=list(records); names=[r.get("start") for r in records]
    reasons=[]
    if len(records)!=len(required) or set(names)!=set(required) or len(set(names))!=len(names):
        reasons.append("ERR_R5_TERMINAL_SET")
    tol=float(cfg["polish"]["cost_descent_tol_chi2"])
    max_steps=int(cfg["polish"]["max_steps"])
    for r in records:
        name=str(r.get("start"))
        cap=_terminal_bool(r.get("polish_hit_cap"))
        state=_terminal_end_state(r.get("end_state"))
        steps=_terminal_steps(r.get("polish_steps"),max_steps)
        if state is None or not finite(r.get("cost"),r.get("dmin")):
            reasons.append("ERR_R5_NONFINITE_OR_INVALID_STATE_"+name)
        if cap is None:
            reasons.append("ERR_R5_POLISH_CAP_SCHEMA_"+name)
        elif cap:
            reasons.append("ERR_R5_POLISH_CAP_"+name)
        if steps is None:
            reasons.append("ERR_R5_POLISH_STEPS_"+name)
        if finite(r.get("dmin")) and float(r["dmin"]) < -tol:
            reasons.append("ERR_R5_COMMON_PROBE_DESCENT_"+name)
        if name=="truth":
            reasons.append("ERR_R5_ORACLE_IN_CERTIFICATE")
    return dict(status="PASS" if not reasons else "UNRESOLVED_PRECISION",
                pass_=not reasons,n_solutions=len(records),
                n_expected=len(required), n_failures=len(reasons),
                failure_reasons=sorted(set(reasons)),
                criterion=f"cost finite, cap=false, common 8-pair probe dmin >= -{tol:g}",
                science_release_allowed=False)


def certify_at_terminal(T,hb,z,Sm,ds_m,gy_m,dts,x0,theta,seed,step_count,hit_cap,start):
    """One common deterministic A8 probe seed for all starts in a row.
    GN directions are recomputed at each terminal state; random dirs use
    the same RNG stream and prior/Q scales. No truth enters the certificate.
    """
    if (not finite(theta[0],theta[1],z,Sm,ds_m,gy_m,dts,x0) or
        int(step_count)<0 or int(step_count)>30):
        return dict(start=start,cost=float("nan"),dmin=float("nan"),
                    end_state=np.full(4,np.nan).tolist(),
                    polish_steps=int(step_count),polish_hit_cap=True,
                    probe_argmin="INVALID_INPUT")
    import filters as FL
    Lm,L0,qv=T.B3._mats(Sm,ds_m,dts)
    mu=np.zeros_like(z)
    cost,X=FL._v2_parts(hb,z,mu,Lm,L0,x0,qv,ds_m,gy_m,dts,
                         theta[0],theta[1],jac=False)
    pf=T.B3.post_fit_P(hb,z,Sm,ds_m,gy_m,dts,x0,theta,np.eye(4))
    # The original A8 fixed GN_ALPHAS and N_DIR=8 are required by R5 spec.
    if (T.B3.GN_ALPHAS!=(1.,.5,.1,.01) or T.B3.N_DIR!=8 or
        T.B3.RHO!=.01):
        raise ValueError("ERR_R5_PROBE_CONFIGURATION")
    dmin,argmin,_=T.B3.probe_min_dcost(
        hb,z,Sm,ds_m,gy_m,dts,x0,theta,seed,pf["_gn_steps"])
    return dict(start=start,cost=float(cost),dmin=float(dmin),
                end_state=X[-1].astype(float).tolist(),
                polish_steps=int(step_count),polish_hit_cap=bool(hit_cap),
                probe_argmin=str(argmin))


def checked_alternative(row,cert,config):
    """Only original near-cost candidate starts are admissible for science
    witness scenarios. Do not mistake multiplicity of starts for minima.
    """
    if cert["status"]!="PASS":
        return dict(status="UNRESOLVED_PRECISION",eligible=False)
    if (not finite(row.get("delta_chi2"),row.get("end_dref"),
                   row.get("nees4_alt"),row.get("delta_nees4"),
                   row.get("delta_logdet_P")) or
        row.get("covariance_alt_spd") not in (True,"True","true",1,1.0)):
        return dict(status="UNCERTIFIED_COVARIANCE",eligible=False)
    eligible=abs(float(row["delta_chi2"]))<=config["ambiguous"]["absolute_cost_gap_chi2_lte"] and float(row["end_dref"])>config["ambiguous"]["end_state_dref_gt"]
    return dict(status="ADMISSIBLE_NEAR_START" if eligible else "NOT_NEAR_START",
                eligible=bool(eligible))


def numeric_flags(alt,config):
    t=config["field_sensitivity"]["numeric_flags"]
    ds=np.asarray(config["ambiguous"]["dref"],float)
    normalized=[abs(float(alt[f"delta_sq_err_{k}"]))/ds[i]**2 for i,k in enumerate(STATES)]
    positive=finite(*normalized,alt["delta_nees4"],alt["delta_logdet_P"])
    return dict(numeric_finite=positive,
                max_scaled_squared_error_delta=max(normalized) if positive else None,
                material_numeric_sensitivity=bool(positive and (
                    max(normalized)>=t["normalized_squared_error_delta_abs_gte"] or
                    abs(float(alt["delta_nees4"]))>=t["nees4_delta_abs_gte"] or
                    abs(float(alt["delta_logdet_P"]))>=t["logdet_cov_delta_abs_gte"])))


def _close(a,b,rtol=1e-7,atol=1e-10):
    return bool(finite(a,b) and
                abs(float(a)-float(b))<=atol+rtol*max(abs(float(a)),abs(float(b))))


def _stored_full_c10(row,prefix):
    """Reconstruct complete 4x4 rotated covariance from 10 saved values."""
    P=np.empty((4,4),float)
    for i in range(4):
        for j in range(i,4):
            value=float(row[f"{prefix}_{i}{j}"])
            P[i,j]=P[j,i]=value
    if not np.isfinite(P).all() or not np.all(np.diag(P)>0):
        raise ValueError("ERR_R5_STORED_C10_NONFINITE_OR_NONPOSITIVE")
    try:
        L=np.linalg.cholesky(P)
    except np.linalg.LinAlgError as exc:
        raise ValueError("ERR_R5_STORED_C10_NONSPD") from exc
    eig=float(np.linalg.eigvalsh(P)[0])
    d=np.sqrt(np.diag(P))
    condition=float(np.linalg.cond(P/d[:,None]/d[None,:]))
    logdet=float(2*np.log(np.diag(L)).sum())
    if not finite(eig,condition,logdet) or eig<=0:
        raise ValueError("ERR_R5_STORED_C10_BAD_DIAGNOSTICS")
    return P,L,eig,float(np.log10(condition)),logdet


def verify_stored_alternative_full_c10(alt,source):
    """A18-03: independent aggregator rechecks stored full C10 and all scores.

    The source is the C3 result with the SAME registered 5-tuple; the
    alternative receipt includes original and alternative radial-tangential
    4x4 matrices and signed 4D errors. The original error is recorded
    explicitly; squared differences cannot recover missing error signs.
    """
    P0,L0,eg0,cond0,ld0=_stored_full_c10(alt,"R5_C10E")
    P1,L1,eg1,cond1,ld1=_stored_full_c10(alt,"R5_C10ALT")
    er0=np.array([alt[f"R5_E_END_ERROR_{k}"] for k in STATES],float)
    er1=np.array([alt[f"alt_end_error_{k}"] for k in STATES],float)
    if not finite(er0,er1):
        raise ValueError("ERR_R5_STORED_C10_BAD_STATE_ERRORS")
    ne0=float(np.linalg.norm(np.linalg.solve(L0,er0))**2)
    ne1=float(np.linalg.norm(np.linalg.solve(L1,er1))**2)
    if not finite(ne0,ne1):
        raise ValueError("ERR_R5_STORED_C10_BAD_NEES")
    for i in range(4):
        for j in range(i,4):
            if not _close(P0[i,j],source[f"C10rot_{i}{j}"],rtol=1e-9,atol=1e-12):
                raise ValueError("ERR_R5_BASE_C10_SOURCE_MISMATCH")
    if (not _close(ne0,source["nees4_C10"]) or
        not _close(ne0,alt["nees4_E"]) or
        not _close(ne1,alt["nees4_alt"]) or
        not _close(ne1-ne0,alt["delta_nees4"])):
        raise ValueError("ERR_R5_STORED_C10_NEES_MISMATCH")
    if (not _close(ld1-ld0,alt["delta_logdet_P"]) or
        not _close(eg1,alt["R5_C10ALT_MIN_EIG"]) or
        not _close(cond1,alt["R5_C10ALT_LOG10_COND"])):
        raise ValueError("ERR_R5_STORED_C10_CONDITION_OR_LOGDET_MISMATCH")
    for i,label in enumerate(STATES):
        if (not _close(P1[i,i]-P0[i,i],alt[f"delta_P_{label}"]) or
            not _close(er1[i]**2-er0[i]**2,alt[f"delta_sq_err_{label}"])):
            raise ValueError("ERR_R5_STORED_C10_DELTA_MISMATCH")
    flag=alt["covariance_alt_spd"]
    if not ((isinstance(flag,(bool,np.bool_)) and bool(flag)) or flag in ("True","true",1)):
        raise ValueError("ERR_R5_STORED_C10_SPD_FLAG_MISMATCH")
    if not _close(ne0,source["nees4_C10"]):
        raise ValueError("ERR_R5_STORED_C10_SOURCE_NEES")
    return dict(full_c10_spd_verified=True,
                full_c10_alt_min_eigenvalue=eg1,
                full_c10_alt_log10_condition=cond1,
                nees4_E_independent=ne0,nees4_alt_independent=ne1,
                delta_nees4_independent=ne1-ne0,
                delta_logdet_P_independent=ld1-ld0,
                upper_triangle_entries_checked=20,
                no_global_map_claim=True)


def _key(row):
    return tuple(str(int(row[k])) if k in ("field","sensor_seed") else str(row[k])
                 for k in ROWKEY)


def registered_batch_row_keys(fields, sensor_seeds):
    """Immutable expected 5-key universe; source rows never determine scope."""
    if fields is None or sensor_seeds is None:
        raise ValueError("ERR_R5_REGISTERED_SCOPE_REQUIRED")
    fs=list(fields); ss=list(sensor_seeds)
    if (not fs or not ss or len(set(fs))!=len(fs) or len(set(ss))!=len(ss)
        or any(type(x) not in (int,np.int64,np.int32) for x in fs+ss)):
        raise ValueError("ERR_R5_REGISTERED_FIELD_OR_SEED_SCHEMA")
    expected=set()
    for f in fs:
        for sn in ss:
            for role in ("LOW","HIGH"):
                for cell in LH_CELLS:
                    for arm in ("IID_BATCH","ORACLE_CORR_BATCH"):
                        expected.add((str(f),role,cell,str(sn),arm))
            for role in ("REV60","FWD60"):
                for cell in RV_CELLS:
                    for arm in ("IID_BATCH","ORACLE_CORR_BATCH"):
                        expected.add((str(f),role,cell,str(sn),arm))
                    if cell in XMODEL_CELLS:
                        expected.add((str(f),role,cell,str(sn),"XMODEL_BATCH"))
    if len(expected)!=len(fs)*len(ss)*36:
        raise ValueError("ERR_R5_REGISTERED_ROW_COUNT")
    return expected


def _incomplete(reason, **detail):
    return dict(status="NOT_EVALUATED_INCOMPLETE",reason=reason,
                science_release_allowed=False,**detail)


def _hypotheses(pred,did_pred,rvpred,sep_pred,eff,lh_primary,rv_cells,xmodel_cells):
    """All original V.decide_v2 registered primary H1/H2/H3/CAL/H4/H4_REPRO
    contrasts. A term is (weight, role, cell, arm, state, 'infl'|'mse').
    """
    tests=[]
    LF=math.log(float(eff["equivalence_factor"]))
    def term(w,r,c,arm,state,kind):
        return (w,(r,c,arm,state),kind)
    def push(typ,id_,tt,offset=0., rule="equiv", predval=0.,applicable=True):
        tests.append(dict(family=typ,id=f"{typ}|{id_}",terms=tt,offset=float(offset),
                          rule=rule,predval=float(predval),applicable=bool(applicable)))
    for r in ("LOW","HIGH"):
        for c in lh_primary:
            for st in ("tan","psi"):
                p=float(pred.loc[(r,c),f"infl_iid_{st}"])
                push("H1",f"{r}|{c}|{st}",[term(1,r,c,"IID_BATCH",st,"infl")],
                     -math.log(p))
    for st in ("psi","tan"):
        kk=[("LOW","POSE_HIGH",1),("LOW","LOWCORR",-1),
            ("HIGH","POSE_HIGH",-1),("HIGH","LOWCORR",1)]
        terms=[term(s,r,c,"IID_BATCH",st,"infl") for r,c,s in kk]
        predv=float(did_pred[(did_pred.state==st)&
                             (did_pred.quantity=="infl_iid")].DID_log.iloc[0])
        push("H2",st,terms,rule="sided",predval=predv,
             applicable=abs(predv)>=math.log(eff["did_min_predicted_factor"]))
    for r in ("LOW","HIGH"):
        for st in ("tan","psi"):
            predv=float(pred.loc[(r,"POSE_HIGH"),f"mse_ratio_oracle_iid_{st}"])
            push("H3",f"{r}|{st}",[
                term(1,r,"POSE_HIGH","ORACLE_CORR_BATCH",st,"mse"),
                term(-1,r,"POSE_HIGH","IID_BATCH",st,"mse")],
                rule="ratio",predval=predv,
                applicable=predv<=eff["oracle_gain_ratio_max"])
    for r in ("LOW","HIGH"):
        for c in lh_primary:
            for st in ("tan","psi"):
                push("CAL",f"{r}|{c}|{st}",[
                    term(1,r,c,"ORACLE_CORR_BATCH",st,"infl")])
    for c in xmodel_cells:
        for arm in ("XMODEL_BATCH","IID_BATCH"):
            for st in ("psi","tan"):
                sp=sep_pred[(sep_pred.cell==c)&(sep_pred.arm==arm)&
                            (sep_pred.state==st)].iloc[0]
                push("H4",f"{c}|{arm}|{st}",[
                    term(1,"REV60",c,arm,st,"infl"),
                    term(-1,"FWD60",c,arm,st,"infl")],
                    rule="sided",predval=float(sp.SEP_log),
                    applicable=bool(sp.testable))
    for r in ("REV60","FWD60"):
        for c in rv_cells:
            for arm in ("IID_BATCH","ORACLE_CORR_BATCH","XMODEL_BATCH"):
                if arm=="XMODEL_BATCH" and c not in xmodel_cells:
                    continue
                for st in ("psi","tan"):
                    predv=float(rvpred.loc[(r,c,arm),f"infl_{st}"])
                    push("H4_REPRO",f"{r}|{c}|{arm}|{st}",[
                        term(1,r,c,arm,st,"infl")],-math.log(predv))
    counts={family:sum(t["family"]==family for t in tests)
            for family in REGISTERED_HYPOTHESIS_COUNTS}
    if counts!=REGISTERED_HYPOTHESIS_COUNTS or len(tests)!=REGISTERED_HYPOTHESIS_COUNT:
        raise ValueError("ERR_R5_REGISTERED_HYPOTHESIS_UNIVERSE")
    if len({t["id"] for t in tests})!=len(tests):
        raise ValueError("ERR_R5_HYPOTHESIS_DUPLICATE")
    return tests


def _verdict(test,lo,hi,eff):
    if not test["applicable"]:
        return "NOT_APPLICABLE" if test["family"]=="H3" else "NOT_TESTABLE"
    if test["rule"]=="ratio":
        return "PASS" if hi<0 else ("FAIL" if lo>0 else "UNDETERMINED")
    if test["rule"]=="sided":
        p=test["predval"]
        if abs(p)<math.log(eff["did_min_predicted_factor"]):
            return "NOT_TESTABLE"
        sg=math.copysign(1,p); a,b=sorted((sg*lo,sg*hi))
        return "PASS" if a>0 else ("FAIL" if b<abs(p)*eff["did_min_fraction_of_prediction"]
                                    else "UNDETERMINED")
    half=math.log(eff["equivalence_factor"])
    return "PASS" if lo>=-half and hi<=half else (
        "FAIL" if lo>half or hi < -half else "UNDETERMINED")


def _summary_verdict(records):
    h1=[x["verdict"] for x in records if x["family"]=="H1"]
    primary=next((x for x in records if x["id"]=="H2|psi"),None)
    if not h1 or primary is None:
        return "NOT_EVALUATED"
    cons=[primary["verdict"]]+[x["verdict"] for x in records
          if x["family"] in ("H3","CAL") and x["applicable"]]
    if "FAIL" in h1: return "NOT_SUPPORTED"
    if "UNDETERMINED" in h1 or not primary["applicable"]: return "INCONCLUSIVE"
    if all(x=="PASS" for x in cons): return "SUPPORTED"
    if "PASS" in cons or "FAIL" in cons: return "MIXED"
    return "INCONCLUSIVE"


def field_paired_conclusion_gate(science_rows,alternatives,reference,config,
                                 require_full_keys=True,registered_fields=None,
                                 registered_sensor_seeds=None):
    """Vectorised paired field bootstrap B=4000, fixed seed and same sample
    indices for E and every admissible-start witness.

    ENVELOPE gives conservative bounds over all per-row alternative assignments,
    whereas global-start witnesses are attainable, not assumed exhaustive.
    CI/sign/verdict sensitivity cannot be treated as science release by itself.
    """
    import pandas as pd
    S=science_rows.copy()
    A=alternatives.copy()
    if require_full_keys is not True:
        raise ValueError("ERR_R5_REGISTERED_SCOPE_BYPASS_FORBIDDEN")
    if registered_fields is None or registered_sensor_seeds is None:
        return _incomplete("MISSING_REGISTERED_CONTRACT_SCOPE")
    expected=registered_batch_row_keys(registered_fields,registered_sensor_seeds)
    if not len(S) or not set(ROWKEY).issubset(S.columns) or "status" not in S:
        return _incomplete("EMPTY_OR_SCHEMA_MISSING_SCIENCE_ROWS",
                           n_expected_keys=len(expected))
    # Run contract coverage on *every batch result*, including FAILED,
    # BEFORE filtering any status. Failed observations are not excluded.
    batch=S[S.arm.astype(str).str.endswith("_BATCH")].copy()
    raw_keys=[_key(x) for x in batch.to_dict("records")]
    keys=set(raw_keys)
    missing=sorted(expected-keys); extra=sorted(keys-expected)
    if len(raw_keys)!=len(set(raw_keys)):
        raise ValueError("ERR_R5_MAIN_DUPLICATE_REGISTERED_KEY")
    if missing or extra or len(raw_keys)!=len(expected):
        return _incomplete("MISSING_OR_EXTRA_REGISTERED_KEYS",
                           n_actual_keys=len(raw_keys),n_expected_keys=len(expected),
                           n_missing=len(missing),n_extra=len(extra),
                           missing_keys=[list(k) for k in missing[:12]],
                           extra_keys=[list(k) for k in extra[:12]])
    invalid=batch[batch.status!="OK"]
    if len(invalid):
        return _incomplete("REGISTERED_ROW_NON_OK",
                           n_failed_rows=len(invalid),n_expected_keys=len(expected),
                           failed_keys=[list(_key(r)) for r in invalid.to_dict("records")[:12]])
    S=batch  # All registered batch rows present and OK; nothing excluded.
    if len(A) and A.duplicated(list(ROWKEY)+["alt_start"]).any():
        raise ValueError("ERR_R5_ALT_DUPLICATE")
    if len(A) and not {_key(x) for x in A.to_dict("records")}.issubset(keys):
        raise ValueError("ERR_R5_ALT_EXTRA_KEY")
    for st in STATES:
        if any(x not in S.columns for x in (f"e_{st}",f"P_{st}")):
            return dict(status="NOT_EVALUATED_INCOMPLETE",
                        reason="MISSING_MAIN_STATE_COLUMNS",
                        science_release_allowed=False)
    S["_r5_key"]=[_key(r) for r in S.to_dict("records")]
    base={r["_r5_key"]:r for r in S.to_dict("records")}
    candidates=defaultdict(dict)
    for r in A.to_dict("records"):
        k=_key(r); name=str(r["alt_start"])
        if name not in STARTS:
            raise ValueError("ERR_R5_ALT_UNREGISTERED_START")
        if not bool(r.get("R5_ALTERNATIVE_ADMISSIBLE",False)):
            raise ValueError("ERR_R5_ALT_NOT_CERTIFIED")
        candidates[k][name]=r
    all_fields=sorted(set(int(f) for f in S.field))
    if len(all_fields)<2:
        return dict(status="NOT_EVALUATED_INCOMPLETE",reason="TOO_FEW_FIELDS",
                    n_fields=len(all_fields),science_release_allowed=False)
    n=len(all_fields);F={f:i for i,f in enumerate(all_fields)}
    arms=defaultdict(list)
    for k,r in base.items():
        arms[(str(r["role"]),str(r["cell"]),str(r["arm"]))].append(k)
    # Each field is a block, never treat starts/sensor repeats as i.i.d.
    groups={}
    for g,kks in arms.items():
        byf=defaultdict(list)
        for k in kks:byf[int(k[0])].append(k)
        if sorted(byf)!=all_fields or len({len(v) for v in byf.values()})!=1:
            return dict(status="NOT_EVALUATED_INCOMPLETE",
                        reason="UNBALANCED_FIELD_GROUP",group=g,
                        science_release_allowed=False)
        for st in STATES:
            group=(g[0],g[1],g[2],st)
            stats={}
            for label in ("E",)+STARTS+("LOW","HIGH"):
                stats[label]=np.zeros((n,2),float)
            for f in all_fields:
                for k in byf[f]:
                    r=base[k];e=float(r[f"e_{st}"]);p=float(r[f"P_{st}"])
                    if not finite(e,p) or p<=0:raise ValueError("ERR_R5_BASE_NONSPD_OR_NONFINITE")
                    values=[(e*e,p,"E")]
                    for name,alt in candidates.get(k,{}).items():
                        er=float(alt[f"alt_end_error_{st}"])
                        pr=p+float(alt[f"delta_P_{st}"])
                        if not finite(er,pr) or pr<=0:
                            raise ValueError("ERR_R5_ALT_NONSPD_OR_NONFINITE")
                        values.append((er*er,pr,name))
                    for label in ("E",)+STARTS:
                        v=next(((err,pc) for err,pc,nn in values if nn==label),(e*e,p))
                        stats[label][F[f],:]+=v
                    errs=np.array([u[0] for u in values]);ps=np.array([u[1] for u in values])
                    stats["LOW"][F[f],:]+=[errs.min(),ps.min()]
                    stats["HIGH"][F[f],:]+=[errs.max(),ps.max()]
            for label in stats:
                stats[label]/=len(byf[all_fields[0]])
            groups[group]=stats
    pred,did_pred,rvpred,sep_pred,eff=reference
    hypothesis=_hypotheses(pred,did_pred,rvpred,sep_pred,eff,
                           LH_PRIMARY,RV_CELLS,XMODEL_CELLS)
    # Fully registered test is meaningful only if every required group exists.
    missing=sorted({term[1] for h in hypothesis for term in h["terms"]}-set(groups))
    if missing:
        return dict(status="NOT_EVALUATED_INCOMPLETE",reason="MISSING_HYPOTHESIS_STRATA",
                    missing_strata=[list(k) for k in missing],
                    n_fields=n,science_release_allowed=False)
    B=int(config["field_sensitivity"]["field_bootstrap_B"])
    seed=int(config["field_sensitivity"]["field_bootstrap_seed"])
    rng=np.random.default_rng(seed)
    draw=rng.integers(0,n,(B,n))
    # Cache all scalar group terms per scenario, identical bootstrap draws.
    cache={}
    for group,dataset in groups.items():
        cache[group]={}
        for label,a in dataset.items():
            means=a[draw].mean(axis=1)
            mm=a.mean(axis=0)
            if not np.isfinite(means).all() or np.any(means<=0):
                raise ValueError("ERR_R5_SCIENCE_NONPOSITIVE_MEANS")
            if label in ("LOW","HIGH"):
                # Bounds applied separately by numerator and denominator.
                pass
            cache[group][label]=(mm,means)
    def observed(t,label,mode):
        w,group,kind=t
        if mode=="BOUND_MIN":
            l="LOW" if w>0 else "HIGH"
            other="HIGH" if w>0 else "LOW"
            m1,b1=cache[group][l];m2,b2=cache[group][other]
            v=(math.log(m1[0])-math.log(m2[1]) if kind=="infl" else math.log(m1[0]))
            x=np.log(b1[:,0])-np.log(b2[:,1]) if kind=="infl" else np.log(b1[:,0])
        elif mode=="BOUND_MAX":
            l="HIGH" if w>0 else "LOW"
            other="LOW" if w>0 else "HIGH"
            m1,b1=cache[group][l];m2,b2=cache[group][other]
            v=(math.log(m1[0])-math.log(m2[1]) if kind=="infl" else math.log(m1[0]))
            x=np.log(b1[:,0])-np.log(b2[:,1]) if kind=="infl" else np.log(b1[:,0])
        else:
            m,b=cache[group][label]
            v=math.log(m[0])-math.log(m[1]) if kind=="infl" else math.log(m[0])
            x=np.log(b[:,0])-np.log(b[:,1]) if kind=="infl" else np.log(b[:,0])
        return w*v,w*x
    all_records=defaultdict(list)
    changed=[];potential=[];numeric_material=False
    for h in hypothesis:
        variants={}
        for label in ("E",)+STARTS:
            point=h["offset"];boot=np.full(B,h["offset"],float)
            for t in h["terms"]:
                p,b=observed(t,label,None);point+=p;boot+=b
            lo,hi=np.quantile(boot,[.025,.975])
            variants[label]=dict(est=float(point),lo=float(lo),hi=float(hi),
                                 se=float(boot.std(ddof=1)),
                                 verdict=_verdict(h,float(lo),float(hi),eff),
                                 ci_includes_zero=bool(lo<=0<=hi),
                                 sign=int(np.sign(point)))
        bound={}
        for mode in ("BOUND_MIN","BOUND_MAX"):
            point=h["offset"];boot=np.full(B,h["offset"],float)
            for t in h["terms"]:
                p,b=observed(t,mode,mode);point+=p;boot+=b
            bound[mode]=dict(est=float(point),
                        lo=float(np.quantile(boot,.025)),
                        hi=float(np.quantile(boot,.975)))
        original=variants["E"]
        differing=[name for name in STARTS
            if (variants[name]["sign"]!=original["sign"] or
                variants[name]["ci_includes_zero"]!=original["ci_includes_zero"] or
                variants[name]["verdict"]!=original["verdict"])]
        # A conservative bound can clear a hypothesis only if *every*
        # admissible row-wise alternative is guaranteed to retain the sign,
        # zero-inclusion of the 95% CI, AND the original categorical verdict.
        # In particular, baseline CI containing zero -> alternative excluding
        # zero must be treated as a possible change (not silently passed).
        lower,upper=bound["BOUND_MIN"],bound["BOUND_MAX"]
        if original["sign"]>0:
            robust_sign=lower["est"]>0
        elif original["sign"]<0:
            robust_sign=upper["est"]<0
        else:
            robust_sign=(lower["est"]==0 and upper["est"]==0)
        if original["ci_includes_zero"]:
            robust_ci=(upper["lo"]<=0 and lower["hi"]>=0)
        elif original["lo"]>0:
            robust_ci=lower["lo"]>0
        else:
            robust_ci=upper["hi"]<0
        v=original["verdict"]
        if v in ("NOT_TESTABLE","NOT_APPLICABLE"):
            robust_verdict=True
        elif h["rule"]=="ratio":
            robust_verdict=(upper["hi"]<0 if v=="PASS" else
                            (lower["lo"]>0 if v=="FAIL" else
                             upper["lo"]<=0 and lower["hi"]>=0))
        elif h["rule"]=="sided":
            sg=math.copysign(1,h["predval"])
            min_or_lo=lower["lo"] if sg>0 else -upper["hi"]
            max_or_lo=upper["lo"] if sg>0 else -lower["hi"]
            min_or_hi=lower["hi"] if sg>0 else -upper["lo"]
            max_or_hi=upper["hi"] if sg>0 else -lower["lo"]
            threshold=abs(h["predval"])*eff["did_min_fraction_of_prediction"]
            robust_verdict=(min_or_lo>0 if v=="PASS" else
                            (max_or_hi<threshold if v=="FAIL" else
                             max_or_lo<=0 and min_or_hi>=threshold))
        else:
            half=math.log(eff["equivalence_factor"])
            robust_verdict=(lower["lo"]>=-half and upper["hi"]<=half if v=="PASS" else
                            (lower["lo"]>half or upper["hi"]< -half if v=="FAIL" else
                             upper["lo"]<=half and lower["hi"]>=-half and
                             (upper["lo"]< -half or lower["hi"]>half)))
        possible=not (robust_sign and robust_ci and robust_verdict)
        if not len(A):
            possible=False  # exactly E: no alternative selection can differ
        if differing:changed.append(h["id"])
        if possible:potential.append(h["id"])
        all_records[h["family"]].append(dict(
           id=h["id"],family=h["family"],applicable=h["applicable"],
           original=original,by_start=variants,
           conservative_point_and_ci_bounds=bound,
           witness_change=bool(differing),witness_starts=differing,
           possible_change_by_conservative_bounds=possible))
    base_verdict=_summary_verdict([dict(family=x["family"],id=x["id"],
                                     verdict=x["original"]["verdict"],applicable=x["applicable"])
          for group in all_records.values() for x in group])
    scenarios={}
    for name in STARTS:
        scenarios[name]=_summary_verdict([dict(family=x["family"],id=x["id"],
            verdict=x["by_start"][name]["verdict"],applicable=x["applicable"])
          for group in all_records.values() for x in group])
    whole_change=any(v!=base_verdict for v in scenarios.values())
    changed=sorted(set(changed))
    potential=sorted(set(potential))
    return dict(status=("ALTERNATIVE_CHANGES_CONCLUSION" if changed or whole_change else
                        ("REVIEW_REQUIRED_POSSIBLE_CHANGE" if potential else
                         "STABLE_ON_GRID_AND_CONSERVATIVE_BOUNDS")),
                n_fields=n, bootstrap_replicates=B, bootstrap_seed=seed,
                all_valid_rows_retained=True,
                n_alternative_rows=len(A),n_hypotheses=sum(map(len,all_records.values())),
                baseline_overall_verdict=base_verdict,
                per_start_overall_verdict=scenarios,
                alternative_changes_conclusion=bool(changed or whole_change),
                witness_changed_hypotheses=changed,
                possible_changed_hypotheses=potential,
                hypotheses=dict(all_records),
                warning="Grid witnesses are achievable, conservative component bounds may not be; no global optimum proof",
                science_release_allowed=False)
