from __future__ import annotations

import json
from pathlib import Path
import socket

import pytest

from nachi_native_feedback.live import LivePlan, collect_live, execute_live, publish_json
from nachi_native_feedback.live_monitor import presentation, save_mark
from nachi_native_feedback.probe import _CaptureStream
from nachi_native_feedback.protocol import build_joint_request

FRAME = (Path(__file__).parent / 'fixtures/derived-response-shape.bin').read_bytes()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **kw): raise AssertionError('No real network operations in live-observer tests')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


class Clock:
    def __init__(self): self.value = 1_000_000_000
    def now(self): return self.value
    def sleep(self, seconds): self.value += max(1, round(seconds * 1e9))


class Stream:
    def __init__(self, clock, fail=None):
        self.clock = clock; self.fail = fail; self.sent = bytearray(); self.count = 0
    def settimeout(self, seconds): assert 0 < seconds <= 1.000001
    def send(self, data): self.sent.extend(data); return len(data)
    def recv(self, size):
        self.clock.value += 1_000_000
        if self.fail: raise self.fail
        self.count += 1
        return FRAME


def test_full_live_window_is_bounded_and_display_is_decimated():
    clock = Clock(); stream = Stream(clock); updates = []
    result = collect_live(stream, updates.append, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'COMPLETE_TIME_LIMIT'
    assert result['elapsed_seconds'] <= 120 and 5000 < result['samples_received'] <= 6000
    assert bytes(stream.sent) == build_joint_request() * result['samples_received']
    assert 1000 < len(updates) < result['samples_received']
    assert updates[-1]['state'] == 'COMPLETE_TIME_LIMIT'
    assert updates[-1]['initial_samples_received']
    assert result['max_change_from_first'] == [0] * 6
    assert result['wire_capture']['rx_bytes'] > 131072
    assert result['wire_capture']['rx_bytes'] <= 4 * 1024 * 1024
    assert not result['measurement_age_known']


def test_local_stop_preserves_data_and_ends_reads():
    clock = Clock(); stream = Stream(clock); updates = []
    result = collect_live(stream, updates.append, clock_ns=clock.now, sleeper=clock.sleep, cancelled=lambda: stream.count >= 20)
    assert result['state'] == 'STOPPED_BY_OPERATOR' and result['samples_received'] == 20
    assert len(stream.sent) == 20 * 233
    assert updates[-1]['state'] == 'STOPPED_BY_OPERATOR'
    assert result['final_observer_state']['current_sample'] is None


def test_read_timeout_stops_without_retry():
    clock = Clock(); stream = Stream(clock, TimeoutError('synthetic timeout')); updates = []
    result = collect_live(stream, updates.append, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'FAILED' and result['samples_received'] == 0
    assert bytes(stream.sent) == build_joint_request()
    assert updates[-1]['state'] == 'FAILED'


def test_repeated_publication_failure_stops_the_observer():
    clock = Clock(); stream = Stream(clock)
    def bad_publish(data): raise OSError('cannot publish')
    result = collect_live(stream, bad_publish, clock_ns=clock.now, sleeper=clock.sleep)
    assert result['state'] == 'FAILED' and result['samples_received'] <= 3
    assert result['publication_errors'] >= 3


@pytest.mark.parametrize('state,age,badge,recent', [
    ('RUNNING', 0.1, 'RECEIVING', True), ('RUNNING', 0.5, 'STALE', False),
    ('RUNNING', 1, 'STALE', False), ('FAILED', 0, 'FAILED', False),
    ('COMPLETE_TIME_LIMIT', 0.1, 'SAVED FINAL', False), ('STOPPED_BY_OPERATOR', 0.1, 'SAVED FINAL', False),
])
def test_display_freshness_and_final_state(state, age, badge, recent):
    data = {'state': state, 'sample_received_counter_ns': 1_000_000_000}
    actual = presentation(data, 1_000_000_000 + round(age*1e9))
    assert actual[0] == badge and actual[1] == recent


def test_pose_marks_require_recent_data_and_ten_samples(tmp_path):
    data = {'state':'RUNNING','sample_received_counter_ns':1_000_000_000,'values':[1,2,3,4,5,6],
            'samples':20,'initial_samples_received':True}
    path = tmp_path/'pose-a.json'
    save_mark(path,'A',data,1_100_000_000)
    assert json.loads(path.read_text())['values'] == [1,2,3,4,5,6]
    with pytest.raises(ValueError): save_mark(path,'B',data,2_000_000_000)
    data['initial_samples_received']=False
    with pytest.raises(ValueError): save_mark(path,'B',data,1_100_000_000)


def test_atomic_publication(tmp_path):
    path=tmp_path/'latest.json'
    publish_json(path,{'state':'WAITING'})
    publish_json(path,{'state':'RUNNING','values':[1,2,3,4,5,6]})
    assert json.loads(path.read_text())['state']=='RUNNING'
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('limit',[0,True,4*1024*1024+1])
def test_capture_limit_is_bounded(limit):
    with pytest.raises(ValueError): _CaptureStream(None,max_rx_bytes=limit)


def test_plan_only_live_never_connects(tmp_path):
    result=execute_live(LivePlan('192.0.2.2','192.0.2.10'),latest_path=tmp_path/'latest.json',cancel_path=tmp_path/'cancel')
    assert result['mode']=='LIVE_OBSERVER_PLAN_ONLY' and not result['controller_contacted']
    assert result['max_read_requests']==6000 and result['max_seconds']==120
    assert result['target_hz']==50 and not result['motion_motor_io_configuration_or_program_operations']


def test_cancelled_before_connect_opens_no_socket(tmp_path):
    cancel=tmp_path/'cancel';cancel.touch()
    result=execute_live(LivePlan('192.0.2.2','192.0.2.10'),latest_path=tmp_path/'latest.json',cancel_path=cancel,execute=True)
    assert result['state']=='STOPPED_BY_OPERATOR' and not result['connection_attempted']
