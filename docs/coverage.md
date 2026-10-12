# Coverage and next priorities

This is a working first testing layer, not a claim that every user interaction is
covered. Tests exercise production behavior where listed; radio/board claims need
separate verification.

| User surface | Present evidence | Remaining work |
|---|---|---|
| ERG target steps, ramps, cadence changes | Accelerated real CPS/CSC packets → firmware callback/queue/collector/decoder → production controller → motor-pulse plant; paired deterministic metrics | Longer workouts, more independent bikes and calibrated acceptance bands |
| Different sensor rates, jitter, delay, outages | Independent acquisition/delivery clocks, immutable packet logs, equal fresh values, fixed scoring clock | Additional meter-specific estimator/filter models and recorded timing distributions |
| Sensor session behavior | Production queue bounds, callbacks, disconnect/reset, timeout and reconnect tests | Multiple device identities, discovery, pairing and real transport contention |
| FTMS app control | Actual request/start/target-power/stop processor; repeated/interrupted ERG, SIM, inclination and resistance transitions; signed downhill and queued ordering | Multi-app ownership and mode transitions in closed-loop physics; rejected ERG mode mutation fixed in firmware `782c2b5` and covered by normal passing regressions (including original-order mutation control) |
| Gearing web settings | Both shipped UI variants run their real JavaScript; presets and custom persistence round trips | Full browser/HTTP/session and accessibility workflows |
| Resistance, homing and thermal safety | Existing production behavioral/native tests retained; damping checks now response-based | Physical calibration, motor slip, electrical load and full firmware scheduling |
| Other sensors and firmware update | Existing sensor/protocol tests retained | Combined real-life sensor combinations, interrupted OTA and complete user journeys |
| Actual hardware | Optional real-BLE bench acquisition software and adapter contracts | No physical bench run yet; raw radio/ESP32 timing and real motion remain unverified |

## Useful next recording

Follow the [collectable real-bike capture procedure](capture-procedure.md): it
includes existing-build serial/UDP/web collection, a lossless local UDP recorder,
a short preflight, provenance/settings, a modest optional ride, and holdout/privacy
handling. One independent 15–20 minute ride is more useful than repeating the
fitting ride.

Default firmware exposes approximately 1 Hz runtime status and controller/FTMS
processing logs. It does not expose raw BLE callback arrival timestamps or a
continuous emitted-step trace. Optional compile-time sensor payload logs reflect
post-queue processing, including surviving equal BLE values, not raw arrival.
Software motor position does not measure actual knob motion/slip. Keep an entire
ride or predeclared contiguous segment out of fitting, and preserve these limits
when interpreting any improvement.
