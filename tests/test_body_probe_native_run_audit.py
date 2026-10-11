"""Unit-only stored-output audit fixture; no native RF ray tracing."""
import json

import numpy as np

from scripts.drive_sim.audit_body_probe_native_run import audit_run, sha


def make_fixture(out):
    out.mkdir()
    n=2
    P=np.stack([np.eye(6)*0.1]*n)
    x=np.zeros((n,6),float)
    trace={
        "t_s":np.array([.2,.4]),
        "F":np.stack([np.eye(6)]*n),
        "G":np.zeros((n,6,3)),
        "Q_input":np.zeros((n,3,3)),
    }
    for k in ("P_pred_before_odom","P_after_odom","P_after_range",
              "P_before_RF","P_after_RF"):
        trace[k]=P
    for k in ("x_pred_before_odom","x_after_odom","x_after_range",
              "x_before_RF","x_after_RF"):
        trace[k]=x
    np.savez_compressed(out/"STATE_TRACE.npz",**trace)
    poses=np.array([[7.,.1,0.],[7.,.1,.01]])
    np.savez_compressed(out/"ORACLE_EVAL_ONLY.npz",
                        t_s=trace["t_s"],true_xyyaw=poses,
                        physical_slip_event=np.array([False,False]))
    rf={"time_rf_s":np.array([.4]),"corresponding_state_index":np.array([1]),
        "detected":np.array([True]),"P1_firstpath":np.array([2.]),
        "P2_firstpath":np.array([1.]),"s_firstpath":np.array([1/3])}
    np.savez_compressed(out/"PROBE_RF_PACKETS.npz",**rf)
    np.savez_compressed(out/"RF_NATIVE_CHANNELS_ORACLE_ONLY.npz",
                        H_full=np.ones((1,257,2,2),complex),
                        time_rf_s=rf["time_rf_s"],
                        true_body_pose_xyyaw=poses[1:])
    (out/"EXECUTION_STATUS.json").write_text(json.dumps({
        "status":"CONTROL_COMPLETE_RF_COLLECTED"}))
    outputs=["STATE_TRACE.npz","ORACLE_EVAL_ONLY.npz",
             "PROBE_RF_PACKETS.npz","EXECUTION_STATUS.json"]
    config={"probe":{"offsets_deg":[0.]},
            "physical":{"slip_mode":"neutral"},
            "rf":{"mode":"range_only"},
            "initial_filter":{"P0_diagonal":[.1]*6}}
    manifest={"config":config,
              "outputs":[{"path":str(out/name),"sha256":sha(out/name)}
                         for name in outputs]}
    (out/"MANIFEST.json").write_text(json.dumps(manifest))


def test_read_only_output_audit_valid_contract(tmp_path):
    out=tmp_path/"native"
    make_fixture(out)
    report=audit_run(out)
    assert report["status"]=="STORED_TRACE_AUDIT_PASS_NOT_SCIENCE"
    assert report["scientific_PASS"] is False
    assert report["n_rf_packets"]==1
    assert report["max_prediction_P6_residual"]==0


def test_read_only_output_audit_finds_bad_power_ratio(tmp_path):
    out=tmp_path/"native"
    make_fixture(out)
    with np.load(out/"PROBE_RF_PACKETS.npz") as z:
        fields={key:z[key] for key in z.files}
    fields["s_firstpath"]=np.array([.9])
    np.savez_compressed(out/"PROBE_RF_PACKETS.npz",**fields)
    report=audit_run(out)
    assert "RF_S_POWER_RATIO_MISMATCH" in report["issues"]
    assert report["scientific_PASS"] is False
