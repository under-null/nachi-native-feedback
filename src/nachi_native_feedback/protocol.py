"""Narrow fixed joint-read profile, observed on one CFD V4.32 installation.

Broader compatibility, documented units and device sample age remain unverified.
No controller-write builder or model-coordinate offsets are provided.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import xml.etree.ElementTree as ET

from .framing import MAX_PAYLOAD, encode_frame

NS = 'flex.gui'
Q = '{' + NS + '}'
KEY = {'unit': '1', 'group': 'Generic', 'id': 'SYSTEM!', 'subid': '400', 'extid': '-1', 'count': '6'}
INTEGER = re.compile(r'[+-]?[0-9]{1,12}\Z')
REAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
FLOAT32_MAX = float.fromhex('0x1.fffffep+127')


class FeedbackError(ValueError):
    pass


class PeerError(FeedbackError):
    pass


class _BoundedTree(ET.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.nodes = 0

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        if self.depth > 8 or self.nodes > 256 or len(attrs) > 12:
            raise FeedbackError('XML structure exceeds profile limits')
        if not tag.startswith(Q) or any(len(x) > 256 for x in attrs.values()):
            raise FeedbackError('Wrong namespace or oversized XML attribute')
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)

    def doctype(self, *args):
        raise FeedbackError('DTD and entity declarations are prohibited')

    def pi(self, *args):
        raise FeedbackError('Processing instructions are prohibited')

    def comment(self, *args):
        raise FeedbackError('Comments are outside the supported XML profile')


def parse_xml(payload: bytes) -> ET.Element:
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_PAYLOAD:
        raise FeedbackError('Invalid XML payload size')
    try:
        text = payload.decode('utf-8-sig', errors='strict')
        declaration = re.match(r'^<\?xml\s+[^?]*\?>', text)
        if declaration:
            encoding = re.search(r'encoding\s*=\s*[\"\x27]([^\"\x27]+)', declaration[0], re.I)
            if encoding and encoding[1].lower() != 'utf-8':
                raise FeedbackError('Only UTF-8 XML is supported')
        root = ET.fromstring(text, parser=ET.XMLParser(target=_BoundedTree()))
    except (UnicodeError, ET.ParseError) as exc:
        raise FeedbackError('Malformed UTF-8 XML') from exc
    if root.tag != Q + 'flexData' or root.attrib != {'version': '1'}:
        raise FeedbackError('Expected flex.gui flexData version 1')
    return root


def _attrs(node, allowed, required=()):
    if set(node.attrib) - set(allowed) or set(required) - set(node.attrib):
        raise FeedbackError('Unexpected or missing attributes on ' + node.tag)


def _whitespace(node):
    if (node.text or '').strip() or any((x.tail or '').strip() for x in node):
        raise FeedbackError('Unexpected mixed XML content')


def _integer(text):
    if not isinstance(text, str) or not INTEGER.fullmatch(text):
        raise FeedbackError('Invalid bounded integer')
    return int(text)


def _real(node):
    text = (node.text or '').strip()
    if node.tag != Q + 'r' or node.attrib or len(node) or not 0 < len(text) <= 64 or not REAL.fullmatch(text):
        raise FeedbackError('Expected a scalar real number')
    value = float(text)
    if not math.isfinite(value) or abs(value) > FLOAT32_MAX:
        raise FeedbackError('Joint value is non-finite or outside the SDK float32 representation')
    return value


def build_joint_request() -> bytes:
    """Fixed one-shot request; no arguments can select another datum or operation."""
    payload = (
        b'<flexData version="1" xmlns="flex.gui"><dataExchange><dataRequest>'
        b'<data unit="1" group="Generic" id="SYSTEM!" subid="400" extid="-1" '
        b'count="6" push="-1" threshold="0.01" priority="5" />'
        b'</dataRequest></dataExchange></flexData>'
    )
    return encode_frame(payload)


@dataclass(frozen=True)
class JointReading:
    values: tuple[float, ...]
    seqid: int | None
    unit: int = 1
    units: str = 'native_raw_unverified'
    controller_timestamp: None = None


@dataclass(frozen=True)
class ParsedMessage:
    readings: tuple[JointReading, ...]
    heartbeats: int
    unrelated_updates: int


def parse_message(payload: bytes) -> ParsedMessage:
    root = parse_xml(payload)
    _whitespace(root)
    readings = []
    heartbeats = 0
    unrelated = 0
    seen = set()
    for branch in root:
        if branch.tag in seen:
            raise FeedbackError('Duplicate top-level XML branch')
        seen.add(branch.tag)
        if branch.tag == Q + 'status':
            _attrs(branch, ())
            _whitespace(branch)
            for item in branch:
                if len(item) or (item.text or '').strip():
                    raise FeedbackError('Malformed status entry')
                if item.tag == Q + 'heartbeat':
                    _attrs(item, ('app',))
                    if 'app' in item.attrib:
                        _integer(item.attrib['app'])
                    heartbeats += 1
                elif item.tag == Q + 'error':
                    _attrs(item, ('errorID', 'context'), ('errorID',))
                    code = _integer(item.attrib['errorID'])
                    raise PeerError(f'Peer status error {code}: {item.get("context", "")}')
                else:
                    raise FeedbackError('Unsupported status message')
        elif branch.tag == Q + 'dataExchange':
            _attrs(branch, ())
            _whitespace(branch)
            for update in branch:
                if update.tag != Q + 'dataUpdate':
                    raise FeedbackError('Expected dataUpdate; no request/ack is accepted as feedback')
                _attrs(update, ('seqid',))
                seqid = _integer(update.attrib['seqid']) if 'seqid' in update.attrib else None
                _whitespace(update)
                for data in update:
                    if data.tag != Q + 'data':
                        raise FeedbackError('Expected a data item')
                    _attrs(data, KEY.keys(), ('unit', 'group', 'id', 'subid'))
                    unit = _integer(data.attrib['unit'])
                    subid = _integer(data.attrib['subid'])
                    extid = _integer(data.attrib.get('extid', '-1'))
                    count = _integer(data.attrib.get('count', '1'))
                    if not 1 <= count <= 64:
                        raise FeedbackError('Data count exceeds supported bounds')
                    if (unit, data.get('group'), data.get('id'), subid) != (1, 'Generic', 'SYSTEM!', 400):
                        unrelated += 1
                        continue
                    if extid != -1 or count != 6:
                        raise FeedbackError('Joint update has unexpected extid or count')
                    _whitespace(data)
                    if len(data) != 6:
                        raise FeedbackError('Incomplete or oversized six-joint update')
                    readings.append(JointReading(tuple(_real(x) for x in data), seqid))
        else:
            raise FeedbackError('Unsupported top-level message: ' + branch.tag)
    if len(readings) > 1:
        raise FeedbackError('Multiple joint snapshots in one XML message are ambiguous')
    return ParsedMessage(tuple(readings), heartbeats, unrelated)
