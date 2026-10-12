# Automatic PR experiments

## What runs

`Automatic firmware comparison` freezes the exact PR head, current remote `develop`,
and the three newest distinct stable release commits once at the start. Drafts,
prereleases, and duplicate SHAs are excluded. Release publication date determines
recency; a failed lookup never falls back to old pins. If the candidate is itself
one of those release SHAs, it runs once. Every revision receives the full short
matrix and six 90-minute cases: empty/full learned table × sensitivity 3/5/10,
seed 7, including the three sprint blocks. A production-learned fixture is trained
on that same frozen develop and reused unchanged by every revision. Plant/model
and scenario configuration is identical. This is simulation, not hardware testing.

Four revision jobs run in parallel, each bounded at 120 minutes, with no fail-fast.
A timeout, unsupported firmware adapter, failed training, or missing case remains
failed/incomplete rather than becoming a passing measurement. Relative regression
and absolute quality-band failures remain separate. Raw evidence is public via
Actions artifacts (90 days), and trusted Pages publication retains validated runs.
Historical cached results are visibly labeled as reused, retaining their original
execution timestamps; they are not presented as newly executed rides.

Caches key exact firmware SHA, baseline SHA, reviewed adapter SHA, evaluator/model/
scenario digest, suite, OS, and revision identity. Changing any of these invalidates
the cache. The shared fixture key uses the same model/engine and exact develop SHA.
Only complete measured coverage is cached; a failed quality band may still be a
complete measurement, so its failure exit code is retained on reuse.

## Event delivery and one-time setup

GitHub does not send SmartSpin2k PR events to a different repository's workflows,
and its ordinary GITHUB_TOKEN is limited to the calling repository. The supported
no-new-secret relay uses the owner's existing connected GitHub app and a PR webhook
automation. It adds one tiny data-only request commit to this repository's main
branch for each new/updated same-repository PR head. That push starts this workflow.
This relay depends on that connection/automation remaining enabled; it is not a
self-contained cross-repository GitHub webhook. No polling schedule is substituted.

Enable only after the receiver is published and verified. Subscribe to repository
`doudar/SmartSpin2k`, pull_request events, with commit updates enabled. On opened,
ready-for-review, or synchronize wake-ups, fetch current PR metadata; ignore closed
PRs. For each head, check the exact request path first and do nothing if it exists.
Commit exactly one new file per push:

`requests/pr-<number>/<40-character-lowercase-head-SHA>.json`

```json
{"schema_version":1,"repository":"doudar/SmartSpin2k","pull_request":123,"head_sha":"0123456789012345678901234567890123456789"}
```

Use API-verified integer PR number and exact head SHA, never PR body/title/commands.
The receiver independently verifies open status, target repository and current
head. An obsolete request fails closed. A new-head event gets its own request.
Do not modify existing requests. To retry an already recorded head, a maintainer
can use workflow_dispatch with that exact SHA; do not create dummy PR events.

Fork PRs are intentionally blocked in the automatic receiver. A successful workflow
name is not proof of maintainer approval because a fork can modify that workflow.
A maintainer must explicitly approve testing that head by dispatching this workflow
on main with the exact SHA. This relay never approves GitHub fork workflows or
bypasses an existing approval gate. It does not post comments or statuses on the
firmware repository. The dashboard and Actions are the report destinations.

The separate firmware-native pull_request check remains on the erg-spike-gate
branch until its workflow change is merged by a maintainer. This setup does not
merge or modify production develop, and does not claim that firmware-native check
is globally installed merely because the simulator relay is active.

## Security boundary

The plan and publisher execute only trusted simulator code. Candidate native code
runs in a disposable, non-root, network-disabled container with dropped Linux
capabilities, no Docker socket, no Actions/runtime tokens, read-only input mounts,
and only its output directory writable on the host. All checkouts disable persisted
credentials. The host rejects symlinks/special files and limits inert output types
and sizes before uploading or caching. Compiled production-source audits run before
build trees are removed. The publisher validates data, renders using trusted main
code, and never executes artifacts. Write/Pages permissions exist only in separate
trusted publication jobs; no candidate job has them.

Manual paired/historical/long workflows delegate to the same dynamic selector and
runner, selecting short or long coverage. Automatic PR requests always run both.
The adapter commit in compatibility provenance is deliberately reviewed and pinned:
that executable trust anchor is distinct from automatically selected firmware
candidates/releases. New incompatible releases fail explicitly and may require an
adapter update; they are never silently skipped or replaced with synthetic results.

## Durable evidence storage and size protection

New validated raw ZIPs are uploaded by the trusted publisher to public GitHub
Release assets in this simulator repository. Each content-addressed filename
includes the run ID and ZIP SHA-256. The publisher re-fetches the asset and verifies
its server SHA-256 digest, byte count, uploaded state, and exact public download URL
before replacing the new local ZIP with an evidence-location pointer. It never
replaces a Release asset or removes an existing immutable Pages record. Releases
are marked as evidence prereleases, not firmware releases. Publication uses the
existing repository-scoped Actions token; no new persistent credential or external
storage service is required. Failed verification retains the ZIP and stops publish.

Pages keeps interactive summaries, display traces, comparison JSON, checksums, and
verified download links. Training downloads use the same verified index. Future
renders reuse validated local display snapshots and do not download or execute
Release artifacts. Release assets have no Actions-style expiration. GitHub currently
allows 1,000 assets per release and less than 2 GiB per asset; each run uses its own
release, with at most 40 bounded records. See [GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

Cached unchanged histories are deduplicated against complete retained records using
the full cache identity, original run/attempt, firmware/model/case provenance, and
raw-file checksums. Complete measurements retain their original record and URL
even when a provisional quality band failed; errored or incomplete executions do
not suppress new evidence. New or changed evidence
is never silently deduplicated. A partially imported batch retains valid links to
its original shared training record.

The verified pre-migration Pages snapshot was 571,652,364 bytes, of which 543,035,550
bytes were ZIPs. Those old records remain untouched. New evidence avoids that raw
ZIP growth: the latest six-long batch's summaries/plots were about 2.45 MB, versus
hundreds of MB of raw input. The publisher fails safely above a 900 MB Pages package,
before [GitHub's 1 GB site limit](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits),
leaving the prior live dashboard intact and verified Release assets retained. This
is a guard against eventual summary growth, not permission to delete old history.
