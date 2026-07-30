"""
trend_analysis.py — Phase 3 (revised): fitness trend since the Feb 1 half
marathon, used to project marathon potential.

Rather than extrapolating from individual training runs via Riegel (fragile —
depends heavily on which runs count as "race effort"), this anchors to an
actual known result:

    Half marathon, Feb 1 2026: 1:34:49

We compute a training "efficiency" metric (pace per heartbeat — lower is
better) around that date and compare it to your current efficiency. The
resulting % change scales your actual half time, and ONLY THEN does Riegel
convert that adjusted half time to marathon distance — so Riegel is doing
pure distance conversion, not also trying to capture a fitness change.

Two parts:
    1. SQL (window function) — rolling 14-day efficiency trend across all
       runs. Exported to CSV for Tableau.
    2. Pandas — baseline-vs-current comparison and the forward projection.

Usage:
    python trend_analysis.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

import db
from analyze import riegel_prediction, format_hms, format_pace, MARATHON

HALF_MARATHON_DATE = "2026-02-01"
HALF_MARATHON_FINISH_SEC = 1 * 3600 + 34 * 60 + 49  # 1:34:49
HALF_MARATHON_DIST_MI = 13.1

WINDOW_DAYS = 14  # +/- window used for baseline and current efficiency
OUTPUT_DIR = Path("output")


# ---------------------------------------------------------------------------
# Part 1: SQL — rolling efficiency trend (window function), for Tableau
# ---------------------------------------------------------------------------

ROLLING_EFFICIENCY_SQL = """
    SELECT
        date,
        distance_km,
        duration_sec,
        avg_hr,
        (duration_sec / (distance_km * 0.621371)) / avg_hr AS efficiency,
        AVG(
            (duration_sec / (distance_km * 0.621371)) / avg_hr
        ) OVER (
            ORDER BY date
            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
        ) AS rolling_14d_efficiency
    FROM runs
    WHERE avg_hr IS NOT NULL
      AND distance_km IS NOT NULL
      AND duration_sec IS NOT NULL
    ORDER BY date;
"""


def get_rolling_efficiency_trend(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    efficiency = pace (sec/mi) / avg_hr — a rough proxy for how much speed
    you're getting per heartbeat. Lower = more efficient = fitter.
    Uses SQLite's window function support (AVG() OVER ...) to compute a
    trailing 14-run rolling average directly in SQL.
    """
    return pd.read_sql_query(ROLLING_EFFICIENCY_SQL, conn, parse_dates=["date"])


def export_trend_for_tableau(trend_df: pd.DataFrame) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "efficiency_trend.csv"
    trend_df.to_csv(out_path, index=False)
    return out_path


# ---------------------------------------------------------------------------
# Part 2: pandas — baseline (around half marathon) vs. current comparison
# ---------------------------------------------------------------------------

def windowed_avg_efficiency(trend_df: pd.DataFrame, center_date: str, window_days: int) -> float:
    """Average raw (non-rolling) efficiency in a window centered on center_date."""
    center = pd.Timestamp(center_date)
    start = center - pd.Timedelta(days=window_days)
    end = center + pd.Timedelta(days=window_days)
    window = trend_df[(trend_df["date"] >= start) & (trend_df["date"] <= end)]
    return window["efficiency"].mean(), len(window)


def current_avg_efficiency(trend_df: pd.DataFrame, window_days: int) -> float:
    """Average raw efficiency over the most recent window_days of data."""
    most_recent_date = trend_df["date"].max()
    start = most_recent_date - pd.Timedelta(days=window_days)
    window = trend_df[trend_df["date"] >= start]
    return window["efficiency"].mean(), len(window), most_recent_date


def project_marathon_from_half(baseline_efficiency: float, current_efficiency: float) -> dict:
    """
    Scales the actual half marathon time by the ratio of efficiency change,
    then Riegel-extrapolates the ADJUSTED half time to marathon distance.

    Lower efficiency value = better (faster pace per heartbeat), so an
    improvement means current_efficiency < baseline_efficiency, and the
    scaling factor (current / baseline) will be < 1 — i.e. it shrinks the
    projected half time to reflect the fitness gain.
    """
    efficiency_ratio = current_efficiency / baseline_efficiency
    pct_change = (efficiency_ratio - 1) * 100  # negative = improvement

    adjusted_half_sec = HALF_MARATHON_FINISH_SEC * efficiency_ratio
    projected_marathon_sec = riegel_prediction(
        adjusted_half_sec, HALF_MARATHON_DIST_MI, MARATHON
    )

    return {
        "efficiency_ratio": efficiency_ratio,
        "pct_change": pct_change,
        "adjusted_half_sec": adjusted_half_sec,
        "projected_marathon_sec": projected_marathon_sec,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    conn = db.get_connection()
    trend_df = get_rolling_efficiency_trend(conn)
    conn.close()

    if trend_df.empty:
        raise SystemExit("No runs with avg_hr found — can't compute efficiency trend.")

    csv_path = export_trend_for_tableau(trend_df)
    print(f"Rolling efficiency trend exported for Tableau: {csv_path}\n")

    baseline_eff, baseline_n = windowed_avg_efficiency(
        trend_df, HALF_MARATHON_DATE, WINDOW_DAYS
    )
    current_eff, current_n, most_recent_date = current_avg_efficiency(
        trend_df, WINDOW_DAYS
    )

    print("=" * 60)
    print("FITNESS TREND: HALF MARATHON (FEB 1) VS. NOW")
    print("=" * 60)
    print(f"Baseline window:  +/-{WINDOW_DAYS}d around {HALF_MARATHON_DATE} "
          f"({baseline_n} runs) -> avg efficiency {baseline_eff:.3f} sec/mi/bpm")
    print(f"Current window:   last {WINDOW_DAYS}d through {most_recent_date.date()} "
          f"({current_n} runs) -> avg efficiency {current_eff:.3f} sec/mi/bpm")
    print()

    if baseline_n < 3 or current_n < 3:
        print("Warning: fewer than 3 runs in one of the windows — "
              "this comparison may be noisy. Consider widening WINDOW_DAYS.\n")

    result = project_marathon_from_half(baseline_eff, current_eff)

    direction = "improved" if result["pct_change"] < 0 else "declined"
    print(f"Efficiency has {direction} by {abs(result['pct_change']):.1f}% "
          f"since the half marathon.\n")

    print("=" * 60)
    print("PROJECTED MARATHON TIME (half-marathon-anchored)")
    print("=" * 60)
    print(f"Actual half marathon (Feb 1):   {format_hms(HALF_MARATHON_FINISH_SEC)}")
    print(f"Fitness-adjusted half estimate: {format_hms(result['adjusted_half_sec'])}")
    print(f"Projected marathon time:        {format_hms(result['projected_marathon_sec'])}  "
          f"({format_pace(result['projected_marathon_sec'] / MARATHON)})")
    print()


if __name__ == "__main__":
    main()
