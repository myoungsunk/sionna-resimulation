"""Training waits for the complete immutable label run; evaluation never subsamples."""
from build_workflow import HERE,ROOT,prefix
def main():
 name='powerjoint-audit-followup-s3-train-evaluate.yml'
 top='''name: POWERJOINT followup S3 OOF margins and recursive evaluation
on:
  workflow_dispatch:
  push:
    branches: [research/powerjoint-audit-followup-20261020]
    paths: [.github/workflows/powerjoint-audit-followup-s3-train-evaluate.yml]
permissions:
  contents: read
  actions: read
jobs:
  train:
'''
 train=prefix()+'''      - name: Wait all locked labels, route OOF, selected-action margins
        working-directory: work
        env:
          GH_TOKEN: ${{ github.token }}
        run: python source/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY/train.py --labels-run 39378144903 --wait --out s3/models
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        if: always()
        with:
          name: powerjoint-s3-models-${{ github.run_id }}
          path: work/s3/models
          retention-days: 30
  evaluate:
    needs: train
    strategy:
      fail-fast: false
      matrix:
        route: [R2, R4, R5, C01, C02, C03, O01, O02, O03]
'''
 evaluation=prefix()+'''      - name: Restore trained models from this run
        working-directory: work
        env:
          GH_TOKEN: ${{ github.token }}
        run: python source/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY/restore_models.py --run ${{ github.run_id }} --out models
      - name: Restore all eight Native LoS historical traces
        if: matrix.route == 'R2'
        working-directory: work
        run: python source/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY/restore_los_reference.py --out references
      - name: Restore T2 historical references
        if: ${{ !startsWith(matrix.route, 'R') }}
        working-directory: work
        run: python source/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S2_N2_GEOMETRY/restore_references.py --route ${{ matrix.route }} --out references
      - name: Restore original new RF
        if: ${{ !startsWith(matrix.route, 'R') }}
        working-directory: work
        run: python source/research/POWERJOINT_AUDIT_RERUN_20261020/restore_route.py --route ${{ matrix.route }} --out source_route
      - name: Frozen 288-row recursive evaluation
        working-directory: work
        run: python source/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY/evaluate.py --route ${{ matrix.route }} --models models/MODELS.json --out s3/evaluation/${{ matrix.route }}
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        if: always()
        with:
          name: powerjoint-s3-evaluation-${{ matrix.route }}-${{ github.run_id }}
          path: |
            work/s3/evaluation
            work/RESTORE_RECEIPT.json
            work/models/MODEL_ARTIFACT_RECEIPT.json
            work/references/*RECEIPT.json
            work/source_route/ARCHIVE_CONTENTS_AND_SHA.json
          retention-days: 30
'''
 (ROOT/'.github/workflows'/name).write_text(top+train+evaluation)
if __name__=='__main__':main()
