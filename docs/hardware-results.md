# Hardware observations

Evidence covers one MZ07L-01 / CFD system V4.32 on a direct Ethernet link to a
Windows Python client. These are experiment results, not a compatibility or
performance claim for every Nachi controller. Site identity and recorded poses
are omitted. [Sanitization](privacy.md) explains exactly what changed.

The measurements predate release packaging and final-review improvements to
local-file validation, CLI checks and display error handling. Those improvements
have offline regression coverage, not an additional hardware run. The fixed
233-byte read request remains unchanged. The reported timings describe the
original experiments, not a fresh benchmark of every release revision.

## First stationary snapshot

One connection, one fixed 233-byte request, one complete 324-byte response.
All six native values matched the immediately reported pendant ANGLE values
when rounded to two decimal places; maximum absolute rounding difference was
0.004498 in that display scale. No conversion/model offset was used. The
operator reported a responsive pendant and no new alarm. The first run's coarse
host clock did not support a latency claim; later runs used a high-resolution
performance counter.

## Stationary paced benchmark

250 requests and 250 valid replies, one connection, 16.961 seconds of collection.
There were no observed protocol errors/timeouts in this run. Each phase excludes
its first five replies from the following steady statistics:

| Requested pacing | Steady replies | Measured replies/s | Median transaction | p95 transaction |
| --- | --- | --- | --- | --- |
| 5 Hz | 45 | 4.983 | 2.396 ms | 2.846 ms |
| 20 Hz | 95 | 19.757 | 2.310 ms | 2.887 ms |
| 50 Hz | 95 | 48.430 | 2.350 ms | 2.856 ms |

In the 50-Hz phase the mean reply interval was 20.648 ms and the mean request
interval 20.655 ms. This supports the inference that host pacing explains much
of the difference from 50 Hz; it is not an isolated causal measurement. It does
not determine the controller's maximum rate. The highest-rate
phase had 100 total replies over approximately two seconds. Unchanging stationary
positions do not establish acquisition freshness.

The published [stationary timing CSV](../results/stationary-timing.csv) contains
all 250 timing rows. Timestamps have a zero-based origin; durations are unchanged.

## Pendant-controlled pose observation

- **5,740 valid replies in 118.996 seconds**, averaging **48.238 replies/s**.
- Median host transaction: **2.483 ms**; p95 **2.961 ms**; maximum **4.649 ms**.
- Largest recorded receive interval: **29.997 ms**.
- The private joint records contained 705 distinct six-joint tuples. Two locally
  marked poses matched their corresponding decoded samples.
- The operator reported that displayed values followed pendant movement, with
  no alarm/frozen display, and confirmed the arm stopped and secured afterward.
- One connection, only repeated fixed joint reads; no custom controller program
  or motion/motor/I/O-write/configuration request was used.

All 5,740 replies were independently decoded and compared with the stored records
before export. Six isolated local display-file publication attempts failed;
later publications recovered. These were display-publication failures, not
missing decoded replies. They are retained as a limitation rather than hidden.

The [pose-observation timing CSV](../results/pose-observation-timing.csv) preserves
all 5,740 timing rows with a shifted clock origin. It contains no joint positions.
Its `transaction_ms` measures the send/reply path; `reply_ms` is the later recorded
receipt/processing timestamp. Do not treat these as identical clock boundaries.

## Reproduction and limits

`python scripts/verify_results.py` recomputes the published rate/latency statistics
and checks CSV hashes/counts. The machine-readable summary is
[hardware-summary.json](../results/hardware-summary.json).

These public files allow verification of exported timing arithmetic. Original
private captures and pose records are not distributed, so readers cannot
independently establish hardware authenticity, the 705-tuple count or pendant
agreement from the public timing rows alone. Those remain reported observations
supported by retained private evidence. Public packet fixtures use fabricated
positions and must not be presented as untouched captures.

The observations do not establish controller sample age, motion-to-feedback
delay, command latency, hard real-time operation, maximum controller throughput,
long-duration reliability or laptop-issued motion. No command-control performance
is claimed. Testing another configuration requires its own reviewed bounded test.
