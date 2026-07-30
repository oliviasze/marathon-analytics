# Garmin Marathon Training Sync (Phase 0-1)

Incremental sync of your Garmin running data into a local SQLite database,
so you can keep it updated every few days between now and race day without
rebuilding anything.

## Setup

```bash
cd garmin_sync
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in your Garmin Connect email + password
```

## Usage

Run this after a run, or every few days:

```bash
python sync_garmin.py
```

First run pulls your recent running activities and stores them in
`training.db`. Every run after that only fetches activities newer than
the latest one already stored — so it's cheap and safe to run often.

Options:

```bash
python sync_garmin.py --full          # rescan recent history regardless of what's stored
python sync_garmin.py --limit 50      # scan more activities per run (default: 20)
```

## Automate it (optional)

To sync automatically every night, add a cron job:

```bash
crontab -e
# add this line (adjust paths):
0 21 * * * cd /path/to/garmin_sync && /usr/bin/python3 sync_garmin.py >> sync.log 2>&1
```

## What gets stored

Each run is saved to the `runs` table in `training.db`: date, distance,
duration, pace, heart rate (avg/max), elevation gain, cadence, training
load, and — best-effort — resting HR and sleep hours for that day.

See `db.py` for the full schema.

## Notes

- Uses the unofficial `garminconnect` library — this is for **personal use
  only** (your own account), not for redistribution or a multi-user product.
- Credentials live in `.env`, which is git-ignored. Never commit it.
- `training.db` is also git-ignored by default — your training data is
  personal, so keep it out of a public repo unless you want it there.

## Next steps (Phase 2+)

- Exploratory analysis + Riegel formula baseline
- Regression model to predict marathon finish time
- Node/Express API layer + React dashboard

See the full project plan doc for the week-by-week breakdown.
