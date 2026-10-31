# nachi-native-feedback

An unofficial Python implementation of a narrow Nachi native **joint-feedback**
profile. It connects directly to the XML service without loading an OpenNR SDK
library or uploading a custom controller program.

**Local release draft: 0.1.0.dev0. Not published.** Hardware evidence covers one
MZ07L-01 with a CFD controller running system V4.32. Other controller families,
firmware versions, options and operating modes have not been qualified.

The read-only hardware observer received **5,740 valid replies in 118.996 s**,
averaging **48.24 replies/s**, during pendant-controlled pose changes. Median
host request-to-complete-reply time was **2.48 ms**. These are observations from
one bounded run, not a controller maximum, source-sample rate or control-loop
latency guarantee. See [hardware results](docs/hardware-results.md).

## Included

- Fixed six-joint request, bounded framing/XML decoder and partial-read/write handling.
- Offline demo/replay, one-shot probe, stationary benchmark and bounded live observer.
- Optional local-file joint display, with stale/failure indicators.
- Offline tests, fabricated packet fixtures, sanitized measured timing rows and protocol notes.
- Standard-library runtime; pytest is a development dependency. The optional GUI needs Tk.

There is no motor, motion, playback, I/O-write, input-force, upload or controller
configuration implementation in this package. Ending observation does not stop
a robot. This project makes no manufacturer-approval or license-entitlement claim.

## Install and try offline

Python 3.12 or newer is required; validation currently covers Python 3.12 on
Windows. From this repository:

```console
python -m pip install ".[test]"
nachi-feedback demo --samples 20
nachi-feedback request
python -m pytest -q
python scripts/verify_results.py
python scripts/check_release.py
```

These commands do not contact a controller. The demo uses fabricated values.
To replay the derived fixture, which also contains fabricated joint values:

```console
nachi-feedback replay tests/fixtures/derived-response-shape.bin
```

## Plan a hardware observation

Start with [hardware use](docs/hardware-use.md). Configure and verify the network
separately; this package never changes adapter/firewall settings. Supply one
literal unicast IPv4 target. There is no DNS lookup, discovery or network scan.

The following addresses belong to a documentation-only range. Replace them
with your reviewed target and local interface address. **Without --execute,
these examples only display plans.**

```console
nachi-feedback probe --host 192.0.2.2 --source-address 192.0.2.10
nachi-feedback benchmark --host 192.0.2.2 --source-address 192.0.2.10
nachi-feedback live --host 192.0.2.2 --source-address 192.0.2.10 --latest-path runs/latest.json --cancel-path runs/cancel.request
```

Only an explicitly reviewed hardware action should add `--execute`. The probe
makes one connection and defaults to one read. The benchmark permits 250 reads
over three paced phases within 30 seconds. The live observer permits at most
6,000 reads over 120 seconds. There is no automatic reconnect or catch-up burst.
See the plan output for bounds; start with a stationary one-shot comparison.

The optional GUI reads the receiver's local JSON file and has no socket route:

```console
nachi-feedback-monitor --data runs/latest.json --cancel-path runs/cancel.request
```

## Evidence and limitations

- [Protocol](docs/protocol.md): observed envelope/selector, optional fields and parsing limits.
- [Hardware results](docs/hardware-results.md): measured rate/latency, scope and caveats.
- [Provenance](docs/provenance.md): upstream research references and independent implementation.
- [Privacy](docs/privacy.md): omitted site data and explicit fixture transformations.
- [Release notes](CHANGELOG.md): draft scope and unresolved work.

Native values numerically matched the tested pendant ANGLE display. Values are
returned unchanged; the package applies no ROS/model offset or radians conversion.
The response supplies no controller sample timestamp. Recent receipt does not
prove recent encoder acquisition. Successful reads do not establish permission
to operate the robot. Motor control and continuous steering are outside this release.

MIT licensed original implementation. Referenced third-party projects retain
their own terms; no vendor SDK, header, schema, manual, executable or license
record is distributed here. This repository is not affiliated with Nachi.
