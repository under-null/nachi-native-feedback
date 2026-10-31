# Public data boundary

The release is assembled by file allowlist, not a copy of the development
workspace. It contains original reader code, tests, documentation, derived
fixtures and selected experimental metrics.

## Removed or never included

- Names, personal filesystem paths, machine names, site IP/MAC addresses and
  original wall-clock/counter origins.
- Recorded robot joint poses, full controller backups, configuration files,
  physical wiring media, PLC projects and raw network/session captures.
- Credentials, license records, vendor manuals/help, headers, XSD schemas,
  SDK libraries, executables and downloaded third-party archives.
- Native motion, I/O-write, program-upload and controller-setting tools.

## What remains measured

`results/*.csv` retain the original timing durations and relative order. Each
run's host counter origin is shifted to zero. All rows are retained; warmup
exclusion is applied only when computing the documented steady statistics.
Counts, byte totals, transaction times and local publication-failure counts
in the summary come from the original experiment. Model/firmware/platform
information is retained because it is necessary to interpret compatibility.

No new controller measurement was made while preparing the release. The timing
exports are not fabricated; the fixture positions are. That distinction is
explicit in the summary, fixture README and hardware report.

## Fixtures and reproduction

The response-shape fixture replaces every recorded joint number with a fabricated
number, preserves the XML structure and rebuilds the envelope. Its new hash is
checked by the tests. The other joint fixtures/demo values are synthetic too.
No public fixture contains the original physical pose. Public timing arithmetic
is reproducible; full pose/raw-capture claims require the retained private evidence.

`scripts/check_release.py` checks the intended source tree and optional wheel/
source archives for private-path patterns, site-looking endpoints, MAC addresses,
credential patterns and unexpected binary/vendor files. It is a content check,
and packaged file hashes must agree with the reviewed manifest. It is not a
guarantee against every possible form of private information. `.gitignore`
also excludes generated runs and local captures. Review staged files before a
future publication; a local recording is not automatically safe to redistribute.
