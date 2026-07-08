import datetime as dt
import json
import os
import re
import time
from pathlib import Path

import requests


RECREATION_GOV_MONITORS = {
    "upper_yosemite": {
        "name": "upper yosemite",
        "facility_id": "232447",
        "url": "https://www.recreation.gov/camping/campgrounds/232447",
    },
    "north_yosemite": {
        "name": "north yosemite",
        "facility_id": "232449",
        "url": "https://www.recreation.gov/camping/campgrounds/232449",
    },
    "lower_yosemite": {
        "name": "lower yosemite",
        "facility_id": "232450",
        "url": "https://www.recreation.gov/camping/campgrounds/232450",
    },
    "north_summit_lassen": {
        "name": "north summit lassen",
        "facility_id": "234041",
        "url": "https://www.recreation.gov/camping/campgrounds/234041",
    },
    "south_summit_lassen": {
        "name": "south summit lassen",
        "facility_id": "234040",
        "url": "https://www.recreation.gov/camping/campgrounds/234040",
    },
}

RESERVE_CA_AVAILABILITY_URL = "https://www.parks.ca.gov/AvailabilityInfo"

RESERVE_CA_MONITORS = {
    "prairie_redwoods": {
        "name": "prairie redwoods",
        "parks_page_id": "415",
        "campground_anchor": "g-631",
        "reserve_url": "https://reservecalifornia.com/park/696",
    },
    "gold_bluffs_redwoods": {
        "name": "gold bluffs redwoods",
        "parks_page_id": "415",
        "campground_anchor": "g-632",
        "reserve_url": "https://reservecalifornia.com/park/697",
    },
}

ACTIVE_MONITORS = (
    "upper_yosemite",
    "north_yosemite",
    "lower_yosemite",
)

SEARCH_MODES = {
    "any": "any available night",
    "all": "every night in the date range",
    "consecutive": "at least N consecutive available nights",
}
DEFAULT_SEARCH_MODE = "any"
DEFAULT_MIN_CONSECUTIVE_NIGHTS = 2

MONITOR_ALIASES = {
    "upper": "upper_yosemite",
    "upper_yosemite": "upper_yosemite",
    "upperyosemite": "upper_yosemite",
    "upper_pines": "upper_yosemite",
    "north": "north_yosemite",
    "north_yosemite": "north_yosemite",
    "northyosemite": "north_yosemite",
    "north_pines": "north_yosemite",
    "lower": "lower_yosemite",
    "lower_yosemite": "lower_yosemite",
    "loweryosemite": "lower_yosemite",
    "lower_pines": "lower_yosemite",
    "north_summit": "north_summit_lassen",
    "north_summit_lassen": "north_summit_lassen",
    "northsummitlassen": "north_summit_lassen",
    "summit_north": "north_summit_lassen",
    "summitnorth": "north_summit_lassen",
    "south_summit": "south_summit_lassen",
    "south_summit_lassen": "south_summit_lassen",
    "southsummitlassen": "south_summit_lassen",
    "summit_south": "south_summit_lassen",
    "summitsouth": "south_summit_lassen",
    "prairie": "prairie_redwoods",
    "prairie_redwoods": "prairie_redwoods",
    "prairieredwoods": "prairie_redwoods",
    "elk": "prairie_redwoods",
    "elk_prairie": "prairie_redwoods",
    "gold": "gold_bluffs_redwoods",
    "gold_bluffs": "gold_bluffs_redwoods",
    "gold_bluffs_redwoods": "gold_bluffs_redwoods",
    "goldbluffsredwoods": "gold_bluffs_redwoods",
}

AVAIL_API = "https://www.recreation.gov/api/camps/availability/campground/{id}/month"
STATE_PATH = Path(".monitor_state.json")


def default_monitor_settings(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    return {
        "enabled": False,
        "checkin": (today + dt.timedelta(days=1)).isoformat(),
        "checkout": (today + dt.timedelta(days=4)).isoformat(),
        "last_alert_key": "",
        "mode": DEFAULT_SEARCH_MODE,
        "min_consecutive_nights": DEFAULT_MIN_CONSECUTIVE_NIGHTS,
    }


def default_user_monitors(today: dt.date | None = None) -> dict:
    return {name: default_monitor_settings(today) for name in monitor_targets()}


def default_user_state(today: dt.date | None = None) -> dict:
    return {
        "last_update_id": 0,
        "monitors": default_user_monitors(today),
    }


def default_state() -> dict:
    today = dt.date.today()
    return {
        "last_update_id": 0,
        "telegram_users": {
            "geronimo": default_user_state(today),
            "sophia": default_user_state(today),
        },
    }


def recreation_monitor_by_facility_id(facility_id: str) -> str | None:
    for name, config in RECREATION_GOV_MONITORS.items():
        if config["facility_id"] == facility_id:
            return name
    return None


def normalize_monitor_settings(monitor: dict) -> dict:
    normalized = default_monitor_settings()
    normalized.update(monitor)
    if normalized.get("mode") not in SEARCH_MODES:
        normalized["mode"] = DEFAULT_SEARCH_MODE
    try:
        min_nights = int(normalized.get("min_consecutive_nights", DEFAULT_MIN_CONSECUTIVE_NIGHTS))
    except (TypeError, ValueError):
        min_nights = DEFAULT_MIN_CONSECUTIVE_NIGHTS
    normalized["min_consecutive_nights"] = max(1, min_nights)
    return normalized


def migrate_old_yosemite_group(monitors: dict, monitor: dict) -> None:
    selected = set(monitor.get("campgrounds", []))
    if not selected:
        selected = {config["facility_id"] for config in RECREATION_GOV_MONITORS.values()}
    for name, config in RECREATION_GOV_MONITORS.items():
        if name not in monitors:
            continue
        monitors[name].update({
            "enabled": bool(monitor.get("enabled", False)) and config["facility_id"] in selected,
            "checkin": monitor.get("checkin") or monitors[name]["checkin"],
            "checkout": monitor.get("checkout") or monitors[name]["checkout"],
            "last_alert_key": "",
        })


def migrate_old_reserve_ca_monitor(user_monitors: dict, old_name: str, new_name: str, monitors: dict) -> None:
    if old_name in monitors and new_name in user_monitors:
        user_monitors[new_name].update(monitors[old_name])


def migrate_user_state(raw_user_state: dict, legacy_update_id: int = 0) -> dict:
    user_state = default_user_state()
    user_state["last_update_id"] = raw_user_state.get("last_update_id", legacy_update_id)
    raw_monitors = raw_user_state.get("monitors", {})
    for name, monitor in raw_monitors.items():
        if name in user_state["monitors"]:
            user_state["monitors"][name].update(monitor)
    for name, monitor in list(user_state["monitors"].items()):
        user_state["monitors"][name] = normalize_monitor_settings(monitor)
    return user_state


def migrate_state(raw: dict) -> dict:
    state = default_state()
    legacy_update_id = raw.get("last_update_id", 0)
    state["last_update_id"] = legacy_update_id
    if "monitors" in raw:
        monitors = raw.get("monitors", {})
        geronimo = state["telegram_users"]["geronimo"]
        geronimo["last_update_id"] = legacy_update_id
        for name, monitor in monitors.items():
            if name in geronimo["monitors"]:
                geronimo["monitors"][name].update(monitor)
        if "yosemite" in monitors:
            migrate_old_yosemite_group(geronimo["monitors"], monitors["yosemite"])
        migrate_old_reserve_ca_monitor(geronimo["monitors"], "prairie", "prairie_redwoods", monitors)
        migrate_old_reserve_ca_monitor(geronimo["monitors"], "gold_bluffs", "gold_bluffs_redwoods", monitors)
        for name, monitor in list(geronimo["monitors"].items()):
            geronimo["monitors"][name] = normalize_monitor_settings(monitor)
    for user_id, raw_user_state in raw.get("telegram_users", {}).items():
        if user_id in state["telegram_users"]:
            if "monitors" in raw_user_state:
                state["telegram_users"][user_id] = migrate_user_state(raw_user_state, legacy_update_id)
            else:
                state["telegram_users"][user_id]["last_update_id"] = raw_user_state.get("last_update_id", legacy_update_id)
    if "monitors" in raw:
        return state
    if "telegram_users" in raw:
        return state

    # Backward compatibility with the original single Yosemite monitor state.
    state["telegram_users"]["geronimo"]["last_update_id"] = legacy_update_id
    migrate_old_yosemite_group(state["telegram_users"]["geronimo"]["monitors"], {
        "enabled": raw.get("enabled", False),
        "checkin": raw.get("checkin"),
        "checkout": raw.get("checkout"),
        "campgrounds": raw.get("campgrounds", [config["facility_id"] for config in RECREATION_GOV_MONITORS.values()]),
    })
    return state


def load_state() -> dict:
    if STATE_PATH.exists():
        return migrate_state(json.loads(STATE_PATH.read_text(encoding="utf-8")))
    return default_state()


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_optional(name: str) -> str:
    return os.getenv(name, "").strip()


TELEGRAM_USER_CONFIG = {
    "geronimo": {
        "name": "Geronimo",
        "bot_token_env": "GERONIMO_TELEGRAM_BOT_TOKEN",
        "fallback_bot_token_env": "TELEGRAM_BOT_TOKEN",
        "chat_id_env": "GERONIMO_TELEGRAM_CHAT_ID",
        "fallback_chat_id_env": "TELEGRAM_CHAT_ID",
    },
    "sophia": {
        "name": "Sophia",
        "bot_token_env": "SOPHIA_TELEGRAM_BOT_TOKEN",
        "chat_id_env": "SOPHIA_TELEGRAM_CHAT_ID",
    },
}


def load_telegram_users() -> dict[str, dict]:
    users = {}
    for user_id, config in TELEGRAM_USER_CONFIG.items():
        bot_token = env_optional(config["bot_token_env"])
        if config.get("fallback_bot_token_env"):
            bot_token = bot_token or env_optional(config["fallback_bot_token_env"])
        chat_id = env_optional(config["chat_id_env"])
        if config.get("fallback_chat_id_env"):
            chat_id = chat_id or env_optional(config["fallback_chat_id_env"])
        if bot_token and chat_id:
            users[user_id] = {
                "id": user_id,
                "name": config["name"],
                "bot_token": bot_token,
                "chat_id": chat_id,
            }
    if not users:
        raise RuntimeError("Missing required Telegram bot token/chat ID configuration")
    return users


TELEGRAM_USERS = load_telegram_users()


def telegram_api(user: dict, method: str, **data):
    resp = requests.post(
        f"https://api.telegram.org/bot{user['bot_token']}/{method}",
        data=data,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def configured_telegram_users() -> list[dict]:
    users = []
    seen = set()
    for user in TELEGRAM_USERS.values():
        key = (user["bot_token"], user["chat_id"])
        if key not in seen:
            seen.add(key)
            users.append(user)
    return users


def send_telegram_to(user: dict, message: str) -> None:
    telegram_api(user, "sendMessage", chat_id=user["chat_id"], text=message, parse_mode="HTML", disable_web_page_preview=True)


def user_reply(user: dict, message: str) -> str:
    return f"Hi {user['name']},\n\n{message}"


def send_user_reply(user: dict, message: str) -> None:
    send_telegram_to(user, user_reply(user, message))


def send_telegram(message: str) -> None:
    for user in configured_telegram_users():
        send_telegram_to(user, message)


def get_updates(user: dict, offset: int):
    return telegram_api(user, "getUpdates", offset=offset, timeout=0, allowed_updates=json.dumps(["message"]))


def base_headers(origin: str = "https://www.recreation.gov/") -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": origin,
        "Origin": origin.rstrip("/"),
    }


def month_starts_between(start: dt.date, end_exclusive: dt.date):
    cursor = start.replace(day=1)
    last = (end_exclusive - dt.timedelta(days=1)).replace(day=1)
    while cursor <= last:
        yield cursor
        if cursor.month == 12:
            cursor = dt.date(cursor.year + 1, 1, 1)
        else:
            cursor = dt.date(cursor.year, cursor.month + 1, 1)


def date_windows(checkin: dt.date, checkout: dt.date) -> list[tuple[dt.date, dt.date]]:
    windows = []
    day = checkin
    while day < checkout:
        windows.append((day, day + dt.timedelta(days=1)))
        day += dt.timedelta(days=1)
    return windows


def fetch_recreation_gov_campsites(cg_id: str, checkin: dt.date, checkout: dt.date) -> dict[str, dict]:
    campsites: dict[str, dict] = {}
    url = AVAIL_API.format(id=cg_id)
    for month_start in month_starts_between(checkin, checkout):
        params = {"start_date": month_start.strftime("%Y-%m-%dT00:00:00.000Z")}
        resp = requests.get(url, params=params, headers=base_headers(), timeout=20)
        resp.raise_for_status()
        for site_id, site in resp.json().get("campsites", {}).items():
            merged = campsites.setdefault(site_id, {
                "loop": site.get("loop", ""),
                "site": site.get("site", ""),
                "type": site.get("campsite_type", "STANDARD NONELECTRIC"),
                "availabilities": {},
            })
            merged["availabilities"].update(site.get("availabilities", {}))
            merged["loop"] = merged.get("loop") or site.get("loop", "")
            merged["site"] = merged.get("site") or site.get("site", "")
            merged["type"] = merged.get("type") or site.get("campsite_type", "STANDARD NONELECTRIC")
    return campsites


def available_recreation_sites_for_night(campsites: dict[str, dict], night: dt.date) -> list[dict]:
    night_key = night.strftime("%Y-%m-%dT00:00:00Z")
    available = []
    for site_id, site in campsites.items():
        if site.get("availabilities", {}).get(night_key) == "Available":
            available.append({
                "campsite_id": site_id,
                "loop": site.get("loop", ""),
                "site": site.get("site", ""),
                "type": site.get("type", "STANDARD NONELECTRIC"),
            })
    return available


def check_recreation_gov_nights(cg_id: str, checkin: dt.date, checkout: dt.date) -> list[dict]:
    campsites = fetch_recreation_gov_campsites(cg_id, checkin, checkout)
    available_nights = []
    for start, end in date_windows(checkin, checkout):
        sites = available_recreation_sites_for_night(campsites, start)
        if sites:
            available_nights.append({
                "checkin": start,
                "checkout": end,
                "sites": sites,
            })
    return available_nights


def check_reserve_ca(monitor_name: str, checkin: dt.date, checkout: dt.date) -> dict:
    config = RESERVE_CA_MONITORS[monitor_name]
    # California State Parks' "length" parameter is inclusive of the arrival day.
    length = (checkout - checkin).days + 1
    params = {
        "arrival_date": checkin.isoformat(),
        "length": str(length),
        "page_id": config["parks_page_id"],
    }
    resp = requests.get(
        RESERVE_CA_AVAILABILITY_URL,
        params=params,
        headers=base_headers("https://www.parks.ca.gov/"),
        timeout=20,
    )
    resp.raise_for_status()
    text = re.sub(r"\s+", " ", resp.text)
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    match = re.search(r"Availability:\s*(Yes|No)", plain, re.I)
    if not match:
        raise RuntimeError(f"Could not parse {config['name']} availability page")

    overall_available = match.group(1).lower() == "yes"
    available_section = text[text.find("Available Campgrounds"):] if "Available Campgrounds" in text else ""
    campground_available = f"href=\"#{config['campground_anchor']}\"" in available_section
    is_available = overall_available and campground_available
    return {
        "available": is_available,
        "label": "Available" if is_available else "Not available",
        "url": reserve_ca_booking_url(monitor_name, checkin, checkout),
    }


def check_reserve_ca_nights(monitor_name: str, checkin: dt.date, checkout: dt.date) -> list[dict]:
    available_nights = []
    for start, end in date_windows(checkin, checkout):
        result = check_reserve_ca(monitor_name, start, end)
        if result["available"]:
            available_nights.append({
                "checkin": start,
                "checkout": end,
                "url": result["url"],
            })
    return available_nights


def recreation_booking_url(monitor_name: str, checkin: dt.date, checkout: dt.date) -> str:
    ci = checkin.strftime("%m%%2F%d%%2F%Y")
    co = checkout.strftime("%m%%2F%d%%2F%Y")
    return f"{RECREATION_GOV_MONITORS[monitor_name]['url']}?checkin={ci}&checkout={co}"


def reserve_ca_booking_url(monitor_name: str, checkin: dt.date, checkout: dt.date) -> str:
    # ReserveCalifornia's UI URL is the most useful target for the alert.
    return (
        f"{RESERVE_CA_MONITORS[monitor_name]['reserve_url']}"
        f"?arrivalDate={checkin.isoformat()}&departureDate={checkout.isoformat()}"
    )


def format_sites(sites: list[dict], limit: int = 8) -> str:
    rows = []
    for site in sites[:limit]:
        label = f"- site {site.get('site') or site.get('campsite_id')}"
        loop = site.get("loop", "").strip()
        if loop:
            label += f" / loop {loop}"
        if site.get("type"):
            label += f" ({site['type']})"
        rows.append(label)
    if len(sites) > limit:
        rows.append(f"- plus {len(sites) - limit} more")
    return "\n".join(rows)


def format_date_window(checkin: dt.date, checkout: dt.date) -> str:
    if checkin.year == checkout.year:
        return f"{checkin.strftime('%b %d')} - {checkout.strftime('%b %d, %Y')}"
    return f"{checkin.strftime('%b %d, %Y')} - {checkout.strftime('%b %d, %Y')}"


def format_recreation_nights(monitor_name: str, nights: list[dict], limit: int = 4) -> str:
    rows = []
    for night in nights[:limit]:
        link = recreation_booking_url(monitor_name, night["checkin"], night["checkout"])
        rows.append(
            f"<a href='{link}'>{format_date_window(night['checkin'], night['checkout'])}</a>\n"
            f"{format_sites(night['sites'], limit=5)}"
        )
    if len(nights) > limit:
        rows.append(f"Plus {len(nights) - limit} more available night(s).")
    return "\n\n".join(rows)


def format_reserve_ca_nights(nights: list[dict], limit: int = 8) -> str:
    rows = []
    for night in nights[:limit]:
        rows.append(
            f"- <a href='{night['url']}'>{format_date_window(night['checkin'], night['checkout'])}</a>"
        )
    if len(nights) > limit:
        rows.append(f"- plus {len(nights) - limit} more available night(s)")
    return "\n".join(rows)


def monitor_targets() -> list[str]:
    return list(ACTIVE_MONITORS)


def monitors_text() -> str:
    rows = []
    for name in monitor_targets():
        config = RECREATION_GOV_MONITORS.get(name, RESERVE_CA_MONITORS.get(name))
        rows.append(f"- {config['name']}")
    return "Available Yosemite monitor names:\n" + "\n".join(rows)


def normalize_monitor_target(value: str) -> str | None:
    key = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return MONITOR_ALIASES.get(key)


def parse_target(rest: str, default: str = "all") -> tuple[list[str], str]:
    words = rest.split()
    parts = rest.split(maxsplit=1)
    if not parts:
        return ([default] if default != "all" else monitor_targets()), ""
    first = parts[0].lower()
    if first in {"all", "both"}:
        return monitor_targets(), parts[1] if len(parts) > 1 else ""
    for width in range(min(3, len(words)), 0, -1):
        candidate = " ".join(words[:width])
        target = normalize_monitor_target(candidate)
        if target in monitor_targets():
            return [target], " ".join(words[width:])
    return [], rest


def monitor_status(name: str, monitor: dict) -> str:
    mode = "ON" if monitor["enabled"] else "OFF"
    label = RECREATION_GOV_MONITORS.get(name, RESERVE_CA_MONITORS.get(name))["name"]
    search_mode = monitor.get("mode", DEFAULT_SEARCH_MODE)
    mode_text = SEARCH_MODES.get(search_mode, SEARCH_MODES[DEFAULT_SEARCH_MODE])
    if search_mode == "consecutive":
        mode_text = f"at least {monitor.get('min_consecutive_nights', DEFAULT_MIN_CONSECUTIVE_NIGHTS)} consecutive available nights"
    return f"{label}: {mode}\nDates: {monitor['checkin']} to {monitor['checkout']}\nMode: {mode_text}"


def status_text(user_state: dict) -> str:
    blocks = [monitor_status(name, user_state["monitors"][name]) for name in monitor_targets()]
    return (
        "Campsite monitors\n\n"
        + "Trigger: external cron-job.org dispatch\n\n"
        + "\n\n".join(blocks)
        + "\n\nUse /help for all commands."
    )


def help_text(state: dict) -> str:
    return (
        "Campsite monitor commands\n\n"
        "Status\n"
        "- /status - show trigger, dates, and watched campsites\n"
        "- /help - show this command guide\n\n"
        "Turn monitors on/off\n"
        "- /start all - turn on every Yosemite campsite\n"
        "- /start upper yosemite\n"
        "- /start north yosemite\n"
        "- /start lower yosemite\n"
        "- /stop all - turn off all Yosemite monitors\n"
        "- /stop upper yosemite - turn off one campsite\n\n"
        "Run a check\n"
        "- /check all - check every Yosemite monitor on the next workflow run\n"
        "- /check upper yosemite - check one campsite once\n"
        "- /monitors - list every available Yosemite campsite name\n\n"
        "Change dates\n"
        "- /dates upper yosemite 2026-05-22 2026-05-26\n"
        "Dates use YYYY-MM-DD. Checkout must be after checkin.\n"
        "The range is checked one night at a time.\n\n"
        "Search mode\n"
        "- /mode upper yosemite any - alert if any night is available\n"
        "- /mode upper yosemite all - alert only if every night is available\n"
        "- /mode upper yosemite consecutive 2 - alert if 2 consecutive nights are available"
    )


def parse_mode_args(rest: str) -> tuple[str | None, int | None]:
    parts = rest.split()
    if not parts:
        return None, None
    mode = parts[0].lower()
    if mode in {"any", "anyday", "any_day", "any-night", "any_night"}:
        return "any", None
    if mode in {"all", "all-days", "all_days", "allnights", "all_nights"}:
        return "all", None
    if mode in {"consecutive", "consecutive-days", "consecutive_days", "consecutive-nights", "consecutive_nights"}:
        min_nights = DEFAULT_MIN_CONSECUTIVE_NIGHTS
        if len(parts) > 1:
            try:
                min_nights = max(1, int(parts[1]))
            except ValueError:
                return None, None
        return "consecutive", min_nights
    return None, None


def process_commands(state: dict) -> list[tuple[str, str]]:
    force_checks: set[tuple[str, str]] = set()
    state.setdefault("telegram_users", {})
    for user in configured_telegram_users():
        user_state = state["telegram_users"].setdefault(user["id"], default_user_state())
        user_state.setdefault("monitors", default_user_monitors())
        updates = get_updates(user, int(user_state.get("last_update_id", 0)) + 1)
        for update in updates:
            user_state["last_update_id"] = max(int(user_state.get("last_update_id", 0)), int(update["update_id"]))
            if user["id"] == "geronimo":
                state["last_update_id"] = user_state["last_update_id"]
            message = update.get("message") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if chat_id != str(user["chat_id"]):
                continue
            text = (message.get("text") or "").strip()
            if not text:
                continue

            command, _, rest = text.partition(" ")
            command = command.lower().split("@", 1)[0]

            if command in {"/help", "/commands"}:
                send_user_reply(user, help_text(state))
            elif command == "/start" and not rest.strip():
                send_user_reply(user, help_text(state))
            elif command == "/status":
                send_user_reply(user, status_text(user_state))
            elif command in {"/start", "/on", "/start_monitor"}:
                targets, _ = parse_target(rest)
                if not targets:
                    send_user_reply(user, "Unknown monitor.\n\n" + monitors_text())
                    continue
                for target in targets:
                    user_state["monitors"][target]["enabled"] = True
                    force_checks.add((user["id"], target))
                send_user_reply(user, "Monitor enabled.\n\n" + status_text(user_state))
            elif command in {"/stop", "/off"}:
                targets, _ = parse_target(rest)
                if not targets:
                    send_user_reply(user, "Unknown monitor.\n\n" + monitors_text())
                    continue
                for target in targets:
                    user_state["monitors"][target]["enabled"] = False
                send_user_reply(user, "Monitor disabled.\n\n" + status_text(user_state))
            elif command == "/check":
                targets, _ = parse_target(rest)
                if not targets:
                    send_user_reply(user, "Unknown monitor.\n\n" + monitors_text())
                    continue
                force_checks.update((user["id"], target) for target in targets)
                send_user_reply(user, "Running availability check for: " + ", ".join(targets))
            elif command in {"/monitors", "/list"}:
                send_user_reply(user, monitors_text())
            elif command == "/settings":
                send_user_reply(user, "Settings are managed in GitHub/cron-job.org now. Use /help for bot commands.")
            elif command == "/dates":
                targets, date_args = parse_target(rest)
                if len(targets) != 1:
                    send_user_reply(user, "Usage: /dates MONITOR_NAME YYYY-MM-DD YYYY-MM-DD\n\n" + monitors_text())
                    continue
                try:
                    ci_s, co_s = date_args.split()[:2]
                    checkin = dt.date.fromisoformat(ci_s)
                    checkout = dt.date.fromisoformat(co_s)
                    if checkout <= checkin:
                        raise ValueError("checkout must be after checkin")
                    monitor = user_state["monitors"][targets[0]]
                    monitor["checkin"] = checkin.isoformat()
                    monitor["checkout"] = checkout.isoformat()
                    monitor["last_alert_key"] = ""
                    force_checks.add((user["id"], targets[0]))
                    send_user_reply(user, f"{targets[0]} dates updated: {monitor['checkin']} to {monitor['checkout']}")
                except Exception:
                    send_user_reply(user, "Usage: /dates MONITOR_NAME YYYY-MM-DD YYYY-MM-DD\n\n" + monitors_text())
            elif command == "/mode":
                targets, mode_args = parse_target(rest)
                if len(targets) != 1:
                    send_user_reply(user, "Usage: /mode MONITOR_NAME any|all|consecutive [N]\n\n" + monitors_text())
                    continue
                mode, min_nights = parse_mode_args(mode_args)
                if not mode:
                    send_user_reply(user, "Usage: /mode MONITOR_NAME any|all|consecutive [N]\n\n" + monitors_text())
                    continue
                monitor = user_state["monitors"][targets[0]]
                monitor["mode"] = mode
                if min_nights is not None:
                    monitor["min_consecutive_nights"] = min_nights
                monitor["last_alert_key"] = ""
                send_user_reply(user, "Search mode updated.\n\n" + monitor_status(targets[0], monitor))
            elif command == "/campgrounds":
                send_user_reply(user, "Campground groups were removed. Use each campsite by name.\n\n" + monitors_text())
            else:
                send_user_reply(user, "Unknown command.\n\n" + status_text(user_state))
    return sorted(force_checks)


def matching_available_nights(available_nights: list[dict], checkin: dt.date, checkout: dt.date, monitor: dict) -> list[dict]:
    mode = monitor.get("mode", DEFAULT_SEARCH_MODE)
    if mode == "any":
        return available_nights

    windows = date_windows(checkin, checkout)
    available_by_checkin = {night["checkin"]: night for night in available_nights}
    if mode == "all":
        if windows and all(start in available_by_checkin for start, _ in windows):
            return [available_by_checkin[start] for start, _ in windows]
        return []

    if mode == "consecutive":
        min_nights = max(1, int(monitor.get("min_consecutive_nights", DEFAULT_MIN_CONSECUTIVE_NIGHTS)))
        matches = []
        run = []
        for start, _ in windows:
            night = available_by_checkin.get(start)
            if night:
                run.append(night)
                continue
            if len(run) >= min_nights:
                matches.extend(run)
            run = []
        if len(run) >= min_nights:
            matches.extend(run)
        return matches

    return available_nights


def availability_mode_label(monitor: dict) -> str:
    mode = monitor.get("mode", DEFAULT_SEARCH_MODE)
    if mode == "consecutive":
        return f"at least {monitor.get('min_consecutive_nights', DEFAULT_MIN_CONSECUTIVE_NIGHTS)} consecutive available nights"
    return SEARCH_MODES.get(mode, SEARCH_MODES[DEFAULT_SEARCH_MODE])


def run_recreation_gov_check(user: dict, name: str, monitor: dict) -> None:
    config = RECREATION_GOV_MONITORS[name]
    checkin = dt.date.fromisoformat(monitor["checkin"])
    checkout = dt.date.fromisoformat(monitor["checkout"])
    available_nights = check_recreation_gov_nights(config["facility_id"], checkin, checkout)
    matching_nights = matching_available_nights(available_nights, checkin, checkout, monitor)
    print(f"{user['id']} {config['name']}: {len(matching_nights)} matching night(s), {len(available_nights)} available night(s)")

    alert_parts = []
    for night in matching_nights:
        site_ids = ",".join(site["campsite_id"] for site in night["sites"][:20])
        alert_parts.append(f"{night['checkin'].isoformat()}:{site_ids}")
    alert_key = f"{monitor.get('mode', DEFAULT_SEARCH_MODE)}:{monitor.get('min_consecutive_nights', DEFAULT_MIN_CONSECUTIVE_NIGHTS)}:" + "|".join(alert_parts)
    if matching_nights and alert_key != monitor.get("last_alert_key", ""):
        send_telegram_to(
            user,
            f"Recreation.gov campsite available!\n\n"
            f"{config['name']}\n"
            f"Selected range: {format_date_window(checkin, checkout)}\n\n"
            f"Mode: {availability_mode_label(monitor)}\n\n"
            f"{format_recreation_nights(name, matching_nights)}\n\nBook now!"
        )
        monitor["last_alert_key"] = alert_key
    elif not matching_nights and monitor.get("last_alert_key"):
        send_telegram_to(user, f"Previously found {config['name']} spots are gone or no longer match your mode. Keeping watch.")
        monitor["last_alert_key"] = ""


def run_reserve_ca_check(user: dict, name: str, monitor: dict) -> None:
    config = RESERVE_CA_MONITORS[name]
    checkin = dt.date.fromisoformat(monitor["checkin"])
    checkout = dt.date.fromisoformat(monitor["checkout"])
    available_nights = check_reserve_ca_nights(name, checkin, checkout)
    matching_nights = matching_available_nights(available_nights, checkin, checkout, monitor)
    print(f"{user['id']} {config['name']}: {len(matching_nights)} matching night(s), {len(available_nights)} available night(s)")
    alert_key = f"{monitor.get('mode', DEFAULT_SEARCH_MODE)}:{monitor.get('min_consecutive_nights', DEFAULT_MIN_CONSECUTIVE_NIGHTS)}:" + "|".join(night["checkin"].isoformat() for night in matching_nights)
    if matching_nights and alert_key != monitor.get("last_alert_key", ""):
        send_telegram_to(
            user,
            f"ReserveCalifornia campsite available!\n\n"
            f"{config['name']}\n"
            f"Selected range: {format_date_window(checkin, checkout)}\n\n"
            f"Mode: {availability_mode_label(monitor)}\n\n"
            f"{format_reserve_ca_nights(matching_nights)}"
        )
        monitor["last_alert_key"] = alert_key
    elif not matching_nights and monitor.get("last_alert_key"):
        send_telegram_to(user, f"Previously found {config['name']} spot is gone or no longer matches your mode. Keeping watch.")
        monitor["last_alert_key"] = ""


def run_checks(state: dict, force_checks: list[tuple[str, str]]) -> None:
    forced = set(force_checks)
    for user in configured_telegram_users():
        user_state = state["telegram_users"].setdefault(user["id"], default_user_state())
        user_state.setdefault("monitors", default_user_monitors())
        for name in monitor_targets():
            monitor = user_state["monitors"][name]
            if not monitor.get("enabled") and (user["id"], name) not in forced:
                print(f"{user['id']} {name} monitor is off")
                continue
            try:
                if name in RECREATION_GOV_MONITORS:
                    run_recreation_gov_check(user, name, monitor)
                else:
                    run_reserve_ca_check(user, name, monitor)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                print(f"{user['id']} {name} monitor HTTP error: {status}")
            except Exception as exc:
                print(f"{user['id']} {name} monitor error: {exc}")


def main():
    state = load_state()
    force_checks = process_commands(state)
    run_checks(state, force_checks)
    save_state(state)


if __name__ == "__main__":
    main()
