"""Artifact layout, provenance, and trust-boundary regression coverage."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

DASHBOARD = Path(__file__).resolve().parents[1] / 'dashboard'
sys.path.insert(0, str(DASHBOARD))
from build import SAFE, build
from ingest import MAX_RECORDS, SPRINT_CASES, ingest
from longride_import import copy_inert


class MultiRevisionIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = self.root / 'incoming'
        self.input.mkdir()
        self.history = self.root / 'history'
        self.identity = 'actions-123-2'
        self.names = ['candidate-aaaaaaaaaaaa', 'release-bbbbbbbbbbbb',
                      'release-cccccccccccc', 'release-dddddddddddd']
        self.base = {'workflow_url': 'https://github.com/doudar/smartspin2k-simulator/actions/runs/123',
                     'workflow_conclusion': 'success', 'workflow_updated_at': '2026-10-12T23:00:00Z',
                     'imported_at': '2026-10-12T23:01:00Z'}
        self.check = {'passed': True, 'absolute_passed': True, 'relative_passed': True,
                      'failures': []}
        self.pair = {**self.check, 'reported_power_comparison': dict(self.check)}
        self.experiment = 'continuous-long-ride-sprints-v2'
        self.plan()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def plan(self, names=None):
        self.write(self.input / 'experiment-plan.json', {
            'schema_version': 1, 'versions': [{'id': name} for name in (names or self.names)],
            'matrix': {'minutes': [90], 'states': ['empty', 'full'],
                       'sensitivities': [3, 5, 10], 'long_seeds': [7]},
        })

    def revision(self, name, *, training=True):
        group = self.input / name
        metadata = {'candidate_ref': name, 'run_started_at': '2026-10-11T12:00:00Z',
                    'run_completed_at': '2026-10-11T12:20:00Z',
                    'runtime_toolchain': {'python': '3.11.10'}}
        self.write(group / 'short/comparison.json', {
            'status': 'complete', 'passed': True,
            'runs': [{'scenario': 'steps', 'seed': 7, **copy.deepcopy(self.pair)}],
        })
        self.write(group / 'short/run-metadata.json', metadata)
        rows = [{**case, **copy.deepcopy(self.pair),
                 'window_comparisons': {n: copy.deepcopy(self.pair) for n in ('early', 'middle', 'late')},
                 'sprint_comparisons': {n: copy.deepcopy(self.pair) for n in ('early', 'middle', 'late')}}
                for case in SPRINT_CASES]
        self.write(group / 'long/paired/longride.json', {
            'status': 'complete', 'experiment': self.experiment, 'runs': rows,
            'requested_cases': copy.deepcopy(SPRINT_CASES),
        })
        self.write(group / 'long/run-metadata.json', metadata)
        for case in SPRINT_CASES:
            key = f"long_90m_{case['initial_state']}_sensitivity{case['sensitivity']}-7"
            for variant in ('baseline', 'candidate'):
                path = group / 'long/paired' / variant / key / 'trace.csv'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('time_s,target_w,power_w,latest_delivered_sensor_power_w,motor_steps,cadence_rpm\n0,100,99,98,120,85\n1,100,99,98,140,85\n')
        if training:
            self.write(group / 'long/training/longride.json', {
                'status': 'complete', 'experiment': self.experiment, 'runs': [],
                'training': {'full_fixture_created': True},
            })
            self.write(group / 'long/training/full.json', {'fixture': 'earned'})
            self.write(group / 'long/training/run-metadata.json', {
                **metadata, 'run_started_at': '2026-10-10T12:00:00Z',
                'run_completed_at': '2026-10-10T12:20:00Z',
            })
        return group

    def run_ingest(self):
        ingest(self.input, self.history, self.identity, self.base)
        build(self.history, self.root / 'site')
        return {p.name: json.loads((p / 'data.json').read_text()) for p in self.history.iterdir()}

    def test_four_revisions_short_six_long_training_are_unique_immutable_and_linked(self):
        for name in self.names:
            self.revision(name)
        records = self.run_ingest()
        self.assertEqual(len(records), 32)
        self.assertEqual(len(json.loads((self.root / 'site/history.json').read_text())), 28)
        for name in self.names:
            prefix = self.identity + '-' + name
            self.assertIn(prefix + '-short', records)
            for case in SPRINT_CASES:
                rid = prefix + f"-long-90m-{case['initial_state']}-sensitivity{case['sensitivity']}-7"
                self.assertTrue(records[rid]['comparison']['passed'])
                self.assertEqual(records[rid]['metadata']['training_run_id'], prefix + '-training')
                self.assertEqual(records[rid]['metadata']['run_completed_at'], '2026-10-11T12:20:00Z')
            self.assertEqual(records[prefix + '-training']['metadata']['run_completed_at'], '2026-10-10T12:20:00Z')
        snapshot = {p.relative_to(self.history): p.read_bytes() for p in self.history.rglob('*') if p.is_file()}
        self.write(self.input / self.names[0] / 'short/comparison.json', {'status': 'failed', 'runs': []})
        self.run_ingest()
        self.assertEqual(snapshot, {p.relative_to(self.history): p.read_bytes() for p in self.history.rglob('*') if p.is_file()})

    def test_invalid_short_and_long_subgroups_do_not_discard_siblings(self):
        for name in self.names:
            self.revision(name)
        (self.input / self.names[0] / 'short/comparison.json').write_text('{bad json')
        (self.input / self.names[1] / 'long/paired/longride.json').write_text('{bad json')
        records = self.run_ingest()
        self.assertEqual(len(records), 26)
        self.assertEqual(records[self.identity + '-' + self.names[0] + '-short']['comparison']['status'], 'incomplete')
        self.assertEqual(records[self.identity + '-' + self.names[0] + '-short']['metadata']['candidate_ref'], self.names[0])
        self.assertEqual(records[self.identity + '-' + self.names[1] + '-long-incomplete']['comparison']['status'], 'incomplete')
        self.assertTrue(records[self.identity + '-' + self.names[1] + '-short']['comparison']['passed'])
        self.assertTrue(records[self.identity + '-' + self.names[2] + '-long-90m-full-sensitivity10-7']['comparison']['passed'])

    def test_absent_revision_produces_short_and_all_six_missing_long_cases(self):
        self.plan([self.names[0]])
        records = self.run_ingest()
        self.assertEqual(len(records), 7)
        self.assertTrue(all(row['comparison']['status'] == 'incomplete' for row in records.values()))
        self.assertTrue(all(row['comparison']['passed'] is False for row in records.values()))
        for case in SPRINT_CASES:
            self.assertIn(self.identity + '-' + self.names[0] + f"-long-90m-{case['initial_state']}-sensitivity{case['sensitivity']}-7", records)

    def test_requested_missing_case_remains_an_explicit_record(self):
        self.plan([self.names[0]])
        group = self.revision(self.names[0], training=False)
        path = group / 'long/paired/longride.json'
        manifest = json.loads(path.read_text())
        manifest['runs'].pop()
        self.write(path, manifest)
        records = self.run_ingest()
        self.assertEqual(len(records), 7)
        rid = self.identity + '-' + self.names[0] + '-long-90m-full-sensitivity10-7'
        self.assertEqual(records[rid]['comparison']['status'], 'incomplete')

    def test_cached_evidence_preserves_original_dates_and_execution_provenance(self):
        self.plan([self.names[0]])
        group = self.revision(self.names[0])
        self.write(group / 'cache-state.json', {'reused': True, 'cache_key': 'exact-pins-v1', 'source_run_id': '99'})
        original = {'workflow_url': 'https://github.com/doudar/smartspin2k-simulator/actions/runs/80',
                    'workflow_updated_at': '2026-10-11T12:21:00Z', 'workflow_conclusion': 'success',
                    'imported_at': '2026-10-11T12:30:00Z'}
        path = group / 'short/run-metadata.json'
        self.write(path, {**json.loads(path.read_text()), **original})
        records = self.run_ingest()
        short = records[self.identity + '-' + self.names[0] + '-short']['metadata']
        for key, value in original.items():
            self.assertEqual(short[key], value)
        self.assertEqual(short['ingestion'], self.base)
        self.assertTrue(short['cache']['reused'])
        self.assertIn('Reused cached evidence from Actions run 99', short['notes'])
        long = records[self.identity + '-' + self.names[0] + '-long-90m-empty-sensitivity3-7']['metadata']
        self.assertEqual(long['workflow_url'], 'https://github.com/doudar/smartspin2k-simulator/actions/runs/99')
        self.assertEqual(long['run_completed_at'], '2026-10-11T12:20:00Z')
        self.assertNotIn('workflow_updated_at', long)

    def test_inert_root_files_and_unplanned_directories_are_ignored(self):
        self.plan([self.names[0]])
        self.revision(self.names[0])
        marker = self.root / 'executed'
        (self.input / 'build.py').write_text(f'from pathlib import Path; Path({str(marker)!r}).touch()')
        (self.input / 'experiment-plan.py').write_text('raise AssertionError("never execute")')
        (self.input / 'unrelated.json').write_text('{unparsed junk')
        (self.input / 'unrelated-link').symlink_to('/etc/passwd')
        unrelated = self.input / 'unplanned/short'
        unrelated.mkdir(parents=True)
        (unrelated / 'comparison.json').write_text('{junk')
        records = self.run_ingest()
        self.assertEqual(len(records), 8)
        self.assertFalse(marker.exists())
        for rid in records:
            with zipfile.ZipFile(self.history / rid / 'evidence.zip') as archive:
                self.assertFalse(any(name.endswith('.py') or name == 'unrelated.json' for name in archive.namelist()))

    def test_symlinked_short_rejected_and_healthy_long_still_published(self):
        self.plan([self.names[0]])
        group = self.revision(self.names[0])
        target = self.root / 'outside-short'
        shutil.move(group / 'short', target)
        (group / 'short').symlink_to(target, target_is_directory=True)
        records = self.run_ingest()
        self.assertEqual(records[self.identity + '-' + self.names[0] + '-short']['comparison']['status'], 'incomplete')
        self.assertTrue(records[self.identity + '-' + self.names[0] + '-long-90m-empty-sensitivity3-7']['comparison']['passed'])

    def test_symlink_in_case_ancestor_is_rejected_without_archiving_target(self):
        self.plan([self.names[0]])
        group = self.revision(self.names[0])
        target = self.root / 'outside-candidate'
        shutil.move(group / 'long/paired/candidate', target)
        (group / 'long/paired/candidate').symlink_to(target, target_is_directory=True)
        records = self.run_ingest()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[self.identity + '-' + self.names[0] + '-long-incomplete']['comparison']['status'], 'incomplete')
        self.assertTrue(records[self.identity + '-' + self.names[0] + '-short']['comparison']['passed'])
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            copy_inert(group / 'long/paired/candidate/long_90m_empty_sensitivity3-7', self.root / 'copy')

    def test_symlink_root_cannot_create_directories_through_outside_parent(self):
        outside = self.root / 'outside'
        outside.mkdir()
        link = self.root / 'linked'
        link.symlink_to(outside, target_is_directory=True)
        ingest(link / 'absent', self.history, self.identity, self.base)
        self.assertFalse((outside / 'absent').exists())
        comparison = json.loads((self.history / (self.identity + '-batch-incomplete') / 'comparison.json').read_text())
        self.assertEqual(comparison['status'], 'incomplete')

    def test_oversized_revision_matrix_is_bounded_and_explicit(self):
        self.plan(self.names + ['extra'])
        records = self.run_ingest()
        self.assertEqual(len(records), 1)
        self.assertEqual(next(iter(records.values()))['comparison']['status'], 'incomplete')

    def test_total_record_budget_rejects_only_oversized_subgroup(self):
        for name in self.names:
            group = self.revision(name, training=False)
            requested = [dict(minutes=minutes, initial_state=state, seed=seed)
                         for minutes in (30, 60, 90) for state in ('empty', 'partial', 'full') for seed in (7, 8, 9)]
            self.write(group / 'long/paired/longride.json', {
                'status': 'incomplete', 'experiment': 'continuous-long-ride-v1',
                'runs': [], 'requested_cases': requested,
            })
        records = self.run_ingest()
        self.assertLessEqual(len(records), MAX_RECORDS)
        self.assertEqual(len(records), 34)
        self.assertTrue(all(self.identity + '-' + name + '-short' in records for name in self.names))
        self.assertEqual(sum(rid.endswith('-long-incomplete') for rid in records), 3)

    def test_legacy_short_root_and_release_matrix_still_import(self):
        (self.input / 'experiment-plan.json').unlink()
        self.write(self.input / 'comparison.json', {'status': 'failed', 'runs': []})
        self.assertEqual(set(self.run_ingest()), {self.identity})
        (self.input / 'comparison.json').unlink()
        self.write(self.input / '26.10.1/comparison.json', {'status': 'complete', 'runs': []})
        self.write(self.input / '26.9.15/comparison.json', {'status': 'failed', 'runs': []})
        records = self.run_ingest()
        self.assertEqual(len(records), 3)
        self.assertIn(self.identity + '-26.10.1', records)
        self.assertIn(self.identity + '-26.9.15', records)

    def test_oversized_safe_revision_name_gets_bounded_immutable_ids(self):
        name = 'a' * 101
        self.plan([name])
        self.revision(name)
        records = self.run_ingest()
        self.assertEqual(len(records), 8)
        self.assertTrue(all(SAFE.fullmatch(rid) for rid in records))
        training_id = next(rid for rid in records if rid.endswith('-training'))
        for rid, record in records.items():
            if '-long-90m-' in rid:
                self.assertEqual(record['metadata']['training_run_id'], training_id)

    def test_plan_suite_preserves_only_the_requested_tests(self):
        for suite, count in (('short', 1), ('long', 6)):
            with self.subTest(suite=suite):
                self.plan([self.names[0]])
                plan_path = self.input / 'experiment-plan.json'
                plan = json.loads(plan_path.read_text())
                self.write(plan_path, {**plan, 'suite': suite})
                self.history = self.root / ('history-' + suite)
                records = self.run_ingest()
                self.assertEqual(len(records), count)
                self.assertTrue(all(row['comparison']['status'] == 'incomplete' for row in records.values()))
                if suite == 'short':
                    self.assertTrue(all(rid.endswith('-short') for rid in records))
                else:
                    self.assertTrue(all('-long-90m-' in rid for rid in records))

    def test_cli_ingests_real_workflow_environment(self):
        self.plan([self.names[0]])
        self.revision(self.names[0])
        env = {**os.environ, 'EVENT_NAME': 'workflow_run', 'SOURCE_RUN_ID': '123',
               'SOURCE_ATTEMPT': '2', 'SOURCE_CONCLUSION': 'success'}
        subprocess.run([sys.executable, str(DASHBOARD / 'ingest.py'), '--input', str(self.input),
                        '--history', str(self.history), '--output', str(self.root / 'site')],
                       env=env, check=True, capture_output=True)
        self.assertEqual(len(json.loads((self.root / 'site/history.json').read_text())), 7)


if __name__ == '__main__':
    unittest.main()
