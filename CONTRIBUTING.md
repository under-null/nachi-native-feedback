# Contributing

Run the offline tests, result verifier and release-content check before a change.
Tests must not contact a robot or change networking. A passing simulated test
does not qualify an additional controller or permit a physical operation.

For compatibility reports, include controller family, firmware, robot model,
the fixed-request hash, observed XML field structure and measured host timing.
Separate observed behavior from inference. Omit serials, credentials, license
data, MAC/site addresses, personal paths, controller backups and recorded poses.
Do not attach raw captures until their complete contents have been reviewed.

New field selectors or write operations belong to separately reviewed research;
do not silently expand this release's fixed read profile. Preserve the one-
outstanding-request, bounded duration and no-reconnect behavior. Make unsupported
responses explicit rather than inventing values or retrying a different command.

This implementation was informed by SDK interoperability research; it is not
presented as a formal clean-room implementation. Credit upstream research and
respect the terms of any material you propose to include.
