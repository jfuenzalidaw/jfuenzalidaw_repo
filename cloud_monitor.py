import datetime as dt
import json
import os
import time
from pathlib import Path

import requests


CAMPGROUNDS = {
    "232450": {"name": "Lower Pines Campground", "url": "https://www.recreation.gov/camping/campgrounds/232450"},
    "232449": {"name": "North Pines Campground", "url": "https://www.recreation.gov/camping/campgrounds/232449"},
    "232447": {"name": "Upper Pines Campground", "url": "https://www.recreation.gov/camping/campgrounds/232447"},
    "232446": {"name": "Wawona Campground", "url": "https://www.recreation.gov/camping/campgrounds/232446"},
}

ALIASES = {
    "lower": "232450",
    "lowerpines": "232450",
    "north": "232449",
    "northpines": "232449",
    "upper": "232447",
    "upperpines": "232447",
    "wawona": "232446",
}

AVAIL_API = "https://www.recreation.gov/api/camps/availability/campground/{id}/month"
STATE_PATH = Path(".monitor_state.json")


def default_state() -> dict:
    today = dt.date.today()
    return {
        "enabled": False,
        "checkin": (today + dt.timedelta(days=1)).isoformat(),
        "checkout": (today + dt.timedelta(days=4)).isoformat(),
        "campgrounds": list(CAMPGROUNDS.keys()),
        "last_update_id": 0,
        "last_alert_key": "",
    }


def load_state() -> dict:
    if STATE_PATH.exists():
        state = default_state()
        state.update(json.loads(STATE_PATH.read_text(encoding="utf-8")))
        return state
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


def base_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.recreation.gov/",
        "Origin": "https://www.recreation.gov",
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


def check_campground(cg_id: str, checkin: dt.date, checkout: dt.date) -> list[dict]:
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


def booking_url(cg_id: str, checkin: dt.date, checkout: dt.date) -> str:
    ci = checkin.strftime("%m%%2F%d%%2F%Y")
    co = checkout.strftime("%m%%2F%d%%2F%Y")
    return f"{CAMPGROUNDS[cg_id]['url']}?checkin={ci}&checkout={co}"


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


def normalize_campgrounds(text: str) -> list[str] | None:
    raw = text.strip().lower()
    if raw == "all":
        return list(CAMPGROUNDS.keys())
    selected = []
    for part in raw.replace(",", " ").split():
        key = part.replace("-", "").replace("_", "").replace(" ", "")
        cg_id = part if part in CAMPGROUNDS else ALIASES.get(key)
        if not cg_id:
            return None
        if cg_id not in selected:
            selected.append(cg_id)
    return selected


def status_text(state: dict) -> str:
    watched = "\n".join(f"- {CAMPGROUNDS[cg_id]['name']}" for cg_id in state["campgrounds"])
    mode = "ON" if state["enabled"] else "OFF"
    return (
        f"Yosemite monitor: {mode}\n\n"
        f"Dates: {state['checkin']} to {state['checkout']}\n\n"
        f"Watching:\n{watched}\n\n"
        "Commands: /start, /stop, /status, /check, "
        "/dates YYYY-MM-DD YYYY-MM-DD, /campgrounds all|wawona|lower|north|upper"
    )


def process_commands(state: dict) -> bool:
    force_check = False
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
            state["enabled"] = True
            send_telegram("Yosemite monitor is ON.\n\n" + status_text(state))
            force_check = True
        elif command in {"/stop", "/off"}:
            state["enabled"] = False
            send_telegram("Yosemite monitor is OFF.")
        elif command == "/check":
            force_check = True
            send_telegram("Running an availability check now.")
        elif command == "/dates":
            try:
                ci_s, co_s = rest.split()[:2]
                checkin = dt.date.fromisoformat(ci_s)
                checkout = dt.date.fromisoformat(co_s)
                if checkout <= checkin:
                    raise ValueError("checkout must be after checkin")
                state["checkin"] = checkin.isoformat()
                state["checkout"] = checkout.isoformat()
                state["last_alert_key"] = ""
                send_telegram(f"Dates updated: {state['checkin']} to {state['checkout']}")
                force_check = True
            except Exception:
                send_telegram("Usage: /dates YYYY-MM-DD YYYY-MM-DD")
        elif command == "/campgrounds":
            selected = normalize_campgrounds(rest)
            if not selected:
                send_telegram("Usage: /campgrounds all OR /campgrounds wawona lower north upper")
            else:
                state["campgrounds"] = selected
                state["last_alert_key"] = ""
                send_telegram("Campgrounds updated.\n\n" + status_text(state))
                force_check = True
        else:
            send_telegram("Unknown command.\n\n" + status_text(state))
    return force_check


def run_check(state: dict) -> None:
    checkin = dt.date.fromisoformat(state["checkin"])
    checkout = dt.date.fromisoformat(state["checkout"])
    available_map = {}
    errors = []
    for cg_id in state["campgrounds"]:
        try:
            sites = check_campground(cg_id, checkin, checkout)
            print(f"{CAMPGROUNDS[cg_id]['name']}: {len(sites)} available")
            if sites:
                available_map[cg_id] = sites
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            msg = f"{CAMPGROUNDS[cg_id]['name']}: HTTP {status}"
            print(msg)
            errors.append(msg)
        except Exception as exc:
            msg = f"{CAMPGROUNDS[cg_id]['name']}: {exc}"
            print(msg)
            errors.append(msg)
        time.sleep(1.5)

    alert_key = "|".join(
        f"{cg_id}:{','.join(site['campsite_id'] for site in sites[:20])}"
        for cg_id, sites in sorted(available_map.items())
    )
    if available_map and alert_key != state.get("last_alert_key", ""):
        blocks = []
        for cg_id, sites in available_map.items():
            blocks.append(
                f"<a href='{booking_url(cg_id, checkin, checkout)}'>{CAMPGROUNDS[cg_id]['name']}</a>\n"
                f"{format_sites(sites)}"
            )
        send_telegram(
            f"Yosemite Campsite Available!\n\n"
            f"{checkin.strftime('%b %d')} - {checkout.strftime('%b %d, %Y')}\n\n"
            f"Available:\n\n" + "\n\n".join(blocks) + "\n\nBook now!"
        )
        state["last_alert_key"] = alert_key
    elif not available_map and state.get("last_alert_key"):
        send_telegram("Previously found Yosemite spots are gone. Keeping watch.")
        state["last_alert_key"] = ""
    elif errors:
        print("Completed with non-fatal errors: " + "; ".join(errors))


def main():
    state = load_state()
    force_check = process_commands(state)
    if state.get("enabled") or force_check:
        run_check(state)
    else:
        print("Monitor is off. Send /start to Telegram to enable it.")
    save_state(state)


if __name__ == "__main__":
    main()
