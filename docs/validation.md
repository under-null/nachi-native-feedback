# Release validation

Version: 0.1.0.dev0, local unpublished draft. The extracted package passes
**813 offline tests** on Python 3.12 / Windows. Tests prohibit real sockets and
DNS; transport tests inject fake streams. The optional GUI is not opened during
tests. GUI help works without Tk; Tk is imported only after argument/path checks
when a display is actually requested.

Coverage includes every two-chunk boundary and truncated EOF of a synthetic
frame, coalescing, malformed headers/XML/numbers, optional reply fields, partial
writes, timeouts, bounded pacing, no automatic reconnect/catch-up, cancellation,
receipt freshness, publication failure, malformed display files, local-output
preflight, reviewed archive contents and plan-only defaults. A passing test
count is not a controller compatibility or safety certificate.

`scripts/verify_results.py` also checks all **250 stationary** and **5,740
pose-observation** timing rows, exported file hashes, phase/warmup counts,
byte totals and reported rate/latency arithmetic. It does not authenticate the
hardware from private raw evidence that is deliberately not distributed.

`scripts/check_release.py` checks the source tree and packaged archives for
unexpected content and common private-data patterns. The separate preparation
review additionally compares against private identifiers outside this repository.
No private identifier list is embedded in the public checker. Archive checks also
require the package contents/hashes to match the reviewed source manifest.

The final review independently rechecked all 5,990 timing rows against retained
private source records, decoded all 5,990 corresponding raw reply frames, and
checked the reported 705 distinct tuples and two pose marks. These private
records remain excluded. See [the review](release-review.md) for the distinction
between public arithmetic checks and retained hardware evidence.

The source manifest records SHA-256 for every intended release file except the
manifest itself. Verify it with:

```console
python scripts/check_release.py --verify-manifest
```

For future changes, rerun tests/result checks and regenerate the manifest before
building. Use the current source rather than treating this recorded count as
evidence about later modifications:

```console
python -m pip install ".[test]"
python -m pytest -q
python scripts/verify_results.py
python scripts/check_release.py --write-manifest
python -m pip install build
python -m build
```

The wheel contains the runtime package and its license/metadata; the source
archive additionally contains tests, notes and sanitized timing results. A
package build does not contact or qualify a physical controller.
