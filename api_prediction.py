"""
api_prediction.py — JSON output of the current marathon time projection,
for the GET /prediction endpoint.

Returns all three views your project has built so far, so the dashboard
can show them side by side instead of picking one:

1. riegel_baseline            — fixed Riegel extrapolation from the Feb 1
                                 half marathon result (Phase 2 baseline)
2. fitness_trend_projection   — half-anchored, efficiency-adjusted
                                 projection (Phase 3, trend_analysis.py)
3. regression_model_projection — Ridge regression on training-context
                                  features (Phase 3/4, model.py)

Each of the latter two degrades gracefully to an "error" field (rather
than failing the whole request) if there isn't enough data yet — e.g.
early in training before 28-day trailing windows exist.

Usage:
    python api_prediction.py

Prints a single JSON object to stdout.
"""
import json

import db
from analyze import (
    HALF_FINISH_SEC,
    HALF_MARATHON,
    MARATHON,
    format_hms,
    format_pace,
    load_runs_df,
    riegel_prediction,
)
from model import (
    add_features,
    add_implied_marathon_time,
    build_model_dataset,
    flag_quality_efforts,
    predict_current_fitness,
    time_based_split,
    train_and_evaluate,
)
from trend_analysis import (
    HALF_MARATHON_DATE,
    WINDOW_DAYS,
    current_avg_efficiency,
    get_rolling_efficiency_trend,
    project_marathon_from_half,
    windowed_avg_efficiency,
)


def sec_to_obj(sec: float) -> dict:
    return {
        "seconds": round(sec),
        "formatted": format_hms(sec),
        "pace_per_mi": format_pace(sec / MARATHON),
    }


def get_riegel_baseline() -> dict:
    riegel_sec = riegel_prediction(HALF_FINISH_SEC, HALF_MARATHON, MARATHON)
    return sec_to_obj(riegel_sec)


def get_fitness_trend_projection() -> dict:
    conn = db.get_connection()
    trend_df = get_rolling_efficiency_trend(conn)
    conn.close()

    baseline_eff, baseline_n = windowed_avg_efficiency(
        trend_df, HALF_MARATHON_DATE, WINDOW_DAYS
    )
    current_eff, current_n, most_recent_date = current_avg_efficiency(
        trend_df, WINDOW_DAYS
    )
    result = project_marathon_from_half(baseline_eff, current_eff)

    return {
        **sec_to_obj(result["projected_marathon_sec"]),
        "pct_change_since_half": round(result["pct_change"], 1),
        "as_of": most_recent_date.strftime("%Y-%m-%d"),
        "baseline_window_n_runs": baseline_n,
        "current_window_n_runs": current_n,
        "low_confidence": baseline_n < 3 or current_n < 3,
    }


def get_regression_model_projection() -> dict:
    df = load_runs_df()
    df = add_implied_marathon_time(df)
    df = add_features(df)
    df = flag_quality_efforts(df)
    model_df = build_model_dataset(df)

    if len(model_df) < 20:
        raise ValueError(
            f"Only {len(model_df)} quality-effort runs with complete "
            "features — need at least 20 to model reliably."
        )

    train_df, test_df = time_based_split(model_df)
    model, model_mae_sec = train_and_evaluate(train_df, test_df)
    predicted_sec, as_of_date = predict_current_fitness(model, df)

    return {
        **sec_to_obj(predicted_sec),
        "as_of": as_of_date.strftime("%Y-%m-%d"),
        "held_out_mae_min": round(model_mae_sec / 60, 1),
        "train_n_runs": len(train_df),
        "test_n_runs": len(test_df),
    }


def main():
    result = {"riegel_baseline": get_riegel_baseline()}

    try:
        result["fitness_trend_projection"] = get_fitness_trend_projection()
    except Exception as e:  # noqa: BLE001 — surface any failure to the API caller
        result["fitness_trend_projection"] = {"error": str(e)}

    try:
        result["regression_model_projection"] = get_regression_model_projection()
    except Exception as e:  # noqa: BLE001
        result["regression_model_projection"] = {"error": str(e)}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
