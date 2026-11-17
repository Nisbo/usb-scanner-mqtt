import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

from usb_scanner_mqtt import update_http as http


class UpdateHTTPTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for patcher in (patch.object(http, 'CACHE_DIR', self.root), patch.object(http.time, 'time', return_value=1000)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def response(self, value):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(value).encode()
        return response

    def test_cache_survives_new_request_and_revalidates_mutable_selectors(self):
        with patch.object(http.urllib.request, 'urlopen', return_value=self.response({'tag_name': 'v1.0.0'})) as request:
            self.assertEqual(http.github('/releases/latest'), {'tag_name': 'v1.0.0'})
            self.assertEqual(request.call_count, 1)
        # A fresh request context reads the shared file instead of calling GitHub.
        with patch.object(http.urllib.request, 'urlopen', return_value=self.response({'tag_name': 'v1.1.0'})) as request:
            self.assertEqual(http.github('/releases/latest')['tag_name'], 'v1.0.0')
            request.assert_not_called()
            with patch.object(http.time, 'time', return_value=1031):
                self.assertEqual(http.github('/releases/latest')['tag_name'], 'v1.1.0')
            request.assert_called_once()

    def test_immutable_comparison_reused_after_selector_expiry(self):
        with patch.object(http.urllib.request, 'urlopen', return_value=self.response({'status': 'ahead'})) as request:
            http.github('/compare/' + 'a'*40 + '...' + 'b'*40)
            with patch.object(http.time, 'time', return_value=2000):
                self.assertEqual(http.github('/compare/' + 'a'*40 + '...' + 'b'*40)['status'], 'ahead')
            request.assert_called_once()

    def test_rate_limit_wait_shared_and_not_retried_until_reset(self):
        error = urllib.error.HTTPError('https://api.github.com/test', 403, 'Forbidden',
                                       {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '2000'}, io.BytesIO(b'private response'))
        with patch.object(http.urllib.request, 'urlopen', side_effect=error) as request:
            with self.assertRaises(http.UpdateError) as first: http.github('/releases/latest')
            self.assertEqual(first.exception.code, 'rate_limit')
            self.assertEqual(first.exception.retry_at, 2001)
            self.assertNotIn('private response', str(first.exception))
            with self.assertRaises(http.UpdateError): http.github('/commits/dev')
            request.assert_called_once()
        with patch.object(http.time, 'time', return_value=2002), patch.object(http.urllib.request, 'urlopen', return_value=self.response({'sha': 'b'*40})) as request:
            self.assertEqual(http.github('/commits/dev')['sha'], 'b'*40)
            request.assert_called_once()

    def test_http_causes_distinct_and_secondary_limit_supported(self):
        for code, headers, body, reason in ((429, {'Retry-After':'120'}, b'', 'rate_limit'),
                                          (403, {}, b'{"message":"secondary rate limit"}', 'rate_limit'),
                                          (403, {}, b'private secret', 'http'),
                                          (404, {}, b'private secret', 'not_found'),
                                          (503, {}, b'private secret', 'http')):
            with self.subTest(code=code, reason=reason):
                (self.root/'rate-limit.json').unlink(missing_ok=True)
                error = urllib.error.HTTPError('https://api.github.com/test', code, 'Error', headers, io.BytesIO(body))
                with patch.object(http.urllib.request, 'urlopen', side_effect=error):
                    with self.assertRaises(http.UpdateError) as caught: http.github('/releases/latest')
                    self.assertEqual(caught.exception.code, reason)
                    self.assertNotIn('private secret', str(caught.exception))
                    if code == 429: self.assertEqual(caught.exception.retry_at, 1120)

    def test_invalid_or_expired_cache_does_not_mask_network_failure(self):
        (self.root/'rate-limit.json').write_text('invalid')
        with patch.object(http.urllib.request, 'urlopen', side_effect=OSError('private error')):
            with self.assertRaises(http.UpdateError) as caught: http.github('/commits/dev')
            self.assertEqual(caught.exception.code, 'network')
            self.assertNotIn('private error', str(caught.exception))
