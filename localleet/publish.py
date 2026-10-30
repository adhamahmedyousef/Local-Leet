"""Publish verified, immutable compact data for GitHub Pages; no tokens are needed."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import time
import http.client
import urllib.error
import urllib.request
import zipfile

DATA_ROOT = 'https://adhamahmedyousef.github.io/Local-Leet/'
def refreshed_today(meta, today=None):
    """Skip backup triggers only after a successful collection on this UTC date."""
    collected = datetime.fromisoformat(meta['collectedAt'].replace('Z', '+00:00'))
    return collected.astimezone(timezone.utc).date() == (today or datetime.now(timezone.utc).date())


def download(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'Local-Leet-data-publisher'})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError('Oversized public data response')
            return raw
        except urllib.error.HTTPError as error:
            error.close()
            if error.code not in (500, 502, 503, 504) or attempt == 4:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead):
            if attempt == 4:
                raise
        delay = 2 ** (attempt + 1)
        print(json.dumps({'event': 'downloadRetry', 'attempt': attempt + 1,
                          'delaySeconds': delay, 'url': url}), flush=True)
        time.sleep(delay)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def check_meta(meta):
    if meta['schemaVersion'] != 1 or len(meta['snapshotId']) != 64 or any(
        c not in '0123456789abcdef' for c in meta['snapshotId']
    ):
        raise ValueError('Invalid immutable snapshot ID')
    if sum(meta['countries'].values()) + meta['unknownCountryRows'] != meta['sourceRows']:
        raise ValueError('Country coverage mismatch')
    if sum(x['entries'] for x in meta['shards'].values()) != meta['indexedUsers']:
        raise ValueError('Profile coverage mismatch')
    for shard, descriptor in meta['shards'].items():
        if len(shard) != 2 or any(c not in '0123456789abcdef' for c in shard):
            raise ValueError('Invalid shard key')
        if not 0 < descriptor['bytes'] <= 200_000:
            raise ValueError('Unsupported compressed shard size')


def keep_previous(site):
    """Keep one full old version so in-flight clients can finish pinned lookups."""
    try:
        pointer = json.loads(download(DATA_ROOT + 'current.json', 2048))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    version = pointer['snapshotId']
    if len(version) != 64 or any(c not in '0123456789abcdef' for c in version):
        raise ValueError('Invalid previous snapshot pointer')
    base = DATA_ROOT + f'snapshots/{version}/'
    raw = download(base + 'metadata.json', 200_000)
    if digest(raw) != pointer['metadataSha256'] or len(raw) != pointer['metadataBytes']:
        raise ValueError('Invalid previous metadata hash')
    meta = json.loads(raw)
    check_meta(meta)
    folder = Path(site) / 'snapshots' / version
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'metadata.json').write_bytes(raw)

    def copy(shard):
        descriptor = meta['shards'][shard]
        payload = download(base + shard + '.json.gz', descriptor['bytes'])
        if len(payload) != descriptor['bytes'] or digest(payload) != descriptor['sha256']:
            raise ValueError('Previous shard integrity failure')
        (folder / f'{shard}.json.gz').write_bytes(payload)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(copy, meta['shards']))
    return meta


def finalize(site, meta):
    check_meta(meta)
    folder = Path(site) / 'snapshots' / meta['snapshotId']
    raw = encode(meta)
    (folder / 'metadata.json').write_bytes(raw)
    pointer = {'schemaVersion': 1, 'snapshotId': meta['snapshotId'],
               'metadataBytes': len(raw), 'metadataSha256': digest(raw)}
    (Path(site) / 'current.json').write_bytes(encode(pointer))
    (Path(site) / '.nojekyll').touch()
    (Path(site) / 'index.html').write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Local Leet data</title>'
        '<h1>Local Leet</h1><p>Versioned country contest rankings.</p>'
        '<p><a href="current.json">Current data version</a></p>'
        '<p>Built By <a href="https://voidhub.co">VoidHub</a>.</p></html>', encoding='utf-8')
    return pointer


def from_package(package, snapshot_id, site):
    """Bootstrap from the already verified extension release, not a second scrape."""
    with zipfile.ZipFile(package) as archive:
        meta = json.loads(archive.read('data/metadata.json'))
        meta['snapshotId'] = snapshot_id
        meta['sourceContentSha256'] = snapshot_id
        check_meta(meta)
        folder = Path(site) / 'snapshots' / snapshot_id
        folder.mkdir(parents=True, exist_ok=True)
        for shard, descriptor in meta['shards'].items():
            raw = archive.read(f'data/{shard}.json.gz')
            if len(raw) != descriptor['bytes'] or digest(raw) != descriptor['sha256']:
                raise ValueError('Bootstrap package data integrity failure')
            (folder / f'{shard}.json.gz').write_bytes(raw)
    return finalize(site, meta)


def from_snapshot(root, site):
    root, site = Path(root), Path(site)
    pointer = json.loads((root / 'current.json').read_text())
    manifest_path = root / pointer['manifest']
    manifest = json.loads(manifest_path.read_text())
    verification = json.loads((root / 'verification.json').read_text())
    if verification['snapshotId'] != manifest['snapshotId']:
        raise ValueError('Snapshot has not been verified')
    version = digest(encode({'source': manifest['contentSha256'],
                             'collectedAt': manifest['collectionFinishedAt']}))
    folder = site / 'snapshots' / version
    folder.mkdir(parents=True, exist_ok=True)
    descriptors = {}
    entries = 0
    for shard, expected in manifest['shards'].items():
        raw = (manifest_path.parent / f'{shard}.json').read_bytes()
        if digest(raw) != expected['sha256']:
            raise ValueError('Source shard integrity failure')
        compact = {key: [r['globalRank'], r['localRank'], r['country'], r['rating']]
                   for key, r in json.loads(raw).items() if key.startswith(('US:', 'CN-SLUG:'))}
        compressed = gzip.compress(encode(compact), compresslevel=9, mtime=0)
        (folder / f'{shard}.json.gz').write_bytes(compressed)
        descriptors[shard] = {'bytes': len(compressed), 'sha256': digest(compressed), 'entries': len(compact)}
        entries += len(compact)
    meta = {'schemaVersion': 1, 'snapshotId': version, 'collectedAt': manifest['collectionFinishedAt'],
            'sourceRows': manifest['sourceRows'], 'indexedUsers': entries,
            'unknownCountryRows': manifest['unknownCountryUsers'],
            'countries': manifest['countries'], 'shards': descriptors}
    meta['sourceContentSha256'] = manifest['contentSha256']
    return finalize(site, meta)
