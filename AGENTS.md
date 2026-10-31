# Repository instructions

This is a read-only feedback project. Normal development and tests are offline.

- Do not contact a controller, scan, change networking/firewalls or execute a
  hardware command without explicit approval for that exact action.
- Default CLI commands must remain plan-only. --execute is an operator opt-in,
  not standing approval for an agent to contact hardware.
- Keep the fixed joint-read profile separate from operations, I/O writes, motor
  control, file transfer, controller programs and configuration changes.
- Do not bypass controller licensing, safety functions, permissions or passwords.
- Tests must block real sockets and DNS; fake streams model transport behavior.
- Do not add vendor files, credentials, site addresses, private paths, controller
  backups or recorded poses. Results use an explicit sanitization scheme.
- Label synthetic fixtures and hardware observations separately. Host reply
  timing does not establish data acquisition age, command latency or servo rate.
- Preserve provenance and distinguish one tested firmware from broader support.
