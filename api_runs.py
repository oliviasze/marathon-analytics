"""
api_runs.py — JSON output of paginated runs, for the GET /runs endpoint.

Reuses analyze.load_runs_df() (same distance_mi / avg_pace_sec_per_mi
conversion used everywhere else) so the API and the CLI scripts never
drift from each other on units.

Usage:
    python api_runs.py [page] [per_page]

Prints a single JSON object to stdout. Any error goes to stderr with a
non-zero exit code, so the Express layer can distinguish success/failure.
"""
import json
import sys

import pandas as pd

from analyze import load_runs_df


def serialize_run(r: pd.Series) -> dict:
    def clean(val):
        return None if pd.isna(val) else val

    return {
        "activity_id": r["activity_id"],
        "date": r["date"].strftime("%Y-%m-%d"),
        "distance_mi": round(r["distance_mi"], 2),
        "duration_sec": int(r["duration_sec"]) if pd.notna(r["duration_sec"]) else None,
        "avg_pace_sec_per_mi": (
            round(r["avg_pace_sec_per_mi"], 1) if pd.notna(r["avg_pace_sec_per_mi"]) else None
        ),
        "avg_hr": int(r["avg_hr"]) if pd.notna(r["avg_hr"]) else None,
        "max_hr": int(r["max_hr"]) if pd.notna(r["max_hr"]) else None,
        "elevation_gain_m": clean(r["elevation_gain_m"]),
        "cadence_avg": clean(r["cadence_avg"]),
        "training_load": clean(r["training_load"]),
        "resting_hr_that_day": (
            int(r["resting_hr_that_day"]) if pd.notna(r["resting_hr_that_day"]) else None
        ),
        "sleep_hours_prior_night": clean(r["sleep_hours_prior_night"]),
        "perceived_type": clean(r["perceived_type"]),
    }


def main():
    page = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    per_page = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    df = load_runs_df()
    df = df.sort_values("date", ascending=False).reset_index(drop=True)

    total = len(df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = df.iloc[start:end]

    payload = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "runs": [serialize_run(r) for _, r in page_df.iterrows()],
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
