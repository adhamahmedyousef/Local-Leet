from datetime import date, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from localleet.publish import ANCHOR, scheduled_today, from_package


class PublishTests(unittest.TestCase):
    def test_two_day_cadence_crosses_month_and_year_boundaries(self):
        for offset in range(400):
            self.assertEqual(scheduled_today(ANCHOR + timedelta(days=offset)), offset % 2 == 0)
        self.assertTrue(scheduled_today(date(2026, 10, 30)))
        self.assertTrue(scheduled_today(date(2026, 11, 1)))
        self.assertFalse(scheduled_today(date(2026, 10, 31)))

    def package(self, root, corrupt=False):
        payload = gzip.compress(b'{"US:alice":[1,1,"EG","1700"]}', mtime=0)
        meta = {'schemaVersion': 1, 'snapshotId': 'bundled', 'collectedAt': '2026-10-28T00:00:00Z',
                'sourceRows': 1, 'indexedUsers': 1, 'unknownCountryRows': 0, 'countries': {'EG': 1},
                'shards': {'aa': {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(), 'entries': 1}}}
        package = root / 'package.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('data/metadata.json', json.dumps(meta))
            archive.writestr('data/aa.json.gz', b'bad' if corrupt else payload)
        return package

    def test_bootstrap_publishes_hash_pinned_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); site = root / 'site'; site.mkdir()
            pointer = from_package(self.package(root), 'a'*64, site)
            metadata = (site / 'snapshots' / ('a'*64) / 'metadata.json').read_bytes()
            self.assertEqual(pointer['metadataSha256'], hashlib.sha256(metadata).hexdigest())
            self.assertEqual(pointer['metadataBytes'], len(metadata))
            self.assertEqual(json.loads((site / 'current.json').read_text()), pointer)

    def test_corrupt_bootstrap_never_publishes_current_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); site = root / 'site'; site.mkdir()
            with self.assertRaisesRegex(ValueError, 'integrity'):
                from_package(self.package(root, corrupt=True), 'a'*64, site)
            self.assertFalse((site / 'current.json').exists())


if __name__ == '__main__':
    unittest.main()
