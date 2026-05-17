# Campsite Monitor

Headless campsite availability monitor for GitHub Actions.

The workflow checks Telegram commands and sends Telegram alerts when matching
campsites are available. Each campsite is managed as its own monitor.

## Monitor Names

- `upper_yosemite`
- `north_yosemite`
- `lower_yosemite`
- `north_summit_lassen`
- `south_summit_lassen`
- `prairie_redwoods`
- `gold_bluffs_redwoods`

Telegram commands also accept the same names with spaces:

- `upper yosemite`
- `north yosemite`
- `lower yosemite`
- `north summit lassen`
- `south summit lassen`
- `prairie redwoods`
- `gold bluffs redwoods`

## GitHub Secrets

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `CRON_JOB_ORG_API_KEY` - required for `/scheduler github` to pause cron-job.org and `/scheduler external` to re-enable it

Do not commit these values to the repository.

## Telegram Commands

Send commands to your bot:

- `/status` - show current settings
- `/help` - show all commands with usage examples
- `/commands` - same as `/help`
- `/monitors` - list all campsite monitor names
- `/start all` - turn every campsite on and run checks
- `/start upper yosemite` - turn one campsite on
- `/stop upper yosemite` - turn one campsite off
- `/check all` - run one check for every campsite on the next workflow run
- `/check upper yosemite` - run one campsite check
- `/dates upper yosemite 2026-05-22 2026-05-26` - set dates for one campsite
- `/scheduler external` - use cron-job.org repository dispatch trigger
- `/scheduler github` - use GitHub Actions' free 5-minute schedule
- `/settings scheduler external` - same as `/scheduler external`
- `/settings scheduler github` - same as `/scheduler github`

Old campground grouping commands such as `/campgrounds yosemite ...` are no
longer used. Use the individual monitor names above instead.

## Campsites

Recreation.gov:

- `upper_yosemite` - `232447` - Upper Pines Campground
- `north_yosemite` - `232449` - North Pines Campground
- `lower_yosemite` - `232450` - Lower Pines Campground
- `north_summit_lassen` - `234041` - Summit Lake North Campground
- `south_summit_lassen` - `234040` - Summit Lake South Campground

ReserveCalifornia:

- `prairie_redwoods` - `https://reservecalifornia.com/park/696`
- `gold_bluffs_redwoods` - `https://reservecalifornia.com/park/697`

## Notes

GitHub Actions scheduled workflows can run as often as every 5 minutes, but
GitHub may delay scheduled jobs during busy periods. This repo also supports a
`repository_dispatch` trigger so cron-job.org can run it on a reliable external
schedule. Use `/scheduler external` or `/scheduler github` in Telegram to choose
which trigger should perform real checks.

This monitor uses public availability pages/APIs and the Telegram Bot API. It
does not log in to booking sites, open a browser, or add campsites to a cart.
