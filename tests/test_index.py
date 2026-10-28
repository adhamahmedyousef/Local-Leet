import json
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from localleet.build import build, identity, shard_for, validate_and_index
from localleet.collect import open_database, save_page


def node(rank, country="EG", rating="2000", username=None, region="US", slug=None):
    return {"currentGlobalRanking": rank, "currentRating": rating, "dataRegion": region,
            "user": {"username": username or f"user{rank}", "profile": {
                "countryCode": country, "countryName": None, "userSlug": slug}}}


def page(nodes, total_pages=1, total_users=None, page_size=None):
    return {"rankingNodes": nodes, "totalPages": total_pages,
            "totalUsers": len(nodes) if total_users is None else total_users,
            "userPerPage": len(nodes) if page_size is None else page_size}


class IndexTests(unittest.TestCase):
    def index(self, nodes):
        entries = {}
        summary = validate_and_index([(1, page(nodes))], entries.__setitem__)
        return entries, summary

    def test_country_order_and_exact_rating_ties(self):
        entries, summary = self.index([
            node(1, rating="2100"), node(2, "US", "2050"),
            node(3, rating="2000"), node(4, rating="2000.0"), node(5, rating="1900"),
        ])
        self.assertEqual([entries[f"US:user{i}"]["localRank"] for i in (1, 3, 4, 5)],
                         [1, 2, 3, 4])
        self.assertEqual([entries[f"US:user{i}"]["localRatingRank"] for i in (1, 3, 4, 5)],
                         [1, 2, 2, 4])
        self.assertEqual(summary["countries"], {"EG": 4, "US": 1})

    def test_missing_country_is_not_inferred_from_region(self):
        entries, summary = self.index([node(1, "", region="CN")])
        self.assertIsNone(entries["CN:user1"]["country"])
        self.assertIsNone(entries["CN:user1"]["localRank"])
        self.assertEqual(summary["unknownCountryUsers"], 1)

    def test_regions_are_distinct_identities(self):
        entries, _ = self.index([node(1, username="same"),
                                 node(2, username="same", region="CN")])
        self.assertEqual(len(entries), 2)

    def test_rejects_duplicate_user(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.index([node(1, username="same"), node(2, username="same")])

    def test_deleted_and_blank_names_count_as_rows_without_ambiguous_lookup(self):
        nodes = [node(1, username="deleted_user"), node(2, username="deleted_user"),
                 node(3, username="active")]
        nodes.append(node(4))
        nodes[-1]["user"]["username"] = ""
        entries, summary = self.index(nodes)
        self.assertEqual(list(entries), ["US:active"])
        self.assertEqual(entries["US:active"]["localRank"], 3)
        self.assertEqual(summary["deletedAccountRows"], 2)
        self.assertEqual(summary["unnamedAccountRows"], 1)
        self.assertEqual(summary["countries"]["EG"], 4)

    def test_rejects_rank_gap_and_duplicate_rank(self):
        for rank in (1, 3):
            with self.subTest(rank=rank), self.assertRaisesRegex(ValueError, "gap/duplicate"):
                self.index([node(1), node(rank)])

    def test_rejects_increasing_rating(self):
        with self.assertRaisesRegex(ValueError, "rating order"):
            self.index([node(1, rating="1000"), node(2, rating="2000")])

    def test_rejects_nan(self):
        with self.assertRaises(ValueError):
            self.index([node(1, rating="NaN")])

    def test_missing_page(self):
        with self.assertRaisesRegex(ValueError, "Missing page"):
            validate_and_index([(2, page([node(1)]))], lambda *_: None)

    def test_incomplete_tail(self):
        with self.assertRaisesRegex(ValueError, "Not all"):
            validate_and_index([(1, page([node(1)], total_pages=2))], lambda *_: None)

    def test_cross_page_metadata_change(self):
        with self.assertRaisesRegex(ValueError, "Metadata changed"):
            validate_and_index([(1, page([node(1)], 2, 2, 1)),
                                (2, page([node(2)], 2, 3, 1))], lambda *_: None)

    def test_total_mismatch_recorded_without_fabricating_users(self):
        summary = validate_and_index([(1, page([node(1)], total_users=10))], lambda *_: None)
        self.assertEqual(summary["sourceRows"], 1)
        self.assertEqual(summary["reportedMinusSourceRows"], 9)

    def test_partial_collection_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "raw.sqlite3"
            connection = open_database(database)
            save_page(connection, 1, page([node(1)]))
            connection.close()
            with self.assertRaisesRegex(ValueError, "not complete"):
                build(database, Path(directory) / "data")
            self.assertFalse((Path(directory) / "data/current.json").exists())

    def test_published_shards_and_cn_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "raw.sqlite3"
            connection = open_database(database)
            save_page(connection, 1, page([node(1, region="CN", slug="public-slug")]))
            connection.execute("INSERT INTO metadata VALUES ('status', 'collected')")
            connection.commit()
            connection.close()
            root = Path(directory) / "data"
            with redirect_stdout(io.StringIO()):
                manifest = build(database, root)
            pointer = json.loads((root / "current.json").read_text())
            self.assertEqual(manifest["snapshotId"], pointer["snapshotId"])
            folder = root / "snapshots" / manifest["snapshotId"]
            for key in (identity("CN", "user1"), "CN-SLUG:public-slug"):
                entries = json.loads((folder / f"{shard_for(key)}.json").read_text())
                self.assertEqual(entries[key]["username"], "user1")


if __name__ == "__main__":
    unittest.main()
