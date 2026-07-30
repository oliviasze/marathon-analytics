"""
add_manual_run.py — manually log a run that wasn't captured by Garmin.
"""
import db
import time

# conversion factor
MI_TO_KM = 1.609344

def add_manual_run():
    # collecting input
    date = input("Date (YYYY-MM-DD): ").strip()
    distance_mi = float(input("Distance (miles): ").strip())
    duration_sec = int(input("Duration (seconds): ").strip())
    avg_hr = input("Avg HR (blank if unknown): ").strip()
    perceived_type = input("Type (easy/tempo/long/interval/race, blank ok): ").strip()

    distance_km = distance_mi * MI_TO_KM

    record = {
        "activity_id": f"manual-{date}-{int(time.time())}",
        "date": date,
        "distance_km": round(distance_km, 3),
        "duration_sec": duration_sec,
        "avg_pace_sec_per_km": round(duration_sec / distance_km, 1) if distance_km else None,
        "avg_hr": int(avg_hr) if avg_hr else None,
        "max_hr": None,
        "elevation_gain_m": None,
        "cadence_avg": None,
        "training_load": None,
        "resting_hr_that_day": None,
        "sleep_hours_prior_night": None,
        "perceived_type": perceived_type or None,
    }

    conn = db.get_connection()
    inserted = db.insert_run(conn, record)
    conn.commit()
    conn.close()

    if inserted:
        print(f"Added manual run on {date}: {distance_mi} mi ({distance_km:.2f} km) in {duration_sec}s.")
    else:
        print("Insert failed — activity_id collision (very unlikely, try again).")

if __name__ == "__main__":
    add_manual_run()