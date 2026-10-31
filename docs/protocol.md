# Implemented native feedback profile

This is an interoperability note for one observed CFD V4.32 installation. It is
not a complete OpenNR specification. It describes our independent reader and
the experiment that qualified this fixed request. [Provenance](provenance.md)
distinguishes vendor-authored reference material, community-hosted files and
our hardware observations. No vendor file is needed to run the package.

## TCP envelope

| Byte offset | Width | Encoding | Observed meaning |
| --- | --- | --- | --- |
| 0 | 2 | little-endian unsigned | Magic 0xBA5E, bytes `5e ba` |
| 2 | 2 | little-endian unsigned | Version 1, bytes `01 00` |
| 4 | 4 | little-endian unsigned | XML payload length in bytes |
| 8 | length | UTF-8 | XML document, no trailing NUL in transmitted length |

TCP receive calls are not message boundaries. The decoder retains partial
headers/bodies and accepts coalesced envelopes. Its **client policy** caps a
payload at 65,536 bytes; that is not a measured server maximum. Invalid magic,
version, lengths or truncated EOF fail the stream without resynchronization.

The tested service used TCP port **9876**. A Nachi vendor example independently
shows NR_DATA_XML/NR_Open with port 9876: NACHI TECHNICAL REPORT Vol.34 B3,
October 2018, edition not stated, **PDF p. 6, printed p. 5**, Figure 6.
This does not prove the service or an option is available on another controller.

## Fixed request

The exact payload is 225 bytes; its envelope is 233 bytes:

```xml
<flexData version="1" xmlns="flex.gui"><dataExchange><dataRequest><data unit="1" group="Generic" id="SYSTEM!" subid="400" extid="-1" count="6" push="-1" threshold="0.01" priority="5" /></dataRequest></dataExchange></flexData>
```

Frame SHA-256:
`db6fc43322cdaf97a741ce5691f0ff4a512d511877b41f5d0179b0f9e3b34ecc`.
`nachi-feedback request` prints this request without opening a socket.

The independently audited NR_AcsAxisTheta implementations identify this unit-1
selector as Generic/SYSTEM!/400, six values. The general unit-number mapping
seen in those libraries is not exposed as an arbitrary selector in this release.
`push=-1` requests pull behavior; XML priority 5 is not a USER-TASK priority.

The tested minimal exchange succeeded without a separate startup handshake.
That is a result for this profile/installation, not a rule for other native
operations or firmware. The reader does not guess negotiation packets, answer
heartbeats, register a push stream or fall back to another protocol.

## Reply and values

The observed response contained `flexData/dataExchange/dataUpdate/data`, with
unit 1, group Generic, id SYSTEM!, subid 400, count 6, followed by six `r` elements.
It omitted both `seqid` and `extid`; the reader permits those omissions, treats
absent extid as -1 and leaves sequence identification unknown. An optional UTF-8
declaration appeared before flexData. The recorded response was 316 XML bytes /
324 envelope bytes.

The derived fixture in `tests/fixtures/derived-response-shape.xml` preserves that
layout, with **all six joint numbers replaced by fabricated values**. Its binary
envelope is regenerated; it is not an original captured packet. The separate
synthetic joint fixture deliberately exercises explicit seqid/extid attributes.

Returned numbers matched the pendant's ANGLE display at two-decimal precision
in the stationary comparison. The client returns the native numbers unchanged.
It applies no J2 model offset or radians conversion and does not set
`units_verified=true`. No controller acquisition timestamp was present. Optional
seqid handling does not invent request/reply correlation for the observed server.

## Parser and polling contract

- Bounded UTF-8 XML, exact namespace/version, depth/node/attribute bounds.
- DTDs, entity declarations, comments and processing instructions rejected.
- Six finite bounded numeric values required for the matching joint datum.
- Unsupported branches, malformed updates, ambiguous multiple snapshots and
  peer error messages fail explicitly. Unrelated data updates are counted.
- Short writes are completed within the same deadline. One request is outstanding
  at a time. A missing, malformed or late reply ends the session; no retry occurs.
- Recent receipt, stale receipt, closed stream and failed stream remain distinct.
  A historical value is never presented as a current sample after expiry/closure.

The live GUI distinguishes RECEIVING from STALE/FAILED/SAVED FINAL. Its local
Stop marker ends observation only. The display is published at approximately
10 Hz while reads target 50 Hz; these are separate rates.

## Unresolved and excluded

Controller data-acquisition age, cache behavior, maximum rate, long-duration
reliability, source timestamps and other firmware/option compatibility remain
unknown. Host request/reply latency is not encoder-to-display latency or a servo
period. This package contains no motion, motor, I/O-write, controller-program,
file-transfer or configuration command encoder. Read-only success does not
qualify any such operation.
