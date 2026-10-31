# Final local release review

Date: 2026-10-31. Version: 0.1.0.dev0. This draft remains unpublished, with no
Git remote configured. All review work is offline relative to the robot.

## Onboarding fixes

- Windows instructions now create and use a virtual environment explicitly,
  without requiring console tools on PATH or a PowerShell policy change.
- The guide distinguishes source/repository contents from the runtime-only wheel.
- Live status/cancellation/result paths must differ. Missing output directories
  and local status-publication failures are rejected before a controller connection.
- GUI help no longer needs Tk installed; a missing Tk/display produces an
  actionable message. The headless reader remains independent of Tk.
- Invalid, oversized or malformed local status files produce a FAILED display
  without reusing old values. Missing data produces WAITING. These states can
  recover when a valid local status file becomes available.

These changes do not change the fixed read request or add any controller command.
They have offline regression coverage. No new hardware validation is implied.

## Evidence review

The public CSV rows were compared against the retained original experiment
records, after shifting the counter origin. The retained receive streams were
decoded again and matched to their recorded joint replies. Pose-mark agreement
and distinct-tuple counts were checked locally without adding those poses to
the public files. The public verifier independently recomputes the exported
rate/latency arithmetic.

Hardware response timing remains an observed host metric. It is not a sample-age,
servo-rate, command-latency or long-duration-reliability guarantee. The host-pacing
explanation is labeled an inference. The report explicitly separates original
hardware experiments from subsequent offline packaging fixes.

## Installation and content review

Fresh Windows/Python 3.12 environments are used for the source installation and
built-wheel checks. Offline demo, request inspection, replay, plan-only probe,
benchmark and observer commands are checked with real sockets/DNS blocked.
The optional GUI's local-file behavior is tested without opening a GUI window.
No Linux/macOS qualification or physical rerun is claimed.

Tracked files and reachable Git history are checked for private identifiers and
unexpected files. The public source and packaged archives are inspected; archive
runtime/source hashes must match the reviewed manifest, not just pass a text scan.
Vendor SDK/header/schema/manual files, credentials, raw captures, recorded poses
and controller backups remain excluded. Synthetic fixture hashes remain separate
from measured timing data. Privacy pattern checks cannot prove the absence of
every conceivable identifying fact; no numerical hardware-performance claim is
used as a claim of general controller compatibility.

See [validation](validation.md) for the final test count and commands, and
[privacy](privacy.md) for the publication boundary. Raw review logs and the
private identifier list are kept outside this repository.
