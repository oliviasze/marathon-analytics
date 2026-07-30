"""
sync_garmin.py — Incremental sync of running activities from Garmin Connect
into the local training.db SQLite database.

Run this after each run (or nightly via cron) between now and race day.
It only fetches activities newer than the latest one already stored,
so it's cheap and safe to run as often as you like.

Setup:
    pip install garminconnect python-dotenv
    cp .env.example .env   # then fill in your Garmin credentials

Usage:
    python sync_garmin.py
    python sync_garmin.py --since 2026-04-27   # one-time backfill from a specific date
    python sync_garmin.py --full               # re-check the last 90 days regardless of what's stored
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, date

from dotenv import load_dotenv

import db

try:
    from garminconnect import Garmin
except ImportError:
    print("Missing dependency. Run: pip install garminconnect python-dotenv")
    sys.exit(1)


DEFAULT_BACKFILL_DAYS = 90


def login() -> Garmin:
    load_dotenv()
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        print("Set GARMIN_EMAIL and GARMIN_PASSWORD in a .env file (see .env.example).")
        sys.exit(1)

    api = Garmin(email, password)
    api.login()
    return api


def to_iso_date(start_time_local: str) -> str:
    # Garmin returns e.g. "2026-07-15 06:32:10"
    return start_time_local.split(" ")[0]


def safe_round(value, digits=2):
    return round(value, digits) if isinstance(value, (int, float)) else None


def parse_activity(activity: dict) -> dict:
    distance_m = activity.get("distance") or 0
    duration_sec = activity.get("duration") or 0
    distance_km = distance_m / 1000 if distance_m else None
    avg_pace_sec_per_km = (
        duration_sec / distance_km if distance_km and duration_sec else None
    )

    return {
        "activity_id": str(activity.get("activityId")),
        "date": to_iso_date(activity.get("startTimeLocal", "")),
        "distance_km": safe_round(distance_km, 3),
        "duration_sec": int(duration_sec) if duration_sec else None,
        "avg_pace_sec_per_km": safe_round(avg_pace_sec_per_km, 1),
        "avg_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "elevation_gain_m": safe_round(activity.get("elevationGain")),
        "cadence_avg": safe_round(activity.get("averageRunningCadenceInStepsPerMinute")),
        "training_load": safe_round(activity.get("activityTrainingLoad")),
        "resting_hr_that_day": None,   # filled in by enrich_with_wellness
        "sleep_hours_prior_night": None,  # filled in by enrich_with_wellness
        "perceived_type": None,        # tag manually later if you want
    }


def enrich_with_wellness(api: Garmin, record: dict) -> dict:
    """Best-effort: adds resting HR and prior-night sleep for the run's date.
    Wellness data isn't always available for every day, so failures here
    are non-fatal — the run still gets stored without it."""
    date_str = record["date"]
    try:
        rhr_data = api.get_rhr_day(date_str)
        record["resting_hr_that_day"] = (
            rhr_data.get("allMetrics", {})
            .get("metricsMap", {})
            .get("WELLNESS_RESTING_HEART_RATE", [{}])[0]
            .get("value")
        )
    except Exception:
        pass

    try:
        sleep_data = api.get_sleep_data(date_str)
        sleep_seconds = (sleep_data.get("dailySleepDTO") or {}).get("sleepTimeSeconds")
        if sleep_seconds:
            record["sleep_hours_prior_night"] = safe_round(sleep_seconds / 3600, 2)
    except Exception:
        pass

    return record


def fetch_new_activities(api: Garmin, start_date: str, since_date: str | None) -> list[dict]:
    """Pulls all running activities between start_date and today, then filters
    to only those strictly newer than since_date (avoids re-inserting the
    boundary run on ordinary incremental syncs). If since_date is None,
    every activity in the range is returned (used for backfills)."""
    end = date.today().isoformat()
    activities = api.get_activities_by_date(start_date, end, activitytype="running")

    new_records = []
    for activity in activities:
        activity_date = to_iso_date(activity.get("startTimeLocal", ""))
        if since_date and activity_date < since_date:
            # shouldn't normally happen since start_date == since_date,
            # but guards against unexpected results outside the range
            continue
        new_records.append(parse_activity(activity))

    return new_records


def main():
    parser = argparse.ArgumentParser(description="Sync Garmin runs into training.db")
    parser.add_argument("--full", action="store_true",
                         help=f"Re-scan the last {DEFAULT_BACKFILL_DAYS} days regardless of what's already stored")
    parser.add_argument("--since", type=str, default=None,
                         help="One-time backfill: fetch all runs from this date (YYYY-MM-DD) through today")
    args = parser.parse_args()

    db.init_db()
    conn = db.get_connection()

    last_synced = db.get_last_synced_date(conn)

    if args.since:
        start_date = args.since
        since_date = None  # backfill: don't filter, we want everything in range
        print(f"Backfilling from {start_date} through today...")
    elif args.full:
        start_date = (datetime.now() - timedelta(days=DEFAULT_BACKFILL_DAYS)).strftime("%Y-%m-%d")
        since_date = None
        print(f"Full re-scan: last {DEFAULT_BACKFILL_DAYS} days...")
    elif last_synced:
        start_date = last_synced
        since_date = last_synced
        print(f"Last synced run: {last_synced}. Fetching anything newer...")
    else:
        start_date = (datetime.now() - timedelta(days=DEFAULT_BACKFILL_DAYS)).strftime("%Y-%m-%d")
        since_date = None
        print("No prior sync found. Fetching recent history...")

    api = login()
    new_records = fetch_new_activities(api, start_date, since_date)

    if not new_records:
        print("No new runs found. You're up to date.")
        conn.close()
        return

    inserted = 0
    for record in new_records:
        record = enrich_with_wellness(api, record)
        if db.insert_run(conn, record):
            inserted += 1
            print(f"  + {record['date']}: {record['distance_km']} km "
                  f"in {record['duration_sec']}s (avg HR {record['avg_hr']})")

    conn.commit()
    conn.close()
    print(f"\nDone. {inserted} new run(s) added to training.db.")


if __name__ == "__main__":
    main()