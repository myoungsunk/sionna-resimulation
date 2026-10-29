#!/usr/bin/env python3
"""Source-specific negative test: does assemble ignore the trace's unmatched count?
Only original source implementation, no RF H/trace writes. Expected CONFIRMED_GAP.
"""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from qclean_uwb.drivesim import rf_store
def main():
 class BankStub:
  freqs_hz=np.linspace(6.25e9,6.75e9,257)
 with tempfile.TemporaryDirectory() as d:
  tag=rf_store.tag_of(1.2,0.)
  (Path(d)/(tag+"_trace.npz")).touch()
  poses=[{"pose_id":0,"x":1.2,"y":0.,"yaw_body_deg":0.}]
  fake=dict(status="OK",unmatched=np.array(1),tau=np.array([1e-8]))
  with patch.object(rf_store,"load_trace",return_value=fake), patch.object(rf_store,"h_for_antenna_yaws",return_value=np.zeros((1,257,2,2),complex)):
   h,meta=rf_store.assemble(poses,[Path(d)],[BankStub()],0,allow_missing=False)
  accepted=bool(meta["complete"] and np.shape(h)==(1,257,2,2))
  assert accepted, "SOURCE_BEHAVIOR_CHANGED"
  print(json.dumps({"code_source":"src/qclean_uwb/drivesim/rf_store.py::assemble","source_status":"CONFIRMED_GAP",
   "trace_status":"OK","unmatched_paths":1,"allow_missing":False,
   "assemble_report_complete":meta["complete"],"H_constructed":accepted,
   "semantic_note":"Source documentation says unmatched=0 needed but actual assemble checks status only; G3 checker is an external release gate. This alone does not prove H physically wrong."}))
if __name__=="__main__":main()
