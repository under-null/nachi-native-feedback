# Planning an observation

This release reads one fixed native joint profile. It does not configure or
qualify your installation. A robot's ordinary controls, safeguards and operating
procedures remain independent of the laptop observer.

1. Review the controller model/firmware and protocol note. Only one CFD V4.32
   installation has been observed. Do not infer FD/CFD interchangeability.
2. Identify one controller IPv4 address and the appropriate Ethernet interface.
   Configure and verify that network outside this tool; never scan for a robot.
3. Begin with a stationary test in a secured local state: motors off, emergency
   stops engaged, covers closed, programs/tasks stopped, and a local operator
   able to observe the pendant. Do not change a controller permission to make a
   read work without understanding the setting.
4. Generate and review a probe plan. Its default is one connection/one request,
   a two-second response timeout and a five-second overall limit. An agent
   requires specific user approval before adding --execute or connecting.
5. Compare all six returned numbers with the pendant's current ANGLE display.
   Record any mismatch, timeout, unsupported response or controller message.
   Do not compensate with a guessed offset or different field selector.
6. Only after that comparison consider a separately reviewed stationary benchmark
   or observer. Any pendant-operated movement is owned by the local operator and
   requires its own appropriate physical procedure. This tool cannot stop it.

The example addresses in README are documentation-only placeholders. The package
opens a single TCP connection only with --execute and only to the supplied literal
IPv4 endpoint. Source binding is optional for the one-shot probe and required for
the benchmark/live receiver; connected endpoints are checked before application
traffic. There is no authentication/cryptographic controller identity claim.

The benchmark is fixed at 50 reads paced at 5 Hz, 100 at 20 Hz and 100 at 50 Hz,
with a one-second response deadline and 30-second total limit. The observer uses
at most 6,000 fixed reads, a 50-Hz target and a 120-second limit. Slow replies
reduce throughput; missed slots do not trigger catch-up bursts or reconnects.

For live observation, use a new directory under ignored `runs/`, ensure no old
cancel marker exists, and create the output directory before starting the receiver.
Status and cancellation paths must be distinct files; a result `--output` path
must also differ. The receiver verifies local status publication before opening
a socket, so a missing directory or local write failure does not contact hardware.
The GUI reads only its JSON data file. Its Stop button writes a local cancellation
marker. Closing the GUI also requests cancellation. Neither action sends a
controller stop command. Readings expire rather than remaining apparently live.
Malformed, oversized or invalid local status files display FAILED; a missing
status file displays WAITING. The display does not substitute its previous values
for unreadable current data.

Generated JSON can include the endpoint, local endpoint, recorded poses and raw
reply bytes. Those are useful locally but are **not public-ready by default**.
Keep them in `runs/`; use the documented sanitization model before sharing data.
Do not upload a private controller backup or packet capture as an issue attachment.
