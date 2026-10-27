import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from health_native.__main__ import Handler
from health_native.reader import HealthReader, SF_DATALESS


def sample(kind, start, end, value, source='Watch', unit='count'):
    return {'type': kind, 'sourceName': source, 'startDate': start,
            'endDate': end, 'value': value, 'unit': unit}


STEPS = 'HKQuantityTypeIdentifierStepCount'
SLEEP = 'HKCategoryTypeIdentifierSleepAnalysis'


class EdgeCases(unittest.TestCase):
    def read_records(self, rows, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            payload = {'export_date': '2026-10-27T09:00:00+08:00', 'records': rows}
            payload.update(overrides)
            (Path(directory) / 'health-native-latest.json').write_text(json.dumps(payload))
            return HealthReader([directory]).read()

    def test_disjoint_sources_add_but_overlapping_sources_do_not(self):
        rows = [sample(STEPS, '2026-10-26T01:00:00+08:00',
                       '2026-10-26T02:00:00+08:00', 100, 'Phone'),
                sample(STEPS, '2026-10-26T02:00:00+08:00',
                       '2026-10-26T03:00:00+08:00', 200)]
        report = self.read_records(rows)
        self.assertEqual(report['days'][0]['steps'], 300)
        self.assertNotIn('steps', report['days'][0]['partial_metrics'])
        rows[0]['endDate'] = '2026-10-26T04:00:00+08:00'
        report = self.read_records(rows)
        self.assertEqual(report['days'][0]['steps'], 100)
        self.assertIn('steps', report['days'][0]['partial_metrics'])

    def test_conflicting_sleep_stages_do_not_inflate_duration(self):
        report = self.read_records([
            sample(SLEEP, '2026-10-26T22:00:00+08:00',
                   '2026-10-27T00:00:00+08:00', 'Core', unit=''),
            sample(SLEEP, '2026-10-26T23:00:00+08:00',
                   '2026-10-27T01:00:00+08:00', 'Deep', unit='')])
        day = report['days'][0]
        self.assertEqual(day['date'], '2026-10-27')
        self.assertEqual(day['sleep_minutes'], 180)
        self.assertEqual(day['sleep_stages'], {'core': 60, 'asleep': 60, 'deep': 60})
        self.assertIn('sleep_minutes', day['partial_metrics'])

    def test_dataless_file_is_not_opened(self):
        reader = HealthReader([])
        path = Path('/synthetic/health-native-latest.json')
        with patch.object(reader, '_files', return_value=[path]), \
                patch.object(Path, 'stat', return_value=SimpleNamespace(
                    st_flags=SF_DATALESS, st_size=1024)), \
                patch.object(Path, 'open', side_effect=AssertionError('must not read placeholder')):
            report = reader.read()
        self.assertEqual(report['source']['files_skipped'], 1)
        self.assertEqual(report['days'], [])
        self.assertIn('iCloud 文件尚未下载', report['source']['warnings'][0])

    def test_invalid_export_time_does_not_use_file_mtime(self):
        report = self.read_records([], export_date='2026-10-27')
        self.assertEqual(report['source']['files_read'], 0)
        self.assertIsNone(report['source']['latest_export'])

    def test_static_symlink_cannot_escape_web_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web = root / 'web'
            web.mkdir()
            private = root / 'private.txt'
            private.write_text('synthetic private content')
            (web / 'link.txt').symlink_to(private)
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.reader = HealthReader([])
            server.web_dir = web
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(HTTPError) as result:
                    urlopen('http://127.0.0.1:%d/link.txt' % server.server_port)
                self.assertEqual(result.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
