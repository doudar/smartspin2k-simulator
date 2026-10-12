# Continuous long rides and starting power tables

`python -m ss2k_sim.longride` adds 30, 60 and 90 minute sessions. Each timed
ride uses **one native process and one continuously evolving production ERG /
power-table state**. No reset occurs between the identical six-minute early,
middle and late probes. The full 20 ms trace, packet acquisitions/deliveries,
production log and minute-level table snapshots are retained.

## Starting states

Generate fixture tables before the timed experiment:

```sh
python -m ss2k_sim.longride train \
  --firmware-root ../firmware-adapter --candidate-root ../firmware-candidate \
  --output output/long-training
python -m ss2k_sim.longride compare \
  --firmware-root ../firmware-adapter --candidate-root ../firmware-candidate \
  --baseline-root ../firmware-baseline --fixtures output/long-training \
  --output output/long-paired --minutes 30 60 90 \
  --states empty partial full --seeds 27 --stress
```

The adapter must expose `Bridge.load_power_table`. Baseline stays pinned to
082d1ee26ddb009d5132547087f77be03d1b0ab7. The same adapter, physical model,
sensor schedules, seed and immutable initial fixture are used for both builds.

- **Empty:** no stored entries at time zero.
- **Partial:** an actual intermediate training snapshot with some, but not all,
  tested-range cells supported.
- **Fully learned tested range:** a real training snapshot with readings >= 2
  and a valid stored position at every one of the 25 grid points: 150, 180, 210,
  240 and 270 W at 75, 80, 85, 90 and 95 rpm. The padding covers the nominal
  80–90 rpm probes plus their ±1.2 rpm modeled drift. This is deliberately **not a claim that
  all 300 firmware cells, every possible cadence, or hardware behavior are known**.

Fixture training is a separate 90-minute ride through unmodified production
learning, using seed 137 and 216-second holds at those grid points. No table
cell is calculated from the physical model or inserted to manufacture coverage.
If training does not earn complete coverage, the tool reports that and does not
write a full fixture. Fixture hashes, training time, segments, seed, firmware,
adapter and profile identity are recorded. The fixture comes from the candidate
revision and is reused unchanged for baseline/candidate, isolating controller
behavior from differing initial tables. This is not a comparison of how the two
versions independently train from scratch; the empty-start rides cover that.

The adapter import is a **RAM snapshot persistence analogue**, performed before
first tick. Production flash save/load, serialized calibration trailers and
persistence reliability are not exercised. Learned table cells are restored;
controller confidence, timers, acquisition buffers and transient state start
fresh. During the timed ride, all those states evolve without restart.

## Measurements and interpretation

Every probe begins with the same 60-second 180 W / 85 rpm lead-in, then repeats
240 W, 150 W, 210 W at 80 rpm, 210 W at 90 rpm, and 180 W at 85 rpm. Entry motor
state can still differ; the lead-in reduces this confound but does not magically
make those histories identical. Scores include power settling, errors, oscillation
and overshoot, separately for effective plant and delivered meter power.

Table coverage is a read-only snapshot of actual stored cells. Learning-event
counts come from production logs and distinguish raw stable observations from
insertion attempts. They are **not all successful insertions**. Table/fallback
gain counts are sampled production logs, **not exhaustive lookup-call counts**.
Trusted seek events and time spent seeking are also reported. No arbitrary
learning-improvement threshold is used and later performance need not improve.

`--stress` adds a 12-second power-packet dropout and a 60-second zero-cadence
rider cue away from the repeated probes, without restarting controller/table state.
The rider decelerates and accelerates at its configured bounded rates; cadence is
not instantaneously forced to zero. Real FTMS pause/resume packets are sent too,
but those packets only change training/status in current production. The physical
pedaling interruption exercises actual low-cadence ERG and learning gates. Whole-ride scores include these
interruptions rather than hiding them. The existing provisional engineering
budgets apply to whole rides and each probe, including delivered-sensor scores;
a long steady section cannot erase a failing probe. These budgets remain
uncalibrated and a failure is not automatically a firmware defect.

Raw data remain at full resolution. Dashboard views may be reduced for display
only; source traces and learning evidence are the authoritative artifacts.
Radio, ESP32/FreeRTOS timing, flash persistence and mechanical fidelity remain
outside coverage. The fitted effective plant is an assumption, not independent
hardware truth.
