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
CRON_JOB_ORG_API = "https://api.cron-job.org"
STATE_PATH = Path(".monitor_state.json")


def default_state() -> dict:
    today = dt.date.today()
    recreation_dates = {
        "enabled": False,
        "checkin": (today + dt.timedelta(days=1)).isoformat(),
        "checkout": (today + dt.timedelta(days=4)).isoformat(),
        "last_alert_key": "",
    }
    return {
        "last_update_id": 0,
        "scheduler": "external",
        "monitors": {
            "upper_yosemite": dict(recreation_dates),
            "north_yosemite": dict(recreation_dates),
            "lower_yosemite": dict(recreation_dates),
            "north_summit_lassen": dict(recreation_dates),
            "south_summit_lassen": dict(recreation_dates),
            "prairie_redwoods": {
                "enabled": True,
                "checkin": "2026-05-24",
                "checkout": "2026-05-26",
                "last_alert_key": "",
            },
            "gold_bluffs_redwoods": {
                "enabled": True,
                "checkin": "2026-05-23",
                "checkout": "2026-05-25",
                "last_alert_key": "",
            },
        },
    }


def recreation_monitor_by_facility_id(facility_id: str) -> str | None:
    for name, config in RECREATION_GOV_MONITORS.items():
        if config["facility_id"] == facility_id:
            return name
    return None


def migrate_old_yosemite_group(state: dict, monitor: dict) -> None:
    selected = set(monitor.get("campgrounds", []))
    if not selected:
        selected = {config["facility_id"] for config in RECREATION_GOV_MONITORS.values()}
    for name, config in RECREATION_GOV_MONITORS.items():
        state["monitors"][name].update({
            "enabled": bool(monitor.get("enabled", False)) and config["facility_id"] in selected,
            "checkin": monitor.get("checkin") or state["monitors"][name]["checkin"],
            "checkout": monitor.get("checkout") or state["monitors"][name]["checkout"],
            "last_alert_key": "",
        })


def migrate_old_reserve_ca_monitor(state: dict, old_name: str, new_name: str, monitors: dict) -> None:
    if old_name in monitors:
        state["monitors"][new_name].update(monitors[old_name])


def migrate_state(raw: dict) -> dict:
    state = default_state()
    if "monitors" in raw:
        state["last_update_id"] = raw.get("last_update_id", 0)
        state["scheduler"] = normalize_scheduler(raw.get("scheduler", "")) or state["scheduler"]
        monitors = raw.get("monitors", {})
        for name, monitor in monitors.items():
            if name in state["monitors"]:
                state["monitors"][name].update(monitor)
        if "yosemite" in monitors:
            migrate_old_yosemite_group(state, monitors["yosemite"])
        migrate_old_reserve_ca_monitor(state, "prairie", "prairie_redwoods", monitors)
        migrate_old_reserve_ca_monitor(state, "gold_bluffs", "gold_bluffs_redwoods", monitors)
        return state

    # Backward compatibility with the original single Yosemite monitor state.
    state["last_update_id"] = raw.get("last_update_id", 0)
    state["scheduler"] = normalize_scheduler(raw.get("scheduler", "")) or state["scheduler"]
    migrate_old_yosemite_group(state, {
        "enabled": raw.get("enabled", False),
        "checkin": raw.get("checkin"),
        "checkout": raw.get("checkout"),
        "campgrounds": raw.get("campgrounds", [config["facility_id"] for config in RECREATION_GOV_MONITORS.values()]),
    })
    return state


def normalize_scheduler(value: str) -> str | None:
    key = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if key in {"external", "cron", "cronjob", "cron_job", "cronjoborg", "cron_job_org"}:
        return "external"
    if key in {"github", "github_actions", "actions", "schedule", "scheduled"}:
        return "github"
    return None


def scheduler_label(value: str) -> str:
    if value == "github":
        return "GitHub Actions schedule (every 5 minutes)"
    return "External cron-job.org dispatch (currently every 2 minutes)"


def trigger_source() -> str:
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    if event_name == "schedule":
        return "github"
    if event_name == "repository_dispatch":
        return "external"
    return "manual"


def should_run_for_scheduler(state: dict) -> bool:
    source = trigger_source()
    if source == "manual":
        return True
    return source == state.get("scheduler", "external")


def set_external_cron_enabled(enabled: bool) -> tuple[bool, str]:
    api_key = os.getenv("CRON_JOB_ORG_API_KEY", "").strip()
    job_id = os.getenv("CRON_JOB_ORG_JOB_ID", "").strip()
    action = "enabled" if enabled else "paused"
    if not api_key or not job_id:
        return (
            False,
            "Missing CRON_JOB_ORG_API_KEY or CRON_JOB_ORG_JOB_ID, so cron-job.org was not "
            f"{action}. Add the API key as a GitHub secret first.",
        )

    resp = requests.patch(
        f"{CRON_JOB_ORG_API}/jobs/{job_id}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"job": {"enabled": enabled}},
        timeout=20,
    )
    if resp.status_code >= 400:
        return False, f"cron-job.org returned HTTP {resp.status_code}; scheduler was not changed."
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    if payload not in ({}, None):
        return False, f"Unexpected cron-job.org response: {payload}; scheduler was not changed."
    return True, f"cron-job.org job {job_id} {action}."


def switch_scheduler(state: dict, scheduler: str) -> tuple[bool, str]:
    if scheduler == state.get("scheduler", "external"):
        return True, "Scheduler already set: " + scheduler_label(scheduler)

    if scheduler == "github":
        ok, cron_message = set_external_cron_enabled(False)
        if not ok:
            return False, cron_message
        state["scheduler"] = "github"
        return True, "Scheduler updated: " + scheduler_label(scheduler) + "\n" + cron_message

    ok, cron_message = set_external_cron_enabled(True)
    if not ok:
        return False, cron_message
    state["scheduler"] = "external"
    return True, "Scheduler updated: " + scheduler_label(scheduler) + "\n" + cron_message


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


BOT_TOKEN = env_required("TELEGRAM_BOT_TOKEN")
CHAT_ID = env_required("TELEGRAM_CHAT_ID")


def telegram_api(method: str, **data):
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=data,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def send_telegram(message: str) -> None:
    telegram_api("sendMessage", chat_id=CHAT_ID, text=message, parse_mode="HTML", disable_web_page_preview=True)


def get_updates(offset: int):
    return telegram_api("getUpdates", offset=offset, timeout=0, allowed_updates=json.dumps(["message"]))


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


def check_yosemite_campground(cg_id: str, checkin: dt.date, checkout: dt.date) -> list[dict]:
    nights = []
    day = checkin
    while day < checkout:
        nights.append(day.strftime("%Y-%m-%dT00:00:00Z"))
        day += dt.timedelta(days=1)

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

    available = []
    for site_id, site in campsites.items():
        if all(site.get("availabilities", {}).get(n) == "Available" for n in nights):
            available.append({
                "campsite_id": site_id,
                "loop": site.get("loop", ""),
                "site": site.get("site", ""),
                "type": site.get("type", "STANDARD NONELECTRIC"),
            })
    return available


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


def monitor_targets() -> list[str]:
    return [*RECREATION_GOV_MONITORS.keys(), *RESERVE_CA_MONITORS.keys()]


def monitors_text() -> str:
    rows = []
    for name in monitor_targets():
        config = RECREATION_GOV_MONITORS.get(name, RESERVE_CA_MONITORS.get(name))
        rows.append(f"- {config['name']}")
    return "Available monitor names:\n" + "\n".join(rows)


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
        if target:
            return [target], " ".join(words[width:])
    return ([default] if default != "all" else monitor_targets()), rest


def monitor_status(name: str, monitor: dict) -> str:
    mode = "ON" if monitor["enabled"] else "OFF"
    label = RECREATION_GOV_MONITORS.get(name, RESERVE_CA_MONITORS.get(name))["name"]
    return f"{label}: {mode}\nDates: {monitor['checkin']} to {monitor['checkout']}"


def status_text(state: dict) -> str:
    blocks = [monitor_status(name, state["monitors"][name]) for name in monitor_targets()]
    return (
        "Campsite monitors\n\n"
        + f"Scheduler: {scheduler_label(state.get('scheduler', 'external'))}\n\n"
        + "\n\n".join(blocks)
        + "\n\nUse /help for all commands."
    )


def help_text(state: dict) -> str:
    return (
        "Campsite monitor commands\n\n"
        "Status\n"
        "- /status - show active scheduler, dates, and watched campgrounds\n"
        "- /help - show this command guide\n\n"
        "Turn monitors on/off\n"
        "- /start all - turn on every campsite\n"
        "- /start upper yosemite\n"
        "- /start north yosemite\n"
        "- /start lower yosemite\n"
        "- /start north summit lassen\n"
        "- /start south summit lassen\n"
        "- /start prairie redwoods\n"
        "- /start gold bluffs redwoods\n"
        "- /stop all - turn off all monitors\n"
        "- /stop upper yosemite - turn off one campsite\n\n"
        "Run a check\n"
        "- /check all - check every monitor on the next workflow run\n"
        "- /check upper yosemite - check one campsite once\n"
        "- /monitors - list every campsite name\n\n"
        "Change dates\n"
        "- /dates upper yosemite 2026-05-22 2026-05-26\n"
        "- /dates prairie redwoods 2026-05-24 2026-05-26\n"
        "Dates use YYYY-MM-DD. Checkout must be after checkin.\n\n"
        "Scheduler\n"
        "- /scheduler external - use cron-job.org dispatch trigger\n"
        "- /scheduler github - use GitHub Actions 5-minute schedule\n"
        "- /settings scheduler external - same as /scheduler external\n"
        "- /settings scheduler github - same as /scheduler github\n\n"
        f"Current scheduler: {scheduler_label(state.get('scheduler', 'external'))}"
    )


def process_commands(state: dict) -> list[str]:
    force_checks: set[str] = set()
    updates = get_updates(int(state.get("last_update_id", 0)) + 1)
    for update in updates:
        state["last_update_id"] = max(int(state.get("last_update_id", 0)), int(update["update_id"]))
        message = update.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if chat_id != str(CHAT_ID):
            continue
        text = (message.get("text") or "").strip()
        if not text:
            continue

        command, _, rest = text.partition(" ")
        command = command.lower().split("@", 1)[0]

        if command in {"/help", "/commands"}:
            send_telegram(help_text(state))
        elif command == "/status":
            send_telegram(status_text(state))
        elif command in {"/start", "/on", "/start_monitor"}:
            targets, _ = parse_target(rest)
            for target in targets:
                state["monitors"][target]["enabled"] = True
                force_checks.add(target)
            send_telegram("Monitor enabled.\n\n" + status_text(state))
        elif command in {"/stop", "/off"}:
            targets, _ = parse_target(rest)
            for target in targets:
                state["monitors"][target]["enabled"] = False
            send_telegram("Monitor disabled.\n\n" + status_text(state))
        elif command == "/check":
            targets, _ = parse_target(rest)
            force_checks.update(targets)
            send_telegram("Running availability check for: " + ", ".join(targets))
        elif command in {"/monitors", "/list"}:
            send_telegram(monitors_text())
        elif command in {"/scheduler", "/schedule"}:
            scheduler = normalize_scheduler(rest)
            if not scheduler:
                send_telegram(
                    "Current scheduler: "
                    + scheduler_label(state.get("scheduler", "external"))
                    + "\n\nUsage: /scheduler external OR /scheduler github"
                )
                continue
            ok, message = switch_scheduler(state, scheduler)
            send_telegram(message)
            if not ok:
                continue
        elif command == "/settings":
            setting, _, value = rest.strip().partition(" ")
            if setting.lower() != "scheduler":
                send_telegram("Usage: /settings scheduler external OR /settings scheduler github")
                continue
            scheduler = normalize_scheduler(value)
            if not scheduler:
                send_telegram("Usage: /settings scheduler external OR /settings scheduler github")
                continue
            ok, message = switch_scheduler(state, scheduler)
            send_telegram(message)
            if not ok:
                continue
        elif command == "/dates":
            targets, date_args = parse_target(rest)
            if len(targets) != 1:
                send_telegram("Usage: /dates MONITOR_NAME YYYY-MM-DD YYYY-MM-DD\n\n" + monitors_text())
                continue
            try:
                ci_s, co_s = date_args.split()[:2]
                checkin = dt.date.fromisoformat(ci_s)
                checkout = dt.date.fromisoformat(co_s)
                if checkout <= checkin:
                    raise ValueError("checkout must be after checkin")
                monitor = state["monitors"][targets[0]]
                monitor["checkin"] = checkin.isoformat()
                monitor["checkout"] = checkout.isoformat()
                monitor["last_alert_key"] = ""
                force_checks.add(targets[0])
                send_telegram(f"{targets[0]} dates updated: {monitor['checkin']} to {monitor['checkout']}")
            except Exception:
                send_telegram("Usage: /dates MONITOR_NAME YYYY-MM-DD YYYY-MM-DD\n\n" + monitors_text())
        elif command == "/campgrounds":
            send_telegram("Campground groups were removed. Use each campsite by name.\n\n" + monitors_text())
        else:
            send_telegram("Unknown command.\n\n" + status_text(state))
    return sorted(force_checks)


def run_recreation_gov_check(name: str, monitor: dict) -> None:
    config = RECREATION_GOV_MONITORS[name]
    checkin = dt.date.fromisoformat(monitor["checkin"])
    checkout = dt.date.fromisoformat(monitor["checkout"])
    sites = check_yosemite_campground(config["facility_id"], checkin, checkout)
    print(f"{config['name']}: {len(sites)} available")

    alert_key = ",".join(site["campsite_id"] for site in sites[:20])
    if sites and alert_key != monitor.get("last_alert_key", ""):
        send_telegram(
            f"Recreation.gov campsite available!\n\n"
            f"<a href='{recreation_booking_url(name, checkin, checkout)}'>{config['name']}</a>\n"
            f"{checkin.strftime('%b %d')} - {checkout.strftime('%b %d, %Y')}\n\n"
            f"{format_sites(sites)}\n\nBook now!"
        )
        monitor["last_alert_key"] = alert_key
    elif not sites and monitor.get("last_alert_key"):
        send_telegram(f"Previously found {config['name']} spots are gone. Keeping watch.")
        monitor["last_alert_key"] = ""


def run_reserve_ca_check(name: str, monitor: dict) -> None:
    config = RESERVE_CA_MONITORS[name]
    checkin = dt.date.fromisoformat(monitor["checkin"])
    checkout = dt.date.fromisoformat(monitor["checkout"])
    result = check_reserve_ca(name, checkin, checkout)
    print(f"{config['name']}: {result['label']}")
    alert_key = f"{name}:{monitor['checkin']}:{monitor['checkout']}:{result['available']}"
    if result["available"] and alert_key != monitor.get("last_alert_key", ""):
        send_telegram(
            f"ReserveCalifornia campsite available!\n\n"
            f"{config['name']}\n"
            f"{checkin.strftime('%b %d')} - {checkout.strftime('%b %d, %Y')}\n\n"
            f"<a href='{result['url']}'>Open ReserveCalifornia</a>"
        )
        monitor["last_alert_key"] = alert_key
    elif not result["available"] and monitor.get("last_alert_key"):
        send_telegram(f"Previously found {config['name']} spot is gone. Keeping watch.")
        monitor["last_alert_key"] = ""


def run_checks(state: dict, force_checks: list[str]) -> None:
    for name in monitor_targets():
        monitor = state["monitors"][name]
        if not monitor.get("enabled") and name not in force_checks:
            print(f"{name} monitor is off")
            continue
        try:
            if name in RECREATION_GOV_MONITORS:
                run_recreation_gov_check(name, monitor)
            else:
                run_reserve_ca_check(name, monitor)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            print(f"{name} monitor HTTP error: {status}")
        except Exception as exc:
            print(f"{name} monitor error: {exc}")


def main():
    state = load_state()
    if not should_run_for_scheduler(state):
        print(
            "Skipping "
            f"{trigger_source()} trigger because scheduler is set to "
            f"{state.get('scheduler', 'external')}"
        )
        save_state(state)
        return
    force_checks = process_commands(state)
    run_checks(state, force_checks)
    save_state(state)


if __name__ == "__main__":
    main()
