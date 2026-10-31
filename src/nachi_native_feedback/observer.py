"""Receipt-age state, deliberately separate from controller measurement freshness."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict
import math
import statistics

from .framing import FrameDecoder, FrameError
from .protocol import FeedbackError, JointReading, parse_message


class FeedbackObserver:
    def __init__(self, stale_after=1.0):
        if isinstance(stale_after, bool) or not math.isfinite(stale_after) or not 0 < stale_after <= 60:
            raise ValueError('Receipt expiry must be in (0, 60] seconds')
        self.stale_after = stale_after
        self.decoder = FrameDecoder()
        self.last: JointReading | None = None
        self.last_received = None
        self.first_received = None
        self._last_clock = None
        self.failure = None
        self.closed = False
        self.frames = 0
        self.samples = 0
        self.heartbeats = 0
        self.unrelated_updates = 0
        self.intervals = deque(maxlen=256)
        self.repeated_seqids = 0

    def fail(self, reason):
        if self.failure is None:
            self.failure = str(reason)

    def _time(self, now):
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
            self.fail('Invalid monotonic clock')
            raise FeedbackError(self.failure)
        if self._last_clock is not None and now < self._last_clock:
            self.fail('Monotonic clock regressed')
            raise FeedbackError(self.failure)
        self._last_clock = now

    def ingest(self, chunk: bytes, now: float) -> tuple[JointReading, ...]:
        self._time(now)
        if self.closed or self.failure:
            raise FeedbackError('Observer has ended or failed; create a new session')
        readings = []
        try:
            for payload in self.decoder.feed(chunk):
                message = parse_message(payload)
                self.frames += 1
                self.heartbeats += message.heartbeats
                self.unrelated_updates += message.unrelated_updates
                for reading in message.readings:
                    if self.last_received is not None:
                        self.intervals.append(now - self.last_received)
                    if self.first_received is None:
                        self.first_received = now
                    if self.last is not None and reading.seqid is not None and reading.seqid == self.last.seqid:
                        self.repeated_seqids += 1
                    self.last = reading
                    self.last_received = now
                    self.samples += 1
                    readings.append(reading)
        except (FrameError, FeedbackError) as exc:
            self.fail(exc)
            raise FeedbackError(str(exc)) from exc
        return tuple(readings)

    def finish(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.decoder.finish()
        except FrameError as exc:
            self.fail(exc)
            raise FeedbackError(str(exc)) from exc

    def snapshot(self, now: float) -> dict:
        self._time(now)
        age = None if self.last_received is None else now - self.last_received
        status = ('FAILED' if self.failure else 'CLOSED' if self.closed else 'NO_DATA' if age is None
                  else 'STALE' if age >= self.stale_after else 'RECENT_RECEIPT')
        sample = asdict(self.last) if self.last is not None else None
        span = None if self.first_received is None else self.last_received - self.first_received
        return {'status': status, 'receipt_age_seconds': age,
                'current_sample': sample if status == 'RECENT_RECEIPT' else None,
                'last_sample_for_history': sample,
                'measurement_age_known': False, 'request_correlation_verified': False,
                'units_verified': False, 'failure': self.failure,
                'frames': self.frames, 'samples': self.samples,
                'heartbeats': self.heartbeats, 'unrelated_updates': self.unrelated_updates,
                'repeated_seqids': self.repeated_seqids,
                'receipt_rate_hz': (self.samples - 1) / span if span and span > 0 else None,
                'median_recent_receipt_interval_seconds': statistics.median(self.intervals) if self.intervals else None}
