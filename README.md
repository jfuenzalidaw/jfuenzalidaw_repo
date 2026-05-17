# Yosemite Monitor

Headless campsite availability monitor for GitHub Actions.

The workflow is triggered by cron-job.org, checks Telegram commands, and sends
Telegram alerts when matching campsites are available.

It currently supports:

- `yosemite` - Recreation.gov Yosemite campgrounds
- `prairie` - Prairie Creek Redwoods SP Elk Prairie Campground on ReserveCalifornia

## GitHub Secrets

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not commit these values to the repository.

## Telegram Commands

Send commands to your bot:

- `/start all` - turn both monitors on and run checks
- `/start yosemite` - turn Yosemite monitoring on
- `/start prairie` - turn Prairie Creek monitoring on
- `/stop all` - turn both monitors off
- `/stop yosemite` - turn Yosemite monitoring off
- `/stop prairie` - turn Prairie Creek monitoring off
- `/status` - show current settings
- `/check all` - run one check for both monitors on the next workflow run
- `/check yosemite` - run one Yosemite check
- `/check prairie` - run one Prairie Creek check
- `/dates yosemite 2026-09-01 2026-09-03` - set Yosemite dates
- `/dates prairie 2026-05-24 2026-05-26` - set Prairie Creek dates
- `/campgrounds yosemite all` - watch all configured Yosemite campgrounds
- `/campgrounds yosemite list` - show all Yosemite campground options
- `/campgrounds yosemite lower north upper` - choose specific Yosemite campgrounds
- `/scheduler external` - use cron-job.org repository dispatch trigger
- `/scheduler github` - use GitHub Actions' free 5-minute schedule
- `/settings scheduler external` - same as `/scheduler external`
- `/settings scheduler github` - same as `/scheduler github`

The Yosemite monitor watches these Recreation.gov campground IDs:

- `232450` - Lower Pines Campground
- `232449` - North Pines Campground
- `232447` - Upper Pines Campground

The Prairie Creek monitor uses:

- California State Parks availability page id `415`
- ReserveCalifornia park URL `https://reservecalifornia.com/park/696`

## Notes

GitHub Actions scheduled workflows can run as often as every 5 minutes, but
GitHub may delay scheduled jobs during busy periods. This repo also supports a
`repository_dispatch` trigger so cron-job.org can run it on a reliable external
schedule. Use `/scheduler external` or `/scheduler github` in Telegram to choose
which trigger should perform real checks. This monitor uses public availability
pages/APIs and the Telegram Bot API. It does not log in to booking sites, open a
browser, or add campsites to a cart.

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
