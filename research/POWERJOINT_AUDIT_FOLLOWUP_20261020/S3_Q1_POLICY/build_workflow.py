"""Emit fixed sharding without changing the locked packet population."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def prefix():
 text=(ROOT/'.github/workflows/powerjoint-audit-followup-s2-new-retry3.yml').read_text()
 text=text[text.index('    runs-on:'):text.index('      - name: Restore historical')]
 return text.replace('timeout-minutes: 180','timeout-minutes: 360').replace('/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY/','/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY/\n            /research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S0_CORRECTIONS/github_io.py\n            /research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY/model.py\n            /research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY/TRAIN_PARAMS.json\n            /research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY/restore_references.py')
def main():
 index=json.loads((HERE/'LABEL_PACKET_INDEX.json').read_text());matrix=[dict(outer=r['outer'],case=r['case'],seed=s) for r in index for s in range(5)];assert len(matrix)==105
 name='powerjoint-audit-followup-s3-labels.yml'
 top='name: POWERJOINT followup S3 all-packet utility labels\non:\n  workflow_dispatch:\n  push:\n    branches: [research/powerjoint-audit-followup-20261020]\n    paths: [.github/workflows/'+name+']\npermissions:\n  contents: read\njobs:\n  labels:\n    strategy:\n      fail-fast: false\n      max-parallel: 20\n      matrix:\n        include: '+json.dumps(matrix)+'\n'
 tail='''      - name: All locked labels, committed protocol, actual seed
        working-directory: work
        run: python source/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY/labels.py --outer ${{ matrix.outer }} --case ${{ matrix.case }} --seed ${{ matrix.seed }} --out s3/labels/${{ matrix.outer }}_${{ matrix.case }}_seed${{ matrix.seed }}
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        if: always()
        with:
          name: powerjoint-s3-label-${{ matrix.outer }}-${{ matrix.case }}-seed${{ matrix.seed }}-${{ github.run_id }}
          path: |
            work/s3
            work/RESTORE_RECEIPT.json
          retention-days: 30
'''
 (ROOT/'.github/workflows'/name).write_text(top+prefix()+tail)
if __name__=='__main__':main()
