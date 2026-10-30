"""Small anonymous client. No browser session, credentials, or challenge bypass."""

import http.client
import json
import threading
import time

ENDPOINT = "https://leetcode.com/graphql/"
SELECTION = """totalUsers userPerPage totalPages
  rankingNodes {
    currentGlobalRanking currentRating dataRegion
    user { username profile { countryCode countryName userSlug } }
  }"""


class SourceError(RuntimeError):
    pass


class AccessBlocked(SourceError):
    """Stop acquisition on a denial; do not repeatedly retry it."""


class Client:
    def __init__(self, interval=1.0):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_request = 0.0
        self.local = threading.local()

    def page(self, number):
        return self.pages([number])[number]

    def pages(self, numbers):
        if not numbers or len(numbers) > 20:
            raise ValueError("A batch must contain 1 to 20 pages")
        document = "query LocalLeetBatch { " + " ".join(
            f"p{number}: globalRanking(page: {int(number)}) {{ {SELECTION} }}"
            for number in numbers
        ) + " }"
        payload = self.request(document)
        result = {}
        for number in numbers:
            data = (payload.get("data") or {}).get(f"p{number}")
            if not isinstance(data, dict) or not isinstance(data.get("rankingNodes"), list):
                raise SourceError(f"Invalid ranking page {number}")
            result[number] = data
        return result

    def request(self, document):
        with self.lock:
            delay = max(0, self.next_request - time.monotonic())
            self.next_request = max(time.monotonic(), self.next_request) + self.interval
        if delay:
            time.sleep(delay)
        connection = getattr(self.local, "connection", None)
        if connection is None:
            connection = http.client.HTTPSConnection("leetcode.com", timeout=45)
            self.local.connection = connection
        body = json.dumps({"query": document})
        try:
            connection.request("POST", "/graphql/", body=body, headers={
                "Content-Type": "application/json",
                "User-Agent": "LocalLeet/0.1 (public ranking research)",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            })
            response = connection.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException):
            connection.close()
            self.local.connection = None
            raise
        if response.status in (401, 403, 429):
            raise AccessBlocked(f"HTTP {response.status}; collection stopped")
        if response.status != 200:
            raise SourceError(f"HTTP {response.status}")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise SourceError("Non-JSON response") from error
        if payload.get("errors"):
            raise SourceError(f"GraphQL: {json.dumps(payload['errors'])}")
        return payload
