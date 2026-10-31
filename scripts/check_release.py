"""Offline source/archive content check. Does not publish or contact hardware."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import ipaddress
import json
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {'README.md', 'LICENSE', 'CHANGELOG.md', 'CONTRIBUTING.md', 'AGENTS.md',
             'pyproject.toml', 'MANIFEST.in', '.gitignore', '.gitattributes', 'release-manifest.json',
             'PKG-INFO', 'setup.cfg'}
GENERATED_METADATA = {'PKG-INFO', 'setup.cfg'}
TOP_DIRS = {'src', 'docs', 'tests', 'results', 'scripts'}
IGNORED = {'.git', '__pycache__', '.pytest_cache', 'build', 'dist'}
ALLOWED_SUFFIXES = {'.py', '.md', '.toml', '.json', '.csv', '.xml', '.bin', '.txt', '.in'}
RUNTIME_FILES = {'__init__.py', '__main__.py', 'framing.py', 'protocol.py',
                 'observer.py', 'probe.py', 'session.py', 'benchmark.py', 'live.py', 'live_monitor.py'}
WHEEL_METADATA = {'METADATA', 'WHEEL', 'entry_points.txt', 'top_level.txt', 'RECORD', 'licenses/LICENSE'}
SDIST_METADATA = {'PKG-INFO', 'setup.cfg'} | {
    'src/nachi_native_feedback.egg-info/'+name for name in (
        'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt', 'entry_points.txt', 'requires.txt', 'top_level.txt')}
DOC_NETS = tuple(ipaddress.ip_network(value) for value in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24'))
INVALID_TEST_IPS = {'0.0.0.0', '224.0.0.1', '255.255.255.255'}


def inspect_body(name, body):
    def require(condition, message):
        if not condition:
            raise ValueError(name+': '+message)
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name,
            'unsafe member path')
    require(len(body) <= 8*1024*1024, 'unexpected file size')
    if path.suffix == '.bin':
        require(path.name == 'derived-response-shape.bin', 'unexpected binary fixture')
        require(body[:4] == bytes.fromhex('5eba0100') and int.from_bytes(body[4:8], 'little') == len(body)-8,
                'invalid derived fixture envelope')
        body = body[8:]
    text = body.decode('utf-8', errors='strict')
    require(not re.search(r'(?i)(?:(?<![\w])[a-z]:[\\/]|/(?:Users|home)/)', text), 'absolute/private filesystem path')
    require(not re.search(r'(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b', text), 'MAC-like identifier')
    require(not re.search(r'(?i)(?:gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|'
                          r'(?:password|api[_-]?key|access[_-]?token)\s*[:=]\s*["\x27][^"\x27]{8,})', text),
            'credential-like content')
    for value in re.findall(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', text):
        address = ipaddress.ip_address(value)
        require(value in INVALID_TEST_IPS or any(address in network for network in DOC_NETS), 'non-documentation endpoint')


def source_files(root=ROOT):
    for path in sorted(Path(root).rglob('*')):
        relative = path.relative_to(root)
        if any(part in IGNORED or part.endswith('.egg-info') for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Symlink in release tree')
        if path.is_dir():
            continue
        if len(relative.parts) == 1:
            if relative.name not in TOP_FILES:
                raise ValueError('Unexpected root file: '+relative.name)
        elif relative.parts[0] not in TOP_DIRS or path.suffix not in ALLOWED_SUFFIXES:
            raise ValueError('Unexpected source/vendor file: '+relative.as_posix())
        yield relative.as_posix(), path.read_bytes()


def check(root=ROOT, archive=None):
    checked = []
    if archive is None:
        entries = list(source_files(root))
    elif str(archive).endswith('.whl'):
        with zipfile.ZipFile(archive) as bundle:
            if bundle.comment or any(item.comment or item.file_size > 8*1024*1024 for item in bundle.infolist()):
                raise ValueError('Unexpected wheel comment/file size')
            entries = [(item.filename, bundle.read(item)) for item in bundle.infolist() if not item.is_dir()]
        packages = {'nachi_native_feedback/'+name for name in RUNTIME_FILES}
        metadata_roots = {name.split('/')[0] for name, _ in entries if '.dist-info/' in name}
        if len(metadata_roots) != 1:
            raise ValueError('Expected one wheel metadata directory')
        metadata_root = metadata_roots.pop()
        if not metadata_root.startswith('nachi_native_feedback-'):
            raise ValueError('Unexpected wheel metadata owner')
        allowed = packages | {metadata_root+'/'+name for name in WHEEL_METADATA}
        if {name for name, _ in entries} != allowed:
            raise ValueError('Unexpected wheel contents')
    else:
        with tarfile.open(archive, 'r:gz') as bundle:
            entries = []
            archive_roots = set()
            for item in bundle.getmembers():
                if item.isdir():
                    continue
                if not item.isfile() or item.uname or item.gname or item.uid or item.gid:
                    raise ValueError('Unexpected archive member/owner metadata')
                name = PurePosixPath(item.name)
                if name.is_absolute() or '..' in name.parts or len(name.parts) < 2:
                    raise ValueError('Unsafe source archive path')
                archive_roots.add(name.parts[0])
                stream = bundle.extractfile(item)
                entries.append(('/'.join(name.parts[1:]), stream.read(8*1024*1024+1)))
            if len(archive_roots) != 1:
                raise ValueError('Expected one source archive root')
    if len({name for name, _ in entries}) != len(entries):
        raise ValueError('Duplicate release/archive filename')
    if sum(len(body) for _, body in entries) > 32*1024*1024:
        raise ValueError('Unexpected release/archive total size')
    for name, body in entries:
        inspect_body(name, body)
        suffix = PurePosixPath(name).suffix.lower()
        if suffix in ('.pdf', '.dll', '.so', '.dat', '.pcap', '.pcapng', '.exe', '.xsd', '.chm'):
            raise ValueError('Vendor/private binary in release')
        checked.append(name)
    if archive is not None:
        expected = json.loads((Path(root)/'release-manifest.json').read_text())['files']
        contents = dict(entries)
        if str(archive).endswith('.whl'):
            for name in RUNTIME_FILES:
                if hashlib.sha256(contents['nachi_native_feedback/'+name]).hexdigest() != expected['src/nachi_native_feedback/'+name]:
                    raise ValueError('Wheel runtime differs from reviewed source manifest')
            if contents[metadata_root+'/licenses/LICENSE'] != (Path(root)/'LICENSE').read_bytes():
                raise ValueError('Wheel license differs from reviewed source')
        else:
            if set(contents) != set(expected) | {'release-manifest.json'} | SDIST_METADATA:
                raise ValueError('Source archive contains missing or unreviewed files')
            if json.loads(contents['release-manifest.json'])['files'] != expected:
                raise ValueError('Source archive manifest differs from reviewed repository')
            if any(hashlib.sha256(contents[name]).hexdigest() != value for name, value in expected.items()):
                raise ValueError('Source archive differs from reviewed source manifest')
    return {'state': 'PASS_RELEASE_CONTENT_CHECK', 'files_checked': len(checked),
            'controller_contacted': False, 'published': False,
            'archive_matches_reviewed_manifest': True if archive is not None else None,
            'limit': 'Pattern/allowlist check, not a complete privacy or rights guarantee.'}


def write_manifest(root=ROOT):
    files = {name: hashlib.sha256(body).hexdigest() for name, body in source_files(root)
             if name != 'release-manifest.json' and name not in GENERATED_METADATA}
    (Path(root)/'release-manifest.json').write_text(json.dumps({'format': 1, 'files': files}, indent=2)+'\n', encoding='utf-8', newline='\n')


def verify_manifest(root=ROOT):
    manifest = json.loads((Path(root)/'release-manifest.json').read_text())['files']
    actual = {name: hashlib.sha256(body).hexdigest() for name, body in source_files(root)
              if name != 'release-manifest.json' and name not in GENERATED_METADATA}
    if actual != manifest:
        raise ValueError('Release manifest differs from source contents')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--write-manifest', action='store_true')
    parser.add_argument('--verify-manifest', action='store_true')
    args = parser.parse_args()
    if args.write_manifest:
        write_manifest()
    if args.verify_manifest:
        verify_manifest()
    print(json.dumps(check(archive=args.archive), indent=2))
