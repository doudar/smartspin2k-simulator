"""Resolve the newest published stable firmware releases to immutable commits.

The API's order is not publication order, so collect every page before sorting.
Only the resulting commit SHAs should be used for downstream source checkouts.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request


REPOSITORY = 'https://github.com/doudar/SmartSpin2k.git'
API_URL = 'https://api.github.com/repos/doudar/SmartSpin2k/releases'
MAX_COUNT = 10
PAGE_SIZE = 100
MAX_PAGES = 1000
TIMEOUT = 30


class ReleaseResolutionError(ValueError):
    """No trustworthy release selection could be established."""


def _count(value):
    if type(value) is not int or not 1 <= value <= MAX_COUNT:
        raise ReleaseResolutionError(f'Release count must be between 1 and {MAX_COUNT}')
    return value


def _timestamp(value, field):
    if not isinstance(value, str) or not re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value
    ):
        raise ReleaseResolutionError(f'{field} must be an ISO timestamp with a timezone')
    try:
        return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ReleaseResolutionError(f'{field} is not a valid timestamp') from None


def _tag(value):
    # These are git ref constraints, not shell escaping. Commands always use argv.
    if (not isinstance(value, str) or not value or len(value) > 1024
            or re.search(r'[\x00-\x20\x7f~^:?*\[\\]', value)
            or '..' in value or '@{' in value or value.endswith('.')
            or any(not part or part.startswith('.') or part.endswith('.lock')
                   for part in value.split('/'))):
        raise ReleaseResolutionError('Release tag is missing or is not a valid git ref')
    return value


def _commit(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ReleaseResolutionError('Release commit must be an exact 40-character lowercase SHA')
    return value


def fetch_releases():
    """Read all pages without following API-supplied URLs or exposing the token."""
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'smartspin2k-simulator-release-resolver',
    }
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    releases = []
    for page in range(1, MAX_PAGES + 1):
        request = urllib.request.Request(
            f'{API_URL}?per_page={PAGE_SIZE}&page={page}', headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.load(response)
                link = response.headers.get('Link', '')
        except urllib.error.HTTPError as error:
            raise ReleaseResolutionError(f'GitHub release API returned HTTP {error.code}') from None
        except (urllib.error.URLError, OSError, ValueError):
            raise ReleaseResolutionError('Could not read valid release JSON from GitHub') from None
        if not isinstance(payload, list) or len(payload) > PAGE_SIZE:
            raise ReleaseResolutionError('GitHub release API must return a list of releases')
        releases.extend(payload)
        # GitHub uses sequential pages. Build the next URL ourselves so an
        # untrusted Link header cannot send GITHUB_TOKEN to another destination.
        has_next = bool(re.search(r'\brel\s*=\s*"next"', link))
        if not has_next and len(payload) < PAGE_SIZE:
            return releases
        if not payload:
            raise ReleaseResolutionError('GitHub release pagination returned an empty non-final page')
    raise ReleaseResolutionError('GitHub release pagination exceeded its safety limit')


def resolve_tag(tag):
    """Resolve lightweight or annotated tags; never use target_commitish."""
    ref = 'refs/tags/' + _tag(tag)
    try:
        output = subprocess.check_output(
            ['git', 'ls-remote', '--exit-code', '--tags', REPOSITORY, ref, ref + '^{}'],
            text=True, stderr=subprocess.PIPE, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        raise ReleaseResolutionError(f'Could not resolve release tag {tag!r}') from None
    refs = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[1] not in (ref, ref + '^{}') or fields[1] in refs:
            raise ReleaseResolutionError(f'Ambiguous or malformed resolution for release tag {tag!r}')
        refs[fields[1]] = _commit(fields[0])
    if ref not in refs:
        raise ReleaseResolutionError(f'Release tag {tag!r} was not found')
    return refs.get(ref + '^{}', refs[ref])


def validate(selection, count=None):
    """Validate an archived selection without re-resolving its moving tags."""
    if not isinstance(selection, dict):
        raise ReleaseResolutionError('Release selection must be a JSON object')
    if type(selection.get('schema_version')) is not int or selection['schema_version'] != 1:
        raise ReleaseResolutionError('Unsupported release selection schema_version')
    if selection.get('repository') != REPOSITORY:
        raise ReleaseResolutionError('Release selection must come from SmartSpin2k')
    _timestamp(selection.get('resolved_at'), 'resolved_at')
    rows = selection.get('releases')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_COUNT:
        raise ReleaseResolutionError('Release selection has an invalid number of releases')
    if count is not None and len(rows) != _count(count):
        raise ReleaseResolutionError(f'Release selection requires exactly {count} releases')
    commits, tags = set(), set()
    previous = None
    for row in rows:
        if not isinstance(row, dict):
            raise ReleaseResolutionError('Each selected release must be an object')
        tag, commit = _tag(row.get('tag')), _commit(row.get('commit'))
        published = _timestamp(row.get('published_at'), 'published_at')
        if commit in commits or tag in tags:
            raise ReleaseResolutionError('Selected releases must have unique tags and commits')
        if previous is not None and published > previous:
            raise ReleaseResolutionError('Selected releases must be sorted by publication time')
        previous = published
        commits.add(commit)
        tags.add(tag)
    return selection


def resolve_releases(count=3):
    """Select the newest ``count`` stable releases with distinct immutable SHAs.

    An invalid release, missing tag, API failure, or insufficient history fails
    explicitly. There is no cached selection or hard-coded tag fallback.
    """
    _count(count)
    candidates = []
    for release in fetch_releases():
        if not isinstance(release, dict):
            raise ReleaseResolutionError('Each GitHub release must be an object')
        if type(release.get('draft')) is not bool or type(release.get('prerelease')) is not bool:
            raise ReleaseResolutionError('GitHub release is missing valid draft/prerelease flags')
        if release['draft'] or release['prerelease']:
            continue
        if 'published_at' not in release:
            raise ReleaseResolutionError('Stable release is missing published_at')
        if release['published_at'] is None:
            continue
        published = _timestamp(release['published_at'], 'published_at')
        candidates.append((published, _tag(release.get('tag_name')), release['published_at']))
    candidates.sort(reverse=True)
    selected, commits, resolved = [], set(), {}
    for _, tag, published_at in candidates:
        if tag not in resolved:
            resolved[tag] = _commit(resolve_tag(tag))
        commit = resolved[tag]
        if commit in commits:
            continue
        selected.append({'tag': tag, 'commit': commit, 'published_at': published_at})
        commits.add(commit)
        if len(selected) == count:
            break
    if len(selected) < count:
        raise ReleaseResolutionError(
            f'Need {count} distinct published stable release commits; found {len(selected)}'
        )
    return validate({
        'schema_version': 1,
        'repository': REPOSITORY,
        'resolved_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'releases': selected,
    }, count=count)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=3, help=f'Number of unique releases (1–{MAX_COUNT}; default: 3)')
    parser.add_argument('--github-output', action='store_true', help='Append a compact matrix to GITHUB_OUTPUT')
    args = parser.parse_args(argv)
    try:
        _count(args.count)
        if args.output.exists():
            raise ReleaseResolutionError('Refusing to overwrite an existing release selection')
        github_output = os.environ.get('GITHUB_OUTPUT') if args.github_output else None
        if args.github_output and not github_output:
            raise ReleaseResolutionError('--github-output requires GITHUB_OUTPUT')
        selection = resolve_releases(args.count)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(selection, indent=2) + '\n')
        if github_output:
            matrix = json.dumps({'include': selection['releases']}, separators=(',', ':'))
            with open(github_output, 'a', encoding='utf-8') as stream:
                stream.write('matrix=' + matrix + '\n')
    except (ReleaseResolutionError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(selection, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    main()
