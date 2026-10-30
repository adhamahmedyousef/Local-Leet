"""Daily refresh pipeline, validated before the Pages deployment can start."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localleet.collect import collect
from localleet.build import build
from localleet.verify import verify
from localleet.publish import (refreshed_today, DATA_ROOT, download, digest, keep_previous,
                              from_package, from_snapshot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--scheduled', action='store_true')
    parser.add_argument('--probe', action='store_true', help='Check anonymous source access without collecting or publishing')
    args = parser.parse_args()
    if args.probe:
        from localleet.source import Client
        first = Client().page(1)
        print(json.dumps({'sourceReachable': True, 'rows': len(first['rankingNodes']),
                          'totalPages': first['totalPages']}))
        return
    if args.scheduled:
        current = json.loads(download(DATA_ROOT + 'current.json', 2048))
        raw = download(DATA_ROOT + f"snapshots/{current['snapshotId']}/metadata.json", 200_000)
        if digest(raw) != current['metadataSha256'] or len(raw) != current['metadataBytes']:
            raise ValueError('Invalid current metadata')
        if refreshed_today(json.loads(raw)):
            print('Already published a collection from today; skipping backup trigger.')
            return
    site = ROOT / 'dist/site'
    if site.exists():
        raise ValueError('Use a fresh staging directory; an existing site must not be overwritten')
    site.mkdir(parents=True)
    previous = keep_previous(site)
    if args.bootstrap:
        config = json.loads((ROOT / 'bootstrap.json').read_text())
        raw = download(config['url'], 30_000_000)
        if digest(raw) != config['sha256']:
            raise ValueError('Bootstrap release integrity failure')
        package = ROOT / 'dist/bootstrap.zip'
        package.write_bytes(raw)
        pointer = from_package(package, config['snapshotId'], site)
    else:
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        database = ROOT / f'data/raw/{run_id}.sqlite3'
        data = ROOT / f'data/refresh-{run_id}'
        collect(database, workers=3, interval=.5, batch_size=20)
        meta = build(database, data)
        if previous and meta['sourceRows'] < previous['sourceRows'] * .8:
            raise ValueError('Unexpected source coverage drop; manual review is required')
        verify(database, data, live=True)
        # Reuse an immutable version if the ranked data itself did not change.
        if previous and meta['contentSha256'] == previous.get('sourceContentSha256'):
            from localleet.publish import finalize
            pointer = finalize(site, previous)
        else:
            pointer = from_snapshot(data, site)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write('publish=true\n')
    print(json.dumps({'publishedCandidate': pointer, 'site': str(site)}, indent=2))


if __name__ == '__main__':
    main()
