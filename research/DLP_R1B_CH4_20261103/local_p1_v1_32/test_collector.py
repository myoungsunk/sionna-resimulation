"""Offline collector regression checks. No RF solver calls or library stand-ins for RF."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
import os
import signal
import copy
from unittest.mock import patch

import numpy as np

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
sys.path.insert(0, str(RUNTIME))
if sys.platform == 'win32':
    # resource is a Linux-only reporting dependency. These tests never call it.
    sys.modules.setdefault('resource', types.ModuleType('resource'))
import r1b_acquire as driver
import r1b_native as native


class CollectorTests(unittest.TestCase):
    def test_32_profile_requires_source_identity_all_levels_science_and_measured_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = types.SimpleNamespace(production_release=root/'release.json', production_plan=root/'plan.json',
                                         contract=root/'contract.json')
            source = {key: {} for key in ('geometry', 'population', 'inputs', 'rf', 'runtime', 'tolerances', 'replay')}
            source['code_files'] = [dict(path=Path(native.__file__).as_posix(), sha256=native.sha(native.__file__))]
            source['local_production'] = dict(precision_adapter={'sha256': 'same-adapter'},
                                              local_required_python='3.11.17', acquisition_policy='FRESH_917')
            source_path = root/'source_contract.json'
            native.writej(source_path, source)
            source_spec = dict(path=str(source_path), sha256=native.sha(source_path))
            contract = copy.deepcopy(source)
            contract['local_production'].update(resource_amendment_id='LOCAL-P1-V1-32',
                         benchmark_levels=list(driver.LEVELS_32), resource_limits=driver.RESOURCE_LIMITS_32,
                         benchmark_source_contract=source_spec,
                         benchmark_measurement_fingerprint=driver.measurement_fingerprint(source))
            native.writej(args.contract, contract)
            plan = dict(production_audit={'sha256': 'audit-hash'}, contract_sha256=native.sha(args.contract),
                        shards=[{}] * 64, resource_amendment_id='LOCAL-P1-V1-32',
                        benchmark_source_contract=source_spec,
                        benchmark_measurement_fingerprint=driver.measurement_fingerprint(source))
            native.writej(args.production_plan, plan)
            environment = root/'environment.json'
            native.writej(environment, dict(status='PASS', contract_sha256=source_spec['sha256'],
                          execution_host=driver.socket.gethostname(), actual_smoke_test=True,
                          resource_limits=driver.RESOURCE_LIMITS_32))
            benchmark_path = root/'benchmark.json'
            benchmark = dict(status='PASS', contract_sha256=source_spec['sha256'],
                             production_contract_sha256=plan['contract_sha256'],
                             execution_host=driver.socket.gethostname(), environment_sha256=native.sha(environment),
                             resource_limits=driver.RESOURCE_LIMITS_32, chosen_worker_count=32,
                             selection_rule='MAX_MEASURED_AGGREGATE_THROUGHPUT_TIE_FEWER_WORKERS', measurements=[])
            for n in driver.LEVELS_32:
                benchmark['measurements'].append(dict(worker_count=n, completed_pose_count=2*n,
                    pose_ids=[((2*(n-1)+2*w+j)*137+75) % 917 for w in range(n) for j in (0, 1)],
                    wall_elapsed_s=60., throughput_pose_per_minute=float(2*n), max_rss_mib=1000.,
                    actual_native_solver=True, scientific_checks_passed=True))
            release = dict(status='APPROVED', authorized_stages=['P1'], approver_identity='user',
                           user_approval_reference='explicit task approval', production_audit_sha256='audit-hash',
                           production_plan_sha256=native.sha(args.production_plan),
                           production_contract_sha256=plan['contract_sha256'],
                           environment=dict(path=str(environment), sha256=native.sha(environment)))

            def validate():
                native.writej(benchmark_path, benchmark)
                release['benchmark'] = dict(path=str(benchmark_path), sha256=native.sha(benchmark_path))
                native.writej(args.production_release, release)
                return driver.validate_release(args, plan)

            with patch.object(driver, 'current_resource_limits', return_value=driver.RESOURCE_LIMITS_32):
                self.assertEqual(validate(), 32)
                removed = benchmark['measurements'].pop()
                with self.assertRaisesRegex(RuntimeError, 'EXACT_FROZEN_NATIVE_BENCHMARK_LEVELS_REQUIRED'):
                    validate()
                benchmark['measurements'].append(removed)
                benchmark['chosen_worker_count'] = 16
                with self.assertRaisesRegex(RuntimeError, 'BENCHMARK_WINNER_SELECTION_MISMATCH'):
                    validate()
                benchmark['chosen_worker_count'] = 32
                benchmark['measurements'][-1]['scientific_checks_passed'] = False
                with self.assertRaisesRegex(RuntimeError, 'BENCHMARK_FROZEN_POSES_OR_SCIENTIFIC_GATES_FAILED'):
                    validate()
                benchmark['measurements'][-1]['scientific_checks_passed'] = True
                contract['rf'] = dict(changed_physics=True)
                native.writej(args.contract, contract)
                with self.assertRaisesRegex(RuntimeError, 'BENCHMARK_PHYSICAL_CONTRACT_MISMATCH'):
                    validate()
                contract['rf'] = {}
                native.writej(args.contract, contract)
            with patch.object(driver, 'current_resource_limits', return_value=dict(cpus=[0], memory_max_bytes=1)):
                with self.assertRaisesRegex(RuntimeError, 'PRODUCTION_RESOURCE_LIMITS_MISMATCH'):
                    validate()

    def test_amended_runtime_rejects_wrong_python_and_unguarded_canary(self):
        contract = dict(local_production=dict(local_required_python='3.11.17'))
        with patch.object(native.platform, 'python_version', return_value='3.12.14'):
            with self.assertRaisesRegex(RuntimeError, 'LOCAL_PYTHON_VERSION_NOT_FROZEN'):
                native.initialize(contract, None, None)
        with patch.object(native, 'load_contract', return_value=(contract, [])):
            with self.assertRaisesRegex(RuntimeError, 'LOCAL_CONTRACT_REQUIRES_GUARDED_PRODUCTION_DRIVER'):
                native.run_canary(types.SimpleNamespace(contract='unused'))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'existing'
            output.mkdir()
            original = output/'FAILURE.json'
            original.write_text('original evidence')
            argv = ['r1b_native.py', '--contract', 'unused', '--banks', 'unused', '--out', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(native, 'readj', return_value=contract):
                self.assertEqual(native.main(), 2)
            self.assertEqual(original.read_text(), 'original evidence')
            self.assertEqual([p.name for p in output.iterdir()], ['FAILURE.json'])

    def test_private_worker_entry_requires_live_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = dict(global_stop_file=str(Path(directory)/'STOP.json'))
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'SUPERVISED_WORKER_ENTRY_REQUIRED'):
                    driver.validate_worker_supervision(plan)

    @unittest.skipIf(sys.platform == 'win32', 'Abrupt-exit integration requires Linux production semantics')
    def test_supervisor_killed_child_blocks_next_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = dict(local_amendment_id='LOCAL-P1-V1', global_stop_file=str(root/'STOP.json'))
            command = [sys.executable, '-c', 'import os,signal;os.kill(os.getpid(),signal.SIGKILL)']
            self.assertEqual(driver.supervise_command(plan, {}, command), -signal.SIGKILL)
            results = list((root/'.supervisors').glob('*/RESULT.json'))
            self.assertEqual(len(results), 1)
            self.assertEqual(native.readj(results[0])['child_returncode'], -signal.SIGKILL)
            with self.assertRaisesRegex(RuntimeError, 'GLOBAL_STOP_REQUESTED'):
                driver.check_global_stop(plan)

    @unittest.skipIf(sys.platform == 'win32', 'PID start-time identity requires Linux procfs')
    def test_orphaned_supervisor_blocks_next_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = dict(local_amendment_id='LOCAL-P1-V1', global_stop_file=str(root/'STOP.json'))
            marker = root/'.supervisors'/'orphan'/'STARTED.json'
            native.writej(marker, dict(supervisor_pid=999999999, supervisor_start_ticks=0))
            with self.assertRaisesRegex(RuntimeError, 'ORPHANED_SUPERVISOR_REQUIRES_REVIEW'):
                driver.check_global_stop(plan)
            self.assertTrue((root/'STOP.json').is_file())

    @unittest.skipIf(sys.platform == 'win32', 'Kernel lock integration requires the production Linux host')
    def test_worker_cap_and_released_kernel_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = dict(global_stop_file=str(Path(directory)/'STOP.json'))
            first = driver.claim_worker_slot(plan, 1)
            try:
                with self.assertRaisesRegex(RuntimeError, 'APPROVED_WORKER_CONCURRENCY_EXCEEDED'):
                    driver.claim_worker_slot(plan, 1)
            finally:
                first.close()
            recovered = driver.claim_worker_slot(plan, 1)
            recovered.close()

    def test_local_plan_preserves_hold_and_rejects_missing_or_duplicate_pose(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = types.SimpleNamespace(contract=root/'contract.json', canary_qa=root/'old_qa.json',
                                         production_plan=root/'plan.json', mode='assemble', banks=root)
            adapter = root/'adapter.py'
            adapter.write_text('# source-only adapter fixture\n')
            contract = dict(local_production=dict(amendment_id='LOCAL-P1-V1', acquisition_policy='FRESH_917',
                            precision_adapter=dict(path=str(adapter), sha256=native.sha(adapter))), inputs=dict(banks=[]))
            native.writej(args.contract, contract)
            native.writej(args.canary_qa, dict(status='HOLD_RF_PARITY'))
            parity = root/'parity.json'
            native.writej(parity, dict(verdict='NUMERIC_PARITY_PASS', checks=dict(fixed_precision=True),
                         original_canary_qa_sha256=native.sha(args.canary_qa), contract_sha256=native.sha(args.contract),
                         precision_adapter_sha256=native.sha(adapter),
                         pose_ids=[0, 150, 221, 440, 458, 476, 696, 916, 75, 305, 610, 809]))
            plan = dict(status='FROZEN', local_amendment_id='LOCAL-P1-V1',
                        contract_sha256=native.sha(args.contract), canary_qa_sha256=native.sha(args.canary_qa),
                        runner_sha256=native.sha(driver.__file__), implementer_identity='implementer',
                        parity_receipt=dict(path=str(parity), sha256=native.sha(parity)), reuse_pose_ids=[],
                        new_pose_ids=list(range(917)), shards=[dict(shard_index=0, pose_ids=list(range(917)),
                        output_dir=str(root/'shard'))], assembly_dir=str(root/'assembly'),
                        global_stop_file=str(root/'STOP.json'))

            def freeze():
                plan['production_spec_sha256'] = driver.canonical_spec_sha(plan)
                audit = root/'audit.json'
                native.writej(audit, dict(status='PASS', separate_agent=True, role='INDEPENDENT_AUDITOR',
                              auditor_identity='auditor', **{key: plan[key] for key in (
                                  'production_spec_sha256', 'runner_sha256', 'contract_sha256', 'canary_qa_sha256')}))
                plan['production_audit'] = dict(path=str(audit), sha256=native.sha(audit))
                native.writej(args.production_plan, plan)

            freeze()
            _, _, canary, _, _ = driver.load_local_locks(args, contract, [])
            self.assertEqual(canary['status'], 'HOLD_RF_PARITY')
            plan['shards'][0]['pose_ids'][-1] = 915
            freeze()
            with self.assertRaisesRegex(RuntimeError, 'LOCAL_SHARDS_NOT_EXACT_917_FRESH_POSES'):
                driver.load_local_locks(args, contract, [])

    def test_release_requires_user_approval_and_exact_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = types.SimpleNamespace(production_release=None, production_plan=root / 'plan.json')
            plan = dict(production_audit={'sha256': 'audit-hash'}, contract_sha256='contract-hash',
                        shards=[{}] * 16)
            native.writej(args.production_plan, plan)
            with self.assertRaisesRegex(RuntimeError, 'USER_PRODUCTION_APPROVAL_REQUIRED'):
                driver.validate_release(args, plan)
            evidence = root / 'evidence.json'
            native.writej(evidence, dict(status='PASS', contract_sha256='contract-hash',
                          execution_host=driver.socket.gethostname(), actual_smoke_test=True))
            benchmark = root / 'benchmark.json'
            native.writej(benchmark, dict(status='PASS', contract_sha256='contract-hash',
                          execution_host=driver.socket.gethostname(), environment_sha256=native.sha(evidence),
                          chosen_worker_count=8, measurements=[dict(worker_count=n, completed_pose_count=n,
                          wall_elapsed_s=60., throughput_pose_per_minute=float(n), max_rss_mib=1000.,
                          actual_native_solver=True) for n in (1, 2, 4, 8)]))
            release = dict(status='APPROVED', authorized_stages=['P1'], approver_identity='user',
                           user_approval_reference='explicit task approval',
                           production_plan_sha256=native.sha(args.production_plan),
                           production_audit_sha256='audit-hash',
                           environment=dict(path=str(evidence), sha256=native.sha(evidence)),
                           benchmark=dict(path=str(benchmark), sha256=native.sha(benchmark)))
            args.production_release = root / 'release.json'
            native.writej(args.production_release, release)
            driver.validate_release(args, plan)
            native.writej(evidence, {'status': 'FAIL'})
            with self.assertRaisesRegex(RuntimeError, 'EVIDENCE_CHANGED'):
                driver.validate_release(args, plan)

    def test_stop_is_shared_and_first_failure_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = dict(local_amendment_id='LOCAL-P1-V1', global_stop_file=str(Path(directory) / 'STOP.json'))
            driver.check_global_stop(plan)
            driver.signal_global_stop(plan, 'first')
            driver.signal_global_stop(plan, 'second')
            self.assertEqual(native.readj(plan['global_stop_file'])['reason'], 'first')
            with self.assertRaisesRegex(RuntimeError, 'GLOBAL_STOP_REQUESTED'):
                driver.check_global_stop(plan)

    def test_existing_shard_output_failure_stops_every_worker_without_output_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root/'shard'
            out.mkdir()
            (out/'evidence.txt').write_text('preserve')
            plan = dict(local_amendment_id='LOCAL-P1-V1', global_stop_file=str(root/'STOP.json'),
                        shards=[dict(shard_index=0, pose_ids=[0], output_dir=str(out))])
            args = types.SimpleNamespace(shard_index=0, out=out, resume=False)
            with patch.object(driver, 'lineage', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'APPEND_ONLY_OUTPUT_DIRECTORY_ALREADY_EXISTS'):
                    driver.run_shard(args, {}, [], {}, plan, {})
            self.assertEqual([p.name for p in out.iterdir()], ['evidence.txt'])
            self.assertEqual((out/'evidence.txt').read_text(), 'preserve')
            with self.assertRaisesRegex(RuntimeError, 'GLOBAL_STOP_REQUESTED'):
                driver.check_global_stop(plan)

    def test_spec_binds_partition_but_excludes_audit_attachment(self):
        plan = dict(shards=[dict(shard_index=0, pose_ids=list(range(917)))])
        original = driver.canonical_spec_sha(plan)
        plan['production_audit'] = dict(path='audit.json', sha256='a' * 64)
        self.assertEqual(original, driver.canonical_spec_sha(plan))
        plan['shards'][0]['pose_ids'].pop()
        self.assertNotEqual(original, driver.canonical_spec_sha(plan))

    def test_raw_reconstruction_v2_and_anchor_tolerance(self):
        row = dict(pose_id='0', t_s='0', x='1.2', y='0.35', yaw_body_deg='0')
        xyz, anchor = np.array([1.2, .35, .45]), np.array([10., 0., 2.65])
        delay = np.linalg.norm(xyz - anchor) / native.C
        freq = 6250400000. + 1950000. * np.arange(native.N)
        h = np.zeros((native.N, 2, 2), dtype=complex)
        h[:, 0, 0] = 1
        h[:, 1, 0] = .5
        obs, cir = native.observer(h)
        source = h[:, :, 0] / 1j
        record = dict(pose_id=0, raw_file='pose_0000.npz', fd=[dict(axis=i, status='PASS') for i in range(3)],
                      los={**obs, 'observer_recompute_abs': 0}, full={**obs, 'observer_recompute_abs': 0})
        contract = dict(local_production={}, replay=dict(range_offset_m=0), tolerances=dict(
            observer_abs=1e-12, source_direct_relative_max=1e-12, native_complex_relative_max=5e-4,
            native_s_abs_max=2e-5, los_delay_abs_s=1e-9, full_direct_relative_max=1e-12))
        payload = dict(pose_id=0, t_s=0., xyz_m=xyz, psi_rad=0., anchor_xyz_m=anchor + [0, 0, 4.44e-16],
                       freq_hz=freq, source_physical_h=source, source_independent_h=source,
                       source_precision_matched_h=h[:, :, 0], source_model_h=np.array([delay*native.C, obs['s']]),
                       source_model_H=np.zeros((2, 4)))
        amplitudes = np.transpose(h * np.exp(2j*np.pi*freq*delay)[:, None, None], (1, 2, 0))
        for mode in ('los', 'full'):
            payload.update({f'H_{mode}': h, f'CIR_{mode}': cir, f'{mode}_path_offsets': np.arange(native.N+1),
                            f'{mode}_path_counts': np.ones(native.N, dtype=int),
                            f'{mode}_tau_s': np.full(native.N, delay), f'{mode}_a': amplitudes,
                            f'{mode}_interactions': np.zeros((3, native.N), dtype=int),
                            f'{mode}_objects': np.zeros((3, native.N), dtype=int)})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / record['raw_file']
            np.savez_compressed(path, **payload)
            record['raw_sha256'] = native.sha(path)
            with patch.object(native, 'precision_reference', side_effect=lambda c, h, f, x, a: h*1j):
                _, measured = driver.validate_raw_pose(path, row, record, contract)
                self.assertEqual(measured['native_source_complex_relative'], 0)
                payload['anchor_xyz_m'] = anchor + [0, 0, 1e-8]
                np.savez_compressed(path, **payload)
                record['raw_sha256'] = native.sha(path)
                with self.assertRaisesRegex(RuntimeError, 'RAW_ANCHOR_NOT_B'):
                    driver.validate_raw_pose(path, row, record, contract)


if __name__ == '__main__':
    unittest.main()
