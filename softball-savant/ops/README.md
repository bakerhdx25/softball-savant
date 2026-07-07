# Softball Savant daily official-data update

The update job uses only public AUSL data:

- `https://theausl.com/data/scheduleApiData_<seasonId>.json`
- `https://theausl.com/game/<gameId>/`
- `https://theausl.com/data/statsApiData_<seasonId>.json`
- `https://theausl.com/data/franchiseStatsApiData_<seasonId>.json`

Run once manually:

```sh
/Users/openclaw/ausl/softball-savant/bin/update-official-public.sh
```

Install the daily devbox job:

```sh
mkdir -p /Users/openclaw/ausl/softball-savant/logs
cp /Users/openclaw/ausl/softball-savant/ops/com.openclaw.softball-savant-update.plist \
  /Users/openclaw/Library/LaunchAgents/com.openclaw.softball-savant-update.plist
launchctl bootstrap "gui/$(id -u)" /Users/openclaw/Library/LaunchAgents/com.openclaw.softball-savant-update.plist
launchctl enable "gui/$(id -u)/com.openclaw.softball-savant-update"
launchctl kickstart -k "gui/$(id -u)/com.openclaw.softball-savant-update"
```

Deploy to Netlify from the local daily job by setting `NETLIFY_AUTH_TOKEN` and
`NETLIFY_SITE_ID` in the job environment. Without those values, the job still
fetches public AUSL data, rebuilds WAR/TTO/site files, and runs tests, but skips
deployment.

For the public site, the preferred production architecture is GitHub Actions plus
GitHub Pages:

- Netlify deploys the static frontend only when code changes.
- `.github/workflows/update-data-feed.yml` rebuilds the official AUSL data every
  day and publishes JSON to GitHub Pages.
- `softball-savant/app.js` fetches the GitHub Pages data feed at runtime, then
  falls back to local `data/site-data.json` for development.
