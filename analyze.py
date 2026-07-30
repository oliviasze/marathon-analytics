"""
analyze.py - what this file does
"""
import sqlite3
from pathlib import Path
 
import matplotlib.pyplot as plt
import pandas as pd
 
import db

OUTPUT_DIR = Path(__file__).parent / "charts"

# baseline data
HALF_MARATHON = 13.1 # miles
HALF_FINISH_SEC = 1 * 3600 + 34 * 60 + 49

# marathon constants
MARATHON = 26.2 # miles
RIEGEL_EXP = 1.06

def format_hms(total_seconds: float) -> str:
    total_seconds = int(round(total_seconds))
    h, remainder = divmod(total_seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}"
 
 
def format_pace(sec_per_mi: float) -> str:
    m, s = divmod(int(round(sec_per_mi)), 60)
    return f"{m}:{s:02d} /mi"

def riegel_prediction(t1, d1, d2):
    """
    Predicts the time it will take to run a distance d2 given a previous time t1
    for a distance d1 using Riegel's formula.
    """
    return t1 * (d2 / d1) ** RIEGEL_EXP

def load_runs_df() -> pd.DataFrame:
    """
    Pulls all rows from training.db and converts into a readable pandas DataFrame
    """
    conn = db.get_connection()
    runs = db.get_all_runs(conn)
    conn.close()
    # If there are no runs, raise a clear error so the user knows to run sync_garmin.py first
    if not runs:
        raise SystemExit("No runs found in training.db — run sync_garmin.py first.")
    df = pd.DataFrame(runs)

    # Converts the date column from text to an actual datetime type, and sorts by date ascending
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    df["distance_mi"] = df["distance_km"] * 0.621371
    df["avg_pace_sec_per_mi"] = df["avg_pace_sec_per_km"] * 1.60934
    return df

def print_summary(df: pd.DataFrame) -> None:
    """
    ...
    """
    print("=" * 60)
    print("TRAINING SUMMARY")
    print("=" * 60)

    print(f"Total runs logged:   {len(df)}")
    print(f"Date range:          {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"Total distance:      {df['distance_mi'].sum():.1f} miles")
    print(f"Avg distance/run:    {df['distance_mi'].mean():.1f} miles")
    print(f"Longest run:         {df['distance_mi'].max():.1f} miles "
          f"(on {df.loc[df['distance_mi'].idxmax(), 'date'].date()})")
    print(f"Avg HR across runs:  {df['avg_hr'].mean():.0f} bpm")
    print()

def weekly_mileage(df: pd.DataFrame) -> pd.DataFrame:
    weekly = (
        df.set_index("date")["distance_mi"]
        .resample("W-MON")
        .sum()
        .rename("weekly_mi")
        .to_frame()
    )
    return weekly

def print_riegel_baseline() -> None:
    predicted_sec = riegel_prediction(
        HALF_FINISH_SEC, HALF_MARATHON, MARATHON
    )
    print("=" * 60)
    print("RIEGEL FORMULA BASELINE")
    print("=" * 60)
    print(f"Reference race:      {HALF_MARATHON:.2f} miles in "
          f"{format_hms(HALF_FINISH_SEC)}")
    print(f"Predicted marathon:  {format_hms(predicted_sec)}  "
          f"({format_pace(predicted_sec / MARATHON  )})")
    print()

def plot_weekly_mileage(weekly: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(weekly.index, weekly["weekly_mi"], width=5, color="#3B82F6")
    ax.set_title("Weekly Mileage")
    ax.set_ylabel("mi")
    ax.set_xlabel("Week")
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path = OUTPUT_DIR / "weekly_mileage.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
 
 
def plot_pace_trend(df: pd.DataFrame) -> Path:
    d = df.dropna(subset=["avg_pace_sec_per_mi"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(d["date"], d["avg_pace_sec_per_mi"] / 60, marker="o", color="#10B981")
    ax.invert_yaxis()  # faster pace (lower number) shown as "up"
    ax.set_title("Pace Trend (lower is faster)")
    ax.set_ylabel("min/mi")
    ax.set_xlabel("Date")
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path = OUTPUT_DIR / "pace_trend.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
 
 
def plot_hr_trend(df: pd.DataFrame) -> Path:
    d = df.dropna(subset=["avg_hr"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(d["date"], d["avg_hr"], marker="o", color="#EF4444", label="Avg HR")
    if d["max_hr"].notna().any():
        ax.plot(d["date"], d["max_hr"], marker="o", color="#F97316",
                 alpha=0.5, label="Max HR")
    ax.set_title("Heart Rate Trend")
    ax.set_ylabel("bpm")
    ax.set_xlabel("Date")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path = OUTPUT_DIR / "hr_trend.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    df = load_runs_df()
 
    print_summary(df)
    print_riegel_baseline()
 
    weekly = weekly_mileage(df)
    print("Weekly mileage:")
    print(weekly)
    print()

    p1 = plot_weekly_mileage(weekly)
    p2 = plot_pace_trend(df)
    p3 = plot_hr_trend(df)
 
    print(f"Charts saved to: {OUTPUT_DIR}/")
    print(f"  - {p1.name}")
    print(f"  - {p2.name}")
    print(f"  - {p3.name}")
   
 
 
if __name__ == "__main__":
    main()


