# High-power early-prefix diagnostic

This is a short, paired tuning experiment for 500/700/1000 W efforts. It does not
change the published 90-minute experiment, its `full` fixture covering 45 declared training-grid cells, the fitted
plant, or existing acceptance budgets/history semantics.

## Run

Use one frozen baseline selection for the whole tuning experiment. Follow the
baseline selection instructions in the README once, then pass that same JSON to
every invocation. The trusted adapter must support `Bridge.load_power_table` for
full-fixture runs; both controller revisions use exactly that same adapter.

```sh
python -m ss2k_sim.high_power \
  --firmware-root ../firmware-adapter \
  --baseline-root ../firmware-baseline \
  --candidate-root ../firmware-candidate \
  --baseline-selection ../baseline-selection.json \
  --fixtures ../archived-training \
  --targets 500 700 1000 \
  --states empty full --sensitivities 3 5 10 --seeds 7 \
  --output output/high-power-001
```

`--fixtures` contains the original earned `full.json`. Its table digest, plant
profile, coordinate reference and original 45-cell coverage are checked. The
entire fixture and original provenance are retained in the result. It is reused
unchanged for baseline and candidate; it is never retrained by this command.
Additional seeds and targets above 240 W up to 1000 W may be supplied explicitly.
The defaults are the 18 cases formed by 3 targets × 2 initial states × 3
sensitivities, with seed 7.

Every case starts a fresh controller and runs for 445 seconds:

- The exact published six-minute early probe, including its six ≤240 W steps
- 100 W for 30 seconds at the original cadence
- The selected high target for 25 seconds
- 100 W recovery for 30 seconds

The rider cadence, noise seed, sensor schedules and initial table are identical
for each firmware pair. Only the sprint target differs across target cases. The
six-minute prefix preserves learning/confidence and controller history before
the sprint; a fresh 30-second-only lead-in would miss that behavior. A read-only
table snapshot is recorded at sprint entry without resetting the controller.

## Output and definitions

`high_power.json` records input provenance, each paired case, metadata, existing
scores, low-power comparisons, and the new diagnostics. Individual run folders
retain traces, firmware logs, sensor packets, FTMS commands, table snapshots, and
`diagnostic.json`. Results are checkpointed after each paired case.

Each signal is evaluated separately: continuous effective plant output and the
last delivered CPS sensor power. No smoothing, plant refit, or noise reduction
is applied. Each sprint and recovery reports peak power, overshoot, undershoot,
MAE and the following for **both ±10 W and ±20 W**, with inclusive boundaries:

- `first_entry_s`: first in-band sample, even if it immediately leaves again
- `first_dwell_entry_s`: start of the first uninterrupted five-second in-band run
- `first_dwell_confirmed_s`: entry plus five seconds
- `final_settling_s`: start of the final in-band run through phase end, provided
  that run lasts at least five seconds
- Seconds above, below, and outside each band
- Count, duration and maximum error of later excursions after the first dwell
  was confirmed

Missing entry/dwell/settling is JSON `null`. Later-excursion fields are `null`
when no first dwell was confirmed. An early successful dwell followed by an
excursion is therefore never silently reported as final stability. Timing uses
the independent trace clock, with samples held until the next sample and the
last interval clipped at phase end, matching existing score integration.

`rise_to_90pct_target_s` is the first sprint sample at or above 90% of the absolute
requested target (450, 630 or 900 W for the defaults). It is not a settling time
or a percentage of the 100 W-to-target step amplitude. Recovery has no rise
metric; its ±10/20 W entry and dwell metrics describe return to 100 W.

The predeclared goal is final ±10 W settling entry **strictly below 10 seconds**,
confirmed by at least five in-band seconds and no later excursion during the
phase. This descriptive goal is separate from existing ±20 W budgets. The
six-minute prefix also gets per-segment ±10/20 W diagnostics and the unmodified
existing absolute/relative regression comparison on both signals.

Exit status 0 means the run completed and the existing low-power prefix budgets
passed. Absolute and relative results are also reported separately, so a baseline
that already fails an absolute budget is not mislabeled as a candidate regression.
Status 1 means those budgets failed; errors have a nonzero status. A
completed diagnostic or exit 0 does **not** claim that the high-power goal was
met: inspect the explicit goal and settling fields for every case/signal.

## Coverage limits

The archived `full` fixture is reused byte-for-byte and covers the original 45 declared
training-grid cells, including the 480/510 W brackets; it may contain other
incidentally learned cells. It does not mean the whole table, a
690/720 W bracket, or support for 1000 W. The report describes actual supported
bracket cells at sprint entry separately, after the shared low-power prefix.
The current 30-column × 30 W table ends at 870 W; 1000 W is beyond its axis and
cannot be a full-bracket learned target. No added or fabricated high cells are
silently included in `full`.

Ingress is production CPS/CSC packet processing and FTMS control in a native
adapter, **not Peloton cable measurement windows**. The effective plant is a
ride-fitted model; metadata retains its original fitted-position/cadence range
and time outside that range. High-target extrapolation remains model-dependent.
This short screen must be followed by unchanged long-ride and real-bike checks
before drawing conclusions about middle/late learning, cable behavior, hardware
timing or mechanical fidelity.
