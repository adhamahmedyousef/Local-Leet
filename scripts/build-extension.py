"""Create a self-contained Chrome MV3 package from the verified local snapshot."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
import sys
import zlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def png_icon(size):
    # Original bracket/locator mark; no copied LeetCode branding or raster dependencies.
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            u, v = (x + .5) / size, (y + .5) / size
            bg = (38, 38, 38, 255)
            orange = (255, 161, 22, 255)
            left = abs(u - (.23 + abs(v - .5) * .65)) < .045 and .25 < v < .75
            right = abs(u - (.77 - abs(v - .5) * .65)) < .045 and .25 < v < .75
            dot = (u - .5) ** 2 + (v - .5) ** 2 < .065 ** 2
            rounded = ((u < .15 and v < .15 and (u-.15)**2 + (v-.15)**2 > .15**2)
                       or (u > .85 and v < .15 and (u-.85)**2 + (v-.15)**2 > .15**2)
                       or (u < .15 and v > .85 and (u-.15)**2 + (v-.85)**2 > .15**2)
                       or (u > .85 and v > .85 and (u-.85)**2 + (v-.85)**2 > .15**2))
            row.extend((0, 0, 0, 0) if rounded else orange if left or right or dot else bg)
        rows.append(b'\x00' + row)

    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))


def main():
    release = None
    if '--from-pages' in sys.argv:
        sys.path.insert(0, str(ROOT))
        from localleet.publish import keep_previous
        with tempfile.TemporaryDirectory() as temporary:
            cached = keep_previous(temporary)
            if not cached:
                raise ValueError('No published ranking snapshot')
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as package:
                folder = Path(temporary) / 'snapshots' / cached['snapshotId']
                for file in folder.iterdir():
                    package.write(file, f'data/{file.name}')
            release = zipfile.ZipFile(io.BytesIO(buffer.getvalue()))
    elif '--from-release' in sys.argv:
        sys.path.insert(0, str(ROOT))
        from localleet.publish import download, digest
        config = json.loads((ROOT / 'bootstrap.json').read_text())
        raw = download(config['url'], 30_000_000)
        if digest(raw) != config['sha256']:
            raise ValueError('Bootstrap release integrity failure')
        release = zipfile.ZipFile(io.BytesIO(raw))
    if release:
        cached = json.loads(release.read('data/metadata.json'))
        manifest = {'snapshotId': cached['snapshotId'], 'collectionFinishedAt': cached['collectedAt'],
                    'sourceRows': cached['sourceRows'], 'unknownCountryUsers': cached['unknownCountryRows'],
                    'countries': cached['countries'], 'shards': {}}
    else:
        pointer = json.loads((ROOT / 'data/current.json').read_text(encoding='utf-8'))
        manifest_path = ROOT / 'data' / pointer['manifest']
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        verification = json.loads((ROOT / 'data/verification.json').read_text(encoding='utf-8'))
        if verification['snapshotId'] != manifest['snapshotId']:
            raise ValueError('Verify the current snapshot before packaging')
    destination = ROOT / 'dist' / f"local-leet-{json.loads((ROOT/'extension/manifest.json').read_text())['version']}"
    destination.mkdir(parents=True, exist_ok=True)
    # Copy only known extension sources; never raw pages, tokens, node_modules, or Git internals.
    source_names = ['manifest.json', 'background.js', 'rank-store.js', 'data-validation.js', 'update-manager.js', 'profile-core.js',
                    'content.js', 'content.css', 'popup.html', 'popup.css', 'popup.js']
    for name in source_names:
        shutil.copy2(ROOT / 'extension' / name, destination / name)
    shutil.copy2(ROOT / 'LICENSE', destination / 'LICENSE')
    (destination / 'assets').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'extension/assets/logo.png', destination / 'assets/logo.png')
    (destination / 'icons').mkdir(exist_ok=True)
    for size in (16, 32, 48, 128):
        (destination / 'icons' / f'{size}.png').write_bytes(png_icon(size))
    data_dir = destination / 'data'
    data_dir.mkdir(exist_ok=True)
    descriptors = {}
    accounts = 0
    if release:
        descriptors, accounts = cached['shards'], cached['indexedUsers']
        for shard, descriptor in descriptors.items():
            raw = release.read(f'data/{shard}.json.gz')
            if len(raw) != descriptor['bytes'] or hashlib.sha256(raw).hexdigest() != descriptor['sha256']:
                raise ValueError('Bootstrap shard integrity failure')
            (data_dir / f'{shard}.json.gz').write_bytes(raw)
        release.close()
    if '--reuse-data' in sys.argv:
        cached = json.loads((data_dir / 'metadata.json').read_text(encoding='utf-8'))
        if cached['snapshotId'] != manifest['snapshotId']:
            raise ValueError('Cannot reuse data from a different snapshot')
        descriptors, accounts = cached['shards'], cached['indexedUsers']
    for shard, descriptor in sorted(manifest['shards'].items()):
        if shard in descriptors:
            cached_raw = (data_dir / f'{shard}.json.gz').read_bytes()
            if hashlib.sha256(cached_raw).hexdigest() != descriptors[shard]['sha256']:
                raise ValueError('Cached package data integrity failure')
            continue
        raw = (manifest_path.parent / f'{shard}.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != descriptor['sha256']:
            raise ValueError(f'Snapshot integrity failure: {shard}')
        source = json.loads(raw)
        compact = {}
        for key, user in source.items():
            # Public .com usernames and .cn slugs only; no ambiguous internal CN names.
            if not (key.startswith('US:') or key.startswith('CN-SLUG:')):
                continue
            compact[key] = [user['globalRank'], user['localRank'], user['country'], user['rating']]
        payload = gzip.compress(json.dumps(compact, ensure_ascii=False, separators=(',', ':')).encode(),
                                compresslevel=9, mtime=0)
        (data_dir / f'{shard}.json.gz').write_bytes(payload)
        descriptors[shard] = {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                              'entries': len(compact)}
        accounts += len(compact)
    meta = {
        'schemaVersion': 1, 'snapshotId': manifest['snapshotId'],
        'collectedAt': manifest['collectionFinishedAt'], 'sourceRows': manifest['sourceRows'],
        'indexedUsers': accounts, 'unknownCountryRows': manifest['unknownCountryUsers'],
        'countries': manifest['countries'], 'shards': descriptors,
    }
    (data_dir / 'metadata.json').write_text(json.dumps(meta, separators=(',', ':')) + '\n', encoding='utf-8')
    archive_path = destination.parent / f'{destination.name}.zip'
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(destination.rglob('*')):
            if file.is_file():
                archive.write(file, file.relative_to(destination))
    report = {'unpacked': str(destination), 'zip': str(archive_path),
              'zipBytes': archive_path.stat().st_size, 'publicProfiles': accounts,
              'snapshotId': manifest['snapshotId'],
              'compressedShardBytes': sum(d['bytes'] for d in descriptors.values()),
              'maxCompressedShardBytes': max(d['bytes'] for d in descriptors.values())}
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/extension-build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
