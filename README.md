# nachi-native-feedback

Created and maintained by [@under-null](https://github.com/under-null).

An unofficial Python implementation of a narrow Nachi native **joint-feedback**
profile. It connects directly to the XML service without loading an OpenNR SDK
library or uploading a custom controller program.

**Development preview: 0.1.0.dev0. Read-only feedback.** Hardware evidence covers one
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
Windows. Install Python with pip and, if you want the optional GUI, Tcl/Tk
support. Get the source with Git, or download and extract the source from the
repository's Code menu:

```console
git clone https://github.com/under-null/nachi-native-feedback.git
cd nachi-native-feedback
```

Check `python --version`, then open PowerShell in that directory.
These commands use a virtual environment directly, so activation and changes
to PowerShell execution policy are unnecessary:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[test]"
.\.venv\Scripts\python.exe -m nachi_native_feedback demo --samples 20
.\.venv\Scripts\python.exe -m nachi_native_feedback request
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/verify_results.py
.\.venv\Scripts\python.exe scripts/check_release.py --verify-manifest
```

The first install may download build/test dependencies. These commands do not
contact a controller. The demo uses fabricated values. For a runtime-only
install, omit `[test]`; the package itself has no third-party runtime dependency.
The same package layout supports `python -m nachi_native_feedback` when console
aliases are not on PATH. On other systems a virtual environment usually places
Python under `.venv/bin/python`; those platforms remain unqualified here.

To replay the derived fixture, which also contains fabricated joint values:

```powershell
.\.venv\Scripts\python.exe -m nachi_native_feedback replay tests/fixtures/derived-response-shape.bin
```

A wheel installation supplies the runtime commands. The repository or source
archive additionally supplies the fixture, tests, notes and result-verification
scripts used above.

## Plan a hardware observation

Start with [hardware use](docs/hardware-use.md). Configure and verify the network
separately; this package never changes adapter/firewall settings. Supply one
literal unicast IPv4 target. There is no DNS lookup, discovery or network scan.

The following addresses belong to a documentation-only range. Replace them
with your reviewed target and local interface address. **Without --execute,
these examples only display plans.**

```powershell
.\.venv\Scripts\python.exe -m nachi_native_feedback probe --host 192.0.2.2 --source-address 192.0.2.10
.\.venv\Scripts\python.exe -m nachi_native_feedback benchmark --host 192.0.2.2 --source-address 192.0.2.10
.\.venv\Scripts\python.exe -m nachi_native_feedback live --host 192.0.2.2 --source-address 192.0.2.10 --latest-path runs/session-01/latest.json --cancel-path runs/session-01/cancel.request
```

Only an explicitly reviewed hardware action should add `--execute`. The probe
makes one connection and defaults to one read. The benchmark permits 250 reads
over three paced phases within 30 seconds. The live observer permits at most
6,000 reads over 120 seconds. There is no automatic reconnect or catch-up burst.
See the plan output for bounds; start with a stationary one-shot comparison.

Before an approved live execution, create a new local run directory; do not
reuse a previous run's cancellation marker. Status, cancellation and optional
`--output` result paths must be distinct. Local status-publication failures are
checked before a connection is attempted.

```powershell
New-Item -ItemType Directory -Path runs/session-01
.\.venv\Scripts\python.exe -m nachi_native_feedback.live_monitor --data runs/session-01/latest.json --cancel-path runs/session-01/cancel.request
```

The optional GUI reads only the receiver's local JSON file. Run it in a second
terminal using the same environment and paths. It displays WAITING until data
arrives; it does not start the receiver. Tcl/Tk is optional for the rest of the
package. `python -m nachi_native_feedback.live_monitor --help` works without it.
After virtual-environment activation, `nachi-feedback` and
`nachi-feedback-monitor` are equivalent console aliases.

## Evidence and limitations

- [Protocol](docs/protocol.md): observed envelope/selector, optional fields and parsing limits.
- [Hardware results](docs/hardware-results.md): measured rate/latency, scope and caveats.
- [Provenance](docs/provenance.md): upstream research references and independent implementation.
- [Privacy](docs/privacy.md): omitted site data and explicit fixture transformations.
- [Release notes](CHANGELOG.md): draft scope and unresolved work.
- [Final review](docs/release-review.md): reproducibility, evidence and privacy checks.

Native values numerically matched the tested pendant ANGLE display. Values are
returned unchanged; the package applies no ROS/model offset or radians conversion.
The response supplies no controller sample timestamp. Recent receipt does not
prove recent encoder acquisition. Successful reads do not establish permission
to operate the robot. Motor control and continuous steering are outside this release.

MIT licensed original implementation. Referenced third-party projects retain
their own terms; no vendor SDK, header, schema, manual, executable or license
record is distributed here. This repository is not affiliated with Nachi.
