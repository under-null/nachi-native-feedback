"""Recompute exported timing arithmetic offline, without hardware or vendor files."""
from pathlib import Path
import csv
import hashlib
import json
import math
import statistics

ROOT = Path(__file__).resolve().parents[1]
STATIONARY_COLUMNS = {'sample', 'phase', 'target_hz', 'request_ms', 'reply_ms',
                      'transaction_ms', 'dispatch_lateness_ms', 'request_bytes', 'reply_bytes'}
LIVE_COLUMNS = {'sample', 'request_ms', 'reply_ms', 'transaction_ms'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, name):
    require(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-8), 'Metric mismatch: '+name)


def rows(path, expected_columns):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        require(set(reader.fieldnames or []) == expected_columns, 'Unexpected timing columns')
        values = [{key: float(value) for key, value in row.items()} for row in reader]
    require(all(math.isfinite(v) and v >= 0 for row in values for v in row.values()), 'Invalid timing number')
    require([row['sample'] for row in values] == list(range(1, len(values)+1)), 'Missing/reordered sample')
    require(values and values[0]['request_ms'] == 0, 'Counter origin was not shifted')
    require(all(b['request_ms'] > a['request_ms'] and b['reply_ms'] > a['reply_ms']
                and b['request_ms'] >= a['reply_ms'] for a, b in zip(values, values[1:])),
            'Nonmonotonic or overlapping timing rows')
    require(all(row['reply_ms'] >= row['request_ms'] for row in values), 'Reply precedes request')
    return values


def verify(root=ROOT):
    results = Path(root)/'results'
    summary = json.loads((results/'hardware-summary.json').read_text())
    require(summary['evidence_type'] == 'sanitized_measured_hardware_results', 'Unlabelled hardware results')
    for name, expected in summary['timing_files'].items():
        require(name in ('stationary-timing.csv', 'pose-observation-timing.csv'), 'Unexpected result file')
        require(hashlib.sha256((results/name).read_bytes()).hexdigest() == expected, 'Timing-file hash mismatch')
    stationary = rows(results/'stationary-timing.csv', STATIONARY_COLUMNS)
    live = rows(results/'pose-observation-timing.csv', LIVE_COLUMNS)
    require(len(stationary) == summary['stationary']['responses'] == 250, 'Stationary sample count mismatch')
    close(sum(row['request_bytes'] for row in stationary), summary['stationary']['application_tx_bytes'], 'TX bytes')
    close(sum(row['reply_bytes'] for row in stationary), summary['stationary']['application_rx_bytes'], 'RX bytes')
    for number, phase in enumerate(summary['stationary']['phases'], 1):
        all_rows = [row for row in stationary if row['phase'] == number]
        require(len(all_rows) == phase['samples'] and all(row['target_hz'] == phase['target_hz'] for row in all_rows), 'Phase mismatch')
        steady = all_rows[5:]
        require(len(steady) == phase['steady_samples'], 'Warmup exclusion mismatch')
        latencies = sorted(row['transaction_ms'] for row in steady)
        close((len(steady)-1)*1000/(steady[-1]['reply_ms']-steady[0]['reply_ms']), phase['reply_hz'], 'phase rate')
        for key, actual in (('median_reply_ms', statistics.median(latencies)),
                            ('p95_reply_ms', latencies[math.ceil(.95*len(latencies))-1]),
                            ('max_reply_ms', max(latencies))):
            close(actual, phase[key], key)
    observed = summary['pose_observation']
    require(len(live) == observed['samples'] == observed['frames'] == 5740, 'Observation sample count mismatch')
    latencies = sorted(row['transaction_ms'] for row in live)
    close((len(live)-1)*1000/(live[-1]['reply_ms']-live[0]['reply_ms']), observed['receipt_rate_hz'], 'observation rate')
    close(statistics.median(latencies), observed['median_transaction_ms'], 'observation median')
    close(latencies[math.ceil(.95*len(latencies))-1], observed['p95_transaction_ms'], 'observation p95')
    close(max(latencies), observed['max_transaction_ms'], 'observation max')
    close(max(b['reply_ms']-a['reply_ms'] for a, b in zip(live, live[1:])), observed['max_reply_interval_ms'], 'observation gap')
    require(not any(summary['measurement_limits'].values()), 'Unsupported measurement claim')
    return {'state': 'PASS_EXPORTED_TIMING_ARITHMETIC', 'controller_contacted': False,
            'stationary_rows': len(stationary), 'observation_rows': len(live),
            'raw_hardware_authenticity_independently_verified': False}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
