# Public performance dashboard

The requested publishing destination is **GitHub Pages**:
https://doudar.github.io/smartspin2k-simulator/ . This URL is live only after the
repository owner enables **Settings → Pages → Build and deployment → Source →
GitHub Actions** and a deployment succeeds. No personal access token is needed.

## What it shows

- Immutable run history, then scenario and seed selection.
- Target, actual modeled plant, baseline plant and delivered-sensor power traces.
- Candidate simulated actual motor position in red, with a separate right-hand steps axis.
  Its source is `motor_steps`, the native virtual motor’s current completed-step counter
  (after motor advancement), not `command_steps` (target) or `physical_steps` (bike
  knob position after backlash/travel stops). This is simulated telemetry, not a
  measured encoder signal; its coordinate can differ from physical bike position.
- Original full-clock scores with absolute quality bands separate from relative
  regression allowances. Both plant and sensor decisions are displayed.
- Exact firmware, adapter, simulator and model fingerprints; release publication
  and experiment timestamps are distinct.
- Full raw evidence ZIP, comparison JSON and per-file SHA-256 checksums. Plots
  are display-decimated, never used to recompute the scores.
- Failed/incomplete runs remain visible. Unsupported historical adapter APIs
  mean unavailable coverage, not bad firmware performance.

These are provisional software experiments. They do not validate radio behavior,
ESP32 scheduling, real motor motion or hardware fidelity. Only runs with matching
simulator/model/adapter/scenario/seed provenance are directly comparable.

## Running and publication

Run **Paired firmware experiment** manually from Actions on `main`. The immutable
adapter defaults to `782c2b5e303115f90bf8f81b724da5717362de39`; the baseline is
release 26.10.1, `082d1ee26ddb009d5132547087f77be03d1b0ab7`. Candidate refs resolve
into recorded exact commits. Changing the paired workflow also runs its pinned
initial experiment on a main-branch push.

The producer has read-only repository permissions and no persisted checkout
credentials. It uploads `paired-evidence` even on a nonzero acceptance result.
**Publish performance dashboard** then runs independently for completed main
branch experiments. It renders from trusted `main` code, never the candidate or
PR checkout. The first dashboard push may temporarily show no runs while the
initial experiment executes; there are no placeholder scores.

The publisher uses three separate jobs:

1. Read-only renderer downloads artifacts as data. It bounds JSON depth, sizes,
   trace length and numbers; rejects symlinks/unsafe paths; accepts only inert
   JSON/CSV/log/PTAB/text evidence. It never copies artifact HTML/JS/SVG or runs
   artifact code. UI content uses `textContent`, fixed routes and a restrictive
   content-security policy. Invalid evidence becomes an explicit incomplete run.
2. Repository-write archive job downloads only the renderer output, runs fixed
   workflow commands, and appends a commit to `gh-pages`. It does not execute
   files from the downloaded site. Existing run IDs are not overwritten.
3. Pages deployment receives only `pages: write` and `id-token: write`, no source
   execution. It requires Pages already configured for GitHub Actions.

No `pull_request_target`, untrusted-head checkout, write-enabled simulation, or
new secret is used. Workflow-run publication checks repository and main branch.
Manual publication also uses the current trusted main renderer.

## Retention and reproducibility

Actions artifacts expire after **90 days**. The static site and compressed raw
archives are retained in **gh-pages Git history** until explicitly removed;
there is no automatic pruning or promise of permanent third-party availability.
Large histories can approach GitHub Pages size limits and will require an
explicit storage/retention decision, not silent deletion. Repository deletion,
force rewriting or owner cleanup can remove evidence. Run IDs include Actions
run ID and attempt; every rerun gets a new entry.

Locally (Python standard library only):

```sh
python dashboard/build.py --history /tmp/history --output /tmp/site \
  --input /path/to/experiment --run-id local-unique-id \
  --metadata /path/to/run-metadata.json
python -m http.server --directory /tmp/site
python -m unittest discover -s tests -p test_dashboard.py -v
```

The optional metadata JSON records `adapter_commit`, `simulator_commit`,
`run_started_at`, `run_completed_at`, `release_tag`, `release_published_at` and
notes. Missing provenance is labeled unrecorded rather than inferred from file
mtime, an artifact name or a release date.

## Historical releases

Retrospective results rerun the released production source **today** under a
shared current test harness. They are not measurements made on the release date
and do not execute a previously released ESP32 binary. Historical API gaps need
reviewed test-only compatibility code, with its exact hash recorded. Never
rewrite old controllers or relax budgets to produce a passing timeline.

Initial investigation verified these official release SHAs:

- 26.10.1: `082d1ee26ddb009d5132547087f77be03d1b0ab7` (2026-10-01T20:47:58Z).
- 26.9.15: `8e861fbbf9e162497647318e3ddb8823926fcce9`.
- 26.8.23: `afe356dc3ae828a4afcfdc5a92968bfa1d4175db`.

All three now run under the same reviewed [test-only compatibility patch](../dashboard/compatibility/history-adapter.patch), plus current `782c2b5`. The **Historical release experiment** workflow runs the bounded four-candidate matrix and publishes each completed/failed experiment. It uses simulator `d475d9fa`, baseline26.10.1 and identical seeds7/27/91. Adapter base `f836c058` plus patch has fingerprint `098a900211f1803e2723634325061b6185b1d5e2fb20e13e8698d42097910f32`.

The patch supplies historical host API plumbing, preserves the historical empty-table constructors in fresh per-ride processes, and uses C++20 for an existing historical `starts_with` call. It does not add newer controller/learning behavior. An automated audit checks production bodies byte-for-byte, allowing only documented peripheral include and virtual-clock seams. The adapter provenance, initial-state audit and local source audit are in `dashboard/compatibility/`. Each cloud experiment includes its own newly executed source audit. Earlier unsupported-API preflight results are superseded, not firmware failures.

Verified local full-matrix absolute passes:26.8.23 7/18,26.9.15 7/18,26.10.1 6/18,current782c2b5 9/18. These are provisional whole-matrix counts, not a declaration that the newest release wins every scenario. See live raw metrics and separate relative decisions for detail.

### Motor display backfill

The trusted renderer rebuilds versioned `motor-v1/<run-id>.json` display data from
archived candidate CSVs. Existing `runs/` summaries, raw ZIPs, comparison JSON and
checksums stay byte-for-byte unchanged. No experiment is rerun and no score changes.
Missing motor columns are unavailable; missing/nonfinite samples create gaps, never
inferred positions. The display decimation preserves gap markers and endpoints.
