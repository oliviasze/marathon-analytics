"""
api_trends.py — JSON output of the rolling 14-day efficiency trend, for
the GET /trends/efficiency endpoint.

Reuses trend_analysis.get_rolling_efficiency_trend() (the same SQL window
function that feeds the Tableau CSV export) so the API and that script
stay in sync.

Usage:
    python api_trends.py

Prints a single JSON object to stdout.
"""
import json

import db
from trend_analysis import get_rolling_efficiency_trend


def main():
    conn = db.get_connection()
    trend_df = get_rolling_efficiency_trend(conn)
    conn.close()

    # Drop rows before the rolling window has enough runs to be meaningful
    trend_df = trend_df.dropna(subset=["rolling_14d_efficiency"])

    points = [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "distance_mi": round(row["distance_km"] * 0.621371, 2),
            "efficiency": round(row["efficiency"], 3),
            "rolling_14d_efficiency": round(row["rolling_14d_efficiency"], 3),
        }
        for _, row in trend_df.iterrows()
    ]

    payload = {
        "unit": "sec/mi/bpm (lower = more efficient)",
        "window_runs": 14,
        "points": points,
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
