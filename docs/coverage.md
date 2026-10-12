# Coverage and next priorities

This is a working first testing layer, not a claim that every user interaction is
covered. Tests exercise production behavior where listed; radio/board claims need
separate verification.

| User surface | Present evidence | Remaining work |
|---|---|---|
| ERG target steps, ramps, cadence changes | Accelerated real CPS/CSC packets → firmware callback/queue/collector/decoder → production controller → motor-pulse plant; paired deterministic metrics | Longer workouts, more independent bikes and calibrated acceptance bands |
| Different sensor rates, jitter, delay, outages | Independent acquisition/delivery clocks, immutable packet logs, equal fresh values, fixed scoring clock | Additional meter-specific estimator/filter models and recorded timing distributions |
| Sensor session behavior | Production queue bounds, callbacks, disconnect/reset, timeout and reconnect tests | Multiple device identities, discovery, pairing and real transport contention |
| FTMS app control | Actual request/start/target-power/stop processor and response tests | Every FTMS procedure, multi-app ownership and all mode transitions in the closed loop |
| Gearing web settings | Both shipped UI variants run their real JavaScript; presets and custom persistence round trips | Full browser/HTTP/session and accessibility workflows |
| Resistance, homing and thermal safety | Existing production behavioral/native tests retained; damping checks now response-based | Physical calibration, motor slip, electrical load and full firmware scheduling |
| Other sensors and firmware update | Existing sensor/protocol tests retained | Combined real-life sensor combinations, interrupted OTA and complete user journeys |
| Actual hardware | Optional real-BLE bench acquisition software and adapter contracts | No physical bench run yet; raw radio/ESP32 timing and real motion remain unverified |

## Useful next recording

One independent 15–20 minute ride is more useful than repeating the fitting ride.
Record bike and sensor model, exact firmware/settings and calibration state, raw
sensor packet arrival timestamps (including equal consecutive values), target
commands, and emitted motor steps/position logs. Use steady 60/80/100 RPM sections,
modest ±20/±50 W steps, a gentle ramp and a few resistance reversals. No risky
sprint or endstop experiment is needed.

Keep one segment or a second ride completely out of model fitting. Ordinary 1 Hz
status logs cannot distinguish estimator lag from packet delay or fresh equal
readings. Software step counts do not establish actual knob motion/slip; use an
independent encoder if that physical distinction is being calibrated. Strip
identity, GPS, absolute dates and unrelated health data from committed fixtures.
