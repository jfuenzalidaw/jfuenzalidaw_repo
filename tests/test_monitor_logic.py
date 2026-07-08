import datetime as dt
import importlib
import os
import unittest
from unittest.mock import Mock, patch


os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
os.environ["TELEGRAM_CHAT_ID"] = "123"

cloud_monitor = importlib.import_module("cloud_monitor")


class MonitorLogicTests(unittest.TestCase):
    def test_geronimo_uses_legacy_chat_id_fallback(self):
        self.assertEqual(cloud_monitor.TELEGRAM_USERS["geronimo"]["name"], "Geronimo")
        self.assertEqual(cloud_monitor.TELEGRAM_USERS["geronimo"]["bot_token"], "test-token")
        self.assertEqual(cloud_monitor.TELEGRAM_USERS["geronimo"]["chat_id"], "123")

    def test_sophia_loads_from_named_bot_and_chat_secrets(self):
        with patch.dict(os.environ, {
            "SOPHIA_TELEGRAM_BOT_TOKEN": "sophia-token",
            "SOPHIA_TELEGRAM_CHAT_ID": "456",
        }):
            users = cloud_monitor.load_telegram_users()

        self.assertEqual(users["sophia"]["name"], "Sophia")
        self.assertEqual(users["sophia"]["bot_token"], "sophia-token")
        self.assertEqual(users["sophia"]["chat_id"], "456")

    def test_send_telegram_broadcasts_to_configured_users(self):
        users = {
            "geronimo": {"id": "geronimo", "name": "Geronimo", "bot_token": "first-token", "chat_id": "123"},
            "sophia": {"id": "sophia", "name": "Sophia", "bot_token": "second-token", "chat_id": "456"},
        }

        with (
            patch.object(cloud_monitor, "TELEGRAM_USERS", users),
            patch.object(cloud_monitor, "send_telegram_to") as send_telegram_to,
        ):
            cloud_monitor.send_telegram("hello")

        sent_users = [call.args[0]["id"] for call in send_telegram_to.call_args_list]
        self.assertEqual(sent_users, ["geronimo", "sophia"])
        self.assertEqual([call.args[1] for call in send_telegram_to.call_args_list], ["hello", "hello"])
        self.assertEqual(send_telegram_to.call_count, 2)

    def test_process_commands_replies_to_authorized_user_chat(self):
        state = cloud_monitor.default_state()
        updates = [
            {"update_id": 1, "message": {"chat": {"id": "999"}, "text": "/status"}},
            {"update_id": 2, "message": {"chat": {"id": "123"}, "text": "/status"}},
        ]

        with (
            patch.object(cloud_monitor, "get_updates", return_value=updates),
            patch.object(cloud_monitor, "send_telegram_to") as send_telegram_to,
        ):
            force_checks = cloud_monitor.process_commands(state)

        self.assertEqual(force_checks, [])
        self.assertEqual(send_telegram_to.call_count, 1)
        self.assertEqual(send_telegram_to.call_args.args[0]["id"], "geronimo")
        self.assertTrue(send_telegram_to.call_args.args[1].startswith("Hi Geronimo,"))
        self.assertIn("Campsite monitors", send_telegram_to.call_args.args[1])

    def test_bare_start_replies_with_help_without_enabling_monitors(self):
        state = cloud_monitor.default_state()
        updates = [
            {"update_id": 1, "message": {"chat": {"id": "123"}, "text": "/start"}},
        ]

        with (
            patch.object(cloud_monitor, "get_updates", return_value=updates),
            patch.object(cloud_monitor, "send_telegram_to") as send_telegram_to,
        ):
            force_checks = cloud_monitor.process_commands(state)

        self.assertEqual(force_checks, [])
        monitors = state["telegram_users"]["geronimo"]["monitors"]
        self.assertFalse(monitors["upper_yosemite"]["enabled"])
        self.assertFalse(monitors["north_yosemite"]["enabled"])
        self.assertFalse(monitors["lower_yosemite"]["enabled"])
        self.assertTrue(send_telegram_to.call_args.args[1].startswith("Hi Geronimo,"))
        self.assertIn("Campsite monitor commands", send_telegram_to.call_args.args[1])

    def test_users_have_independent_dates_and_modes(self):
        state = cloud_monitor.default_state()
        users = {
            "geronimo": {"id": "geronimo", "name": "Geronimo", "bot_token": "first-token", "chat_id": "123"},
            "sophia": {"id": "sophia", "name": "Sophia", "bot_token": "second-token", "chat_id": "456"},
        }
        updates_by_user = {
            "geronimo": [
                {"update_id": 1, "message": {"chat": {"id": "123"}, "text": "/dates upper yosemite 2026-08-01 2026-08-07"}},
                {"update_id": 2, "message": {"chat": {"id": "123"}, "text": "/mode upper yosemite all"}},
            ],
            "sophia": [
                {"update_id": 10, "message": {"chat": {"id": "456"}, "text": "/dates upper yosemite 2026-09-10 2026-09-12"}},
                {"update_id": 11, "message": {"chat": {"id": "456"}, "text": "/mode upper yosemite consecutive 2"}},
            ],
        }

        def updates_for_user(user, offset):
            return updates_by_user[user["id"]]

        with (
            patch.object(cloud_monitor, "TELEGRAM_USERS", users),
            patch.object(cloud_monitor, "get_updates", side_effect=updates_for_user),
            patch.object(cloud_monitor, "send_telegram_to"),
        ):
            force_checks = cloud_monitor.process_commands(state)

        geronimo_monitor = state["telegram_users"]["geronimo"]["monitors"]["upper_yosemite"]
        sophia_monitor = state["telegram_users"]["sophia"]["monitors"]["upper_yosemite"]
        self.assertEqual(geronimo_monitor["checkin"], "2026-08-01")
        self.assertEqual(geronimo_monitor["checkout"], "2026-08-07")
        self.assertEqual(geronimo_monitor["mode"], "all")
        self.assertEqual(sophia_monitor["checkin"], "2026-09-10")
        self.assertEqual(sophia_monitor["checkout"], "2026-09-12")
        self.assertEqual(sophia_monitor["mode"], "consecutive")
        self.assertEqual(sophia_monitor["min_consecutive_nights"], 2)
        self.assertEqual(force_checks, [("geronimo", "upper_yosemite"), ("sophia", "upper_yosemite")])

    def test_dates_all_updates_every_user_monitor(self):
        state = cloud_monitor.default_state()
        updates = [
            {"update_id": 1, "message": {"chat": {"id": "123"}, "text": "/dates all 2026-08-01 2026-08-07"}},
        ]

        with (
            patch.object(cloud_monitor, "get_updates", return_value=updates),
            patch.object(cloud_monitor, "send_telegram_to") as send_telegram_to,
        ):
            force_checks = cloud_monitor.process_commands(state)

        monitors = state["telegram_users"]["geronimo"]["monitors"]
        for name in cloud_monitor.monitor_targets():
            self.assertEqual(monitors[name]["checkin"], "2026-08-01")
            self.assertEqual(monitors[name]["checkout"], "2026-08-07")
        self.assertEqual(
            force_checks,
            [("geronimo", "lower_yosemite"), ("geronimo", "north_yosemite"), ("geronimo", "upper_yosemite")],
        )
        self.assertIn("Dates updated for: upper_yosemite, north_yosemite, lower_yosemite", send_telegram_to.call_args.args[1])

    def test_mode_all_updates_every_user_monitor(self):
        state = cloud_monitor.default_state()
        updates = [
            {"update_id": 1, "message": {"chat": {"id": "123"}, "text": "/mode all consecutive 2"}},
            {"update_id": 2, "message": {"chat": {"id": "123"}, "text": "/mode all any"}},
        ]

        with (
            patch.object(cloud_monitor, "get_updates", return_value=updates),
            patch.object(cloud_monitor, "send_telegram_to") as send_telegram_to,
        ):
            force_checks = cloud_monitor.process_commands(state)

        self.assertEqual(force_checks, [])
        monitors = state["telegram_users"]["geronimo"]["monitors"]
        for name in cloud_monitor.monitor_targets():
            self.assertEqual(monitors[name]["mode"], "any")
            self.assertEqual(monitors[name]["min_consecutive_nights"], 2)
        self.assertIn("Search mode updated for: upper_yosemite, north_yosemite, lower_yosemite", send_telegram_to.call_args.args[1])

    def test_migrate_shared_monitor_state_into_geronimo_only(self):
        raw = {
            "last_update_id": 5,
            "telegram_users": {
                "geronimo": {"last_update_id": 6},
                "sophia": {"last_update_id": 7},
            },
            "monitors": {
                "upper_yosemite": {
                    "enabled": True,
                    "checkin": "2026-08-01",
                    "checkout": "2026-08-07",
                    "last_alert_key": "old",
                },
            },
        }

        state = cloud_monitor.migrate_state(raw)

        geronimo_monitor = state["telegram_users"]["geronimo"]["monitors"]["upper_yosemite"]
        sophia_monitor = state["telegram_users"]["sophia"]["monitors"]["upper_yosemite"]
        self.assertTrue(geronimo_monitor["enabled"])
        self.assertEqual(geronimo_monitor["checkin"], "2026-08-01")
        self.assertEqual(geronimo_monitor["checkout"], "2026-08-07")
        self.assertEqual(geronimo_monitor["mode"], "any")
        self.assertFalse(sophia_monitor["enabled"])
        self.assertEqual(state["telegram_users"]["geronimo"]["last_update_id"], 6)
        self.assertEqual(state["telegram_users"]["sophia"]["last_update_id"], 7)

    def test_migrate_new_user_state_does_not_apply_legacy_defaults(self):
        raw = {
            "last_update_id": 5,
            "telegram_users": {
                "geronimo": {
                    "last_update_id": 6,
                    "monitors": {
                        "upper_yosemite": {
                            "enabled": True,
                            "checkin": "2026-08-01",
                            "checkout": "2026-08-07",
                            "last_alert_key": "",
                            "mode": "all",
                            "min_consecutive_nights": 2,
                        },
                    },
                },
            },
        }

        state = cloud_monitor.migrate_state(raw)

        monitor = state["telegram_users"]["geronimo"]["monitors"]["upper_yosemite"]
        self.assertTrue(monitor["enabled"])
        self.assertEqual(monitor["checkin"], "2026-08-01")
        self.assertEqual(monitor["checkout"], "2026-08-07")
        self.assertEqual(monitor["mode"], "all")

    def test_monitor_targets_are_only_yosemite_pines(self):
        self.assertEqual(
            cloud_monitor.monitor_targets(),
            ["upper_yosemite", "north_yosemite", "lower_yosemite"],
        )

        text = cloud_monitor.monitors_text()
        self.assertIn("upper yosemite", text)
        self.assertIn("north yosemite", text)
        self.assertIn("lower yosemite", text)
        self.assertNotIn("lassen", text)
        self.assertNotIn("redwoods", text)
        self.assertNotIn("gold bluffs", text)

    def test_hidden_monitor_names_are_not_command_targets(self):
        targets, rest = cloud_monitor.parse_target("gold bluffs redwoods")

        self.assertEqual(targets, [])
        self.assertEqual(rest, "gold bluffs redwoods")

    def test_all_targets_only_yosemite_pines(self):
        targets, rest = cloud_monitor.parse_target("all")

        self.assertEqual(targets, ["upper_yosemite", "north_yosemite", "lower_yosemite"])
        self.assertEqual(rest, "")

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

    def test_matching_available_nights_respects_all_mode(self):
        nights = [
            {"checkin": dt.date(2026, 5, 22), "checkout": dt.date(2026, 5, 23)},
            {"checkin": dt.date(2026, 5, 23), "checkout": dt.date(2026, 5, 24)},
        ]
        monitor = {"mode": "all"}

        self.assertEqual(
            cloud_monitor.matching_available_nights(nights, dt.date(2026, 5, 22), dt.date(2026, 5, 24), monitor),
            nights,
        )
        self.assertEqual(
            cloud_monitor.matching_available_nights(nights[:1], dt.date(2026, 5, 22), dt.date(2026, 5, 24), monitor),
            [],
        )

    def test_matching_available_nights_respects_consecutive_mode(self):
        nights = [
            {"checkin": dt.date(2026, 5, 22), "checkout": dt.date(2026, 5, 23)},
            {"checkin": dt.date(2026, 5, 23), "checkout": dt.date(2026, 5, 24)},
            {"checkin": dt.date(2026, 5, 25), "checkout": dt.date(2026, 5, 26)},
        ]
        monitor = {"mode": "consecutive", "min_consecutive_nights": 2}

        self.assertEqual(
            cloud_monitor.matching_available_nights(nights, dt.date(2026, 5, 22), dt.date(2026, 5, 26), monitor),
            nights[:2],
        )

    def test_run_checks_skips_hidden_enabled_monitors(self):
        state = cloud_monitor.default_state()
        for monitor in state["telegram_users"]["geronimo"]["monitors"].values():
            monitor["enabled"] = True
        users = {
            "geronimo": {"id": "geronimo", "name": "Geronimo", "bot_token": "first-token", "chat_id": "123"},
        }

        with (
            patch.object(cloud_monitor, "TELEGRAM_USERS", users),
            patch.object(cloud_monitor, "run_recreation_gov_check") as recreation_check,
            patch.object(cloud_monitor, "run_reserve_ca_check") as reserve_ca_check,
        ):
            cloud_monitor.run_checks(state, [])

        checked_names = [call.args[1] for call in recreation_check.call_args_list]
        self.assertEqual(checked_names, ["upper_yosemite", "north_yosemite", "lower_yosemite"])
        reserve_ca_check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
