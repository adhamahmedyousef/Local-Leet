"""Check the deliverable ZIP, source parity, all compressed shards, and least-privilege manifest."""
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / 'reports/extension-build.json').read_text())
folder = Path(report['unpacked'])
archive = Path(report['zip'])
manifest = json.loads((folder / 'manifest.json').read_text())
assert manifest['manifest_version'] == 3
assert set(manifest.get('permissions', [])) == {'storage', 'alarms'}
assert manifest.get('host_permissions') == ['https://adhamahmedyousef.github.io/*']
assert not manifest.get('web_accessible_resources')
assert manifest['background']['type'] == 'module'
for source in (ROOT / 'extension').iterdir():
    if source.suffix in ('.js', '.css', '.html', '.json'):
        assert source.read_bytes() == (folder / source.name).read_bytes(), f'Stale source: {source.name}'
metadata = json.loads((folder / 'data/metadata.json').read_text())
assert (ROOT / 'extension/assets/logo.png').read_bytes() == (folder / 'assets/logo.png').read_bytes()
entries = 0
for shard, descriptor in metadata['shards'].items():
    raw = (folder / 'data' / f'{shard}.json.gz').read_bytes()
    assert len(raw) == descriptor['bytes']
    assert hashlib.sha256(raw).hexdigest() == descriptor['sha256']
    decoded = json.loads(gzip.decompress(raw))
    assert len(decoded) == descriptor['entries']
    for key in decoded:
        assert key.startswith(('US:', 'CN-SLUG:'))
        assert hashlib.sha256(key.encode()).hexdigest()[:2] == shard
    entries += len(decoded)
assert entries == metadata['indexedUsers']
with zipfile.ZipFile(archive) as package:
    names = package.namelist()
    assert len(names) == len(set(names))
    assert 'manifest.json' in names
    assert not any(name.startswith(('/', '\\')) or '..' in Path(name).parts for name in names)
    for name in names:
        assert package.read(name) == (folder / name).read_bytes(), f'Stale ZIP entry: {name}'
    assert package.testzip() is None
result = {
    'version': manifest['version'], 'snapshotId': metadata['snapshotId'],
    'publicProfiles': entries, 'gzipShardsVerified': len(metadata['shards']),
    'packageFiles': len(names), 'archiveBytes': archive.stat().st_size,
    'archiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'sourceParity': True, 'zipIntegrity': True,
    'permissions': manifest['permissions'], 'hostPermissions': manifest['host_permissions'], 'webAccessibleResources': [],
}
(ROOT / 'reports/extension-package-verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
