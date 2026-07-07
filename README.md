# Campsite Monitor

Headless campsite availability monitor for GitHub Actions.

The workflow checks Telegram commands and sends Telegram alerts when matching
campsites are available. Each campsite is managed as its own monitor. Date
ranges are checked one night at a time, so a range alerts when at least one
one-night stay inside that range is available. GitHub Actions schedules the
workflow every five minutes, and the existing external dispatch can also wake
the workflow. Each active run checks every 15 seconds while it is active.

## Monitor Names

- `upper_yosemite`
- `north_yosemite`
- `lower_yosemite`

Telegram commands also accept the same names with spaces:

- `upper yosemite`
- `north yosemite`
- `lower yosemite`

## GitHub Secrets

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `GERONIMO_TELEGRAM_CHAT_ID`
- `SOPHIA_TELEGRAM_BOT_TOKEN`
- `SOPHIA_TELEGRAM_CHAT_ID`

`TELEGRAM_CHAT_ID` is still supported as the legacy fallback for Geronimo's
conversation. `TELEGRAM_BOT_TOKEN` is still supported as the legacy fallback
for Geronimo's bot token. Prefer named user secrets for new configuration so
additional Telegram conversations can be added cleanly.

Optional, for self-dispatching the next monitoring run when a scheduled run
finishes:

- `CAMPSITE_GH_WORKFLOW_PAT`
- `GH_WORKFLOW_PAT`

Do not commit these values to the repository.

## Telegram Users

The current Telegram conversation is linked to the named user `geronimo`.
Sophia's conversation is linked to the named user `sophia` and bot username
`Yosemite_sofiag_bot`. Commands are accepted only from configured user chat IDs.
Availability alerts are sent to every configured user conversation.

## Telegram Commands

Send commands to your bot:

- `/status` - show current settings
- `/help` - show all commands with usage examples
- `/commands` - same as `/help`
- `/monitors` - list available Yosemite campsite monitor names
- `/start all` - turn every Yosemite campsite on and run checks
- `/start upper yosemite` - turn one campsite on
- `/stop upper yosemite` - turn one campsite off
- `/check all` - run one check for every Yosemite campsite on the next workflow run
- `/check upper yosemite` - run one campsite check
- `/dates upper yosemite 2026-05-22 2026-05-26` - set dates for one campsite

Date ranges are scanned as one-night stays. For example,
`/dates upper yosemite 2026-05-22 2026-05-26` checks May 22-23, May 23-24,
May 24-25, and May 25-26 independently.

Old campground grouping commands such as `/campgrounds yosemite ...` are no
longer used. Use the individual monitor names above instead.

## Campsites

Recreation.gov:

- `upper_yosemite` - `232447` - Upper Pines Campground
- `north_yosemite` - `232449` - North Pines Campground
- `lower_yosemite` - `232450` - Lower Pines Campground

## Trigger

The recurring GitHub trigger is GitHub Actions schedule:

```text
*/5 * * * *
```

GitHub scheduled workflows use a five-minute cron because that is GitHub
Actions' shortest supported schedule interval. Each scheduled run performs 20
monitoring cycles with a target 15-second start-to-start cadence.

The workflow also accepts the existing `repository_dispatch` event from the
external dispatcher. Those dispatch runs perform 8 monitoring cycles with the
same 15-second target cadence, matching the dispatcher's roughly two-minute
wake-up interval. If a check takes longer than 15 seconds, the next cycle starts
after the current check finishes instead of overlapping it.

The workflow also keeps `workflow_dispatch` so you can manually test it from the
GitHub Actions tab. The workflow can self-dispatch the next run with
`continue_monitoring=true` when `CAMPSITE_GH_WORKFLOW_PAT` or `GH_WORKFLOW_PAT`
is configured.

## Notes

This monitor uses public availability pages/APIs and the Telegram Bot API. It
does not log in to booking sites, open a browser, or add campsites to a cart.
