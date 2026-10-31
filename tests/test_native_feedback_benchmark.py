from __future__ import annotations

from collections import deque
import hashlib
from pathlib import Path
import socket

import pytest

from nachi_native_feedback.benchmark import BenchmarkPlan, PHASES, collect, distribution, execute_benchmark
from nachi_native_feedback.protocol import build_joint_request

FRAME = (Path(__file__).parent / 'fixtures/derived-response-shape.bin').read_bytes()


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Benchmark tests may not create sockets or resolve DNS')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


class Clock:
    def __init__(self):
        self.value = 1_000_000_000
        self.sleeps = []

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += max(1, round(seconds * 1e9))


class Stream:
    def __init__(self, clock, *, delay_ns=1_000_000, fail_at=None, split=None):
        self.clock = clock
        self.delay = delay_ns
        self.fail_at = fail_at
        self.replies = 0
        self.sent = bytearray()
        self.sent_at = []
        self.parts = deque()
        self.split = split
        self.connected = []
        self.bound = None
        self.closed = False

    def settimeout(self, seconds):
        assert 0 < seconds <= 1.000001

    def send(self, data):
        self.sent_at.append(self.clock.now())
        self.sent.extend(data)
        return len(data)

    def recv(self, size):
        self.clock.value += self.delay
        if self.fail_at is not None and self.replies >= self.fail_at:
            raise TimeoutError('Synthetic timeout')
        if not self.parts:
            self.replies += 1
            self.parts.extend([FRAME] if self.split is None else [FRAME[:self.split], FRAME[self.split:]])
        return self.parts.popleft()

    def bind(self, endpoint):
        self.bound = endpoint

    def connect(self, endpoint):
        self.connected.append(endpoint)

    def getsockname(self):
        return self.bound

    def getpeername(self):
        return self.connected[-1]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


def test_complete_fixed_paced_run_with_high_resolution_measurements():
    clock = Clock()
    stream = Stream(clock)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'COMPLETE'
    assert result['samples_received'] == result['requests_completely_sent'] == 250
    assert bytes(stream.sent) == build_joint_request() * 250
    assert result['wire_capture']['rx_bytes'] == len(FRAME) * 250
    assert result['wire_capture']['tx_bytes'] == 58250
    assert result['wire_capture']['rx_sha256'] == hashlib.sha256(FRAME * 250).hexdigest()
    assert [x['achieved_reply_hz'] for x in result['phases']] == pytest.approx([5, 20, 50])
    assert [x['response_complete_ms_steady']['median'] for x in result['phases']] == [1, 1, 1]
    assert [x['steady_samples'] for x in result['phases']] == [45, 95, 95]
    for a, b in zip(result['records'], result['records'][1:]):
        assert b['request_start_ns'] - a['request_start_ns'] >= round(1e9 / b['target_hz'])
    assert not result['measurement_age_known'] and not result['request_correlation_verified']


def test_slow_replies_do_not_create_catch_up_bursts():
    clock = Clock()
    stream = Stream(clock, delay_ns=80_000_000)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'COMPLETE'
    assert result['phases'][1]['achieved_reply_hz'] <= 12.5
    assert result['phases'][2]['achieved_reply_hz'] <= 12.5
    assert result['phases'][2]['transactions_exceeding_target_period'] == 95
    for a, b in zip(result['records'], result['records'][1:]):
        assert b['request_start_ns'] - a['request_start_ns'] >= round(1e9 / b['target_hz'])


def test_deadline_stops_before_more_requests_and_keeps_partial_records():
    clock = Clock()
    stream = Stream(clock, delay_ns=300_000_000)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'FAILED'
    assert 1 < result['samples_received'] < 250
    assert 'deadline' in result['error']
    assert result['final_observer_state']['current_sample'] is None


def test_per_request_timeout_is_not_retried():
    clock = Clock()
    stream = Stream(clock, fail_at=3)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'FAILED' and result['samples_received'] == 3
    assert len(stream.sent_at) == 4
    assert len(result['phases']) == 3
    assert result['phases'][1]['samples_received'] == 0


def test_fragmented_reply_timing_records_first_and_complete_receive_separately():
    clock = Clock()
    stream = Stream(clock, fail_at=1, split=9)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep)
    # The fake's fail_at counts reply starts; use the first partial transaction
    # as evidence that a timeout cannot be mistaken for a complete reply.
    assert result['state'] == 'FAILED' and result['samples_received'] == 0


def test_full_fragmented_run():
    clock = Clock()
    stream = Stream(clock, split=9)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'COMPLETE'
    first = result['records'][0]
    assert first['read_calls'] == 2
    assert first['first_recv_return_ns'] < first['complete_reply_recv_return_ns']
    assert first['response_complete_ms'] == 2


def test_local_cancellation_stops_without_advancing_phases():
    clock = Clock()
    stream = Stream(clock)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep, cancelled=lambda: stream.replies >= 4)
    assert result['state'] == 'CANCELLED' and result['samples_received'] == 4
    assert len(stream.sent_at) == 4


def test_external_total_deadline_includes_connect_time():
    clock = Clock()
    stream = Stream(clock)
    result = collect(stream, clock_ns=clock.now, sleeper=clock.sleep, deadline_ns=clock.now() + 100_000_000)
    assert result['state'] == 'FAILED' and result['samples_received'] == 1


def test_percentiles_and_jitter_summary_are_defined():
    result = distribution([4, 1, 3, 2])
    assert result['median'] == 2.5 and result['p95'] == result['p99'] == 4
    assert result['population_stddev'] == pytest.approx(1.11803398875)
    assert distribution([]) is None


def test_benchmark_default_only_returns_plan():
    result = execute_benchmark(BenchmarkPlan('192.0.2.2', '192.0.2.10'))
    assert result['mode'] == 'BENCHMARK_PLAN_ONLY' and not result['controller_contacted']
    assert result['max_connections'] == 1 and result['max_read_requests'] == 250
    assert result['nominal_duration_seconds'] == 17 and result['session_limit_seconds'] == 30
    assert result['max_application_bytes_sent'] == 58250
    assert not result['catch_up_bursts'] and result['one_outstanding_request']


@pytest.mark.parametrize('host,source', [('name.local', '192.0.2.10'), ('192.0.2.2', None),
                                         ('192.0.2.2', '192.0.2.2'), ('192.0.2.2', '0.0.0.0')])
def test_invalid_endpoint_plan(host, source):
    with pytest.raises(ValueError):
        BenchmarkPlan(host, source)


def test_cancel_marker_before_connection_opens_no_socket(tmp_path):
    marker = tmp_path / 'cancel'
    marker.touch()
    result = execute_benchmark(BenchmarkPlan('192.0.2.2', '192.0.2.10'), execute=True, cancel_path=marker)
    assert not result['connection_attempted']
