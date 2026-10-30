from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import io
import urllib.error
from unittest.mock import patch

from localleet.publish import refreshed_today, from_package, download
from localleet.verify import check_profile_freshness


class PublishTests(unittest.TestCase):
    @patch('localleet.publish.time.sleep')
    @patch('localleet.publish.urllib.request.urlopen')
    def test_transient_download_retries_then_recovers(self, open_url, sleep):
        open_url.side_effect = [urllib.error.HTTPError('https://example.test', 503, 'Unavailable', {}, None),
                                io.BytesIO(b'valid')]
        self.assertEqual(download('https://example.test', 5), b'valid')
        self.assertEqual(open_url.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch('localleet.publish.time.sleep')
    @patch('localleet.publish.urllib.request.urlopen')
    def test_retries_are_bounded_and_permanent_errors_fail_immediately(self, open_url, sleep):
        open_url.side_effect = urllib.error.HTTPError('https://example.test', 503, 'Unavailable', {}, None)
        with self.assertRaises(urllib.error.HTTPError):
            download('https://example.test', 5)
        self.assertEqual(open_url.call_count, 5)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8, 16])
        for status in (403, 404, 429):
            open_url.reset_mock(); sleep.reset_mock()
            open_url.side_effect = urllib.error.HTTPError('https://example.test', status, 'Denied', {}, None)
            with self.assertRaises(urllib.error.HTTPError):
                download('https://example.test', 5)
            self.assertEqual(open_url.call_count, 1)
            sleep.assert_not_called()

    @patch('localleet.publish.time.sleep')
    @patch('localleet.publish.urllib.request.urlopen')
    def test_timeout_recovers_but_oversized_data_is_rejected(self, open_url, sleep):
        open_url.side_effect = [TimeoutError(), io.BytesIO(b'valid')]
        self.assertEqual(download('https://example.test', 5), b'valid')
        open_url.side_effect = [io.BytesIO(b'too large')]
        with self.assertRaisesRegex(ValueError, 'Oversized'):
            download('https://example.test', 5)

    def test_daily_refresh_and_backup_skip_use_utc_date(self):
        meta = {'collectedAt': '2026-10-30T11:41:41Z'}
        self.assertTrue(refreshed_today(meta, date(2026, 10, 30)))
        self.assertFalse(refreshed_today(meta, date(2026, 10, 31)))
        self.assertFalse(refreshed_today(meta, date(2026, 11, 1)))
        self.assertTrue(refreshed_today({'collectedAt': '2026-10-31T01:00:00+03:00'}, date(2026, 10, 30)))

    def test_profile_freshness_blocks_old_source_even_when_internal_checks_pass(self):
        class Client:
            def request(self, query):
                return {'data': {'userContestRanking': {'globalRanking': 97444, 'rating': 1745.122}}}
        node = {'user': {'username': 'alice'}, 'currentGlobalRanking': 108215, 'currentRating': '1724.845'}
        with self.assertRaisesRegex(ValueError, 'refusing stale'):
            check_profile_freshness(Client(), node)
        node.update(currentGlobalRanking=97444, currentRating='1745.122')
        self.assertTrue(check_profile_freshness(Client(), node)['matches'])
        node['currentRating'] = '1744'
        with self.assertRaisesRegex(ValueError, 'refusing stale'):
            check_profile_freshness(Client(), node)

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
