from pathlib import Path
import importlib.util
import json
import sys
import hashlib
import re
import zipfile

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


def test_all_relative_document_links_resolve():
    for path in [ROOT/'README.md', *sorted((ROOT/'docs').glob('*.md'))]:
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if target.startswith(('https://', 'http://', '#')):
                continue
            assert (path.parent/target.split('#')[0]).is_file(), (path.name, target)


@pytest.mark.parametrize('kind', ['valid', 'extra-header', 'changed-runtime', 'duplicate', 'traversal'])
def test_wheel_check_requires_exact_reviewed_files(tmp_path, kind):
    checker = script('check_release')
    root = tmp_path/'reviewed'; root.mkdir()
    license_body = (ROOT/'LICENSE').read_bytes()
    (root/'LICENSE').write_bytes(license_body)
    contents = {'nachi_native_feedback/'+name: (ROOT/'src/nachi_native_feedback'/name).read_bytes()
                for name in checker.RUNTIME_FILES}
    manifest = {'src/'+name: hashlib.sha256(body).hexdigest() for name, body in contents.items()}
    (root/'release-manifest.json').write_text(json.dumps({'files': manifest}))
    metadata = 'nachi_native_feedback-0.1.0.dev0.dist-info/'
    contents.update({metadata+name: license_body if name == 'licenses/LICENSE' else b'metadata'
                     for name in checker.WHEEL_METADATA})
    if kind == 'extra-header':
        contents['nachi_native_feedback/unreviewed.h'] = b'Unexpected header'
    elif kind == 'changed-runtime':
        contents['nachi_native_feedback/protocol.py'] += b'\n# unexpected change\n'
    elif kind == 'traversal':
        contents['../outside.py'] = b'bad path'
    archive = tmp_path/'candidate.whl'
    with zipfile.ZipFile(archive, 'w') as bundle:
        for name, body in contents.items():
            bundle.writestr(name, body)
        if kind == 'duplicate':
            with pytest.warns(UserWarning):
                bundle.writestr('nachi_native_feedback/protocol.py', b'duplicate')
    if kind == 'valid':
        assert checker.check(root, archive)['archive_matches_reviewed_manifest']
    else:
        with pytest.raises(ValueError):
            checker.check(root, archive)
