"""Plan-first stationary timing run of the already observed fixed joint read.

One endpoint, one connection, serial requests, bounded pacing, no catch-up burst.
Execution requires the specific hardware authorization in AGENTS.md.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import statistics
import time

from .observer import FeedbackObserver
from .probe import ProbePlan, _CaptureStream
from .protocol import FeedbackError, build_joint_request
from .session import ReadOnlyPoller

PHASES = ((5.0, 50), (20.0, 100), (50.0, 100))
MAX_DURATION_SECONDS = 30.0
RESPONSE_TIMEOUT_SECONDS = 1.0
WARMUP_PER_PHASE = 5


def distribution(values):
    if not values:
        return None
    data = sorted(values)
    return {'count': len(data), 'min': data[0], 'median': statistics.median(data),
            'p95': data[math.ceil(0.95 * len(data)) - 1],
            'p99': data[math.ceil(0.99 * len(data)) - 1], 'max': data[-1],
            'mean': statistics.fmean(data), 'population_stddev': statistics.pstdev(data),
            'quantile_method': 'nearest rank'}


@dataclass(frozen=True)
class BenchmarkPlan:
    host: str
    source_address: str
    port: int = 9876

    def __post_init__(self):
        if self.source_address is None:
            raise ValueError('Benchmark requires an explicit local IPv4 source')
        ProbePlan(self.host, self.port, source_address=self.source_address)

    def describe(self):
        frame = build_joint_request()
        return {**asdict(self), 'mode': 'BENCHMARK_PLAN_ONLY', 'controller_contacted': False,
                'max_connections': 1, 'automatic_reconnect': False,
                'phases': [{'target_hz': hz, 'samples': count} for hz, count in PHASES],
                'max_read_requests': sum(count for _, count in PHASES),
                'nominal_duration_seconds': sum(count / hz for hz, count in PHASES),
                'session_limit_seconds': MAX_DURATION_SECONDS,
                'per_response_timeout_seconds': RESPONSE_TIMEOUT_SECONDS,
                'warmup_samples_excluded_per_phase': WARMUP_PER_PHASE,
                'max_application_bytes_sent': len(frame) * sum(n for _, n in PHASES),
                'request_frame_sha256': hashlib.sha256(frame).hexdigest(),
                'timing_clock': 'perf_counter_ns / QueryPerformanceCounter on this host',
                'one_outstanding_request': True, 'catch_up_bursts': False,
                'stationary_entire_run': True, 'controller_sample_age_known': False,
                'motion_motor_io_or_configuration_operations': False,
                'network_settings_changed_by_this_module': False}


class _MeasuredStream:
    def __init__(self, wire, clock_ns):
        self.wire = wire
        self.clock_ns = clock_ns
        self.send_calls = []
        self.recv_calls = []

    def settimeout(self, timeout):
        self.wire.settimeout(timeout)

    def send(self, data):
        before = self.clock_ns()
        count = self.wire.send(data)
        after = self.clock_ns()
        self.send_calls.append({'before_ns': before, 'after_ns': after, 'bytes': count})
        return count

    def recv(self, size):
        before = self.clock_ns()
        chunk = self.wire.recv(size)
        after = self.clock_ns()
        self.recv_calls.append({'before_ns': before, 'after_ns': after, 'bytes': len(chunk)})
        return chunk


class BenchmarkCancelled(FeedbackError):
    pass


def collect(stream, *, clock_ns=time.perf_counter_ns, sleeper=time.sleep, cancelled=lambda: False, deadline_ns=None):
    """Injectable collection engine. It neither creates nor reconnects a socket."""
    wire = _CaptureStream(stream)
    measured = _MeasuredStream(wire, clock_ns)
    observer = FeedbackObserver(stale_after=RESPONSE_TIMEOUT_SECONDS)
    poller = ReadOnlyPoller(measured, observer, clock=lambda: clock_ns() / 1e9)
    started = clock_ns()
    deadline = started + int(MAX_DURATION_SECONDS * 1e9)
    if deadline_ns is not None:
        deadline = min(deadline, deadline_ns)
    records = []
    previous_start = None
    state = 'RUNNING'
    error = None

    def check():
        if cancelled():
            raise BenchmarkCancelled('Local cancellation requested; no further read requests')
        now = clock_ns()
        if now >= deadline:
            raise FeedbackError('Benchmark session deadline expired')
        return now

    try:
        for phase, (target_hz, samples) in enumerate(PHASES, 1):
            period_ns = round(1e9 / target_hz)
            for index in range(samples):
                now = check()
                # Scheduling from the last actual start prevents missed slots
                # being compressed into a burst, including across phase changes.
                due = now if previous_start is None else previous_start + period_ns
                while now < due:
                    sleeper(min((due - now) / 1e9, (deadline - now) / 1e9, 0.05))
                    now = check()
                before_send = len(measured.send_calls)
                before_recv = len(measured.recv_calls)
                request_start = check()
                item = poller.poll(RESPONSE_TIMEOUT_SECONDS, session_deadline=deadline / 1e9)
                valid_sample = clock_ns()
                if valid_sample >= deadline:
                    raise FeedbackError('Reply completed after the benchmark session deadline')
                sends = measured.send_calls[before_send:]
                recvs = measured.recv_calls[before_recv:]
                if not sends or not recvs:
                    raise FeedbackError('Incomplete timing trace')
                records.append({'phase': phase, 'sample_in_phase': index + 1,
                                'target_hz': target_hz, 'request_start_ns': request_start,
                                'first_send_call_ns': sends[0]['before_ns'],
                                'last_send_return_ns': sends[-1]['after_ns'],
                                'first_recv_return_ns': recvs[0]['after_ns'],
                                'complete_reply_recv_return_ns': recvs[-1]['after_ns'],
                                'valid_sample_ns': valid_sample,
                                'write_calls': len(sends), 'read_calls': len(recvs),
                                'request_bytes': sum(x['bytes'] for x in sends),
                                'reply_bytes': sum(x['bytes'] for x in recvs),
                                'dispatch_lateness_ms': max(0, request_start - due) / 1e6,
                                'response_complete_ms': (recvs[-1]['after_ns'] - sends[0]['before_ns']) / 1e6,
                                'valid_sample_ms': (valid_sample - request_start) / 1e6,
                                'reading': asdict(item['reading'])})
                previous_start = sends[0]['before_ns']
        state = 'COMPLETE'
    except BenchmarkCancelled as exc:
        state, error = 'CANCELLED', str(exc)
        observer.fail(exc)
    except (OSError, FeedbackError) as exc:
        state, error = 'FAILED', str(exc)
        observer.fail(exc)
    finally:
        try:
            observer.finish()
        except FeedbackError as exc:
            state, error = 'FAILED', str(exc)
    finished = clock_ns()
    result = {'state': state, 'error': error, 'started_counter_ns': started,
              'finished_counter_ns': finished, 'collection_elapsed_seconds': (finished - started) / 1e9,
              'requests_completely_sent': poller.requests_sent, 'samples_received': len(records),
              'records': records, 'final_observer_state': observer.snapshot(finished / 1e9),
              'phases': summarize(records), 'wire_capture': wire.report(),
              'io_calls': {'send': measured.send_calls, 'recv': measured.recv_calls},
              'measurement_age_known': False, 'request_correlation_verified': False,
              'timing_meaning': 'Host request/reply and dispatch timing; not controller acquisition age or servo rate'}
    return result


def summarize(records):
    phases = []
    for phase, (target_hz, expected) in enumerate(PHASES, 1):
        rows = [x for x in records if x['phase'] == phase]
        steady = rows[WARMUP_PER_PHASE:]
        starts = [x['request_start_ns'] for x in steady]
        arrivals = [x['complete_reply_recv_return_ns'] for x in steady]
        intervals_ms = [(b - a) / 1e6 for a, b in zip(arrivals, arrivals[1:])]
        dispatch_ms = [(b - a) / 1e6 for a, b in zip(starts, starts[1:])]
        deviation_ms = [abs(x - 1000 / target_hz) for x in intervals_ms]
        span = (arrivals[-1] - arrivals[0]) / 1e9 if len(arrivals) > 1 else 0
        phases.append({'phase': phase, 'target_hz': target_hz, 'expected_samples': expected,
                       'samples_received': len(rows), 'warmup_excluded': min(len(rows), WARMUP_PER_PHASE),
                       'steady_samples': len(steady), 'achieved_reply_hz': (len(steady) - 1) / span if span > 0 else None,
                       'response_complete_ms_all': distribution([x['response_complete_ms'] for x in rows]),
                       'response_complete_ms_steady': distribution([x['response_complete_ms'] for x in steady]),
                       'valid_sample_ms_steady': distribution([x['valid_sample_ms'] for x in steady]),
                       'reply_interval_ms_steady': distribution(intervals_ms),
                       'dispatch_interval_ms_steady': distribution(dispatch_ms),
                       'absolute_reply_interval_deviation_from_target_ms': distribution(deviation_ms),
                       'dispatch_lateness_ms': distribution([x['dispatch_lateness_ms'] for x in steady]),
                       'transactions_exceeding_target_period': sum(x['valid_sample_ms'] > 1000 / target_hz for x in steady)})
    return phases


def execute_benchmark(plan: BenchmarkPlan, *, execute=False, cancel_path: Path | None = None):
    if execute is not True:
        return plan.describe()
    import socket

    started = time.perf_counter_ns()
    connection_attempted = False
    local_endpoint = remote_endpoint = None
    result = None
    try:
        if cancel_path is not None and cancel_path.exists():
            raise BenchmarkCancelled('Local cancellation was requested before connection')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
            connection_attempted = True
            stream.settimeout(RESPONSE_TIMEOUT_SECONDS)
            stream.bind((plan.source_address, 0))
            stream.connect((plan.host, plan.port))
            local_endpoint, remote_endpoint = stream.getsockname(), stream.getpeername()
            if local_endpoint[0] != plan.source_address or tuple(remote_endpoint) != (plan.host, plan.port):
                raise FeedbackError('Socket endpoint does not match the approved source/target')
            result = collect(stream, cancelled=lambda: cancel_path is not None and cancel_path.exists(),
                             deadline_ns=started + int(MAX_DURATION_SECONDS * 1e9))
    except (OSError, FeedbackError) as exc:
        result = {'state': 'FAILED', 'error': str(exc), 'records': [], 'samples_received': 0,
                  'requests_completely_sent': 0, 'wire_capture': None, 'phases': []}
    return {**result, 'mode': 'EXPLICIT_STATIONARY_BENCHMARK', 'plan': plan.describe(),
            'connection_attempted': connection_attempted, 'local_endpoint': local_endpoint,
            'remote_endpoint': remote_endpoint,
            'total_elapsed_seconds': (time.perf_counter_ns() - started) / 1e9,
            'clock_information': vars(time.get_clock_info('perf_counter')),
            'automatic_reconnect': False, 'controller_sample_age_known': False}
