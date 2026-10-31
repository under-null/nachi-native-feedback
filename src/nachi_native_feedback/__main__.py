"""Offline replay/demo plus a plan-first, separately approved future TCP probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

from .framing import encode_frame
from .observer import FeedbackObserver
from .probe import ProbePlan, execute_probe
from .protocol import FeedbackError, build_joint_request


def synthetic_payload(index):
    values = [10.0 + 2 * math.sin(index / 10), -20.0, 30.0, -40.0, 50.0, -60.0]
    values_xml = ''.join(f'<r>{x:.6f}</r>' for x in values)
    return (f'<flexData version="1" xmlns="flex.gui"><dataExchange><dataUpdate seqid="{index}">'
            f'<data unit="1" group="Generic" id="SYSTEM!" subid="400" extid="-1" count="6">'
            f'{values_xml}</data></dataUpdate></dataExchange></flexData>').encode('utf-8')


def demo(samples=240):
    observer = FeedbackObserver(stale_after=0.5)
    first = None
    last = None
    for index in range(samples):
        frame = encode_frame(synthetic_payload(index))
        for chunk in (frame[:1], frame[1:7], frame[7:19], frame[19:]):
            observer.ingest(chunk, index * 0.02)
        last = observer.snapshot(index * 0.02)
        if first is None:
            first = last
    stale = observer.snapshot((samples - 1) * 0.02 + 0.6)
    observer.finish()
    return {'mode': 'OFFLINE_SYNTHETIC_DEMO', 'controller_contacted': False,
            'timebase': 'virtual clock; not measured controller throughput',
            'first': first, 'last': last, 'after_silence': stale,
            'after_disconnect': observer.snapshot((samples - 1) * 0.02 + 0.6)}


def replay(path: Path):
    # No arbitrary capture timestamps are promoted to device measurement time.
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Offline capture exceeds 8 MiB limit')
    observer = FeedbackObserver()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4096), b''):
            digest.update(chunk)
            observer.ingest(chunk, time.monotonic())
    observer.finish()
    return {'mode': 'OFFLINE_FILE_REPLAY', 'controller_contacted': False,
            'capture_sha256': digest.hexdigest(),
            'timebase': 'local file replay; rates do not measure controller throughput',
            'final_state': observer.snapshot(time.monotonic())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    demo_parser = subs.add_parser('demo', help='Synthetic fragmented-stream demonstration')
    demo_parser.add_argument('--samples', type=int, default=240, choices=range(1, 10001), metavar='1..10000')
    replay_parser = subs.add_parser('replay', help='Decode a bounded saved binary stream, offline')
    replay_parser.add_argument('capture', type=Path)
    request_parser = subs.add_parser('request', help='Display the fixed one-shot request; no network')
    probe_parser = subs.add_parser('probe', help='Plan only unless --execute is explicitly supplied')
    probe_parser.add_argument('--host', required=True, help='One literal unicast IPv4 address; no DNS or scan')
    probe_parser.add_argument('--port', type=int, default=9876)
    probe_parser.add_argument('--samples', type=int, default=1)
    probe_parser.add_argument('--timeout', type=float, default=2.0)
    probe_parser.add_argument('--duration', type=float, default=5.0)
    probe_parser.add_argument('--source-address', help='Bind this literal local IPv4 address; do not change adapter settings')
    probe_parser.add_argument('--execute', action='store_true',
                              help='Connect once. An agent must first obtain specific user approval under AGENTS.md.')
    benchmark_parser = subs.add_parser('benchmark', help='Fixed stationary timing plan; no network without --execute')
    benchmark_parser.add_argument('--host', required=True)
    benchmark_parser.add_argument('--source-address', required=True)
    benchmark_parser.add_argument('--port', type=int, default=9876)
    benchmark_parser.add_argument('--cancel-path', type=Path, help='Local cancellation marker; stops further reads')
    benchmark_parser.add_argument('--execute', action='store_true', help='Requires specific user authorization under AGENTS.md')
    live_parser = subs.add_parser('live', help='Bounded native observer plan; operator owns all pendant motion')
    live_parser.add_argument('--host', required=True)
    live_parser.add_argument('--source-address', required=True)
    live_parser.add_argument('--port', type=int, default=9876)
    live_parser.add_argument('--latest-path', type=Path, required=True)
    live_parser.add_argument('--cancel-path', type=Path, required=True)
    live_parser.add_argument('--execute', action='store_true', help='Requires specific user authorization under AGENTS.md')
    for child in (demo_parser, replay_parser, request_parser, probe_parser, benchmark_parser, live_parser):
        child.add_argument('--output', type=Path, help='Save JSON locally')
    args = parser.parse_args()
    try:
        if args.command == 'demo':
            result = demo(args.samples)
        elif args.command == 'replay':
            result = replay(args.capture)
        elif args.command == 'request':
            frame = build_joint_request()
            result = {'mode': 'OFFLINE_REQUEST_INSPECTION', 'controller_contacted': False,
                      'xml': frame[8:].decode('utf-8'), 'frame_hex': frame.hex(),
                      'sha256': hashlib.sha256(frame).hexdigest()}
        elif args.command == 'probe':
            plan = ProbePlan(args.host, args.port, args.samples, args.timeout, args.duration, args.source_address)
            result = execute_probe(plan, execute=args.execute)
        elif args.command == 'benchmark':
            from .benchmark import BenchmarkPlan, execute_benchmark
            plan = BenchmarkPlan(args.host, args.source_address, args.port)
            result = execute_benchmark(plan, execute=args.execute, cancel_path=args.cancel_path)
        else:
            from .live import LivePlan, execute_live
            plan = LivePlan(args.host, args.source_address, args.port)
            result = execute_live(plan, latest_path=args.latest_path, cancel_path=args.cancel_path, execute=args.execute)
        body = json.dumps(result, indent=2, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(body + '\n', encoding='utf-8')
        print(body)
        return 1 if result.get('final_state', {}).get('failure') or result.get('state') in ('FAILED', 'CANCELLED') else 0
    except (OSError, FeedbackError, ValueError) as exc:
        print(json.dumps({'mode': 'ERROR', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
