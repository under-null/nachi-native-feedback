from pathlib import Path
import importlib.util
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exported_hardware_arithmetic():
    result = script('verify_results').verify(ROOT)
    assert result['stationary_rows'] == 250 and result['observation_rows'] == 5740
    assert not result['raw_hardware_authenticity_independently_verified']


def test_release_contains_only_expected_public_content():
    assert script('check_release').check(ROOT)['files_checked'] > 20


def test_no_original_workspace_package_is_imported():
    import nachi_native_feedback
    assert 'site-packages' in nachi_native_feedback.__file__ or 'src' in nachi_native_feedback.__file__
    assert not any(name.startswith('tools.native_feedback') for name in sys.modules)


@pytest.mark.parametrize('content', [
    b'address = '+b'10'+b'.9.8.7', b':'.join([b'aa']*6),
    ('C'+':/'+'Users/example/private').encode(),
    ('password'+" = '"+'example-secret'+"'").encode(),
])
def test_release_scanner_rejects_private_looking_content(content):
    with pytest.raises(ValueError):
        script('check_release').inspect_body('docs/accidental.md', content)


def test_result_files_do_not_contain_recorded_joint_values():
    result = json.loads((ROOT/'results/hardware-summary.json').read_text())
    assert 'recorded joint poses' in result['sanitization']['omitted']
    assert not result['measurement_limits']['controller_sample_age_known']
    assert all('values' not in line for line in (ROOT/'results/pose-observation-timing.csv').read_text().splitlines())
