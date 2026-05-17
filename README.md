# Yosemite Monitor

Headless campsite availability monitor for GitHub Actions.

The workflow is triggered by cron-job.org, checks Telegram commands, and sends
Telegram alerts when matching campsites are available.

It currently supports:

- `yosemite` - Recreation.gov Yosemite campgrounds
- `prairie` - Prairie Creek Redwoods SP Elk Prairie Campground on ReserveCalifornia
- `gold` / `gold_bluffs` - Prairie Creek Redwoods SP Gold Bluffs Beach Camp on ReserveCalifornia

## GitHub Secrets

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `CRON_JOB_ORG_API_KEY` - optional, required for `/scheduler github` to pause cron-job.org and `/scheduler external` to re-enable it

Do not commit these values to the repository.

## Telegram Commands

Send commands to your bot:

- `/start all` - turn all monitors on and run checks
- `/start yosemite` - turn Yosemite monitoring on
- `/start prairie` - turn Elk Prairie monitoring on
- `/start gold` - turn Gold Bluffs Beach monitoring on
- `/stop all` - turn all monitors off
- `/stop yosemite` - turn Yosemite monitoring off
- `/stop prairie` - turn Elk Prairie monitoring off
- `/stop gold` - turn Gold Bluffs Beach monitoring off
- `/status` - show current settings
- `/help` - show all commands with usage examples
- `/commands` - same as `/help`
- `/check all` - run one check for every monitor on the next workflow run
- `/check yosemite` - run one Yosemite check
- `/check prairie` - run one Elk Prairie check
- `/check gold` - run one Gold Bluffs Beach check
- `/dates yosemite 2026-09-01 2026-09-03` - set Yosemite dates
- `/dates prairie 2026-05-24 2026-05-26` - set Prairie Creek dates
- `/dates gold 2026-05-23 2026-05-25` - set Gold Bluffs Beach dates
- `/campgrounds yosemite all` - watch all configured Recreation.gov campgrounds
- `/campgrounds yosemite list` - show all Recreation.gov campground options
- `/campgrounds yosemite lower north upper summitnorth summitsouth` - choose specific Recreation.gov campgrounds
- `/scheduler external` - use cron-job.org repository dispatch trigger
- `/scheduler github` - use GitHub Actions' free 5-minute schedule
- `/settings scheduler external` - same as `/scheduler external`
- `/settings scheduler github` - same as `/scheduler github`

The Recreation.gov monitor watches these campground IDs:

- `232450` - Lower Pines Campground
- `232449` - North Pines Campground
- `232447` - Upper Pines Campground
- `234041` - Summit Lake North Campground
- `234040` - Summit Lake South Campground

The ReserveCalifornia monitors use:

- California State Parks availability page id `415`
- Elk Prairie ReserveCalifornia park URL `https://reservecalifornia.com/park/696`
- Gold Bluffs Beach ReserveCalifornia park URL `https://reservecalifornia.com/park/697`

## Notes

GitHub Actions scheduled workflows can run as often as every 5 minutes, but
GitHub may delay scheduled jobs during busy periods. This repo also supports a
`repository_dispatch` trigger so cron-job.org can run it on a reliable external
schedule. Use `/scheduler external` or `/scheduler github` in Telegram to choose
which trigger should perform real checks. This monitor uses public availability
pages/APIs and the Telegram Bot API. It does not log in to booking sites, open a
browser, or add campsites to a cart.

If `CRON_JOB_ORG_API_KEY` is configured, `/scheduler github` also pauses the
cron-job.org job and `/scheduler external` enables it again. The workflow passes
the cron-job.org job id `7604120` as `CRON_JOB_ORG_JOB_ID`.

## Reliable External Trigger

If GitHub's native `schedule` trigger does not fire reliably, use any free cron
service to call GitHub's dispatch API every 5 minutes.

Request:

```text
POST https://api.github.com/repos/jfuenzalidaw/jfuenzalidaw_repo/dispatches
```

Headers:

```text
Accept: application/vnd.github+json
Authorization: Bearer YOUR_FINE_GRAINED_GITHUB_TOKEN
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

Body:

```json
{"event_type":"yosemite-monitor"}
```

Create the token with access only to this repository and permission:

- Contents: read-only
- Actions: read/write
