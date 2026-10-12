"""Accelerated firmware-boundary experiments with an independent physical plant."""
import argparse
import hashlib
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .adapter import load_adapter, source_provenance, file_fingerprint
from .model import BikeConfig
from .performance import summarize, compare, DEFAULT_BUDGET
from .runner import run
from .scenarios import scenarios

BASELINE_SHA = '082d1ee26ddb009d5132547087f77be03d1b0ab7'
PACKAGE = Path(__file__).resolve().parent


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('compare', 'run', 'check-adapter'):
        q = sub.add_parser(command)
        q.add_argument('--firmware-root', type=Path, required=True, help='Trusted checkout containing the native adapter; same adapter for all builds')
        q.add_argument('--adapter-sha256', help='Reject a mismatched immutable adapter fingerprint')
        if command == 'check-adapter':
            continue
        q.add_argument('--candidate-root', type=Path, required=True)
        q.add_argument('--output', type=Path, required=True)
        q.add_argument('--profile', type=Path, default=PACKAGE/'profiles/ride_20260927.json')
        q.add_argument('--seeds', type=int, nargs='+', default=[7])
        q.add_argument('--scenario', action='append', help='Run named subset; default full matrix')
        if command == 'compare':
            q.add_argument('--baseline-root', type=Path, required=True)
            q.add_argument('--baseline-sha', default=BASELINE_SHA, help='Exact expected baseline commit; clean checkout required')
    return p


def execute(args):
    adapter, adapter_info = load_adapter(args.firmware_root, args.adapter_sha256)
    if args.command == 'check-adapter':
        print(json.dumps(adapter_info, indent=2))
        return 0
    selected = [s for s in scenarios() if not args.scenario or s[0] in args.scenario]
    if not selected or args.scenario and set(args.scenario)-{s[0] for s in selected}:
        raise ValueError('Unknown scenario; choose '+', '.join(s[0] for s in scenarios()))
    roots = {'candidate': args.candidate_root.resolve()}
    if args.command == 'compare':
        roots = {'baseline': args.baseline_root.resolve(), **roots}
    provenance = {name: source_provenance(root) for name, root in roots.items()}
    if args.command == 'compare' and (provenance['baseline']['commit'] != args.baseline_sha or provenance['baseline']['dirty']):
        raise ValueError('Baseline must be a clean checkout at exact commit '+args.baseline_sha)
    profile = json.loads(args.profile.read_text())
    config = BikeConfig(**profile['bike'])
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError('Choose a new empty output directory to preserve prior evidence')
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'status': 'incomplete', 'passed': False,
        'coverage_level': 'Production BLE packet decode/collect + FTMS procedure + ERG + virtual motor; no radio, ESP32 scheduler or physical hardware',
        'firmware': provenance, 'adapter': adapter_info,
        'simulator_sha256': file_fingerprint(PACKAGE, [p for p in PACKAGE.rglob('*') if p.is_file() and '__pycache__' not in p.parts]),
        'profile_sha256': file_fingerprint(args.profile.parent, [args.profile]),
        'package_config_sha256': hashlib.sha256((PACKAGE.parent/'pyproject.toml').read_bytes()).hexdigest() if (PACKAGE.parent/'pyproject.toml').is_file() else None,
        'bike': asdict(config), 'seeds': args.seeds, 'absolute_budgets': DEFAULT_BUDGET,
        'budget_status': 'Provisional engineering budgets, not calibrated acceptance or hardware fidelity proof',
        'scenarios': [{'name': name, 'segments': [asdict(segment) for segment in workout.segments],
            'workout_sha256': hashlib.sha256(json.dumps([asdict(segment) for segment in workout.segments], sort_keys=True).encode()).hexdigest(),
            'power_schedule': power.to_dict(), 'cadence_schedule': cadence.to_dict()} for name, workout, power, cadence in selected],
        'runs': []}
    try:
        executables = {name: adapter.build(args.output/name/'build', source_root=root, packet_ingress=True) for name, root in roots.items()}
        for name, workout, power, cadence in selected:
            for seed in args.seeds:
                scores = {}
                for variant in roots:
                    output = args.output/variant/f'{name}-{seed}'
                    trace, metadata = run(workout, config, executables[variant], output,
                        seed=seed, initial_position=profile.get('start_position', 7433),
                        power_schedule=power, cadence_schedule=cadence,
                        packet_ingress=True, bridge_factory=adapter.Bridge)
                    scores[variant] = summarize(trace, workout.duration, workout)
                    reported_trace = trace.copy(); reported_trace[:, 2] = trace[:, 14]
                    scores[variant]['delivered_sensor_metrics'] = summarize(reported_trace, workout.duration, workout)
                    (output/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
                    (output/'score.json').write_text(json.dumps(scores[variant], indent=2)+'\n')
                result = compare(scores['candidate'], scores['baseline']) if 'baseline' in scores else {'passed': None, 'note': 'Single diagnostic run; no paired acceptance decision'}
                if 'baseline' in scores:
                    reported = compare(scores['candidate']['delivered_sensor_metrics'], scores['baseline']['delivered_sensor_metrics'])
                    result['reported_power_comparison'] = reported
                    result['passed'] = result['passed'] and reported['passed']
                    result['failures'] += ['delivered sensor: '+f for f in reported['failures']]
                row = {'scenario': name, 'seed': seed, 'scores': scores,
                       'power': power.to_dict(), 'cadence': cadence.to_dict(), **result}
                manifest['runs'].append(row)
                print(f"{name} seed={seed}: "+('PASS' if result['passed'] else 'FAIL' if result['passed'] is False else 'UNPAIRED'), flush=True)
        manifest['status'] = 'complete'
        manifest['passed'] = all(row['passed'] for row in manifest['runs']) if args.command == 'compare' else None
        return 1 if manifest['passed'] is False else 0
    except BaseException as exc:
        manifest['status'] = 'failed'
        manifest['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        (args.output/'comparison.json').write_text(json.dumps(manifest, indent=2)+'\n')


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return execute(args)
    except (Exception, KeyboardInterrupt) as exc:
        print(f'SIMULATOR FAILED: {exc}', file=sys.stderr)
        return 2
