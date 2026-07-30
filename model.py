"""
model.py — Phase 3: regression modeling to beat the Riegel baseline.

Approach:
    Each run gets a "Riegel-implied marathon time" as its target — i.e.
    what Riegel's formula would predict for the marathon if THAT run were
    treated as the reference race. Longer, harder-effort runs give more
    trustworthy implied times than short easy jogs, but every row still
    contributes a label without needing an actual marathon result yet.

    We then engineer training-context features (recent long run pace,
    HR-normalized pace, trailing mileage, elevation) and fit a regression
    to predict implied marathon time from those features. If the model's
    predictions are closer to a held-out run's own implied time than
    Riegel's single-reference-race baseline is, that's a win.

Usage:
    python model.py
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

import db
from analyze import load_runs_df, riegel_prediction, format_hms, format_pace, \
    HALF_MARATHON, HALF_FINISH_SEC, MARATHON, RIEGEL_EXP

RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Target: Riegel-implied marathon time from each run's own distance/duration
# ---------------------------------------------------------------------------

def add_implied_marathon_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each run, extrapolate a marathon-equivalent time using Riegel's
    formula with that run's own distance/duration as the reference.
    Very short runs (<3 mi) are excluded — Riegel's exponent is unreliable
    extrapolating that far, and short easy runs are rarely race-effort.

    IMPORTANT: this computes an implied time for every eligible run, but
    only a subset (flagged by is_quality_effort below) should actually be
    used as regression TARGETS — see build_model_dataset(). Easy runs still
    get an implied_marathon_sec value here so they remain available as
    feature-window inputs, but their implied time is not race-representative
    and shouldn't be trained against directly.
    """
    df = df.copy()
    df["implied_marathon_sec"] = df.apply(
        lambda r: riegel_prediction(r["duration_sec"], r["distance_mi"], MARATHON)
        if r["distance_mi"] >= 3 else np.nan,
        axis=1,
    )
    return df


def flag_quality_efforts(df: pd.DataFrame, pace_percentile_threshold: float = 0.6) -> pd.DataFrame:
    """
    Flags which runs represent race-effort (vs. easy/junk miles), so only
    these get used as regression targets. A run counts as quality if:
      - it's the longest run in its calendar week (long run), OR
      - its pace is faster than the given percentile of pace among all
        runs in the trailing 60 days (i.e. a relatively hard effort for
        that period — tempo/interval-like, even if untagged)

    This is a heuristic, not a substitute for manually tagging
    perceived_type — if you tag runs, prefer using those tags instead.
    """
    df = df.copy()
    df["pace_sec_per_mi"] = df["duration_sec"] / df["distance_mi"]

    df["week"] = df["date"].dt.to_period("W")
    longest_per_week = df.groupby("week")["distance_mi"].transform("max")
    is_long_run = df["distance_mi"] == longest_per_week

    is_relatively_fast = pd.Series(False, index=df.index)
    for i, row in df.iterrows():
        window_start = row["date"] - pd.Timedelta(days=60)
        trailing = df[(df["date"] >= window_start) & (df["date"] <= row["date"])]
        if len(trailing) >= 5:
            threshold_pace = trailing["pace_sec_per_mi"].quantile(1 - pace_percentile_threshold)
            is_relatively_fast.at[i] = row["pace_sec_per_mi"] <= threshold_pace

    df["is_quality_effort"] = is_long_run | is_relatively_fast
    df = df.drop(columns=["week", "pace_sec_per_mi"])
    return df


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds trailing-window training-context features, computed using only
    data up to (and not including) each run's own date — avoids leaking
    a run's own performance into its own features.
    """
    df = df.copy()
    df = df.sort_values("date").reset_index(drop=True)

    # per-run HR-normalized pace, used only as an input to the trailing
    # average below — never used directly as a feature for its own row,
    # since that would leak the current run's own effort into its target
    df["_per_run_hr_norm_pace"] = df["duration_sec"] / df["distance_mi"] / df["avg_hr"]

    # trailing 14/28-day windows (all excluding the current run)
    long_run_pace = []
    trailing_mileage_4wk = []
    trailing_elevation = []
    trailing_hr_norm_pace = []

    for i, row in df.iterrows():
        window_start_14d = row["date"] - pd.Timedelta(days=14)
        window_start_28d = row["date"] - pd.Timedelta(days=28)

        prior_14d = df[(df["date"] >= window_start_14d) & (df["date"] < row["date"])]
        prior_28d = df[(df["date"] >= window_start_28d) & (df["date"] < row["date"])]

        if len(prior_14d) > 0:
            longest = prior_14d.loc[prior_14d["distance_mi"].idxmax()]
            pace = longest["duration_sec"] / longest["distance_mi"]
        else:
            pace = np.nan
        long_run_pace.append(pace)

        trailing_mileage_4wk.append(
            prior_28d["distance_mi"].sum() / 4 if len(prior_28d) > 0 else np.nan
        )
        trailing_elevation.append(
            prior_28d["elevation_gain_m"].mean() if len(prior_28d) > 0 else np.nan
        )
        trailing_hr_norm_pace.append(
            prior_14d["_per_run_hr_norm_pace"].mean() if len(prior_14d) > 0 else np.nan
        )

    df["recent_long_run_pace"] = long_run_pace
    df["trailing_4wk_avg_weekly_mi"] = trailing_mileage_4wk
    df["trailing_elevation_avg_m"] = trailing_elevation
    df["hr_normalized_pace"] = trailing_hr_norm_pace
    df = df.drop(columns=["_per_run_hr_norm_pace"])

    return df


FEATURE_COLUMNS = [
    "hr_normalized_pace",
    "recent_long_run_pace",
    "trailing_4wk_avg_weekly_mi",
    "trailing_elevation_avg_m",
]


# ---------------------------------------------------------------------------
# Model fitting + evaluation
# ---------------------------------------------------------------------------

def build_model_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Filters down to rows with a valid target and no missing features
    (early runs won't have 14/28-day trailing windows yet), AND restricts
    to quality-effort runs only — easy runs remain in `df` for feature
    windows but are excluded here since their implied_marathon_sec isn't
    race-representative."""
    model_df = df.dropna(subset=["implied_marathon_sec"] + FEATURE_COLUMNS)
    model_df = model_df[model_df["is_quality_effort"]]
    return model_df


def time_based_split(model_df: pd.DataFrame, test_frac: float = 0.2):
    """Splits by date rather than randomly — trains on earlier runs,
    tests on the most recent ones, which mirrors how the model will
    actually be used (predicting forward toward race day)."""
    model_df = model_df.sort_values("date")
    split_idx = int(len(model_df) * (1 - test_frac))
    train = model_df.iloc[:split_idx]
    test = model_df.iloc[split_idx:]
    return train, test


def evaluate_riegel_baseline(test_df: pd.DataFrame) -> float:
    """Riegel baseline: predict every test run's implied marathon time
    using the fixed half-marathon reference, ignoring any training
    context features. This is the number the regression needs to beat."""
    riegel_pred = riegel_prediction(HALF_FINISH_SEC, HALF_MARATHON, MARATHON)
    predictions = np.full(len(test_df), riegel_pred)
    mae_sec = mean_absolute_error(test_df["implied_marathon_sec"], predictions)
    return mae_sec


def train_and_evaluate(train_df: pd.DataFrame, test_df: pd.DataFrame):
    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["implied_marathon_sec"]
    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["implied_marathon_sec"]

    model = Ridge(alpha=1.0, random_state=RANDOM_STATE)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae_sec = mean_absolute_error(y_test, preds)

    return model, mae_sec


def print_feature_importance(model: Ridge):
    print("Feature coefficients (Ridge):")
    for name, coef in zip(FEATURE_COLUMNS, model.coef_):
        print(f"  {name:30s} {coef:+.4f}")
    print()


def predict_current_fitness(model: Ridge, df: pd.DataFrame):
    """Uses the most recent available trailing-window features (i.e. today's
    training context) to predict marathon time going forward."""
    latest = df.dropna(subset=FEATURE_COLUMNS).sort_values("date").iloc[-1]
    X_latest = latest[FEATURE_COLUMNS].to_frame().T
    predicted_sec = model.predict(X_latest)[0]
    return predicted_sec, latest["date"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    df = load_runs_df()
    df = add_implied_marathon_time(df)
    df = add_features(df)
    df = flag_quality_efforts(df)

    model_df = build_model_dataset(df)
    n_quality = df["is_quality_effort"].sum()
    print(f"Quality-effort runs flagged: {n_quality} / {len(df)}")
    print(f"Runs available for modeling (after filtering): {len(model_df)} / {n_quality}")

    if len(model_df) < 20:
        raise SystemExit(
            "Not enough runs with complete features + target to model reliably. "
            "Check that distance_mi >= 3mi runs and 28-day trailing windows exist."
        )

    train_df, test_df = time_based_split(model_df)
    print(f"Train: {len(train_df)} runs | Test: {len(test_df)} runs (time-based split)\n")

    riegel_mae = evaluate_riegel_baseline(test_df)
    model, model_mae = train_and_evaluate(train_df, test_df)

    print("=" * 60)
    print("MODEL VS. RIEGEL BASELINE (mean absolute error on held-out runs)")
    print("=" * 60)
    print(f"Riegel baseline MAE:   {riegel_mae/60:.1f} min")
    print(f"Regression model MAE:  {model_mae/60:.1f} min")
    if model_mae < riegel_mae:
        improvement = (1 - model_mae / riegel_mae) * 100
        print(f"-> Model improves on Riegel by {improvement:.1f}%")
    else:
        print("-> Model did not beat Riegel on this split.")
    print()

    print_feature_importance(model)

    predicted_sec, as_of_date = predict_current_fitness(model, df)
    print("=" * 60)
    print("CURRENT MARATHON PREDICTION (regression model)")
    print("=" * 60)
    print(f"As of training context through: {as_of_date.date()}")
    print(f"Predicted marathon time:  {format_hms(predicted_sec)}  "
          f"({format_pace(predicted_sec / MARATHON)})")
    print()


if __name__ == "__main__":
    main()