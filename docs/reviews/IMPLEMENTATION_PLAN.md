# Error management and functional hardening

Authorized 14 October 2026. Baseline 2026.1.39, bcbc788.

## Stage 1: lifecycle ownership
- [x] Invalidate attachment initialization and async completions across detach/stop.
- [x] Prevent stopped event/outage coordinators accepting late work.
- [x] Regression tests and release.

## Stage 2: reporting and boundaries
- [x] Concise first/reminder/recovery reporting shared across runtime paths.
- [x] Guard SDK/timer/action boundaries; remove traceback output at every level.
- [x] GPIO uses shared output completion; no reads after failed writes.
- [x] Regression tests and release.

## Stage 3: availability and recovery
- [x] Native initialization failure has explicit status and bounded retry.
- [x] Logical I2C startup/provider loss publishes unavailability.
- [x] Server and channel outage persistence/cadence aligned.
- [x] Regression tests and release.

## Stage 4: functional corrections
- [x] Fahrenheit delta converts to SDK Celsius; formula arity checks.
- [x] Sensor action attribute, malformed preferences/configuration, VCP mappings.
- [x] Identity normalization and physical/device counts.
- [x] Regression tests and release.

## Stage 5: consolidation and maintenance
- [x] Shared polling fault lifecycle, retaining sensor-specific algorithms.
- [x] Outage cleanup, catalog TTL, test hook documentation, optional SDK handling.
- [x] Evaluate LCD diff rendering/startup polling/UI splitting against benefit/risk.
- [x] Full validation, release, live acceptance checklist.

Excluded: debug tracebacks in Indigo, generic decorator as recovery substitute,
custom distribution ZIP, broad rewrite. RFID history is already bounded.
Live hardware acceptance is recorded separately from automated evidence.

Stage 1 automated acceptance: 422 tests; version 2026.1.40. Live acceptance pending.

Stage 2 automated acceptance: 429 tests; version 2026.1.41.

Stage 3 automated acceptance: 434 tests; version 2026.1.42.

VCP4115/4116 mappings verified against installed SDK enums and vendor current units:
https://www.phidgets.com/?prodid=1286 and https://www.phidgets.com/?prodid=1374.
Unit mapping correction does not constitute hardware acceptance.

Test review: removed the validator source-line-count assertion and replaced its
architecture introspection with a malformed-row-count behavior regression. A
function's length was not a meaningful correctness requirement.

Stage 4 automated acceptance: 441 tests; version 2026.1.43.

Stage 5 decisions:
- Shared peripheral fault/recovery handling; GPIO and I2C LCD use common native
  completion/initialization retry behavior. No separate one-second LCD retry loop.
- I2C LCD frames use changed-cell writes; failed transfers invalidate the display
  cache and require a full redraw. HD44780 character ROM mapping is retained
  because ROM variants differ; no untested accented-character translation added.
- First sensor poll remains synchronous to preserve model metadata and dynamic
  state creation. The guarded path retains a retry if publication fails.
- Extract diagnostic menus, retain focused validators/menu builders. Further
  monolithic UI reorganization offers little defect-reduction benefit here.
- Keep atomic/fsynced outage writes for immediate crash-safe records; file I/O
  still runs synchronously. A worker/persistence rewrite is not justified without
  evidence of actual disk stalls. Cleanup handles deleted/obsolete devices.
- Firmware override documented as administrative, temporary and read-only.
- Dependency-install tests now model a supported Indigo host independently of
  the test machine's filesystem; no supported-host runtime advice was changed.
- Simulator-specific RFID behavior and sensor algorithms retained.

All code stages completed. Automated acceptance and published version recorded
in FINAL_ACCEPTANCE.md. Live hardware acceptance remains pending; it cannot be
claimed from mock-based testing.

Stage 5 automated acceptance: 453 tests; version 2026.1.44.
