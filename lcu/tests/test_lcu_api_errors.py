import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import requests

from lcu.core.lcu_api import LCUAPI


class RequestFailureTests(unittest.TestCase):
    """A request that failed again after reconnecting returned None with no
    trace, so callers acted on missing data without any hint why"""

    def setUp(self):
        session = MagicMock()
        session.get.side_effect = requests.exceptions.ConnectionError('client closed')
        session.patch.side_effect = requests.exceptions.ConnectionError('client closed')
        self.connection = SimpleNamespace(ok=True, base='https://127.0.0.1:1', session=session,
                                          refresh_if_needed=lambda force=False: None)
        self.api = LCUAPI(self.connection)

    def test_a_failed_get_is_logged(self):
        with self.assertLogs(level='DEBUG') as logs:
            self.assertIsNone(self.api.get('/lol-champ-select/v1/session', timeout=1.0, use_cache=False))
        self.assertTrue(any('GET /lol-champ-select/v1/session failed' in line for line in logs.output))

    def test_a_get_that_keeps_failing_is_said_once_until_league_answers(self):
        """Nov 9: polled GETs flooded the window while League restarted; each path is said once (debug)"""
        path = '/lol-champ-select/v1/session'
        with self.assertLogs(level='DEBUG') as logs:
            for _ in range(5):
                self.api.get(path, timeout=1.0, use_cache=False)
        self.assertEqual(sum('failed after reconnecting' in line for line in logs.output), 1)

        self.connection.session.get.side_effect = None
        self.connection.session.get.return_value = SimpleNamespace(status_code=404)
        self.api.get(path, timeout=1.0, use_cache=False)  # League answers again

        self.connection.session.get.side_effect = requests.exceptions.ConnectionError('client closed')
        with self.assertLogs(level='DEBUG') as logs:
            self.api.get(path, timeout=1.0, use_cache=False)
        self.assertEqual(sum('failed after reconnecting' in line for line in logs.output), 1)

    def test_a_failed_patch_is_logged(self):
        with self.assertLogs(level='DEBUG') as logs:
            self.assertIsNone(self.api.patch('/lol-champ-select/v1/session/my-selection', {}, timeout=1.0))
        self.assertTrue(any('PATCH /lol-champ-select/v1/session/my-selection failed' in line for line in logs.output))


if __name__ == '__main__':
    unittest.main()
