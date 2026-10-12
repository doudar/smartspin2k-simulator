"""Select develop once, then carry its immutable identity through an experiment."""
import argparse
from contextlib import contextmanager
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REPOSITORY = 'https://github.com/doudar/SmartSpin2k.git'
REF = 'refs/heads/develop'
ENV = 'SS2K_BASELINE_SELECTION'


def validate(selection):
    if not re.fullmatch(r'[0-9a-f]{40}', selection.get('commit', '')):
        raise ValueError('Baseline selection requires an exact 40-character commit')
    if selection.get('mode') not in ('develop', 'replay'):
        raise ValueError('Baseline selection mode must be develop or explicit replay')
    if selection.get('repository') != REPOSITORY or (selection['mode'] == 'develop' and selection.get('ref') != REF):
        raise ValueError('New baselines must come from SmartSpin2k develop')
    return selection


def resolve(replay_sha=None):
    if replay_sha is None:
        # Never use a cached tracking branch, a release tag, or a stale fallback.
        output = subprocess.check_output(['git', 'ls-remote', '--exit-code', REPOSITORY, REF], text=True, timeout=60)
        rows = [line.split() for line in output.splitlines()]
        if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != REF:
            raise ValueError('Could not uniquely resolve remote develop')
        commit = rows[0][0]
    else:
        commit = replay_sha
    return validate({'repository': REPOSITORY, 'ref': REF if replay_sha is None else None,
                     'commit': commit, 'mode': 'develop' if replay_sha is None else 'replay',
                     'resolved_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})


def arguments(parser):
    parser.add_argument('--baseline-selection', type=Path, help='Selection JSON resolved once by the enclosing experiment')
    parser.add_argument('--baseline-mode', choices=('develop', 'replay'), default='develop')
    parser.add_argument('--baseline-sha', help='Exact archived baseline; requires --baseline-mode replay')


def select(args=None):
    path = getattr(args, 'baseline_selection', None) or os.environ.get(ENV)
    replay = getattr(args, 'baseline_mode', 'develop') == 'replay'
    sha = getattr(args, 'baseline_sha', None)
    if path:
        if replay or sha:
            raise ValueError('Selection file cannot be combined with baseline overrides')
        return validate(json.loads(Path(path).read_text()))
    if replay != bool(sha):
        raise ValueError('--baseline-sha requires --baseline-mode replay and vice versa')
    return resolve(sha)


def establish(path):
    """Outer wrapper: resolve once before any matrix/training work, or reuse parent pin."""
    selection = select()
    path = Path(path).resolve()
    if path.exists():
        raise FileExistsError('Choose a new baseline selection file; prior selections are immutable')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection, indent=2)+'\n')
    os.environ[ENV] = str(path)
    return selection


@contextmanager
def pinned_root(root, selection):
    """Build from a detached worktree even if the supplied checkout changes later."""
    root = Path(root).resolve()
    sha = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True).strip()
    if sha != selection['commit'] or dirty:
        raise ValueError('Baseline must be a clean checkout at resolved '+selection['mode']+' commit '+selection['commit'])
    with tempfile.TemporaryDirectory(prefix='ss2k-baseline-') as temp:
        destination = Path(temp)/'source'
        # A local clone leaves source Git administration read-only, including in
        # the sandbox used to compile untrusted PR firmware. No network fetch.
        subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', '--no-checkout', str(root), str(destination)], check=True)
        subprocess.run(['git', '-C', str(destination), 'checkout', '--quiet', '--detach', selection['commit']], check=True)
        yield destination


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--replay-sha')
    p.add_argument('--github-output', action='store_true')
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError('Refusing to overwrite an existing baseline selection')
    selection = resolve(a.replay_sha)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(selection, indent=2)+'\n')
    if a.github_output:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('sha='+selection['commit']+'\n')
    print(selection['commit'])


if __name__ == '__main__':
    main()
