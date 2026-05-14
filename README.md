# Yosemite Monitor

Headless Recreation.gov availability monitor for GitHub Actions.

The workflow runs every 5 minutes, checks Telegram commands, and sends Telegram
alerts when matching Yosemite campsites are available.

## GitHub Secrets

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not commit these values to the repository.

## Telegram Commands

Send commands to your bot:

- `/start` - turn monitoring on and run a check
- `/stop` - turn monitoring off
- `/status` - show current settings
- `/check` - run one check on the next workflow run
- `/dates 2026-09-01 2026-09-03` - set check-in/check-out dates
- `/campgrounds all` - watch all configured campgrounds
- `/campgrounds wawona lower north upper` - choose specific campgrounds

The monitor watches these Recreation.gov campground IDs:

- `232450` - Lower Pines Campground
- `232449` - North Pines Campground
- `232447` - Upper Pines Campground
- `232446` - Wawona Campground

## Notes

GitHub Actions scheduled workflows can run as often as every 5 minutes, but
GitHub may delay scheduled jobs during busy periods. This monitor uses only the
public availability API and Telegram Bot API. It does not log in to
Recreation.gov, open a browser, or add campsites to a cart.
