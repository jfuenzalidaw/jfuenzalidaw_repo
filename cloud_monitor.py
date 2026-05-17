import datetime as dt
import json
import os
import re
import time
from pathlib import Path

import requests


YOSEMITE_CAMPGROUNDS = {
    "232450": {"name": "Lower Pines Campground", "url": "https://www.recreation.gov/camping/campgrounds/232450"},
    "232449": {"name": "North Pines Campground", "url": "https://www.recreation.gov/camping/campgrounds/232449"},
    "232447": {"name": "Upper Pines Campground", "url": "https://www.recreation.gov/camping/campgrounds/232447"},
}

YOSEMITE_ALIASES = {
    "lower": "232450",
    "lowerpines": "232450",
    "north": "232449",
    "northpines": "232449",
    "upper": "232447",
    "upperpines": "232447",
}

PRAIRIE = {
    "name": "Prairie Creek Redwoods SP Elk Prairie Campground",
    "parks_page_id": "415",
    "reserve_url": "https://reservecalifornia.com/park/696",
    "availability_url": "https://www.parks.ca.gov/AvailabilityInfo",
}

AVAIL_API = "https://www.recreation.gov/api/camps/availability/campground/{id}/month"
STATE_PATH = Path(".monitor_state.json")


def default_state() -> dict:
    today = dt.date.today()
    return {
        "last_update_id": 0,
        "scheduler": "external",
        "monitors": {
            "yosemite": {
                "enabled": False,
                "checkin": (today + dt.timedelta(days=1)).isoformat(),
                "checkout": (today + dt.timedelta(days=4)).isoformat(),
                "campgrounds": list(YOSEMITE_CAMPGROUNDS.keys()),
                "last_alert_key": "",
            },
            "prairie": {
                "enabled": True,
                "checkin": "2026-05-24",
                "checkout": "2026-05-26",
                "last_alert_key": "",
            },
        },
    }


def sanitize_yosemite_monitor(monitor: dict) -> None:
    supported = list(YOSEMITE_CAMPGROUNDS.keys())
    selected = [cg_id for cg_id in monitor.get("campgrounds", []) if cg_id in YOSEMITE_CAMPGROUNDS]
    monitor["campgrounds"] = selected or supported


def migrate_state(raw: dict) -> dict:
    state = default_state()
    if "monitors" in raw:
        state["last_update_id"] = raw.get("last_update_id", 0)
        state["scheduler"] = normalize_scheduler(raw.get("scheduler", "")) or state["scheduler"]
        for name, monitor in raw.get("monitors", {}).items():
            if name in state["monitors"]:
                state["monitors"][name].update(monitor)
        sanitize_yosemite_monitor(state["monitors"]["yosemite"])
        return state

    # Backward compatibility with the original single Yosemite monitor state.
    state["last_update_id"] = raw.get("last_update_id", 0)
    state["scheduler"] = normalize_scheduler(raw.get("scheduler", "")) or state["scheduler"]
    state["monitors"]["yosemite"].update({
        "enabled": raw.get("enabled", False),
        "checkin": raw.get("checkin", state["monitors"]["yosemite"]["checkin"]),
        "checkout": raw.get("checkout", state["monitors"]["yosemite"]["checkout"]),
        "campgrounds": raw.get("campgrounds", list(YOSEMITE_CAMPGROUNDS.keys())),
        "last_alert_key": raw.get("last_alert_key", ""),
    })
    sanitize_yosemite_monitor(state["monitors"]["yosemite"])
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


def check_prairie(checkin: dt.date, checkout: dt.date) -> dict:
    # California State Parks' "length" parameter is inclusive of the arrival day.
    length = (checkout - checkin).days + 1
    params = {
        "arrival_date": checkin.isoformat(),
        "length": str(length),
        "page_id": PRAIRIE["parks_page_id"],
    }
    resp = requests.get(
        PRAIRIE["availability_url"],
        params=params,
        headers=base_headers("https://www.parks.ca.gov/"),
        timeout=20,
    )
    resp.raise_for_status()
    text = re.sub(r"\s+", " ", resp.text)
    match = re.search(r"Availability:\s*</?[^>]*>\s*<strong>\s*<span[^>]*>\s*(Yes|No)\s*</span>", text, re.I)
    if not match:
        match = re.search(r"Availability:\s*(Yes|No)", re.sub(r"<[^>]+>", " ", text), re.I)
    if not match:
        raise RuntimeError("Could not parse Prairie availability page")
    is_available = match.group(1).lower() == "yes"
    return {
        "available": is_available,
        "label": "Available" if is_available else "Not available",
        "url": prairie_booking_url(checkin, checkout),
    }


def yosemite_booking_url(cg_id: str, checkin: dt.date, checkout: dt.date) -> str:
    ci = checkin.strftime("%m%%2F%d%%2F%Y")
    co = checkout.strftime("%m%%2F%d%%2F%Y")
    return f"{YOSEMITE_CAMPGROUNDS[cg_id]['url']}?checkin={ci}&checkout={co}"


def prairie_booking_url(checkin: dt.date, checkout: dt.date) -> str:
    # ReserveCalifornia's UI URL is the most useful target for the alert.
    return f"{PRAIRIE['reserve_url']}?arrivalDate={checkin.isoformat()}&departureDate={checkout.isoformat()}"


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


def normalize_yosemite_campgrounds(text: str) -> list[str] | None:
    raw = text.strip().lower()
    if raw == "all":
        return list(YOSEMITE_CAMPGROUNDS.keys())
    selected = []
    for part in raw.replace(",", " ").split():
        key = part.replace("-", "").replace("_", "").replace(" ", "")
        cg_id = part if part in YOSEMITE_CAMPGROUNDS else YOSEMITE_ALIASES.get(key)
        if not cg_id:
            return None
        if cg_id not in selected:
            selected.append(cg_id)
    return selected


def yosemite_campgrounds_text() -> str:
    rows = []
    for cg_id, campground in YOSEMITE_CAMPGROUNDS.items():
        aliases = sorted(alias for alias, alias_id in YOSEMITE_ALIASES.items() if alias_id == cg_id)
        alias_text = ", ".join(aliases)
        rows.append(f"- {campground['name']} ({cg_id}) aliases: {alias_text}")
    return "Yosemite campground options:\n" + "\n".join(rows)


def parse_target(rest: str, default: str = "all") -> tuple[list[str], str]:
    parts = rest.split(maxsplit=1)
    if not parts:
        return ([default] if default != "all" else ["yosemite", "prairie"]), ""
    first = parts[0].lower()
    if first in {"all", "both"}:
        return ["yosemite", "prairie"], parts[1] if len(parts) > 1 else ""
    if first in {"yosemite", "prairie"}:
        return [first], parts[1] if len(parts) > 1 else ""
    return ([default] if default != "all" else ["yosemite", "prairie"]), rest


def monitor_status(name: str, monitor: dict) -> str:
    mode = "ON" if monitor["enabled"] else "OFF"
    base = f"{name}: {mode}\nDates: {monitor['checkin']} to {monitor['checkout']}"
    if name == "yosemite":
        watched = "\n".join(f"- {YOSEMITE_CAMPGROUNDS[cg_id]['name']}" for cg_id in monitor["campgrounds"])
        return f"{base}\nWatching:\n{watched}"
    return f"{base}\nWatching:\n- {PRAIRIE['name']}"


def status_text(state: dict) -> str:
    blocks = [monitor_status(name, state["monitors"][name]) for name in ("yosemite", "prairie")]
    return (
        "Campsite monitors\n\n"
        + f"Scheduler: {scheduler_label(state.get('scheduler', 'external'))}\n\n"
        + "\n\n".join(blocks)
        + "\n\nCommands:\n"
          "/start [all|yosemite|prairie]\n"
          "/stop [all|yosemite|prairie]\n"
          "/status\n"
          "/check [all|yosemite|prairie]\n"
          "/dates [yosemite|prairie] YYYY-MM-DD YYYY-MM-DD\n"
          "/campgrounds yosemite all|list|lower|north|upper\n"
          "/scheduler external|github\n"
          "/settings scheduler external|github"
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

        if command in {"/help", "/status"}:
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
        elif command in {"/scheduler", "/schedule"}:
            scheduler = normalize_scheduler(rest)
            if not scheduler:
                send_telegram(
                    "Current scheduler: "
                    + scheduler_label(state.get("scheduler", "external"))
                    + "\n\nUsage: /scheduler external OR /scheduler github"
                )
                continue
            state["scheduler"] = scheduler
            send_telegram("Scheduler updated: " + scheduler_label(scheduler))
        elif command == "/settings":
            setting, _, value = rest.strip().partition(" ")
            if setting.lower() != "scheduler":
                send_telegram("Usage: /settings scheduler external OR /settings scheduler github")
                continue
            scheduler = normalize_scheduler(value)
            if not scheduler:
                send_telegram("Usage: /settings scheduler external OR /settings scheduler github")
                continue
            state["scheduler"] = scheduler
            send_telegram("Scheduler updated: " + scheduler_label(scheduler))
        elif command == "/dates":
            targets, date_args = parse_target(rest, default="yosemite")
            if len(targets) != 1:
                send_telegram("Usage: /dates yosemite YYYY-MM-DD YYYY-MM-DD or /dates prairie YYYY-MM-DD YYYY-MM-DD")
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
                send_telegram("Usage: /dates yosemite YYYY-MM-DD YYYY-MM-DD or /dates prairie YYYY-MM-DD YYYY-MM-DD")
        elif command == "/campgrounds":
            targets, cg_args = parse_target(rest, default="yosemite")
            if targets != ["yosemite"]:
                send_telegram("Campground selection is only supported for Yosemite.")
                continue
            if cg_args.strip().lower() == "list":
                send_telegram(yosemite_campgrounds_text())
                continue
            selected = normalize_yosemite_campgrounds(cg_args)
            if not selected:
                send_telegram("Usage: /campgrounds yosemite list OR /campgrounds yosemite all OR /campgrounds yosemite lower north upper")
            else:
                state["monitors"]["yosemite"]["campgrounds"] = selected
                state["monitors"]["yosemite"]["last_alert_key"] = ""
                force_checks.add("yosemite")
                send_telegram("Yosemite campgrounds updated.\n\n" + status_text(state))
        else:
            send_telegram("Unknown command.\n\n" + status_text(state))
    return sorted(force_checks)


def run_yosemite_check(monitor: dict) -> None:
    checkin = dt.date.fromisoformat(monitor["checkin"])
    checkout = dt.date.fromisoformat(monitor["checkout"])
    available_map = {}
    errors = []
    for cg_id in monitor["campgrounds"]:
        try:
            sites = check_yosemite_campground(cg_id, checkin, checkout)
            print(f"{YOSEMITE_CAMPGROUNDS[cg_id]['name']}: {len(sites)} available")
            if sites:
                available_map[cg_id] = sites
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            msg = f"{YOSEMITE_CAMPGROUNDS[cg_id]['name']}: HTTP {status}"
            print(msg)
            errors.append(msg)
        except Exception as exc:
            msg = f"{YOSEMITE_CAMPGROUNDS[cg_id]['name']}: {exc}"
            print(msg)
            errors.append(msg)
        time.sleep(1.5)

    alert_key = "|".join(
        f"{cg_id}:{','.join(site['campsite_id'] for site in sites[:20])}"
        for cg_id, sites in sorted(available_map.items())
    )
    if available_map and alert_key != monitor.get("last_alert_key", ""):
        blocks = []
        for cg_id, sites in available_map.items():
            blocks.append(
                f"<a href='{yosemite_booking_url(cg_id, checkin, checkout)}'>{YOSEMITE_CAMPGROUNDS[cg_id]['name']}</a>\n"
                f"{format_sites(sites)}"
            )
        send_telegram(
            f"Yosemite Campsite Available!\n\n"
            f"{checkin.strftime('%b %d')} - {checkout.strftime('%b %d, %Y')}\n\n"
            f"Available:\n\n" + "\n\n".join(blocks) + "\n\nBook now!"
        )
        monitor["last_alert_key"] = alert_key
    elif not available_map and monitor.get("last_alert_key"):
        send_telegram("Previously found Yosemite spots are gone. Keeping watch.")
        monitor["last_alert_key"] = ""
    elif errors:
        print("Yosemite completed with non-fatal errors: " + "; ".join(errors))


def run_prairie_check(monitor: dict) -> None:
    checkin = dt.date.fromisoformat(monitor["checkin"])
    checkout = dt.date.fromisoformat(monitor["checkout"])
    result = check_prairie(checkin, checkout)
    print(f"{PRAIRIE['name']}: {result['label']}")
    alert_key = f"prairie:{monitor['checkin']}:{monitor['checkout']}:{result['available']}"
    if result["available"] and alert_key != monitor.get("last_alert_key", ""):
        send_telegram(
            f"Prairie Creek campsite available!\n\n"
            f"{PRAIRIE['name']}\n"
            f"{checkin.strftime('%b %d')} - {checkout.strftime('%b %d, %Y')}\n\n"
            f"<a href='{result['url']}'>Open ReserveCalifornia</a>"
        )
        monitor["last_alert_key"] = alert_key
    elif not result["available"] and monitor.get("last_alert_key"):
        send_telegram("Previously found Prairie Creek spot is gone. Keeping watch.")
        monitor["last_alert_key"] = ""


def run_checks(state: dict, force_checks: list[str]) -> None:
    for name in ("yosemite", "prairie"):
        monitor = state["monitors"][name]
        if not monitor.get("enabled") and name not in force_checks:
            print(f"{name} monitor is off")
            continue
        try:
            if name == "yosemite":
                run_yosemite_check(monitor)
            else:
                run_prairie_check(monitor)
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
