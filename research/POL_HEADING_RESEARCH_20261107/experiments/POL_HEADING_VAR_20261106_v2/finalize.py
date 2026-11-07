import run_heading as m
import json
rows=json.loads((m.BASE/'PROGRESS.json').read_text(encoding='utf-8'))
assert len(rows)==40 and len(list((m.BASE/'outputs').glob('*.npz')))==40
assert all(m.sha(p)==h for p,h in json.loads((m.BASE/'INPUT_HASHES.json').read_text(encoding='utf-8')).items())
validation=json.loads((m.BASE/'VALIDATION.json').read_text(encoding='utf-8'))
m.dump('RESULT.json',dict(status='ALL_40_OUTPUTS_COMPLETED_FINALIZATION_RECOVERED',original_runner_exit_code=1,cause='cp949 decoding of UTF-8 INPUT_HASHES after all outputs and CSV were saved',recovery='explicit UTF-8 read, hashes rechecked, all saved metrics revalidated; no estimator rerun',rows=40,inputs_unchanged=True,validation=validation['status'],adoption=False,output_hashes={p.name:m.sha(p) for p in (m.BASE/'outputs').glob('*.npz')}))
print('FINALIZATION_RECOVERED; NUMERICAL_CONVERGENCE_FAIL')
