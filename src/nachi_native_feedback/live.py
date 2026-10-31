"""Bounded live observer. Fixed joint reads only; operator owns all pendant motion."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import time

from .observer import FeedbackObserver
from .probe import ProbePlan, _CaptureStream
from .protocol import FeedbackError, build_joint_request
from .session import ReadOnlyPoller

TARGET_HZ = 50
MAX_READS = 6000
MAX_SECONDS = 120
REPLY_TIMEOUT = 1.0
PUBLISH_PERIOD_NS = 100_000_000


@dataclass(frozen=True)
class LivePlan:
    host: str
    source_address: str
    port: int = 9876

    def __post_init__(self):
        if self.source_address is None:
            raise ValueError('Explicit local source address required')
        ProbePlan(self.host, self.port, source_address=self.source_address)

    def describe(self):
        request = build_joint_request()
        return {**asdict(self), 'mode': 'LIVE_OBSERVER_PLAN_ONLY', 'controller_contacted': False,
                'max_connections': 1, 'target_hz': TARGET_HZ, 'max_read_requests': MAX_READS,
                'max_seconds': MAX_SECONDS, 'response_timeout_seconds': REPLY_TIMEOUT,
                'max_application_bytes_sent': len(request) * MAX_READS,
                'max_rx_capture_bytes': 4 * 1024 * 1024,
                'request_sha256': hashlib.sha256(request).hexdigest(),
                'automatic_reconnect': False, 'one_outstanding_request': True,
                'catch_up_bursts': False, 'display_publication_hz': 10,
                'controller_measurement_age_known': False,
                'motion_motor_io_configuration_or_program_operations': False,
                'operator_owns_all_pendant_motion': True}


def publish_json(path: Path, data):
    """Atomic local publication, not a network service. Failure stays visible by age."""
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(data, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def validate_live_paths(latest_path: Path, cancel_path: Path):
    """Validate local destinations without creating a socket or deleting markers."""
    if latest_path.resolve() == cancel_path.resolve():
        raise ValueError('Status and cancellation paths must be different files')
    for path in (latest_path, cancel_path):
        if not path.parent.is_dir():
            raise ValueError('Create the status/cancellation parent directories before execution')
        if path.exists() and not path.is_file():
            raise ValueError('Status/cancellation paths must name files, not directories')


def collect_live(stream, publish, *, clock_ns=time.perf_counter_ns, sleeper=time.sleep,
                 cancelled=lambda: False, deadline_ns=None):
    observer = FeedbackObserver(stale_after=0.5)
    wire = _CaptureStream(stream, max_rx_bytes=4 * 1024 * 1024)
    poller = ReadOnlyPoller(wire, observer, clock=lambda: clock_ns() / 1e9)
    start = clock_ns()
    deadline = min(start + MAX_SECONDS * 1_000_000_000, deadline_ns) if deadline_ns is not None else start + MAX_SECONDS * 1_000_000_000
    previous_start = None
    last_publication = None
    publication_errors = 0
    consecutive_publication_errors = 0
    first_values = None
    records = []
    state = 'RUNNING'
    error = None

    def emit(final=False):
        nonlocal last_publication, publication_errors, consecutive_publication_errors
        now = clock_ns()
        if not final and last_publication is not None and now - last_publication < PUBLISH_PERIOD_NS:
            return
        last = observer.last
        data = {'mode': 'NATIVE_LIVE_OBSERVER', 'state': state, 'error': error,
                'published_counter_ns': now, 'sample_received_counter_ns': round(observer.last_received * 1e9) if observer.last_received is not None else None,
                'samples': len(records), 'first_values': first_values,
                'values': list(last.values) if last is not None else None,
                'receipt_rate_hz': observer.snapshot(now / 1e9)['receipt_rate_hz'],
                'remaining_seconds': max(0, (deadline - now) / 1e9),
                'initial_samples_received': len(records) >= 10,
                'measurement_age_known': False, 'units': 'native_angle_scale',
                'publication_errors': publication_errors}
        try:
            publish(data)
            last_publication = now
            consecutive_publication_errors = 0
        except OSError:
            publication_errors += 1
            consecutive_publication_errors += 1

    emit()
    try:
        for _ in range(MAX_READS):
            if cancelled():
                state = 'STOPPED_BY_OPERATOR'
                break
            now = clock_ns()
            # Reserve the full reply budget, so normal expiry need not abandon
            # a just-started transaction at the end of the two-minute window.
            if deadline - now <= round(REPLY_TIMEOUT * 1e9):
                state = 'COMPLETE_TIME_LIMIT'
                break
            due = now if previous_start is None else previous_start + round(1e9 / TARGET_HZ)
            while now < due and not cancelled():
                sleeper(min((due - now) / 1e9, 0.05))
                now = clock_ns()
            if cancelled():
                state = 'STOPPED_BY_OPERATOR'
                break
            if deadline - now <= round(REPLY_TIMEOUT * 1e9):
                state = 'COMPLETE_TIME_LIMIT'
                break
            request_start = clock_ns()
            item = poller.poll(REPLY_TIMEOUT, session_deadline=deadline / 1e9)
            received = clock_ns()
            reading = item['reading']
            if first_values is None:
                first_values = list(reading.values)
            records.append({'index': len(records) + 1, 'received_counter_ns': received,
                            'request_start_counter_ns': request_start,
                            'host_transaction_seconds': item['host_transaction_seconds'],
                            'reading': asdict(reading)})
            previous_start = request_start
            emit()
            if consecutive_publication_errors >= 3:
                raise FeedbackError('Live display publication failed three times; observation stopped')
        else:
            state = 'COMPLETE_SAMPLE_LIMIT'
    except (OSError, FeedbackError) as exc:
        state, error = 'FAILED', str(exc)
        observer.fail(exc)
    finally:
        try:
            observer.finish()
        except FeedbackError as exc:
            state, error = 'FAILED', str(exc)
        emit(final=True)
    finish = clock_ns()
    return {'state': state, 'error': error, 'samples_received': len(records),
            'requests_completely_sent': poller.requests_sent, 'records': records,
            'elapsed_seconds': (finish - start) / 1e9, 'publication_errors': publication_errors,
            'first_values': first_values, 'last_values': list(observer.last.values) if observer.last else None,
            'max_change_from_first': [max(abs(x['reading']['values'][j] - first_values[j]) for x in records) for j in range(6)] if records else None,
            'wire_capture': wire.report(), 'measurement_age_known': False,
            'final_observer_state': observer.snapshot(finish / 1e9)}


def execute_live(plan: LivePlan, *, latest_path: Path, cancel_path: Path, execute=False):
    if execute is not True:
        return plan.describe()
    import socket

    started = time.perf_counter_ns()
    result = None
    attempted = False
    paths_valid = False
    local_endpoint = remote_endpoint = None

    def publish(data):
        publish_json(latest_path, data)

    try:
        validate_live_paths(latest_path, cancel_path)
        paths_valid = True
        if cancel_path.exists():
            return {'state': 'STOPPED_BY_OPERATOR', 'error': None, 'connection_attempted': False,
                    'samples_received': 0, 'records': [], 'plan': plan.describe()}
        # Fail a local publication problem before any controller contact. This
        # also replaces a previous run's display with an explicit waiting state.
        publish({'mode': 'NATIVE_LIVE_OBSERVER', 'state': 'WAITING', 'error': None,
                 'published_counter_ns': time.perf_counter_ns(),
                 'sample_received_counter_ns': None, 'samples': 0, 'values': None})
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
            attempted = True
            stream.settimeout(REPLY_TIMEOUT)
            stream.bind((plan.source_address, 0))
            stream.connect((plan.host, plan.port))
            local_endpoint, remote_endpoint = stream.getsockname(), stream.getpeername()
            if local_endpoint[0] != plan.source_address or tuple(remote_endpoint) != (plan.host, plan.port):
                raise FeedbackError('Connected socket does not match the approved endpoint')
            result = collect_live(stream, publish, cancelled=cancel_path.exists,
                                  deadline_ns=started + MAX_SECONDS * 1_000_000_000)
    except (OSError, ValueError) as exc:
        result = {'state': 'FAILED', 'error': str(exc), 'samples_received': 0, 'records': [], 'wire_capture': None}
        if paths_valid:
            try:
                publish({'mode': 'NATIVE_LIVE_OBSERVER', 'state': 'FAILED', 'error': str(exc),
                         'published_counter_ns': time.perf_counter_ns(), 'sample_received_counter_ns': None,
                         'samples': 0, 'values': None})
            except OSError:
                pass
    return {**result, 'mode': 'EXPLICIT_NATIVE_LIVE_OBSERVER', 'plan': plan.describe(),
            'connection_attempted': attempted, 'local_endpoint': local_endpoint,
            'remote_endpoint': remote_endpoint, 'automatic_reconnect': False,
            'operator_owns_all_pendant_motion': True}
