from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from localleet.collect import collect, open_database, save_page
from localleet.source import AccessBlocked, Client, SourceError
from test_index import node, page


class CollectorTests(unittest.TestCase):
    def test_client_batch_contract(self):
        client = Client()
        with patch.object(client, "request", return_value={
            "data": {"p1": page([node(1)]), "p2": page([node(2)])}
        }) as request:
            self.assertEqual(list(client.pages([1, 2])), [1, 2])
            document = request.call_args.args[0]
            self.assertIn("p1: globalRanking(page: 1)", document)
            self.assertIn("p2: globalRanking(page: 2)", document)
        with self.assertRaises(ValueError):
            client.pages(list(range(21)))

    def test_client_rejects_missing_page(self):
        with patch.object(Client, "request", return_value={"data": {}}):
            with self.assertRaises(SourceError):
                Client().pages([1])

    def test_collector_resumes_and_marks_complete(self):
        pages = {i: page([node(i)], 3, 3, 1) for i in range(1, 4)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.sqlite3"
            connection = open_database(path)
            save_page(connection, 1, pages[1])
            save_page(connection, 2, pages[2])
            connection.close()
            with patch.object(Client, "page", return_value=pages[1]), patch.object(
                Client, "pages", side_effect=lambda numbers: {i: pages[i] for i in numbers}
            ) as fetch, redirect_stdout(io.StringIO()):
                collect(path, workers=1)
            self.assertEqual(fetch.call_args.args[0], [3])
            connection = open_database(path)
            self.assertEqual(dict(connection.execute("SELECT key,value FROM metadata"))["status"],
                             "collected")
            connection.close()

    def test_access_denial_stops_without_retry_and_preserves_pages(self):
        first = page([node(1)], 3, 3, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.sqlite3"
            with patch.object(Client, "page", return_value=first), patch.object(
                Client, "pages", side_effect=AccessBlocked("HTTP 429")
            ) as fetch, redirect_stdout(io.StringIO()):
                with self.assertRaises(AccessBlocked):
                    collect(path, workers=1)
            self.assertEqual(fetch.call_count, 1)
            connection = open_database(path)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0], 1)
            self.assertEqual(dict(connection.execute("SELECT key,value FROM metadata"))["status"],
                             "blocked")
            connection.close()

    def test_changed_first_page_refuses_mixed_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.sqlite3"
            connection = open_database(path)
            save_page(connection, 1, page([node(1)]))
            connection.close()
            with patch.object(Client, "page", return_value=page([node(1, rating="1999")])):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    collect(path, workers=1)


if __name__ == "__main__":
    unittest.main()
