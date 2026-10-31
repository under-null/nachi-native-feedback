# Fixture provenance

All joint numbers in these files are fabricated. `derived-response-shape.xml`
retains the element/attribute layout of one hardware response, including absent
`extid` and `seqid`, but replaces all six recorded numbers with fabricated ones.
Its `.bin` envelope is regenerated from those bytes. It is not an untouched
controller capture. The other XML fixtures are synthetic parser inputs.
`request.xml` is our fixed independently written read request. No vendor schema
or SDK file is included. Hardware timing rows are separately labeled under
`results/`; they are measured values, not these synthetic fixture values.
