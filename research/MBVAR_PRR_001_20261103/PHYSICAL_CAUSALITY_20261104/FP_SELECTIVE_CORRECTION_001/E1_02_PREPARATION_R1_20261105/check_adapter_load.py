"""Constructor readiness only; no evidence/native/replay invocation."""
import os
from pathlib import Path
from qclean_uwb.fp_sc.followup.engine import OriginalAdapter
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.contracts import write_json
root=Path('/work')
adapter=OriginalAdapter(root,revision_evidence=RevisionEvidenceAdapter('VAB','TWO_PORT_UNION'))
assert adapter.revision_evidence.arm=='VAB'
assert len(os.sched_getaffinity(0))<4
write_json(Path(__file__).with_name('ADAPTER_LOAD.json'),dict(
    status='PASS_ORIGINAL_ADAPTER_WITH_VAB_CONSTRUCTOR_ONLY',
    original_source_hashes=adapter.source_hashes,cpu_affinity=sorted(os.sched_getaffinity(0)),
    native_calls=0,evidence_calls=0,replay_calls=0,E1_02_started=False,E2_started=False))
print('ADAPTER_CONSTRUCTOR_PASS_NO_SCIENCE',flush=True)
