"""Local-file and onboarding regressions; no GUI or real socket is opened."""
import json
import sys

import pytest

from nachi_native_feedback.__main__ import main
from nachi_native_feedback.live import LivePlan, execute_live
from nachi_native_feedback import live_monitor


def record(**changes):
    return {'state': 'RUNNING', 'sample_received_counter_ns': 1_000_000_000,
            'samples': 20, 'initial_samples_received': True,
            'values': [1, 2, 3, 4, 5, 6], 'first_values': [0]*6,
            'receipt_rate_hz': 50, 'remaining_seconds': 100, **changes}


@pytest.mark.parametrize('changes', [
    {'values': [1]}, {'values': ['1']*6}, {'values': [True]*6},
    {'values': [float('nan')]*6}, {'values': [float('inf')]*6}, {'values': [10**500]*6},
    {'first_values': [0]}, {'state': 1}, {'state': 'unknown'},
    {'samples': '20'}, {'samples': True}, {'samples': -1}, {'samples': 6001},
    {'sample_received_counter_ns': -1}, {'sample_received_counter_ns': 2**80},
    {'receipt_rate_hz': '50'}, {'remaining_seconds': float('nan')},
    {'initial_samples_received': 'true'}, {'error': []}, {'values': None},
])
def test_invalid_status_never_becomes_a_live_display(changes, tmp_path):
    path = tmp_path/'latest.json'
    path.write_text(json.dumps(record(**changes)))
    data = live_monitor.read_display(path)
    assert live_monitor.presentation(data, 1_100_000_000)[0] == 'FAILED'
    assert data['values'] is None


@pytest.mark.parametrize('body', ['[]', 'null', '{', 'x'*65537])
def test_invalid_file_shape_and_size_are_display_failures(tmp_path, body):
    path = tmp_path/'latest.json'; path.write_text(body)
    assert live_monitor.read_display(path)['state'] == 'FAILED'


def test_valid_status_missing_file_and_recovery(tmp_path):
    path = tmp_path/'latest.json'
    assert live_monitor.read_display(path)['state'] == 'WAITING'
    path.write_text('bad')
    assert live_monitor.read_display(path)['state'] == 'FAILED'
    path.write_text(json.dumps(record()))
    assert live_monitor.presentation(live_monitor.read_display(path), 1_100_000_000)[:2] == ('RECEIVING', True)


def test_help_does_not_require_tk(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, 'tkinter', None)
    monkeypatch.setattr(sys, 'argv', ['monitor', '--help'])
    with pytest.raises(SystemExit) as exc:
        live_monitor.main()
    assert exc.value.code == 0 and '--data' in capsys.readouterr().out


def test_missing_tk_has_actionable_message(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, 'tkinter', None)
    monkeypatch.setattr(sys, 'argv', ['monitor', '--data', str(tmp_path/'latest.json'),
                                    '--cancel-path', str(tmp_path/'cancel')])
    with pytest.raises(SystemExit, match='Tcl/Tk'):
        live_monitor.main()


@pytest.mark.parametrize('kind', ['missing-parent', 'same-file', 'directory'])
def test_bad_destinations_fail_before_socket_creation(tmp_path, kind):
    latest, cancel = tmp_path/'latest.json', tmp_path/'cancel'
    if kind == 'missing-parent':
        latest = tmp_path/'missing'/'latest.json'
    elif kind == 'same-file':
        cancel = latest
    else:
        latest.mkdir()
    result = execute_live(LivePlan('192.0.2.2', '192.0.2.10'), latest_path=latest,
                          cancel_path=cancel, execute=True)
    assert result['state'] == 'FAILED' and not result['connection_attempted']


def test_publication_error_fails_before_socket_creation(monkeypatch, tmp_path):
    from nachi_native_feedback import live
    def cannot_publish(*args):
        raise PermissionError('Synthetic permission failure')
    monkeypatch.setattr(live, 'publish_json', cannot_publish)
    result = execute_live(LivePlan('192.0.2.2', '192.0.2.10'), latest_path=tmp_path/'latest.json',
                          cancel_path=tmp_path/'cancel', execute=True)
    assert result['state'] == 'FAILED' and not result['connection_attempted']


def test_output_cannot_overwrite_live_status(monkeypatch, tmp_path, capsys):
    latest = tmp_path/'latest.json'
    monkeypatch.setattr(sys, 'argv', ['feedback', 'live', '--host', '192.0.2.2',
        '--source-address', '192.0.2.10', '--latest-path', str(latest),
        '--cancel-path', str(tmp_path/'cancel'), '--output', str(latest)])
    assert main() == 1 and 'different files' in capsys.readouterr().err
    assert not latest.exists()
