# SmartSpin2k simulator

An independent bike plant and ride-level evaluator for SmartSpin2k firmware.
The accelerated path runs the real production controller through a firmware-owned
native adapter, while this repository owns physics, rider cadence, workouts,
sensor sampling, Bluetooth packet encoding, scoring and experiment orchestration.

## Boundary and ownership

- `ss2k_sim/`: bike model, rider/workout plans, sampling, evaluator and reports.
- `ss2k_sim/ble/`: standard CPS/CSC encoding and optional real-hardware bench.
- Firmware checkout: `scripts/erg_sim/bridge.py`, `native.cpp`, `virtual_ble*`,
  `virtual_ftms*`, and the actual firmware source. These files are **not copied**
  here. An explicit trusted `--firmware-root` supplies the adapter.
- `--baseline-root` and `--candidate-root` supply only the controller revisions
  to build. Both use exactly the same adapter and simulator.

The simulated plant receives signed motor pulses and rider cadence. Workout watt
targets are sent only through the controller's FTMS procedure path; neither target
watts nor controller positions are fed into the physical plant. Raw CPS/CSC bytes
cross the virtual GATT boundary into production decoder/collection functions.
Independent sample clocks preserve acquisition timestamps through delay/dropouts.
Continuous effective plant power is recorded on the fixed plant clock even during
sensor outages. The fitted response pole includes physical and meter dynamics,
so this is not independently calibrated mechanical ground truth. Actual sensor
acquisitions read a continuous delayed estimator using a separate noise process;
they do not resample a hidden 1 Hz report. Delivered sensor power is recorded and
scored separately; both comparisons must pass. Timing is quantized forward to the
plant integration tick, with actual acquisition/delivery times preserved.

This is accelerated software-boundary testing. It does **not** validate real
Bluetooth radio behavior, NimBLE/FreeRTOS scheduling, ESP32 timing, motor electrical
behavior or mechanical fidelity. Model dynamics and stress schedules are exposed
assumptions. A passing result is not hardware certification.

## Install

Python 3.10+ and C/C++ compilers (`gcc` and C++17 `g++`) are required for accelerated runs.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m ss2k_sim --help
```

Optional reports: `python -m pip install -e '.[reports]'`.

## Paired baseline/candidate experiment

Prepare three local firmware checkouts. The adapter checkout should be pinned to
`f836c058d5ab474c36ec6f9384256db70596ac5c`, which contains the reviewed packet
adapter. Older controller revisions need not contain the adapter.
The baseline must be clean and exactly at the pinned develop commit below.
Use trusted firmware code: loading the adapter executes its Python build code.

From the simulator checkout, create pinned sibling worktrees once:

```sh
git clone https://github.com/doudar/SmartSpin2k.git ../firmware-adapter
git -C ../firmware-adapter checkout --detach f836c058d5ab474c36ec6f9384256db70596ac5c
git -C ../firmware-adapter worktree add --detach ../firmware-baseline 082d1ee26ddb009d5132547087f77be03d1b0ab7
git -C ../firmware-adapter worktree add --detach ../firmware-candidate f836c058d5ab474c36ec6f9384256db70596ac5c
python -m ss2k_sim check-adapter --firmware-root ../firmware-adapter
python -m ss2k_sim compare \
  --firmware-root ../firmware-adapter \
  --baseline-root ../firmware-baseline \
  --candidate-root ../firmware-candidate \
  --output output/paired
```

Default baseline: `082d1ee26ddb009d5132547087f77be03d1b0ab7`.
An intentional baseline change requires `--baseline-sha EXACT_COMMIT`.
`--adapter-sha256 HASH` optionally enforces the fingerprint printed by
`check-adapter`. Select a diagnostic subset using `--scenario steps --seeds 27`.
The full default matrix covers steps, ramps, cadence changes, differing power and
cadence sample rates, latency, jitter and outages, across three seeded runs.

A single revision can be inspected with `run`, the same arguments without
`--baseline-root`. Single runs are explicitly unpaired and do not receive a
paired acceptance decision. No result directory is silently overwritten.

Outputs include `comparison.json`, per-ride `trace.csv`, raw delivered sensor
packet logs, cadence plans, power-table snapshots, scores and adapter logs.
The manifest records exact firmware commits, dirty status and source hashes,
adapter file hashes, simulator hashes, plant configuration, schedules and seeds.
Source fingerprints capture dirty candidate changes that a commit ID alone misses.

Comparison uses absolute ride-quality budgets and relative regression allowances.
Budgets are provisional engineering criteria, not calibrated acceptance limits.
Bias, oscillation, frozen response, slow settling and hidden outage samples are
covered by deliberate negative fixtures. A bad baseline does not excuse a bad
candidate: absolute budgets still apply. Exit 1 means failed comparison; exit 2
means infrastructure/input failure. Partial experiment evidence is retained.

## Optional real-hardware cross-check

```sh
python -m pip install -e '.[bench]'
python -m ss2k_sim.ble.bench --help
```

The hardware runner requires Linux BlueZ, separate dedicated peripheral and
central adapters, actual SS2K BLE addresses, an independently wired STEP/DIR or
encoder counter, profile/workout files and explicit firmware provenance. It does
not flash, reconfigure or read private controller positions. The counter streams
newline JSON via `serial:///dev/ttyACM0`, `tcp://host:port`, or `unix:///path`:

```json
{"seq": 1, "timestamp_us": 10000, "forward": 20, "reverse": 2}
```

All fields are nonnegative integers. Sequence and monotonic device timestamps
strictly increase; forward/reverse pulse totals never decrease. Send heartbeats
even while stationary. Stale, malformed, reset, impossible-rate and disconnected
sources fail the run. Counter origin and initial physical position are established
by the bench operator. STEP/DIR proves electrical pulses, not actual mechanical
motion; use an encoder if that distinction matters.

The runner requires both sensor subscriptions, the expected isolated sensor peer,
live FTMS telemetry, successful indicated control/start/target results and a
confirmed STOP. Real DIS firmware revision is checked; image hash and config are
operator attestations, clearly distinguished from live readback. No observed motor
motion fails the boundary check. Successful acquisition is **ungraded**.
Software unit tests use injected adapters and are not hardware validation.

Current gaps and the next useful calibration recording are listed in
[coverage](docs/coverage.md). Initial per-seed results are in
[initial results](docs/initial-results.md).

## Native integration negative control

```sh
SS2K_FIRMWARE_ROOT=../firmware-adapter python -m unittest discover -s tests -p test_packet_ride.py -v
```

This compiles the production packet/controller path twice, with the same plant:
once normally and once with motor pulses forced to zero in a temporary adapter.
The stuck plant must show zero travel and be rejected by the relative ride
evaluator. No production source is modified. Without the explicit trusted
firmware path this integration test is skipped; ordinary contract tests still run.

## CI

`tests.yml` runs standalone contract and negative-fixture tests without firmware
hardware. `paired.yml` is manual and requires an exact 40-character adapter commit
input; it resolves the candidate ref, checks out the immutable baseline and saves
all experiment artifacts even on failure. It uses the verified firmware origin
`doudar/SmartSpin2k`; private repositories need appropriately authorized checkout
credentials. The standalone simulator must still have its exact published commit verified by
remote CI; local tests alone do not establish that result.

## Provenance and license

Initial independent Python modules and profiles were extracted from the
SmartSpin2k working tree based on commit
`83505906b31461294c0ead58e2fe7368259199a9`, including then-uncommitted simulator
improvements. Exact initial content hashes are in `SOURCE_PROVENANCE.json`.
Firmware remains in its own repository; no controller implementation is vendored.
The firmware repository's legacy Python simulator may remain for compatibility;
new simulator changes should be maintained here rather than manually mirrored.

The source project is licensed under GNU GPL version 2. Its license is preserved
in `LICENSE`; this derived package uses the same GPL-2.0 license. Profile parameters
are fitted/effective model assumptions and must not be represented as independent
measurements of every operating condition.
