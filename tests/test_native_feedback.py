from __future__ import annotations

from collections import deque
import json
import math
from pathlib import Path
import random
import socket
import struct
import sys
import xml.etree.ElementTree as ET

import pytest

from nachi_native_feedback.__main__ import demo, main, replay, synthetic_payload
from nachi_native_feedback.framing import FrameDecoder, FrameError, MAX_PAYLOAD, encode_frame
from nachi_native_feedback.observer import FeedbackObserver
from nachi_native_feedback.probe import ProbePlan, execute_probe
from nachi_native_feedback.protocol import FeedbackError, PeerError, build_joint_request, parse_message
from nachi_native_feedback.session import ReadOnlyPoller

FIXTURES = Path(__file__).parent / 'fixtures'
JOINTS = (FIXTURES / 'joints.xml').read_bytes()
HEARTBEAT = (FIXTURES / 'heartbeat.xml').read_bytes()
VALUES = (10.0, -20.0, 30.0, -40.0, 50.0, -60.0)
FRAME = bytes.fromhex('5eba0100') + len(JOINTS).to_bytes(4, 'little') + JOINTS


@pytest.fixture(autouse=True)
def prohibit_real_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No real socket or DNS operation is permitted by this test suite')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


@pytest.mark.parametrize('split', range(len(FRAME) + 1))
def test_every_tcp_split(split):
    decoder = FrameDecoder()
    assert decoder.feed(FRAME[:split]) + decoder.feed(FRAME[split:]) == [JOINTS]
    decoder.finish()


@pytest.mark.parametrize('end', range(1, len(FRAME)))
def test_every_truncated_eof(end):
    decoder = FrameDecoder()
    decoder.feed(FRAME[:end])
    with pytest.raises(FrameError):
        decoder.finish()
    assert decoder.failed
    with pytest.raises(FrameError):
        decoder.feed(FRAME)


def test_many_coalesced_frames_random_fragmentation():
    stream = b''.join(encode_frame(synthetic_payload(i)) for i in range(240))
    rng = random.Random(175003)
    observer = FeedbackObserver()
    offset = 0
    got = []
    while offset < len(stream):
        take = rng.randint(1, 8192)
        got.extend(observer.ingest(stream[offset:offset + take], 1.0))
        offset += take
    observer.finish()
    assert len(got) == 240 and [x.seqid for x in got] == list(range(240))
    assert observer.snapshot(1)['status'] == 'CLOSED'


@pytest.mark.parametrize('header', [
    bytes.fromhex('0000010001000000'), bytes.fromhex('5eba020001000000'),
    bytes.fromhex('5eba010000000000'), bytes.fromhex('5eba010001000100'),
    bytes.fromhex('5eba0100ffffffff'),
])
def test_bad_headers_fail_without_resynchronization(header):
    decoder = FrameDecoder()
    with pytest.raises(FrameError):
        decoder.feed(header + FRAME)
    assert decoder.failed and decoder.pending_bytes == 0
    with pytest.raises(FrameError):
        decoder.feed(FRAME)


def test_exact_payload_limit_and_buffer_bound():
    payload = b'x' * MAX_PAYLOAD
    decoder = FrameDecoder()
    frame = encode_frame(payload)
    assert decoder.feed(frame[:-1]) == []
    assert decoder.pending_bytes == MAX_PAYLOAD + 7
    assert decoder.feed(frame[-1:]) == [payload]
    with pytest.raises(FrameError):
        encode_frame(payload + b'x')


def test_request_is_exact_fixed_read_fixture():
    golden_xml = (FIXTURES / 'request.xml').read_bytes().rstrip(b'\r\n')
    request = build_joint_request()
    assert request == bytes.fromhex('5eba0100e1000000') + golden_xml
    root = ET.fromstring(request[8:])
    assert [x.tag for x in root] == ['{flex.gui}dataExchange']
    assert [x.tag for x in root[0]] == ['{flex.gui}dataRequest']
    assert root[0][0][0].attrib == {'unit': '1', 'group': 'Generic', 'id': 'SYSTEM!', 'subid': '400',
                                   'extid': '-1', 'count': '6', 'push': '-1', 'threshold': '0.01', 'priority': '5'}


def test_joint_snapshot_preserves_native_values_and_unknowns():
    result = parse_message(JOINTS)
    assert result.readings[0].values == VALUES
    assert result.readings[0].seqid == 42
    assert result.readings[0].units == 'native_raw_unverified'
    assert result.readings[0].controller_timestamp is None
    assert result.readings[0].values[1] == -20.0  # No ROS J2 offset or radians conversion.


def test_derived_response_shape_with_optional_metadata_absent():
    import hashlib
    raw = (FIXTURES / 'derived-response-shape.bin').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '16d0ad1aac592136e0c87466d56f7f8c200838618a7cc1ee2f3dfe998144284b'
    assert raw[:8] == bytes.fromhex('5eba01003c010000')
    decoder = FrameDecoder()
    payloads = []
    for offset in range(0, len(raw), 7):
        payloads.extend(decoder.feed(raw[offset:offset+7]))
    decoder.finish()
    assert payloads == [(FIXTURES / 'derived-response-shape.xml').read_bytes()]
    reading = parse_message(payloads[0]).readings[0]
    assert reading.seqid is None
    assert reading.values == (10.123456, 120.123456, -30.123456, 40.123456, -50.123456, -160.123456)


@pytest.mark.parametrize('before,after', [
    (b'xmlns="flex.gui"', b'xmlns="wrong"'),
    (b'version="1"', b'version="2"'), (b' version="1"', b''),
    (b'count="6"', b'count="5"'), (b'count="6"', b'count="7"'),
    (b'extid="-1"', b'extid="0"'),
    (b'<r>10.0</r>', b'<r>NaN</r>'), (b'<r>10.0</r>', b'<r>INF</r>'),
    (b'<r>10.0</r>', b'<r>1e999</r>'), (b'<r>10.0</r>', b'<r>1e100</r>'),
    (b'<r>10.0</r>', b'<r a="1">10.0</r>'),
    (b'<r>10.0</r>', b'<i>1</i>'), (b'<r>10.0</r>', b''),
    (b'<r>10.0</r>', b'<r>1</r><r>2</r>'),
    (b'<r>10.0</r>', b'<r>1,234</r>'),
    (b'<r>10.0</r>', b'<r>0x1.0p1</r>'),
    (b'<r>10.0</r>', b'<r><r>1</r></r>'),
    (b'<dataExchange>', b'<dataExchange unexpected="x">'),
    (b'<dataUpdate seqid="42">', b'<dataUpdate seqid="1234567890123">'),
    (b'</flexData>', b'junk</flexData>'),
])
def test_invalid_joint_messages_are_not_accepted(before, after):
    with pytest.raises(FeedbackError):
        parse_message(JOINTS.replace(before, after))


@pytest.mark.parametrize('xml', [
    b'<!DOCTYPE flexData [<!ENTITY x "1">]><flexData version="1" xmlns="flex.gui">&x;</flexData>',
    b'<!DOCTYPE flexData SYSTEM "file:///not-readable-test-fixture"><flexData version="1" xmlns="flex.gui"/>',
    b'<!DOCTYPE flexData [<!ENTITY % x SYSTEM "https://example.invalid/dtd">%x;]><flexData version="1" xmlns="flex.gui"/>',
    b'<flexData version="1" xmlns="flex.gui"><?bad instruction?></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><!-- comment --></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><control><key state="true"/></control></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><operations/></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><constantData/></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><programSync/></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><dataExchange><dataRequest/></dataExchange></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><dataExchange><dataUpdateAck/></dataExchange></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><status/><status/></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><status><heartbeat><r>1</r></heartbeat></status></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><status><heartbeat app="NaN"/></status></flexData>',
    b'<flexData version="1" xmlns="flex.gui"><status><hidden/></status></flexData>',
    b'<?xml version="1.0" encoding="utf-16"?><flexData version="1" xmlns="flex.gui"/>',
    b'\xff\xfe\x00',
    b'<flexData version="1" xmlns="flex.gui"><a><a><a><a><a><a><a><a/></a></a></a></a></a></a></a></flexData>',
    b'<flexData version="1" xmlns="flex.gui">' + b'<status/>' * 257 + b'</flexData>',
])
def test_untrusted_xml_and_unsupported_branches(xml):
    with pytest.raises(FeedbackError):
        parse_message(xml)


def test_optional_extid_and_seqid():
    result = parse_message(JOINTS.replace(b' extid="-1"', b'').replace(b' seqid="42"', b''))
    assert result.readings[0].values == VALUES
    assert result.readings[0].seqid is None


@pytest.mark.parametrize('old,new', [(b'unit="1"', b'unit="2"'), (b'subid="400"', b'subid="410"'),
                                    (b'id="SYSTEM!"', b'id="V!"'), (b'group="Generic"', b'group="PLC"')])
def test_unrelated_updates_do_not_become_joint_data(old, new):
    message = parse_message(JOINTS.replace(old, new))
    assert not message.readings and message.unrelated_updates == 1


def test_schema_valid_peer_error_is_a_failure():
    with pytest.raises(PeerError, match='7'):
        parse_message((FIXTURES / 'peer-error.xml').read_bytes())


def test_duplicate_snapshot_in_single_message_rejected():
    root = ET.fromstring(JOINTS)
    root[0].append(ET.fromstring(ET.tostring(root[0][0])))
    with pytest.raises(FeedbackError, match='ambiguous'):
        parse_message(ET.tostring(root))


def test_receipt_expiry_heartbeat_and_disconnect():
    observer = FeedbackObserver(stale_after=0.5)
    assert observer.snapshot(0)['status'] == 'NO_DATA'
    observer.ingest(FRAME, 1)
    assert observer.snapshot(1.49)['current_sample']['values'] == VALUES
    observer.ingest(encode_frame(HEARTBEAT), 1.5)
    stale = observer.snapshot(1.5)
    assert stale['status'] == 'STALE' and stale['current_sample'] is None
    assert stale['last_sample_for_history']['values'] == VALUES
    assert stale['heartbeats'] == 1 and not stale['measurement_age_known']
    observer.finish()
    assert observer.snapshot(2)['status'] == 'CLOSED'
    with pytest.raises(FeedbackError):
        observer.ingest(FRAME, 2)


def test_failure_invalidates_previous_good_sample():
    observer = FeedbackObserver()
    observer.ingest(FRAME, 1)
    with pytest.raises(FeedbackError):
        observer.ingest(encode_frame(b'<bad/>'), 2)
    state = observer.snapshot(2)
    assert state['status'] == 'FAILED' and state['current_sample'] is None
    assert state['last_sample_for_history']['values'] == VALUES
    with pytest.raises(FeedbackError):
        observer.ingest(FRAME, 3)


@pytest.mark.parametrize('bad_time', [-1, float('nan'), float('inf'), True, 0.5])
def test_clock_failures(bad_time):
    observer = FeedbackObserver()
    observer.ingest(FRAME, 1)
    with pytest.raises(FeedbackError):
        observer.snapshot(bad_time)
    assert observer.snapshot(2)['status'] == 'FAILED'


def test_repeated_seqid_is_diagnostic_not_assumed_sample_clock():
    observer = FeedbackObserver()
    observer.ingest(FRAME, 1)
    observer.ingest(FRAME, 2)
    state = observer.snapshot(2)
    assert state['samples'] == 2 and state['repeated_seqids'] == 1
    assert state['request_correlation_verified'] is False


class MemoryStream:
    def __init__(self, chunks=(), send_limit=10000, error=None):
        self.chunks = deque(chunks)
        self.send_limit = send_limit
        self.sent = bytearray()
        self.timeouts = []
        self.error = error
        self.connected_to = []
        self.closed = False
        self.bound_to = ('192.0.2.10', 50000)

    def settimeout(self, value):
        self.timeouts.append(value)

    def send(self, data):
        count = min(len(data), self.send_limit)
        self.sent.extend(data[:count])
        return count

    def recv(self, count):
        if self.error:
            raise self.error
        return self.chunks.popleft() if self.chunks else b''

    def connect(self, endpoint):
        self.connected_to.append(endpoint)

    def bind(self, endpoint):
        self.bound_to = endpoint

    def getsockname(self):
        return self.bound_to

    def getpeername(self):
        return self.connected_to[-1]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


def test_partial_writes_and_reads_send_only_one_fixed_request():
    stream = MemoryStream([FRAME[:3], FRAME[3:14], FRAME[14:]], send_limit=7)
    poller = ReadOnlyPoller(stream, clock=lambda: 1)
    result = poller.poll()
    assert result['reading'].values == VALUES
    assert bytes(stream.sent) == build_joint_request()
    assert poller.requests_sent == 1 and all(0 < x <= 2 for x in stream.timeouts)


def test_pull_reply_delivered_one_byte_at_a_time():
    stream = MemoryStream([bytes([x]) for x in FRAME], send_limit=1)
    poller = ReadOnlyPoller(stream, clock=lambda: 1)
    assert poller.poll()['reading'].values == VALUES
    assert bytes(stream.sent) == build_joint_request()


@pytest.mark.parametrize('stream', [MemoryStream(), MemoryStream([FRAME[:-1], b'']),
                                    MemoryStream(send_limit=0), MemoryStream(error=TimeoutError('timeout')),
                                    MemoryStream(error=ConnectionResetError('reset')),
                                    MemoryStream([encode_frame(HEARTBEAT)] * 128),
                                    MemoryStream([FRAME + FRAME])])
def test_transaction_failures_are_terminal(stream):
    poller = ReadOnlyPoller(stream, clock=lambda: 1)
    with pytest.raises(FeedbackError):
        poller.poll()
    assert poller.observer.snapshot(1)['status'] == 'FAILED'
    before = bytes(stream.sent)
    with pytest.raises(FeedbackError):
        poller.poll()
    assert bytes(stream.sent) == before


def test_heartbeat_then_reply_and_partial_trailer():
    stream = MemoryStream([encode_frame(HEARTBEAT), FRAME + FRAME[:3]])
    poller = ReadOnlyPoller(stream, clock=lambda: 1)
    assert poller.poll()['reading'].values == VALUES
    before = bytes(stream.sent)
    with pytest.raises(FeedbackError, match='partial'):
        poller.poll()
    assert bytes(stream.sent) == before


def test_deadline_does_not_restart_on_short_reads():
    clock = iter([0, 0, 0.1, 0.2, 2.1])
    stream = MemoryStream([FRAME[:1]])
    poller = ReadOnlyPoller(stream, clock=lambda: next(clock))
    with pytest.raises(FeedbackError, match='deadline'):
        poller.poll(timeout=2)
    assert poller.observer.failure


@pytest.mark.parametrize('kwargs', [
    {'host': 'robot.local'}, {'host': '0.0.0.0'}, {'host': '224.0.0.1'}, {'host': '255.255.255.255'},
    {'host': '::1'}, {'host': 123}, {'host': '192.0.2.2/24'},
    {'port': 0}, {'port': 65536}, {'samples': 0}, {'samples': 11}, {'samples': True},
    {'duration': 16}, {'response_timeout': 6}, {'duration': float('nan')}, {'duration': float('inf')},
    {'source_address': '0.0.0.0'}, {'source_address': '192.0.2.2'}, {'source_address': 'host.local'},
])
def test_invalid_probe_plans(kwargs):
    with pytest.raises(ValueError):
        ProbePlan(**({'host': '192.0.2.2'} | kwargs))


def test_plan_only_has_no_network_path():
    plan = ProbePlan('192.0.2.2')
    result = execute_probe(plan)
    assert result['mode'] == 'PLAN_ONLY' and not result['controller_contacted']
    assert result['connections'] == 1 and result['max_read_requests'] == 1


def test_explicit_probe_uses_only_fake_socket_and_closes(monkeypatch):
    stream = MemoryStream([FRAME], send_limit=7)
    monkeypatch.setattr(socket, 'socket', lambda *args: stream)
    result = execute_probe(ProbePlan('192.0.2.2'), execute=True, clock=lambda: 1)
    assert stream.connected_to == [('192.0.2.2', 9876)] and stream.closed
    assert bytes(stream.sent) == build_joint_request()
    assert len(result['records']) == 1 and result['final_state']['status'] == 'CLOSED'
    assert bytes.fromhex(result['wire_capture']['rx_hex']) == FRAME


def test_failed_probe_does_not_retry(monkeypatch):
    stream = MemoryStream(error=TimeoutError('silent peer'))
    monkeypatch.setattr(socket, 'socket', lambda *args: stream)
    result = execute_probe(ProbePlan('192.0.2.2', samples=10), execute=True, clock=lambda: 1)
    assert len(stream.connected_to) == 1 and stream.closed
    assert result['final_state']['status'] == 'FAILED' and result['records'] == []
    assert bytes(stream.sent) == build_joint_request()


def test_explicit_local_source_is_bound_and_verified_before_request(monkeypatch):
    stream = MemoryStream([FRAME])
    monkeypatch.setattr(socket, 'socket', lambda *args: stream)
    result = execute_probe(ProbePlan('192.0.2.2', source_address='192.0.2.10'), execute=True, clock=lambda: 1)
    assert stream.bound_to == ('192.0.2.10', 0)
    assert result['local_endpoint'][0] == '192.0.2.10'
    assert bytes(stream.sent) == build_joint_request()


def test_wrong_connected_source_sends_no_application_request(monkeypatch):
    stream = MemoryStream([FRAME])
    stream.getsockname = lambda: ('198.51.100.11', 50000)
    monkeypatch.setattr(socket, 'socket', lambda *args: stream)
    result = execute_probe(ProbePlan('192.0.2.2', source_address='192.0.2.10'), execute=True, clock=lambda: 1)
    assert result['final_state']['status'] == 'FAILED' and not stream.sent and stream.closed


def test_offline_demo_and_replay_under_network_guard(tmp_path):
    result = demo(240)
    assert result['last']['samples'] == 240
    assert result['first']['current_sample']['values'][0] != result['last']['current_sample']['values'][0]
    assert result['after_silence']['status'] == 'STALE'
    assert result['after_disconnect']['current_sample'] is None
    capture = tmp_path / 'synthetic.bin'
    capture.write_bytes(FRAME)
    result = replay(capture)
    assert result['final_state']['last_sample_for_history']['values'] == VALUES
    assert result['controller_contacted'] is False


def test_default_probe_cli_is_plan_only(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['native-feedback', 'probe', '--host', '192.0.2.2'])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'PLAN_ONLY'
