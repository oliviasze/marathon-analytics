"""
api_health.py — JSON output of pipeline/data status, for GET /health.

Lets the dashboard show a clean "not enough data yet" state instead of
just surfacing a raw error string from /prediction. Reports:

- total runs synced, and date range
- how many are "quality effort" runs (model.py's heuristic) with
  complete 28-day trailing windows — i.e. usable as regression rows
- whether that count clears the 20-run threshold model.py requires
- how stale the local DB is relative to today (days since last sync)

Usage:
    python api_health.py

Prints a single JSON object to stdout. Exits 0 even if the DB is empty
or the model isn't ready yet — those are valid states, not failures.
"""
import json
from datetime import datetime, timezone

from analyze import load_runs_df
from model import add_features, add_implied_marathon_time, build_model_dataset, flag_quality_efforts

MODEL_MIN_RUNS = 20


def main():
    try:
        df = load_runs_df()
    except SystemExit:
        # load_runs_df() raises SystemExit if the runs table is empty
        print(json.dumps({
            "status": "empty",
            "total_runs": 0,
            "message": "No runs found — run sync_garmin.py first.",
        }))
        return

    total_runs = len(df)
    last_run_date = df["date"].max()
    days_since_last_sync = (
        datetime.now(timezone.utc).replace(tzinfo=None) - last_run_date
    ).days

    df = add_implied_marathon_time(df)
    df = add_features(df)
    df = flag_quality_efforts(df)
    model_df = build_model_dataset(df)
    model_ready_runs = len(model_df)
    model_ready = model_ready_runs >= MODEL_MIN_RUNS

    payload = {
        "status": "ok",
        "total_runs": total_runs,
        "date_range": {
            "first": df["date"].min().strftime("%Y-%m-%d"),
            "last": last_run_date.strftime("%Y-%m-%d"),
        },
        "days_since_last_sync": days_since_last_sync,
        "regression_model": {
            "ready": model_ready,
            "usable_runs": model_ready_runs,
            "min_runs_required": MODEL_MIN_RUNS,
            "runs_still_needed": max(0, MODEL_MIN_RUNS - model_ready_runs),
        },
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
