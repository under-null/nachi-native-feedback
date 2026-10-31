# Provenance and attribution

The Python reader, tests, diagnostic tools and notes in this release were written
for this project. Development used public source review, static inspection of
community-hosted SDK libraries and experiments on an owned controller. This is
an independent interoperability implementation, **not a formal clean-room claim**.
The underlying protocol is Nachi's; this project does not claim to have invented it.

No SDK/header/schema/manual/vendor binary, disassembly listing, license record or
third-party source archive is distributed. The package does not load either
audited library at runtime. This project's MIT license applies to its original
implementation and notes, not to separately referenced third-party materials.

## Pinned public references

| Reference | Reviewed revision | Contribution to the investigation |
| --- | --- | --- |
| [samkwok-hkclr/nachi_robot](https://github.com/samkwok-hkclr/nachi_robot/tree/3f317f47ba72cd07a7d7c6413d3eb0e4217da24b) | 3f317f47ba72cd07a7d7c6413d3eb0e4217da24b | API calls, schema vocabulary and one native-library implementation |
| [Huoleit/ros2_control_mz25](https://github.com/Huoleit/ros2_control_mz25/tree/281f88b232db0dc30af878e300a18b0445c17c01) | 281f88b232db0dc30af878e300a18b0445c17c01 | Independent library build, API use and schema comparison |
| [ZainZh/PRISM](https://github.com/ZainZh/PRISM/tree/dd1d0e443a2b34e56b6f5b57fdbb75661f85ac72) | dd1d0e443a2b34e56b6f5b57fdbb75661f85ac72 | Additional header/schema vocabulary and integration examples |

Their code/examples retain their upstream terms. Community hosting is not Nachi
certification or proof that a function is installed on any particular controller.
The inspected C++ clients generally call SDK functions; our Python client
constructs and parses the narrow wire exchange directly.

Two distinct saved Linux libraries corroborated the envelope and axis selector.
The research anchors below identify the inspected inputs without shipping them:

| SHA-256 of research input | SendData anchor | NR_AcsAxisTheta anchor |
| --- | --- | --- |
| c6471d61cbaf346b0dfc63c56a8383d0700a0afc440abb324ab484d78aa4cb4b | 0x40070 | 0x4D3A0 |
| caa86428e6b6c5619f28ebcbad8e95d5af8814611a01493a15eaf75d916ba1ec | 0x8B6C0 | 0xA43B0 |

Those are offline reference anchors, not addresses to use against a running
controller. The independent hardware response qualified the fixed profile on
the one tested installation. An SDK accessor name or schema alone did not.

## Primary vendor context

[NACHI TECHNICAL REPORT Vol.34 B3](https://www.nachi-fujikoshi.co.jp/dcms_media/other/34B3.pdf),
October 2018, edition not stated, **PDF p. 6, printed p. 5**, Figure 6,
shows NR_Open/NR_DATA_XML with port 9876. It does not supply this reader's wire
format or establish broad hardware compatibility.

The available English OpenNR manual reference is **TFDEN-175-003, 3rd ed.**
The inspected copy is incomplete and has website overlays; controller
applicability is uncertain. It is not redistributed. Its contents on **PDF p. 7**
lists operation pages absent from that copy. This release makes no motion-command
contract claim from those missing pages. Its independent read results are
documented as observations, not generalized manual promises.

## Evidence levels

1. The packet layout/selector was recovered from comparative static research.
2. One physical CFD V4.32 installation returned matching six-axis data.
3. Pacing and pose-change runs measured host reply behavior and operator agreement.
4. The exported timing arithmetic can be recomputed from the public CSV files.

The public bundle omits private raw poses/captures. It therefore does not let a
reader independently authenticate the physical experiment from those originals.
Synthetic fixtures establish code behavior; they never establish hardware support.
