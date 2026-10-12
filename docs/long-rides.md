# Continuous 90-minute rides, sprint response and ERG sensitivity

The current `continuous-long-ride-sprints-v2` experiment runs **six paired cases**:
90 minutes × empty / fully learned declared range × ERG sensitivity 3 / 5 / 10.
Every ride uses seed 7 and one native process with continuously evolving production
ERG / power-table state. Existing v1 30/60/90-minute, partial-table experiments
remain immutable historical evidence; they are not relabeled as sprint rides.

## Exact sprint schedule

Each ride includes three identical blocks, with the same 85 rpm cadence cue and
segment-relative modeled drift:

| Block | 100 W lead-in | 500 W sprint | 100 W recovery |
|---|---|---|---|
| Early | 6:00–6:30 | 6:30–6:55 | 6:55–7:25 |
| Middle | 48:00–48:30 | 48:30–48:55 | 48:55–49:25 |
| Late | 82:35–83:05 | 83:05–83:30 | 83:30–84:00 |

Blocks replace endurance time so duration remains exactly 90 minutes. Their
30 / 25 / 30-second boundaries are exact simulation time, carried through the
adapter's actual FTMS Set Target Power procedure (opcode 0x05). Successful raw
control payloads and their simulation times are saved in `ftms_control_packets.json`.
These are virtual packet ingress, not over-the-air Bluetooth measurements.

The unchanged six-minute learning probes start at 0:00, 42:00 and 84:00. No
sprint overlaps a probe, sensor dropout or pedaling pause. A common 30-second
100 W lead-in reduces entry-state differences; it does not reset the motor,
controller or learner or make their different histories identical.

## Reproduce the matrix

First resolve and check out the current `develop` baseline using the
[paired setup](../README.md#paired-baselinecandidate-experiment). Keep its
`SS2K_BASELINE_SELECTION` environment variable set before training and throughout
the matrix; do not re-resolve between cases.

```sh
python -m ss2k_sim.longride train \
  --firmware-root ../firmware-adapter --candidate-root ../firmware-candidate \
  --output output/long-training
python -m ss2k_sim.longride compare \
  --firmware-root ../firmware-adapter --candidate-root ../firmware-candidate \
  --baseline-root ../firmware-baseline --fixtures output/long-training \
  --output output/long-paired --minutes 90 --states empty full \
  --sensitivities 3 5 10 --seeds 7 --stress
```

The adapter must expose `Bridge.load_power_table`. The baseline is the clean
exact `develop` SHA recorded once for this experiment, before training; its
selection is retained in the evidence. Archived replays require an explicit
replay selection and remain labeled as replays. Sensitivity is passed to the native
adapter initialization, which calls production `userConfig->setERGSensitivity`;
it is not a simulator gain multiplier. Both builds receive exactly the same
sensitivity, physical model, sensor schedules, cadence plan, seed and initial table.
No controller tuning or acceptance-threshold changes are part of this experiment.

## Earned starting tables

- **Empty:** no stored entries at time zero.
- **Fully learned declared range:** an actual production-learning snapshot with
  readings >= 2 and valid stored positions at **45 grid cells**: 90, 120, 150,
  180, 210, 240, 270, 480 and 510 W at 75, 80, 85, 90 and 95 rpm. The 90/120 and
  480/510 W cells bracket the requested 100/500 W blocks. This does not claim all
  300 firmware cells are known, nor that every production lookup/gain is trusted.
  Runtime confidence and slope gates can still choose fallback behavior.

Training is a separate 90-minute ride with 120-second holds at those grid points,
seed 7 and canonical ERG sensitivity 5. All cells come from unmodified production
learning; no cell is calculated from the physical model or inserted to manufacture
coverage. A full fixture is written only if all 45 cells actually earn support.
The same candidate-trained, immutable fixture seeds both firmware builds and all
three sensitivities. This isolates controller behavior, not how each sensitivity
independently trains from scratch; empty-start rides cover that evolution.
Hashes, source revisions, profile identity, segments, seed and training sensitivity
are retained. Seed 7 repeatability is not multi-seed robustness coverage.

Import is a **RAM snapshot persistence analogue**, before the first tick.
Production flash serialization and save/load reliability are not tested. Stored
cells are restored, while controller confidence, timers and transient state start
fresh. All state then evolves continuously without restarts.

## Measurements and interpretation

Each sprint has its own plant and delivered-CPS summary and comparison, separate
from whole-ride and early/middle/late probe scores. Reports include first reach of
450 W, first five-second dwell within ±20 W of 500 W, peak power/overshoot,
seconds above 520 W, seconds outside ±20 W during the 25-second effort, recovery
settling to 100 W, recovery peak and seconds above 120 W. Null rise/settling means
the threshold was never achieved within that effort or recovery, not zero seconds.
The original provisional absolute and relative budgets apply to every 85-second
block, including recovery. A long steady section cannot hide a missed sprint.
Large immediate post-sprint error is included, not discarded as a warm-up period.

The unchanged six-minute probes repeat a 60-second 180 W / 85 rpm lead-in, then
240 W, 150 W, 210 W at 80 rpm, 210 W at 90 rpm, and 180 W at 85 rpm. Whole-ride,
probe and sprint decisions include both effective plant and delivered meter power.
No improvement from learning is assumed and a provisional failure alone is not
proof of a firmware defect.

`--stress` retains a 12-second power-packet dropout at 22:30 and a 60-second
zero-cadence rider cue at 23:00–24:00. Bounded deceleration/reacceleration and real
FTMS pause/resume packets are included. Current production pause packets change
status only; the physical pedaling cue exercises actual low-cadence gates.
Whole-ride scores include interruptions and unattainable power at zero cadence.

Learning-event counts distinguish raw observations and insertion attempts;
these are not all accepted insertions. Table/fallback gain counts are sampled
production logs, not exhaustive lookup counts. Table coverage is read-only actual
stored-cell evidence. Minute-level snapshots plus sprint/probe-start snapshots,
full 20 ms traces, sensor acquisitions/deliveries and production logs are retained.

## Physical-model limits

The effective plant is fitted to one recorded ride, not independent hardware
truth. Its original fit covered positions 6292–18881 and cadence 56–114 rpm.
Positions/cadences outside those ranges are model extrapolation. Every ride records
seconds outside the original fit ranges, both overall and for each sprint block.
Within-range membership alone does not establish hardware fidelity at 500 W or
validate the short transient. Training at high-power / low-cadence grid points
can extend outside recorded support even though the production learner genuinely
earns the simulated cells. Radio, ESP32/FreeRTOS scheduling, flash persistence,
backlash and mechanical fidelity remain outside coverage.

Dashboard traces may be reduced for display only. Full-rate archived evidence
is authoritative, and previous scenario versions remain separately labeled.
