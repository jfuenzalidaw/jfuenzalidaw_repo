import datetime as dt
import importlib
import os
import unittest
from unittest.mock import Mock, patch


os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")

cloud_monitor = importlib.import_module("cloud_monitor")


class MonitorLogicTests(unittest.TestCase):
    def test_date_windows_split_range_into_one_night_stays(self):
        windows = cloud_monitor.date_windows(
            dt.date(2026, 5, 22),
            dt.date(2026, 5, 26),
        )

        self.assertEqual(
            windows,
            [
                (dt.date(2026, 5, 22), dt.date(2026, 5, 23)),
                (dt.date(2026, 5, 23), dt.date(2026, 5, 24)),
                (dt.date(2026, 5, 24), dt.date(2026, 5, 25)),
                (dt.date(2026, 5, 25), dt.date(2026, 5, 26)),
            ],
        )

    def test_date_windows_empty_when_checkout_equals_checkin(self):
        self.assertEqual(
            cloud_monitor.date_windows(dt.date(2026, 5, 22), dt.date(2026, 5, 22)),
            [],
        )

    def test_recreation_gov_nights_alert_when_one_night_available(self):
        campsites = {
            "101": {
                "loop": "A",
                "site": "12",
                "type": "STANDARD NONELECTRIC",
                "availabilities": {
                    "2026-05-22T00:00:00Z": "Reserved",
                    "2026-05-23T00:00:00Z": "Available",
                    "2026-05-24T00:00:00Z": "Reserved",
                },
            },
        }

        with patch.object(cloud_monitor, "fetch_recreation_gov_campsites", return_value=campsites):
            available = cloud_monitor.check_recreation_gov_nights(
                "232447",
                dt.date(2026, 5, 22),
                dt.date(2026, 5, 25),
            )

        self.assertEqual(len(available), 1)
        self.assertEqual(available[0]["checkin"], dt.date(2026, 5, 23))
        self.assertEqual(available[0]["checkout"], dt.date(2026, 5, 24))
        self.assertEqual(available[0]["sites"][0]["campsite_id"], "101")

    def test_reserve_ca_nights_return_only_available_windows(self):
        results = [
            {"available": False, "url": "first"},
            {"available": True, "url": "second"},
            {"available": False, "url": "third"},
        ]
        mocked_check = Mock(side_effect=results)

        with patch.object(cloud_monitor, "check_reserve_ca", mocked_check):
            available = cloud_monitor.check_reserve_ca_nights(
                "gold_bluffs_redwoods",
                dt.date(2026, 5, 22),
                dt.date(2026, 5, 25),
            )

        self.assertEqual(len(available), 1)
        self.assertEqual(available[0]["checkin"], dt.date(2026, 5, 23))
        self.assertEqual(available[0]["checkout"], dt.date(2026, 5, 24))
        self.assertEqual(available[0]["url"], "second")


if __name__ == "__main__":
    unittest.main()
