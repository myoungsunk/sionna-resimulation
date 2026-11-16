"""Portable read-only Stage0 archive checks; Python standard library, no EKF replay."""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[5]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def data(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def rows(name):
    with (ROOT / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def close(actual, expected, label):
    if not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-10):
        raise ValueError((label, actual, expected))


def main():
    manifest = data('MANIFEST.json')
    for rel, entry in manifest['files'].items():
        path = ROOT / rel
        if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError(f'Original Stage0 artifact mismatch: {rel}')
    checksums = (ROOT / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
    for line in checksums:
        digest, rel = line.split('  ', 1)
        path = (ROOT / rel).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError(f'Published checksum mismatch: {rel}')
    contract_hash = sha(ROOT / 'RUN_CONTRACT.json')
    if contract_hash != manifest['root_contract_sha256']:
        raise ValueError('Frozen root contract changed')
    input_map = data('INPUT_LOCATIONS.json')
    for rec in input_map['bindings'] + input_map.get('source_dependencies', []):
        if rec['status'] != 'MATCHED' or not rec['repository_path']:
            raise ValueError(f'Unresolved published input: {rec["original_path"]}')
        if sha(REPO / rec['repository_path']) != rec['sha256']:
            raise ValueError(f'Input hash mismatch: {rec["repository_path"]}. Retrieve Git LFS objects if needed.')
    r2 = rows('r2_seed_decomposition/PACKET_TIMELINE.csv')
    summaries = data('r2_seed_decomposition/SUMMARY.json')['windows']
    groups = {}
    max_ledger = 0.
    for row in r2:
        key = (int(row['seed']), row['arm'])
        group = groups.setdefault(key, [])
        error, prior = float(row['heading_error_deg']), float(row['prior_error_deg'])
        update = float(row['range_update_deg']) + float(row['conditional_s_update_deg'])
        close(error, prior + update, 'R2 update')
        max_ledger = max(max_ledger, abs(error-prior-update))
        if group:
            previous = float(group[-1]['heading_error_deg'])
            close(prior, previous + float(row['gyro_white_deg']) + float(row['bg_correction_deg']), 'R2 prediction')
        group.append(row)
    for rec in summaries:
        use = [float(row['heading_error_deg']) for row in groups[(rec['seed'], rec['arm'])]
               if rec['start_s'] <= float(row['t_s']) < rec['end_s']]
        rms = math.sqrt(math.fsum(e*e for e in use) / len(use))
        close(rms, rec['heading_rmse_deg'], 'R2 window RMS')
    r5 = rows('r5_passage_bias/R5_TIMELINE.csv')
    r5_groups = {}
    near_count = 0
    for row in r5:
        r5_groups.setdefault((int(row['seed']),row['arm']), []).append(row)
        close(float(row['b_deg']), float(row['b_prior_deg']) + float(row['b_range_update_deg']) + float(row['b_s_update_deg']), 'R5 btheta update')
        if float(row['own_prior_rho_m']) < 3.:
            near_count += 1
            close(float(row['q_s']), 0., 'R5 own-prior near q_s')
    r5_result = data('r5_passage_bias/RESULTS.json')
    for paired in r5_result['paired_passages']:
        crossing = r5_result['passages'][paired['passage']-1]['time_s']
        for arm, field in [('G1_LORO','g1_y_rmse_cm'), ('G1_KI','hybrid_y_rmse_cm')]:
            use = [float(row['y_error_cm']) for row in r5_groups[(paired['seed'],arm)]
                   if crossing-10. <= float(row['t_s']) < crossing+10.]
            close(math.sqrt(math.fsum(e*e for e in use)/len(use)), paired[field], 'R5 passage y RMS')
    for row in rows('r5_passage_bias/R5_AR_MEMORY_AND_INFORMATION.csv'):
        close(float(row['crossing_b_posterior_deg']), float(row['crossing_propagated_incoming_b_deg']) + float(row['crossing_decayed_updates_deg']), 'R5 AR ledger')
    for lane in ('r2_seed_decomposition','r5_passage_bias','rref_exposure'):
        if data(f'{lane}/VERIFICATION.json')['status'] != 'PASS':
            raise ValueError(f'Archived verification did not pass: {lane}')
    print(json.dumps({'status':'PASS','original_artifacts':len(manifest['files'])+1,
                      'published_checksums':len(checksums),'mapped_inputs':len(input_map['bindings']),
                      'additional_source_dependencies':len(input_map.get('source_dependencies', [])),
                      'R2_packets':len(r2),'R5_packets':len(r5),'R5_own_near_packets':near_count,
                      'R2_max_update_ledger_abs_deg':max_ledger,
                      'root_contract_sha256':contract_hash,'EKF_replays':0},ensure_ascii=False))


if __name__ == '__main__':
    main()
