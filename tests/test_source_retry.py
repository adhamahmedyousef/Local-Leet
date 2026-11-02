import unittest
from unittest.mock import Mock, patch
from localleet.source import Client, SourceError, AccessBlocked

class RetryTests(unittest.TestCase):
    def run_responses(self, statuses, headers=None):
        connections=[]
        for status in statuses:
            c=Mock(); r=c.getresponse.return_value
            r.status=status; r.read.return_value=b'{"data": {}}'
            r.getheader.return_value=headers
            connections.append(c)
        return connections

    def test_transient_failures_reconnect_then_succeed(self):
        for status in [404,408,429,500,502,503,504]:
            with self.subTest(status=status):
                c=Client(); connections=self.run_responses([status,200])
                with patch('localleet.source.http.client.HTTPSConnection',side_effect=connections), patch.object(c,'_pace'), patch.object(c,'_cooldown') as cooldown:
                    self.assertEqual(c.request('query'), {'data':{}})
                    cooldown.assert_called_once_with(0,f'HTTP {status}',None)
                    connections[0].close.assert_called_once()

    def test_persistent_404_is_bounded(self):
        c=Client(); connections=self.run_responses([404]*6)
        with patch('localleet.source.http.client.HTTPSConnection',side_effect=connections), patch.object(c,'_pace'), patch.object(c,'_cooldown') as cooldown:
            with self.assertRaisesRegex(SourceError,'exhausted 6'):
                c.request('query')
            self.assertEqual(cooldown.call_count,5)

    def test_denials_are_not_retried(self):
        for status in [401,403,400]:
            c=Client()
            with patch('localleet.source.http.client.HTTPSConnection',side_effect=self.run_responses([status])), patch.object(c,'_pace'), patch.object(c,'_cooldown') as cooldown:
                with self.assertRaises(AccessBlocked if status in [401,403] else SourceError): c.request('query')
                cooldown.assert_not_called()

    def test_shared_cooldown_respects_retry_after(self):
        c=Client(.5)
        with patch('localleet.source.time.monotonic',return_value=100), patch('builtins.print'):
            c._cooldown(0,'HTTP 429','120')
        self.assertEqual(c.next_request,220)
        self.assertEqual(c.interval,1)

    def test_pacing_rechecks_extended_cooldown(self):
        c=Client(); c.next_request=10
        with patch('localleet.source.time.monotonic',side_effect=[0,5,10,10]), patch('localleet.source.time.sleep') as sleep:
            c._pace()
        self.assertEqual([x.args[0] for x in sleep.call_args_list],[10,5])

    def test_timeout_retries(self):
        c=Client(); connections=self.run_responses([200,200]); connections[0].request.side_effect=TimeoutError()
        with patch('localleet.source.http.client.HTTPSConnection',side_effect=connections), patch.object(c,'_pace'), patch.object(c,'_cooldown') as cooldown:
            c.request('query'); cooldown.assert_called_once()
