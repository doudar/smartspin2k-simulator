# Public performance dashboard

The requested publishing destination is **GitHub Pages**:
https://doudar.github.io/smartspin2k-simulator/ . This URL is live only after the
repository owner enables **Settings → Pages → Build and deployment → Source →
GitHub Actions** and a deployment succeeds. No personal access token is needed.

## What it shows

- Firmware-first navigation, immutable run history and scenario selection; all displayed tests use seed 7.
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
adapter defaults to `b776105cd1e3edb93a91bada3f27aaecc25533dc`. Every new
experiment resolves the current `doudar/SmartSpin2k` `develop` head exactly once,
before baseline checkout or training. All cases reuse that recorded clean SHA;
resolution failure stops the experiment. Candidate refs resolve into recorded
exact commits. The selected repository/ref, SHA, timestamp and selection mode
are retained with the evidence. Changing the paired workflow also runs its pinned
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

All three now run under the same reviewed [test-only compatibility patch](../dashboard/compatibility/history-adapter.patch), plus current `782c2b5`. The **Historical release experiment** workflow runs the bounded four-candidate matrix and publishes each completed/failed experiment. The retained historical batch used simulator `d475d9fa`, baseline26.10.1 and identical seeds7/27/91. New historical batches use the current simulator and a once-resolved current `develop` baseline for every candidate, with seed 7. Release 26.10.1 remains a separate exact-pinned candidate checkout; it is never an alias for the baseline. Original multi-seed evidence remains unchanged. Adapter base `f836c058` plus patch has fingerprint `098a900211f1803e2723634325061b6185b1d5e2fb20e13e8698d42097910f32`.

The patch supplies historical host API plumbing, preserves the historical empty-table constructors in fresh per-ride processes, and uses C++20 for an existing historical `starts_with` call. It does not add newer controller/learning behavior. An automated audit checks production bodies byte-for-byte, allowing only documented peripheral include and virtual-clock seams. The adapter provenance, initial-state audit and local source audit are in `dashboard/compatibility/`. Each cloud experiment includes its own newly executed source audit. Earlier unsupported-API preflight results are superseded, not firmware failures.

Verified local full-matrix absolute passes:26.8.23 7/18,26.9.15 7/18,26.10.1 6/18,current782c2b5 9/18. These are provisional whole-matrix counts, not a declaration that the newest release wins every scenario. See live raw metrics and separate relative decisions for detail.

### Motor display backfill

The trusted renderer rebuilds versioned `motor-v1/<run-id>.json` display data from
archived candidate CSVs. Existing `runs/` summaries, raw ZIPs, comparison JSON and
checksums stay byte-for-byte unchanged. No experiment is rerun and no score changes.
Missing motor columns are unavailable; missing/nonfinite samples create gaps, never
inferred positions. The display decimation preserves gap markers and endpoints.

## Continuous long rides and starting-table evidence

The **Long ride learning experiment** workflow now publishes
`continuous-long-ride-sprints-v2`: six 90-minute paired cases, with **empty or
fully learned starting tables × ERG sensitivity 3, 5 or 10**, all at seed 7.
The current `develop` baseline is resolved once before training and retained
across the whole six-case matrix. Training uses one canonical sensitivity-5 production-learning run, and every
sensitivity receives the same earned fixture for its selected starting state.
Both revisions receive identical starting-table data; no plant-to-table oracle
or controller replacement is used. RAM import is not a flash-persistence test.

The v2 full fixture earned all **45 declared tested-grid cells** at
90, 120, 150, 180, 210, 240, 270, 480 and 510 W × 75, 80, 85, 90 and 95 rpm.
Those cells bracket the 100 W recovery and 500 W sprint targets. “Fully learned”
means measured support on this declared grid, never the entire 300-cell firmware
table or a calibrated physical-bike validation. Read the [long-ride methodology
and model caveats](long-rides.md) before interpreting high-power behavior.

Archived `continuous-long-ride-v1` runs remain separately accessible as **Long
rides without sprints (v1 archive)**. They retain their original 30/60/90-minute
and empty/partial/full matrix, original 25-cell grid at 150–270 W × 75–95 rpm,
original scenarios and provenance. V2 does not relabel or rewrite that evidence.

Every case gets an immutable evidence record. The scenario remains `long_ride`
while sensitivity is included in its record ID and original artifact folder name,
preventing collisions between the three configurations. One shared training
archive is linked by its exact training run ID from all six cases. It includes
original training traces, snapshots and earned fixture files. Missing or
incomplete requested cases remain visible.

The learning panel shows initial/final measured support and repeated early,
middle and late six-minute probes. A separate **500 W sprint response** panel
shows the three early/middle/late 85-second blocks at 85 rpm: 100 W for 30 seconds,
500 W for 25 seconds and 100 W for 30 seconds. Each block has a shared-chart zoom
button, plant and delivered-sensor response metrics for both revisions, separate
block decisions, and starting-table coverage and fingerprints.

Sprint response metrics expose rise time to 450 W, settling at 500 W, peak power,
overshoot, time above 520 W, time outside ±20 W, and recovery settling, peak and
time above 120 W. Recorded null rise/settling results explicitly say the threshold
was not reached or settled during that phase. Missing data remains unavailable.
These full-rate phase measurements cannot be replaced by whole-ride averages;
block pass/fail applies the recorded budgets to the entire 85-second block.

Whole-ride, all three probe and all three sprint-block decisions, for **both plant
and delivered-sensor signals**, determine v2 aggregate quality results. A failure
in any sprint signal defeats an overall pass. V1 aggregate results still use its
whole ride and probes only. Log counts are observations/insertion attempts or
sampled gain messages, not counts of accepted inserts or exhaustive lookups.
Comparisons are descriptive; learning is not assumed to improve performance.
The sensor outage and actual cadence-zero rider pause remain separate from the
probes and sprint blocks; see the methodology for the exact schedule.

Long-ride display traces retain endpoints, bounded target transitions and
per-bucket extrema to preserve brief overshoots; raw20ms CSV files remain complete.
Motor traces use the same extrema-preserving approach. Archives retain the
existing32MiB/file and200MiB/case bounds; measured90-minute traces fit those
bounds. Build directories and executables are excluded. Unsafe or oversized
payloads are reported as incomplete, never executed or silently truncated.


## Firmware-first test navigation

The primary selector groups by recorded firmware branch or release. Test type,
starting table and scenario are separate controls. V2 offers ERG sensitivity
3/5/10 at a fixed 90-minute duration; only archived v1 offers duration and partial
starting-table controls. All displayed tests use seed 7, without a seed selector. The
secondary experiment selector shows the original experiment date, exact candidate
commit and unique record ID. A branch grouping is navigation only: different
tests can use different revisions, simulators or adapters. No scores are pooled
across records and no equivalence between branch snapshots is assumed.

Switching firmware keeps the chosen test, duration or sensitivity, starting table,
scenario and fixed seed. Missing combinations remain selected and explicitly unavailable, with no
stale chart, learning panel or sprint panel. A firmware with no matching experiment also clears
its evidence links and provenance. Switching test type deliberately selects a
suitable scenario (remembering the previous short scenario), while retaining the
seed. Selecting v2 from an archived partial-table case uses the supported empty
starting state. A missing seed is never silently replaced. The newest matching recorded
experiment is selected when changing firmware; other dates remain selectable.
Existing run-ID URL fragments still open the corresponding exact evidence record.

Long-ride coverage is currently limited to the recorded development snapshot.
Historical release baselines inside paired results are not relabeled as standalone
candidate experiments. This navigation update reruns no physics and changes no
immutable run files, original scores, evidence ZIPs or checksums. The renderer
adds selection metadata to the regenerated history index; versioned motor and
cadence presentation sidecars are derived separately from the original archive.

### Cadence and shared inspection

The versioned `cadence-v1/` presentation sidecar is rebuilt from each retained
candidate `trace.csv` without rewriting `runs/`, checksums, scores, or evidence
ZIPs. Its RPM signal is `cadence_rpm`: the simulated rider cadence passed to the
bike plant, not a physical measurement or a complete firmware-received cadence
trace. CSC packets and sparse control logs are not used to invent missing runtime
RPM values. The reserved received-cadence column is null when unavailable.

A separate cadence panel shares the power/motor chart's elapsed-time window;
dragging either panel and all zoom controls affect both. RPM scaling is independent
of watts and motor steps. Zero-cadence pauses and missing-data gaps are retained.

Hover either panel to inspect power, motor and cadence at one cursor time. On touch
screens, a tap pins the same readout; Select area still opts into drag zoom. Values
show their own nearest retained sample timestamps rather than interpolated values
or claimed raw-resolution samples. Missing values remain unavailable. Tap outside
or press Escape to dismiss. With the chart focused, Left/Right and Home/End inspect
retained sample times. Changing the run, scenario, or window clears the readout.

### Fixed comparison seed

The dashboard uses seed 7 for every displayed test and has no seed selector.
Charts, availability and summary counts are filtered to recorded seed-7 rows.
Older evidence and other seeds remain in unchanged original downloads; they are
never relabeled. Combinations without recorded seed-7 evidence show unavailable.

The [automatic PR pipeline](automation.md) publishes short plus six long cases for each selected firmware revision. Its cross-repository relay must be enabled separately; workflow files alone do not activate future PR events.
