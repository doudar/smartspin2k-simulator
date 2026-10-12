import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from ss2k_sim import releases


SHA_A, SHA_B, SHA_C, SHA_D = (character * 40 for character in 'abcd')


def release(tag='v-new', published='2026-03-01T12:00:00Z', **overrides):
    return {'tag_name': tag, 'published_at': published, 'draft': False,
            'prerelease': False, 'target_commitish': 'moving-main', **overrides}


def response(payload, link=''):
    result = io.BytesIO(json.dumps(payload).encode())
    result.headers = {'Link': link}
    return result


def selection():
    return {'schema_version': 1, 'repository': releases.REPOSITORY,
            'resolved_at': '2026-04-01T00:00:00+00:00', 'releases': [
                {'tag': 'v-new', 'commit': SHA_A, 'published_at': '2026-03-01T12:00:00Z'},
                {'tag': 'v-middle', 'commit': SHA_B, 'published_at': '2026-02-01T12:00:00Z'},
                {'tag': 'v-old', 'commit': SHA_C, 'published_at': '2026-01-01T12:00:00Z'},
            ]}


class ReleaseTests(unittest.TestCase):
    def test_filters_and_sorts_by_publication_not_api_order_or_target(self):
        rows = [release('v-old', '2026-01-01T12:00:00Z'),
                release('v-pre', '2026-05-01T12:00:00Z', prerelease=True),
                release('v-new'),
                release('v-draft', '2026-05-01T12:00:00Z', draft=True),
                release('v-middle', '2026-02-01T12:00:00Z'),
                release('v-unpublished', None)]
        with patch.object(releases, 'fetch_releases', return_value=rows), \
                patch.object(releases, 'resolve_tag', side_effect=[SHA_A, SHA_B, SHA_C]) as resolve:
            result = releases.resolve_releases()
        self.assertEqual(result['releases'], selection()['releases'])
        self.assertEqual([call.args[0] for call in resolve.call_args_list], ['v-new', 'v-middle', 'v-old'])
        self.assertIs(releases.validate(result, count=3), result)

    def test_sort_uses_timezone_aware_instants(self):
        rows = [release('v-older', '2026-03-01T15:00:00+04:00'), release('v-new')]
        with patch.object(releases, 'fetch_releases', return_value=rows), \
                patch.object(releases, 'resolve_tag', return_value=SHA_A):
            self.assertEqual(releases.resolve_releases(1)['releases'][0]['tag'], 'v-new')

    def test_duplicate_commits_and_tags_are_skipped_without_resolving_twice(self):
        rows = [release(), release(), release('v-same', '2026-02-20T00:00:00Z'),
                release('v-middle', '2026-02-01T12:00:00Z'), release('v-old', '2026-01-01T12:00:00Z')]
        with patch.object(releases, 'fetch_releases', return_value=rows), \
                patch.object(releases, 'resolve_tag', side_effect=[SHA_A, SHA_A, SHA_B, SHA_C]) as resolve:
            result = releases.resolve_releases()
        self.assertEqual(result['releases'], selection()['releases'])
        self.assertEqual(resolve.call_count, 4)

    def test_insufficient_unique_stable_history_fails_without_static_fallback(self):
        for rows in ([], [release()], [release(), release('v-other')]):
            with self.subTest(rows=rows), patch.object(releases, 'fetch_releases', return_value=rows), \
                    patch.object(releases, 'resolve_tag', return_value=SHA_A):
                with self.assertRaisesRegex(releases.ReleaseResolutionError, 'Need 3.*found'):
                    releases.resolve_releases()

    def test_missing_tag_resolution_is_fatal_instead_of_skipping_newest(self):
        with patch.object(releases, 'fetch_releases', return_value=[release()]), \
                patch.object(releases, 'resolve_tag', side_effect=releases.ReleaseResolutionError('missing tag')):
            with self.assertRaisesRegex(releases.ReleaseResolutionError, 'missing tag'):
                releases.resolve_releases(1)

    def test_malformed_release_metadata_is_rejected(self):
        invalid = [None, [], {}, release(draft='false'), release(prerelease=None),
                   release(tag_name=None), release(tag_name=''), release(published_at='yesterday'),
                   release(published_at='2026-03-01T12:00:00'), release(published_at='2026-99-01T12:00:00Z')]
        missing_date = release()
        del missing_date['published_at']
        invalid.append(missing_date)
        for row in invalid:
            with self.subTest(row=row), patch.object(releases, 'fetch_releases', return_value=[row]), \
                    patch.object(releases, 'resolve_tag') as resolve:
                with self.assertRaises(releases.ReleaseResolutionError):
                    releases.resolve_releases(1)
                resolve.assert_not_called()

    def test_count_is_bounded_before_network(self):
        for count in (0, -1, 11, True, 1.0, '3', None):
            with self.subTest(count=count), patch.object(releases, 'fetch_releases') as fetch:
                with self.assertRaises(releases.ReleaseResolutionError):
                    releases.resolve_releases(count)
                fetch.assert_not_called()


class ReleaseApiTests(unittest.TestCase):
    def test_pagination_reads_all_pages_before_sorting(self):
        pages = [response([release('v-old', '2026-01-01T12:00:00Z')], '<https://api.github.com/example?page=2>; rel="next"'),
                 response([release()])]
        with patch.object(releases.urllib.request, 'urlopen', side_effect=pages) as fetch, \
                patch.object(releases, 'resolve_tag', return_value=SHA_A):
            result = releases.resolve_releases(1)
        self.assertEqual(result['releases'][0]['tag'], 'v-new')
        self.assertEqual([call.args[0].full_url for call in fetch.call_args_list], [
            releases.API_URL + '?per_page=100&page=1', releases.API_URL + '?per_page=100&page=2'])

    def test_full_page_without_link_still_checks_for_more(self):
        with patch.object(releases.urllib.request, 'urlopen', side_effect=[response([release()] * 100), response([])]) as fetch:
            self.assertEqual(len(releases.fetch_releases()), 100)
        self.assertEqual(fetch.call_count, 2)

    def test_token_only_in_header_and_next_link_cannot_change_host(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'private-token'}, clear=True), \
                patch.object(releases.urllib.request, 'urlopen', side_effect=[
                    response([release()], '<https://untrusted.invalid/collect>; rel="next"'), response([])]) as fetch:
            releases.fetch_releases()
        for call in fetch.call_args_list:
            request = call.args[0]
            self.assertEqual(request.get_header('Authorization'), 'Bearer private-token')
            self.assertTrue(request.full_url.startswith(releases.API_URL + '?'))
            self.assertNotIn('private-token', request.full_url)
            self.assertEqual(call.kwargs['timeout'], releases.TIMEOUT)

    def test_unauthenticated_public_api_works(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(releases.urllib.request, 'urlopen', return_value=response([])) as fetch:
            self.assertEqual(releases.fetch_releases(), [])
        self.assertIsNone(fetch.call_args.args[0].get_header('Authorization'))

    def test_http_network_and_json_failures_are_explicit_and_redacted(self):
        errors = [urllib.error.HTTPError(releases.API_URL, 403, 'private-token', {}, None),
                  urllib.error.URLError('private-token'), TimeoutError('private-token')]
        for error in errors:
            with self.subTest(error=type(error)), patch.object(releases.urllib.request, 'urlopen', side_effect=error):
                with self.assertRaises(releases.ReleaseResolutionError) as caught:
                    releases.fetch_releases()
                self.assertNotIn('private-token', str(caught.exception))
        malformed = io.BytesIO(b'not JSON')
        with patch.object(releases.urllib.request, 'urlopen', return_value=malformed):
            with self.assertRaisesRegex(releases.ReleaseResolutionError, 'valid release JSON'):
                releases.fetch_releases()

    def test_invalid_page_shapes_fail(self):
        for payload in ({'message': 'error'}, None, [release()] * 101):
            with self.subTest(payload=type(payload)), patch.object(releases.urllib.request, 'urlopen', return_value=response(payload)):
                with self.assertRaises(releases.ReleaseResolutionError):
                    releases.fetch_releases()

    def test_broken_and_endless_pagination_fail(self):
        with patch.object(releases.urllib.request, 'urlopen', return_value=response([], '<anything>; rel="next"')):
            with self.assertRaisesRegex(releases.ReleaseResolutionError, 'empty non-final'):
                releases.fetch_releases()
        with patch.object(releases, 'MAX_PAGES', 1), \
                patch.object(releases.urllib.request, 'urlopen', return_value=response([release()], '<anything>; rel="next"')):
            with self.assertRaisesRegex(releases.ReleaseResolutionError, 'safety limit'):
                releases.fetch_releases()


class ReleaseTagTests(unittest.TestCase):
    def test_lightweight_tag_resolves_exact_ref(self):
        with patch.object(releases.subprocess, 'check_output', return_value=SHA_A + '\trefs/tags/v-fixture\n') as git:
            self.assertEqual(releases.resolve_tag('v-fixture'), SHA_A)
        self.assertEqual(git.call_args.args[0], ['git', 'ls-remote', '--exit-code', '--tags',
                                              releases.REPOSITORY, 'refs/tags/v-fixture', 'refs/tags/v-fixture^{}'])
        self.assertNotIn('shell', git.call_args.kwargs)

    def test_annotated_tag_uses_peeled_commit_not_tag_object(self):
        with patch.object(releases.subprocess, 'check_output', return_value=(
                SHA_A + '\trefs/tags/v-fixture\n' + SHA_B + '\trefs/tags/v-fixture^{}\n')):
            self.assertEqual(releases.resolve_tag('v-fixture'), SHA_B)

    def test_shell_metacharacters_remain_literal_argv(self):
        tag = 'v-$(touch${IFS}unwanted);literal'
        with patch.object(releases.subprocess, 'check_output', return_value=SHA_A + '\trefs/tags/' + tag + '\n') as git:
            self.assertEqual(releases.resolve_tag(tag), SHA_A)
        self.assertEqual(git.call_args.args[0][-2:], ['refs/tags/' + tag, 'refs/tags/' + tag + '^{}'])
        self.assertNotIn('shell', git.call_args.kwargs)

    def test_invalid_tag_cannot_be_used_as_pattern(self):
        for tag in ('', None, 'v*', 'v?', 'v[12]', 'v\nnext', 'v bad', 'v^{}', '../v', 'v/../x',
                    '/v', 'v/', '.v', 'v.lock', 'v//x', 'v\\x', 'v@{x}', 'v.'):
            with self.subTest(tag=tag), patch.object(releases.subprocess, 'check_output') as git:
                with self.assertRaises(releases.ReleaseResolutionError):
                    releases.resolve_tag(tag)
                git.assert_not_called()

    def test_missing_ambiguous_and_malformed_remote_refs_fail(self):
        ref = 'refs/tags/v-fixture'
        for output in ('', SHA_A + '\t' + ref + '^{}\n', SHA_A + '\trefs/tags/other\n',
                       'short\t' + ref + '\n', SHA_A + '\t' + ref + '\textra\n',
                       (SHA_A + '\t' + ref + '\n') * 2):
            with self.subTest(output=output), patch.object(releases.subprocess, 'check_output', return_value=output):
                with self.assertRaises(releases.ReleaseResolutionError):
                    releases.resolve_tag('v-fixture')

    def test_git_failure_is_explicit_and_has_no_stale_fallback(self):
        for error in (subprocess.CalledProcessError(2, 'git', stderr='private-token'),
                      subprocess.TimeoutExpired('git', 30), FileNotFoundError('git')):
            with self.subTest(error=type(error)), patch.object(releases.subprocess, 'check_output', side_effect=error):
                with self.assertRaisesRegex(releases.ReleaseResolutionError, 'Could not resolve'):
                    releases.resolve_tag('v-fixture')


class ReleaseSelectionTests(unittest.TestCase):
    def test_replay_validation_never_re_resolves_tags(self):
        archived = selection()
        with patch.object(releases, 'resolve_tag') as resolver, patch.object(releases, 'fetch_releases') as fetch:
            self.assertIs(releases.validate(archived, count=3), archived)
        resolver.assert_not_called()
        fetch.assert_not_called()

    def test_invalid_selection_fields_are_rejected(self):
        invalid = [None, [], {}, {**selection(), 'schema_version': True},
                   {**selection(), 'schema_version': 2}, {**selection(), 'repository': 'other'},
                   {**selection(), 'resolved_at': None}, {**selection(), 'releases': []},
                   {**selection(), 'releases': selection()['releases'][::-1]}]
        for field, value in (('commit', 'bad'), ('commit', None), ('tag', None), ('published_at', 'bad')):
            broken = selection()
            broken['releases'][0][field] = value
            invalid.append(broken)
        for field in ('commit', 'tag'):
            broken = selection()
            broken['releases'][1][field] = broken['releases'][0][field]
            invalid.append(broken)
        broken = selection()
        broken['releases'][0] = None
        invalid.append(broken)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(releases.ReleaseResolutionError):
                releases.validate(value)
        with self.assertRaisesRegex(releases.ReleaseResolutionError, 'exactly 1'):
            releases.validate(selection(), count=1)

    def test_cli_writes_immutable_json_and_compact_github_matrix(self):
        expected = selection()
        with tempfile.TemporaryDirectory() as temp:
            output, github_output = Path(temp) / 'nested' / 'release-selection.json', Path(temp) / 'github-output'
            github_output.write_text('existing=value\n')
            with patch.object(releases, 'resolve_releases', return_value=expected) as resolve, \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(github_output)}), patch('sys.stdout', new_callable=io.StringIO) as stdout:
                self.assertEqual(releases.main(['--output', str(output), '--github-output']), 0)
            resolve.assert_called_once_with(3)
            self.assertEqual(json.loads(output.read_text()), expected)
            self.assertEqual(json.loads(stdout.getvalue()), expected)
            lines = github_output.read_text().splitlines()
            self.assertEqual(lines[0], 'existing=value')
            self.assertEqual(lines[1], 'matrix=' + json.dumps({'include': expected['releases']}, separators=(',', ':')))
            with patch.object(releases, 'resolve_releases') as resolve, patch('sys.stderr', new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    releases.main(['--output', str(output)])
            resolve.assert_not_called()
            self.assertEqual(json.loads(output.read_text()), expected)

    def test_cli_missing_github_output_bad_count_and_resolution_failure_create_no_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'selection.json'
            for arguments in (['--github-output'], ['--count', '0'], ['--count', '11']):
                with self.subTest(arguments=arguments), patch.dict(os.environ, {}, clear=True), \
                        patch.object(releases, 'resolve_releases') as resolve, patch('sys.stderr', new_callable=io.StringIO):
                    with self.assertRaises(SystemExit):
                        releases.main(['--output', str(output), *arguments])
                resolve.assert_not_called()
                self.assertFalse(output.exists())
            with patch.object(releases, 'resolve_releases', side_effect=releases.ReleaseResolutionError('no releases')), \
                    patch('sys.stderr', new_callable=io.StringIO) as stderr:
                with self.assertRaises(SystemExit):
                    releases.main(['--output', str(output)])
            self.assertIn('no releases', stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_count_override(self):
        expected = copy.deepcopy(selection())
        expected['releases'] = expected['releases'][:1]
        with tempfile.TemporaryDirectory() as temp, patch.object(releases, 'resolve_releases', return_value=expected) as resolve, \
                patch('sys.stdout', new_callable=io.StringIO):
            releases.main(['--output', str(Path(temp) / 'selection.json'), '--count', '1'])
        resolve.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
