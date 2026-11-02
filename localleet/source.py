"""Small anonymous client. No browser session, credentials, or challenge bypass."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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

    def _pace(self):
        # Recheck after waking: another worker may have extended the cooldown.
        while True:
            with self.lock:
                delay = self.next_request - time.monotonic()
                if delay <= 0:
                    self.next_request = time.monotonic() + self.interval
                    return
            time.sleep(delay)

    def _cooldown(self, attempt, reason, retry_after=None):
        delay = min(300, 10 * 2 ** attempt)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                try:
                    delay = max(delay, (parsedate_to_datetime(retry_after) -
                                        datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        with self.lock:
            self.interval = min(5.0, max(1.0, self.interval * 2))
            self.next_request = max(self.next_request, time.monotonic() + delay)
        print(json.dumps({'event': 'source_retry', 'attempt': attempt + 1,
                          'reason': reason, 'waitSeconds': delay,
                          'requestIntervalSeconds': self.interval}), flush=True)

    def request(self, document):
        body = json.dumps({'query': document})
        for attempt in range(6):
            self._pace()
            connection = getattr(self.local, 'connection', None)
            if connection is None:
                connection = http.client.HTTPSConnection('leetcode.com', timeout=45)
                self.local.connection = connection
            retry_after = None
            try:
                connection.request('POST', '/graphql/', body=body, headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'LocalLeet/0.1 (public ranking research)',
                    'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
                })
                response = connection.getresponse()
                raw = response.read()
            except (OSError, http.client.HTTPException) as error:
                reason = type(error).__name__
            else:
                if response.status == 200:
                    try:
                        payload = json.loads(raw)
                    except (ValueError, UnicodeError) as error:
                        raise SourceError('Non-JSON response') from error
                    if not isinstance(payload, dict):
                        raise SourceError('Invalid JSON response')
                    if payload.get('errors'):
                        raise SourceError(f"GraphQL: {json.dumps(payload['errors'])}")
                    return payload
                if response.status in (401, 403):
                    raise AccessBlocked(f'HTTP {response.status}; collection stopped')
                if response.status not in (404, 408, 429, 500, 502, 503, 504):
                    raise SourceError(f'HTTP {response.status}')
                reason = f'HTTP {response.status}'
                retry_after = response.getheader('Retry-After')
            connection.close()
            self.local.connection = None
            if attempt == 5:
                raise SourceError(f'{reason}; exhausted 6 attempts')
            self._cooldown(attempt, reason, retry_after)
