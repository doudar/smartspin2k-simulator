# Collect a reproducible real-bike ride

This procedure collects what the existing firmware actually exposes. It does not
require a firmware change, an encoder, deliberate sensor disconnection, a sprint,
or an endstop experiment. A 15–20 minute independent ride can help assess model
transfer; it cannot by itself separate meter filtering, radio delay and mechanics.

Source audit: firmware commit `f836c058d5ab474c36ec6f9384256db70596ac5c`.
Older/newer builds must be identified and their available log formats checked.
No hardware capture has been performed to validate these instructions.

## What each timestamp and position means

| Record | Available in normal builds? | Meaning and limitation |
|---|---|---|
| `[milliseconds][level](module): ...` | Yes | Device `millis()` when the log is formatted, before delivery to log sinks; not host time or BLE callback arrival. |
| `W=… C=… H=… G=… R=… P=current->target` | Yes at this pin | Approximately one-second runtime snapshots. W is corrected/accepted runtime watts, C cadence, H heart rate, G gear/shifter position, R resistance. P is software current and commanded target position, not pulse-by-pulse telemetry or actual knob angle. |
| `ERG Mode Target: …` with response | Yes | FTMS command processing and response, later than original app send/callback receipt. Preserve errors and mode/target changes too. |
| ERG `Moving to`, seek/feedback messages | Yes | Controller decisions/state; a decision is not proof of completed physical movement. |
| Hex sensor payload plus `PW`, `CD`, `POS` | Only with compile-time `DEBUG_BLE_TX_RX` | Collector processing after dequeue, not BLE callback arrival. Surviving ordinary BLE notifications with equal values can appear separately; Peloton data is explicitly log-throttled to 1 Hz. |
| Raw BLE callback arrival timestamps / queue-loss count | No | Callback queues bytes/UUIDs without an arrival timestamp. Full queues can silently drop data. Do not create these columns from downstream logs. |
| True knob motion, backlash, slip, individual emitted pulses | No continuous trace | Requires separately synchronized physical instrumentation for a calibration claim. Software stepper position alone is insufficient. |

Equal runtime watts on consecutive one-second status lines do not prove new
notifications arrived. `Measurement::setValue` refreshes its value timestamp even
for equal values at this pin, but status lines do not expose that timestamp.
The optional sensor-processing log preserves equal processed observations without
making callback/radio timing observable. No available logging transport proves
losslessness: the shared appender buffer is bounded and UDP is best-effort.

## 1. Record provenance before riding

Keep a small, manually prepared `metadata.json` or text note beside the capture:

- Unique anonymous session label, e.g. `bike-a-ride-02`; label `calibration` or
  `holdout` **before** analysis. Do not include the rider's name.
- Bike/resistance mechanism and meter/cadence sensor model, meter firmware if
  known, power source and transport (CPS/FTMS/Peloton/etc.), controlling app and
  version, and whether cadence comes from the meter or a separate sensor.
- Installed firmware version, full source commit if known, board revision and
  build environment (`release`, `S3release`, etc.), plus any local modifications
  or custom build flags. A checkout SHA is not proof it was flashed; record how
  the installed image was identified. Mark unknowns honestly.
- ERG sensitivity, power correction factor, shift steps, motor speed/power,
  direction, minimum watts/resistance and travel limits, homing state, and
  whether PowerTable For Power is enabled. Record whether the power table is
  already learned; retain its starting artifact locally if already available.
  Never clear it or re-home just for this recording. Note settings changed
  during the ride and the approximate device-relative time.
- Logging transport, helper/simulator revision, known logging flags, meter
  zero-offset/calibration state, warm-up completed, and any normal mechanical
  changes since the fitting ride. Keep sensor simulation disabled for real data.

Read settings in the existing web Settings page. Do not share a full settings
export: `/configJSON` includes a `password` field. If an export already exists,
keep it private and manually extract only the required non-secret settings.
`/runtimeConfigJSON` is a read-only runtime snapshot, not a historical recording.
Neither endpoint needs polling during the ride.

## 2. Choose one primary capture transport

Start recording before the controlling app enters ERG. Keep the computer awake.
Do not flash firmware, alter network security, or change the computer's Wi-Fi
network just to gather a first capture. USB is preferable when already usable.
Opening a serial port may reset some boards; begin before pedaling and reject a
capture with an unexplained mid-ride reset.

### USB serial: existing firmware, no extra diagnostic flag

Firmware initializes serial at 115200 baud. Use the correct existing device port,
identified with `pio device list`, then from the firmware checkout:

```sh
pio device monitor -p <verified-port> -b 115200 --filter log2file
```

The monitor prints its output filename; retain that complete file and stop with
Ctrl-C. A serial terminal with explicit save-to-file is an equivalent option.
Do not open multiple monitors on the same port. Availability of USB CDC/UART
varies by board/build; confirm real status lines during the short validation
below rather than assuming a particular debug environment is necessary.
This command observes an already installed build and does not upload firmware.

### UDP: collect from the existing LAN

On the device Settings page, turn on **UDP Logging** and save, preserving the
other settings. The firmware broadcasts logs to `255.255.255.255:10000` only while
station Wi-Fi reports connected. Use the existing trusted LAN; client isolation,
firewalls or routed networks may block broadcasts. Do not weaken security to fix
this; use serial instead. This broadcast can expose log contents to other LAN
clients. Restore the prior UDP setting after collection.

From this simulator checkout (Python standard library only):

```sh
mkdir -p output/capture/bike-a-ride-02
python tools/capture_udp.py capture output/capture/bike-a-ride-02/ride.jsonl \
  --device-ip <verified-device-ip> \
  --firmware-sha <full-installed-firmware-source-commit>
# Stop with Ctrl-C after the ride, then inspect again if desired:
python tools/capture_udp.py inspect output/capture/bike-a-ride-02/ride.jsonl
```

Use the SHA of the **installed** build, not automatically the audit pin above.
The helper records this as user-reported, never hardware-verified. For a build
whose source SHA is unknown, use serial or web and clearly record that limitation.
`--duration 60` gives a one-minute sample. The helper refuses to overwrite an
existing file, preserves each selected-device datagram (including exact
duplicates and non-UTF-8 bytes in base64), and records host-relative monotonic
receipt time separately from firmware log time. The source IP is used to filter
but is not stored. Payloads can still contain private data. The listener writes
only to the local capture file and sends no commands to the bike.

The sequential record number is **host-created**, not a source packet counter;
it cannot reveal packets lost before receipt. It is not a BLE packet capture or a
direct input file for the simulator's existing FIT/log fitter.

### Web console: short fallback, not a full-ride archive

Open the device's existing `status.html` (Developer tools → Debug Console), then
**Save Debug Log**. It connects to `ws://<device-host>:8080`. There is no separate
UDP switch required for WebSocket logging. The page holds only about 1000 log
entries and discards older entries when full, so a final save can omit most of a
verbose ride. Use it for the short preflight or explicitly labeled partial
segments; do not present the final browser buffer as the whole ride.

### Optional diagnostic build, not required or performed here

`DEBUG_BLE_TX_RX` in `include/settings.h` enables processed raw-payload diagnostics
at compile time. It is commented out at the audit pin. Merely choosing a `debug`
build does not enable it, and there is no runtime toggle for it. A separately
authorized rebuild/flash could collect those diagnostics, with exact flags/image
recorded, but adds load and still provides no callback timestamps or queue-loss
counter. Do not modify or flash firmware as part of this default procedure.

## 3. Validate a short sample before committing to a full ride

Collect 30–60 seconds while using the bike normally at an easy effort. Inspect
locally; the UDP helper's summary is a sanity check, not a pass/fail certification.

- Verify repeated `W=… C=… … P=…->…` lines with plausible changing cadence/watts
  and approximately 1000 ms device-time intervals. Zero values while stopped are
  expected. Lack of `sensor_processing` records is normal in default builds.
- Enter ERG or make one small comfortable target change and confirm the
  `ERG Mode Target` line and response. `Responding: 80 05 01` indicates success
  for Set Target Power at this pin. Keep the original app workout/target plan;
  status `P=…->…` is a motor position target, **not target watts**.
- Check for a reset/backward firmware clock, long status gaps, missing target
  commands, serial corruption or app disconnections. The helper flags gaps over
  2500 ms and backward log timestamps; network reorder can also cause backwards
  timestamps, and `millis()` wraps after roughly 49.7 days. Split/review affected
  segments, do not silently interpolate away gaps or sort away resets.
- Preserve original order and all repeated values. Note observed stalls, slipping
  or unusual noise as rider observations, without treating them as measurements.

If these checks fail, fix the recording path before a full ride. Capture quality
and transport loss remain uncertain even when no gaps are detected.

## 4. Optional modest sequence

An ordinary ride is acceptable. If comfortable, after normal warm-up choose an
already comfortable easy/moderate ERG target and collect:

1. Two minutes of steady cadence near the rider's normal cadence.
2. Three comfortable cadence plateaus of 60–90 seconds each, e.g. 60/80/100 RPM
   only if all are normal and comfortable for this rider. Lower/narrower choices
   are fine; record achieved cadence rather than requiring these values.
3. A few small target increases/decreases, initially about 20 W, holding each
   for 60–90 seconds. Up to 50 W only if routinely comfortable. Stop a change
   that feels too hard rather than forcing cadence to meet it.
4. A gentle two-minute target ramp within the same comfortable range, then easy
   recovery. A return to a lower target already supplies a resistance reversal.

Do not seek mechanical limits, provoke faults, deliberately stall the rider or
motor, or attempt manual knob adjustments against a moving motor. Stop testing
if movement/noise/resistance is unexpected. There is no requirement to complete
any sequence or generate a failure.

## 5. Package, split and redact

Retain the complete original log privately. For analysis, store raw capture,
provenance note, target/workout plan, relative-time event notes and any optional
FIT export together under ignored `output/capture/<session>/`. Mark alignment
anchors and their uncertainty; firmware uptime, host monotonic time and FIT UTC
are distinct clocks. Do not infer subsecond alignment from 1 Hz FIT/status data.

Prefer a second entire ride as holdout. Freeze the simulator profile and
acceptance criteria before opening it for evaluation. If only one ride exists,
predeclare whole contiguous holdout segments with transition/warm-up buffers,
not randomly mixed adjacent samples. Learned firmware table state persists
within a ride: document that shared state. A holdout used for tuning becomes
calibration data; acquire or retain a different untouched holdout afterward.

Before sharing or committing any fixture, create and review a sanitized copy.
Remove passwords/secrets, SSIDs/IPs/MACs and device names that identify people,
GPS, absolute dates, usernames, and unrelated heart-rate/health fields (including
`H=…`, HR sensor packets and FIT fields). JSONL contains both text and base64 of
the same raw payload: removing text alone does **not** redact it. Decode, redact
and re-encode, or share a minimal derived dataset instead, documenting removed
fields. Keep timing/order/equal values and relative offsets unchanged. Do not
commit raw captures by default.

## Audited source references

All firmware links below are immutable at the audit pin:

- [Logging and serial timestamp path](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/SS2KLog.cpp), [log macros/buffer](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/include/SS2KLog.h)
- [BLE callback and bounded queue](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/BLE_Client.cpp), [dequeue path](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/BLE_Common.cpp), [collector and optional packet logs](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/SensorCollector.cpp)
- [Status snapshot and serial setup](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/Main.cpp), [measurement timestamps](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/include/SmartSpin_parameters.h), [software motor positions](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/Stepper.cpp)
- [FTMS command logs](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/BLE_Fitness_Machine_Service.cpp), [ERG decisions](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/ERG_Mode.cpp)
- [UDP broadcast](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/UdpAppender.cpp), [port](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/include/UdpAppender.h), [settings UI](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/data/settings.html)
- [Web console retention/export](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/data/status.html), [WebSocket port](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/include/WebsocketAppender.h)
- [Compile-time defaults](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/include/settings.h), [build environments](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/platformio.ini), [settings JSON fields](https://github.com/doudar/SmartSpin2k/blob/f836c058d5ab474c36ec6f9384256db70596ac5c/src/SmartSpin_parameters.cpp)
