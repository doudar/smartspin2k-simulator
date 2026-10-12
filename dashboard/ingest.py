#!/usr/bin/env python3
"""Workflow-event ingestion. Inputs affect data only, never a code checkout."""
import argparse
import csv
import datetime
import hashlib
import json
import os
import tempfile
from pathlib import Path

from build import (MAX_FILE, SAFE, build, collect, materialize, read_json, valid_tree,
                   validate, validate_evidence_location, validate_metadata)
from longride_import import prepare

MAX_REVISION_GROUPS = 4
MAX_RECORDS = 40
ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError,
          OSError, RecursionError, csv.Error)
SPRINT_CASES = [dict(minutes=90, initial_state=state, sensitivity=sensitivity, seed=7)
                for state in ('empty', 'full') for sensitivity in (3, 5, 10)]


def present(path):
    """A dangling symlink is an invalid input, not an absent input."""
    return path.exists() or path.is_symlink()


def check_root(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Symlink evidence root')
    if path.exists() and not path.is_dir():
        raise ValueError('Evidence root is not a directory')


def run_id(identity, suffix=''):
    if not suffix:
        return identity
    result = identity + '-' + suffix
    if SAFE.fullmatch(result):
        return result
    # Preserve deterministic, bounded identities even for unsafe/oversized names.
    result = identity + '-sha256-' + hashlib.sha256(suffix.encode()).hexdigest()[:24]
    if not SAFE.fullmatch(result):
        raise ValueError('Workflow identity leaves no room for a record ID')
    return result


def rejected(stage, name, message, metadata=None):
    dest = stage / name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'comparison.json').write_text(json.dumps({
        'status': 'incomplete', 'passed': False, 'runs': [], 'error': message,
    }))
    if metadata:
        (dest / 'run-metadata.json').write_text(json.dumps(metadata))
    return dest


def available_metadata(root):
    """Retain validated provenance on failed batches without trusting bad fields."""
    try:
        return validate_metadata(read_json(root / 'run-metadata.json'))
    except ERRORS:
        return {}


def cache_metadata(group):
    path = group / 'cache-state.json'
    if not present(path):
        return {}
    value = read_json(path)
    valid_tree(value)
    if not isinstance(value, dict) or type(value.get('reused')) is not bool:
        raise ValueError('Invalid cache provenance')
    if not isinstance(value.get('cache_key'), str):
        raise ValueError('Invalid cache key')
    for field in ('source_run_id', 'source_attempt'):
        source = value.get(field)
        if source is not None and (not isinstance(source, str) or not source.isdigit()):
            raise ValueError('Invalid cache source identity')
    return value


def revision_sources(root, stage, identity, names, suite='both'):
    """Flatten each revision independently, so one bad subgroup cannot hide peers."""
    if len(names) > MAX_REVISION_GROUPS:
        raise ValueError('Revision batch too large')
    result = []
    kinds = ('short', 'long') if suite == 'both' else (suite,)
    for index, name in enumerate(names):
        group = root / name
        prefix = run_id(identity, name)
        if len(prefix) > 60:
            prefix = run_id(identity, 'revision-' + hashlib.sha256(name.encode()).hexdigest()[:16])
        work = stage / str(index)
        try:
            if not SAFE.fullmatch(name):
                raise ValueError('Unsafe revision path')
            check_root(group)
            cache = cache_metadata(group)
        except ERRORS as exc:
            for kind in kinds:
                source = rejected(work, kind, f'Revision validation rejected this payload: {type(exc).__name__}. Raw payload was not published.')
                result.append((source, run_id(prefix, kind), {}))
            continue
        if 'short' in kinds:
            short = group / 'short'
            result.append((short, run_id(prefix, 'short'), cache))
        if 'long' not in kinds:
            continue
        long = group / 'long'
        try:
            check_root(long)
            sources = prepare(long, work / 'long', prefix, missing_cases=SPRINT_CASES)
            # Reserve one placeholder for every remaining short and long subgroup.
            remaining = (len(names) - index - 1) * len(kinds)
            if len(result) + len(sources) > MAX_RECORDS - remaining:
                raise ValueError('Experiment batch too large')
        except ERRORS as exc:
            source = rejected(work, 'long-incomplete', f'Long-ride batch validation failed: {type(exc).__name__}. Unsafe payload was not published; inspect the Actions artifact.', available_metadata(long))
            sources = [source]
        for source in sources:
            result.append((source, run_id(prefix, source.name), cache))
    return result


def evidence_sources(root, stage, identity):
    """Accept legacy evidence and the bounded revision/{short,long} layout."""
    check_root(root)
    plan = root / 'experiment-plan.json'
    names = None
    suite = 'both'
    if present(plan):
        value = read_json(plan)
        valid_tree(value)
        if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
            raise ValueError('Invalid experiment plan')
        suite = value.get('suite', 'both')
        if suite not in ('both', 'short', 'long'):
            raise ValueError('Invalid experiment suite')
        versions = value.get('versions')
        if not isinstance(versions, list) or not 1 <= len(versions) <= MAX_REVISION_GROUPS:
            raise ValueError('Invalid revision plan size')
        names = []
        for version in versions:
            name = version.get('id') if isinstance(version, dict) else None
            if not isinstance(name, str) or not SAFE.fullmatch(name) or name in names:
                raise ValueError('Invalid revision identity')
            names.append(name)
    if names is None:
        names = sorted(path.name for path in root.iterdir()
                       if path.is_dir() and any(present(path / kind) for kind in ('short', 'long')))
    if names:
        return revision_sources(root, stage, identity, names, suite)
    prepared = prepare(root, stage, identity)
    if prepared is not None:
        return [(source, run_id(identity, source.name), {}) for source in prepared]
    # Legacy release matrix: only direct comparison/metadata children are evidence.
    children = sorted(path for path in root.iterdir() if path.is_dir() and
                      any(present(path / name) for name in ('comparison.json', 'run-metadata.json')))
    sources = children if children and not present(root / 'comparison.json') else [root]
    if len(sources) > MAX_RECORDS:
        raise ValueError('Experiment batch too large')
    return [(source, run_id(identity, source.name if source != root else ''), {}) for source in sources]


def import_metadata(source, base_metadata, cache):
    path = source / 'run-metadata.json'
    metadata = validate_metadata(read_json(path)) if present(path) else {}
    # Cached evidence keeps its actual execution time and original workflow URL.
    # The importing workflow has a separate provenance record, never a new run date.
    if cache:
        metadata['cache'] = cache
        metadata['ingestion'] = dict(base_metadata)
        if cache['reused']:
            origin = cache.get('source_run_id')
            if origin:
                metadata.setdefault('workflow_url', f'https://github.com/doudar/smartspin2k-simulator/actions/runs/{origin}')
            metadata['notes'] = (metadata.get('notes') or '') + ' Reused cached evidence' + (f' from Actions run {origin}' if origin else '') + '; original execution timestamps and provenance are retained.'
    for key, value in base_metadata.items():
        if cache.get('reused') and key in ('workflow_conclusion', 'workflow_updated_at'):
            continue
        metadata.setdefault(key, value)
    if present(source / 'adapter-provenance.json') and not metadata.get('runtime_toolchain'):
        metadata['notes'] = (metadata.get('notes') or '') + ' Runtime toolchain was not recorded for this cloud run. Any toolchain in adapter-provenance.json describes original local validation only; the initial-state audit is linked from the repository compatibility directory.'
    return metadata


# Import-time decoration is not execution evidence. All other metadata, the full
# comparison (including firmware/configuration and case identity), and every raw
# evidence file must match before a cached import can reference an older record.
IMPORT_METADATA = {'cache', 'ingestion', 'imported_at', 'notes', 'training_run_id',
                   'workflow_url', 'workflow_conclusion', 'workflow_updated_at'}


def cache_fingerprint(metadata, comparison, checksums):
    cache = metadata.get('cache', {})
    if not isinstance(cache, dict) or type(cache.get('reused')) is not bool:
        return None
    origin = tuple(cache.get(field) for field in ('cache_key', 'source_run_id', 'source_attempt'))
    if not all(isinstance(value, str) and value for value in origin):
        return None
    if not all(value.isdigit() for value in origin[1:]):
        return None
    validate(comparison)
    if comparison['status'] != 'complete' or comparison.get('batch_status', 'complete') != 'complete':
        return None
    training = metadata.get('evidence_only') is True
    if training:
        fixture = comparison.get('training')
        if not isinstance(fixture, dict) or fixture.get('full_fixture_created') is not True:
            return None
    elif type(comparison.get('passed')) is not bool or not comparison.get('runs'):
        return None
    # A role is independent of the importing Actions run ID. Full comparisons
    # also distinguish scenario, seed, duration, initial state and sensitivity.
    role = 'training' if training else comparison.get('experiment', 'short')
    provenance = {key: value for key, value in metadata.items() if key not in IMPORT_METADATA}
    files = {name: digest for name, digest in checksums.items() if name != 'run-metadata.json'}
    payload = [origin, role, provenance, comparison, files]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def archived_cache_records(history):
    """Index only verified complete records; never modify existing archives."""
    result = {}
    for record in sorted(history.iterdir()) if history.exists() else []:
        try:
            if not record.is_dir() or not SAFE.fullmatch(record.name):
                continue
            check_root(record)
            data = read_json(record / 'data.json')
            valid_tree(data)
            if data['id'] != record.name:
                continue
            metadata = validate_metadata(data['metadata'])
            sums = record / 'SHA256SUMS.txt'
            if sums.is_symlink() or sums.stat().st_size > MAX_FILE:
                continue
            checksums = {}
            for line in sums.read_text().splitlines():
                digest, separator, name = line.partition('  ')
                if (not separator or len(digest) != 64 or
                        any(char not in '0123456789abcdef' for char in digest) or
                        not name or name in checksums or
                        any(not SAFE.fullmatch(part) for part in name.split('/'))):
                    raise ValueError('Invalid archived evidence checksums')
                checksums[name] = digest
            archive = record / 'evidence.zip'
            if 'comparison.json' not in checksums or archive.is_symlink():
                continue
            pointer = record / 'evidence-location.json'
            if present(pointer):
                validate_evidence_location(read_json(pointer), record.name)
            elif not archive.is_file():
                continue
            training_id = metadata.get('training_run_id')
            if training_id and (not SAFE.fullmatch(training_id) or
                                not (history / training_id / 'data.json').is_file()):
                continue
            fingerprint = cache_fingerprint(metadata, data['comparison'], checksums)
            if fingerprint:
                result.setdefault(fingerprint, record.name)
        except ERRORS:
            # A malformed old record cannot suppress new evidence. The normal
            # dashboard build still validates and reports any damaged history.
            continue
    return result


def cached_record(source, metadata, archived):
    if not metadata.get('cache', {}).get('reused') or not archived:
        return None
    files = collect(source)
    if 'comparison.json' not in files:
        return None
    comparison = json.loads(files['comparison.json'])
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    return archived.get(cache_fingerprint(metadata, comparison, checksums))


def ingest(root, history, identity, base_metadata):
    if not SAFE.fullmatch(identity):
        raise ValueError('Invalid workflow identity')
    archived = archived_cache_records(history)
    training_aliases = {}
    with tempfile.TemporaryDirectory(prefix='longride-evidence-') as temporary:
        stage = Path(temporary)
        try:
            check_root(root)
            root.mkdir(parents=True, exist_ok=True)
            sources = evidence_sources(root, stage / 'prepared', identity)
            if len(sources) > MAX_RECORDS:
                raise ValueError('Experiment batch too large')
        except ERRORS as exc:
            source = rejected(stage, 'batch-incomplete', f'Evidence batch validation failed: {type(exc).__name__}. Unsafe payload was not published; inspect the Actions artifact.')
            sources = [(source, run_id(identity, 'batch-incomplete'), {})]
        for index, (source, rid, cache) in enumerate(sources):
            if (history / rid).exists():
                continue
            try:
                check_root(source)
                metadata = import_metadata(source, base_metadata, cache)
                original = cached_record(source, metadata, archived)
                if original:
                    if metadata.get('evidence_only') is True:
                        training_aliases[rid] = original
                    continue
                training_id = metadata.get('training_run_id')
                if training_id in training_aliases:
                    metadata['training_run_id'] = training_aliases[training_id]
                    # Only prepared, generated metadata may be rewritten; raw
                    # input and all previously archived evidence stay immutable.
                    if stage in source.parents:
                        path = source / 'run-metadata.json'
                        prepared_metadata = validate_metadata(read_json(path))
                        prepared_metadata['training_run_id'] = metadata['training_run_id']
                        path.write_text(json.dumps(prepared_metadata, allow_nan=False))
                materialize(source, history / rid, rid, metadata)
            except ERRORS as exc:
                safe = rejected(stage / 'rejected', str(index), f'Evidence validation rejected this payload: {type(exc).__name__}. Raw payload was not published.', available_metadata(source))
                metadata = import_metadata(safe, base_metadata, cache)
                metadata['notes'] = (metadata.get('notes') or '') + ' Original artifact remains available in Actions subject to retention.'
                materialize(safe, history / rid, rid, metadata)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    if os.getenv('EVENT_NAME') == 'workflow_run':
        source_run = os.environ['SOURCE_RUN_ID']
        attempt = os.environ['SOURCE_ATTEMPT']
        if not source_run.isdigit() or not attempt.isdigit():
            raise ValueError('Invalid workflow identity')
        identity = f'actions-{source_run}-{attempt}'
        metadata = {
            'workflow_url': f'https://github.com/doudar/smartspin2k-simulator/actions/runs/{source_run}',
            'workflow_conclusion': os.getenv('SOURCE_CONCLUSION'),
            'workflow_updated_at': os.getenv('SOURCE_DATE'),
            'imported_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        ingest(args.input, args.history, identity, metadata)
    build(args.history, args.output)


if __name__ == '__main__':
    main()
