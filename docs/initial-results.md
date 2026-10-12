# Initial paired packet experiments

Baseline firmware: `082d1ee26ddb009d5132547087f77be03d1b0ab7`. Candidate/adapter firmware commit: `f836c058d5ab474c36ec6f9384256db70596ac5c` on `erg-spike-gate`. Its production controller sources are unchanged from `83505906b31461294c0ead58e2fe7368259199a9`; the commit changes testing only. Both revisions used the same reviewed packet adapter and independent simulator.

All 18 comparisons stayed inside the predeclared relative regression allowances. Nine meet both provisional absolute quality budgets. These are modeled experiments, not hardware or independently validated physical claims. No thresholds were widened to obtain these results.

The scoring clock observes continuous effective plant power independently of sensor sampling/delivery. The delivered sensor signal is scored separately. Its latency/noise means it can fail a band that the plant signal meets.

| Scenario | Seed | Plant MAE baseline → candidate (W) | Plant p95 candidate (W) | Delivered p95 candidate (W) | Absolute + relative |
|---|---:|---:|---:|---:|---|
| steps | 7 | 9.19 → 8.75 | 39.38 | 57.00 | pass |
| steps | 27 | 8.97 → 9.04 | 39.64 | 71.00 | outside provisional band |
| steps | 91 | 9.34 → 9.52 | 41.48 | 71.00 | outside provisional band |
| ramp | 7 | 13.35 → 12.43 | 23.54 | 35.00 | pass |
| ramp | 27 | 12.26 → 11.78 | 21.85 | 35.00 | pass |
| ramp | 91 | 13.18 → 12.81 | 25.21 | 33.00 | pass |
| cadence_shift | 7 | 16.66 → 16.51 | 47.72 | 61.00 | outside provisional band |
| cadence_shift | 27 | 15.05 → 14.76 | 44.77 | 49.00 | pass |
| cadence_shift | 91 | 13.86 → 13.94 | 44.80 | 50.00 | pass |
| slow_power | 7 | 14.15 → 14.15 | 79.75 | 87.00 | outside provisional band |
| slow_power | 27 | 13.02 → 13.02 | 65.69 | 76.00 | outside provisional band |
| slow_power | 91 | 12.35 → 12.35 | 61.10 | 93.00 | outside provisional band |
| fast_power_slow_cadence | 7 | 18.27 → 15.51 | 43.38 | 49.00 | pass |
| fast_power_slow_cadence | 27 | 20.37 → 15.63 | 46.21 | 50.00 | pass |
| fast_power_slow_cadence | 91 | 20.33 → 15.61 | 41.58 | 58.00 | pass |
| sensor_outage | 7 | 8.54 → 8.04 | 28.74 | 68.00 | outside provisional band |
| sensor_outage | 27 | 8.65 → 8.11 | 39.15 | 81.00 | outside provisional band |
| sensor_outage | 91 | 9.19 → 8.52 | 42.72 | 84.00 | outside provisional band |

The slow-power scenarios miss the 60 W plant p95 band on both revisions, mainly around target transitions. Several delivered-sensor p95 bands also fail. Steady-state and settling values are retained in each score rather than excluding transition errors from the full-ride grade.

A prior development run had an unintended hidden 1 Hz acquisition bottleneck and mixed delayed sensor power with plant scoring. Its numerical conclusions are superseded; they are not used as acceptance evidence. Tests now explicitly verify that fast acquisitions observe a continuously changing plant even when the legacy reporting clock has not ticked.

Validation: 87 firmware-side Python tests passed, with one optional test skipped and two expected failures documenting existing CSC decoder rollover defects. The native firmware test suite passed 79 cases. A compiled closed-loop negative control with stuck motor pulses is rejected. The standalone package also passes all 32 tests with its native negative control enabled. Radio, ESP32 scheduling and physical bench validation were not performed.

Reproduce with `python -m ss2k_sim compare` and the explicit firmware adapter/baseline/candidate paths documented in the README. Full run artifacts include raw packet/acquisition/delivery logs, independent power traces, all per-seed metrics and source/adapter fingerprints.
