import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ss2k_sim import baseline
from ss2k_sim.cli import parser

SHA = 'a'*40
NEXT = 'b'*40


class BaselineTests(unittest.TestCase):
    def test_remote_develop_not_release_or_cached_branch(self):
        with patch.object(baseline.subprocess, 'check_output', return_value=SHA+'\trefs/heads/develop\n') as git:
            selection = baseline.resolve()
        self.assertEqual(selection['commit'], SHA)
        self.assertEqual(selection['mode'], 'develop')
        self.assertEqual(git.call_args.args[0], ['git', 'ls-remote', '--exit-code', baseline.REPOSITORY, baseline.REF])

    def test_resolution_failure_has_no_stale_fallback(self):
        with patch.object(baseline.subprocess, 'check_output', side_effect=subprocess.CalledProcessError(2, 'git')):
            with self.assertRaises(subprocess.CalledProcessError): baseline.resolve()
        for bad in ('', SHA+'\trefs/tags/latest\n', 'invalid\trefs/heads/develop\n'):
            with patch.object(baseline.subprocess, 'check_output', return_value=bad):
                with self.assertRaises(ValueError): baseline.resolve()

    def test_matrix_pin_survives_moving_remote_resolved_once(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            with patch.object(baseline.subprocess, 'check_output', side_effect=[SHA+'\t'+baseline.REF, NEXT+'\t'+baseline.REF]) as git:
                first = baseline.establish(Path(temp)/'selection.json')
                # Training and every short/long/historical subprocess see the same file.
                for _ in range(15):
                    self.assertEqual(baseline.select(), first)
                self.assertEqual(git.call_count, 1)
                self.assertEqual(baseline.resolve()['commit'], NEXT)
                self.assertEqual(baseline.select()['commit'], SHA)

    def test_replay_is_deliberate_labeled_and_does_not_lookup_develop(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(baseline, 'resolve', wraps=baseline.resolve) as resolver:
            args=argparse.Namespace(baseline_mode='replay', baseline_sha=SHA)
            self.assertEqual(baseline.select(args)['mode'], 'replay')
            resolver.assert_called_once_with(SHA)
            args.baseline_mode='develop'
            with self.assertRaises(ValueError): baseline.select(args)
            args.baseline_mode='replay'; args.baseline_sha=None
            with self.assertRaises(ValueError): baseline.select(args)

    def test_selection_and_manual_override_conflict_fails(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            path=Path(temp)/'pin.json';path.write_text(json.dumps(baseline.resolve(SHA)))
            os.environ[baseline.ENV]=str(path)
            with self.assertRaises(ValueError): baseline.select(argparse.Namespace(baseline_sha=NEXT))
            self.assertEqual(baseline.select()['commit'], SHA)

    def test_defaults_have_no_static_sha(self):
        a=parser().parse_args(['compare','--firmware-root','a','--candidate-root','c','--baseline-root','b','--output','o'])
        self.assertIsNone(a.baseline_sha)
        self.assertEqual(a.baseline_mode, 'develop')

    def test_frozen_baseline_ignores_supplied_branch_movement(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'repo';root.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
            git('init','-q');git('config','user.email','test@example.com');git('config','user.name','Test')
            (root/'file').write_text('first');git('add','file');git('commit','-qm','first')
            first=git('rev-parse','HEAD')
            with baseline.pinned_root(root, baseline.resolve(first)) as frozen:
                (root/'file').write_text('second');git('commit','-qam','second')
                self.assertEqual((frozen/'file').read_text(),'first')
                self.assertNotEqual(git('rev-parse','HEAD'), first)
                self.assertEqual(subprocess.check_output(['git','-C',str(frozen),'rev-parse','HEAD'],text=True).strip(), first)
            self.assertFalse(frozen.exists())
            with self.assertRaises(ValueError):
                with baseline.pinned_root(root, baseline.resolve(first)): pass

    def test_long_training_and_compare_share_one_pin(self):
        import importlib.util
        from contextlib import contextmanager
        spec=importlib.util.spec_from_file_location('baseline_long_wrapper', Path(__file__).parents[1]/'dashboard/longride_experiment.py')
        wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
        @contextmanager
        def frozen(root, selection):
            self.assertEqual(selection['commit'], SHA)
            yield Path('frozen-baseline')
        seen=[]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            output=Path(temp)/'result'
            def child(cmd):
                seen.append(baseline.select())
                if 'train' in cmd:
                    fixture=output/'training';fixture.mkdir();(fixture/'full.json').write_text('{}')
                else:
                    self.assertEqual(cmd[cmd.index('--baseline-root')+1], 'frozen-baseline')
                return 0
            # Resolve once. If the outer runner or child re-resolves, NEXT would leak.
            with patch.object(baseline, 'resolve', side_effect=[{'commit':SHA,'mode':'develop','repository':baseline.REPOSITORY,'ref':baseline.REF}, {'commit':NEXT}]) as resolver, patch.object(baseline, 'pinned_root', frozen), patch.object(wrapper, 'sha', return_value=NEXT), patch.object(wrapper.subprocess, 'check_output', return_value='compiler'), patch.object(wrapper.subprocess, 'call', side_effect=child):
                self.assertEqual(wrapper.main(['--output',str(output)]),0)
                self.assertEqual(resolver.call_count,1)
            self.assertEqual([x['commit'] for x in seen],[SHA,SHA])
            self.assertEqual(json.loads((output/'paired/run-metadata.json').read_text())['baseline_selection']['commit'],SHA)
            self.assertNotIn(baseline.ENV,os.environ)
