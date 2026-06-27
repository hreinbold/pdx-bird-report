"""
Build a fine-grained (2-min bucket) crow detection dataset focused on
90-minute windows around sunrise and sunset, for spotting roost-flight
movement that gets smoothed away at coarser bucket sizes.

Reuses the existing crow_detections.csv (no new BirdWeather pull needed).
Sunrise/sunset times come from the free sunrise-sunset.org API (no key
required).
"""

import requests
import pandas as pd
import time
from datetime import datetime, timedelta

LAT = 45.52   # rough center of your PDX bbox - adjust if you want a more precise reference point
LON = -122.65
FOCUS_WINDOW_MINUTES = 120  # total window width, centered on sunrise/sunset
BUCKET_MINUTES = 2

SUN_API_URL = "https://api.sunrise-sunset.org/json"


def get_sun_times(date_str):
    """
    Returns (sunrise, sunset) as timezone-aware datetimes for the given
    date (YYYY-MM-DD), in the local Portland time already used by your
    detection timestamps.
    """
    params = {"lat": LAT, "lng": LON, "date": date_str, "formatted": 0}
    resp = requests.get(SUN_API_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "OK":
        raise RuntimeError(f"Sunrise-sunset API error: {data}")

    # API returns UTC ISO8601 strings - your detection timestamps are
    # already offset-aware (e.g. -07:00), so convert to the same tz
    sunrise_utc = pd.to_datetime(data["results"]["sunrise"])
    sunset_utc = pd.to_datetime(data["results"]["sunset"])

    return sunrise_utc, sunset_utc


def build_focus_window(df, center_time, label):
    """
    Filter df to a FOCUS_WINDOW_MINUTES window centered on center_time,
    then bucket at BUCKET_MINUTES resolution.
    """
    half_window = timedelta(minutes=FOCUS_WINDOW_MINUTES / 2)
    window_start = center_time - half_window
    window_end = center_time + half_window

    # df timestamps and center_time both need to be timezone-aware and
    # comparable - this assumes df['timestamp'] is already tz-aware
    # (it will be, since pd.read_csv with parse_dates picks up the
    # -07:00 offset already present in the raw data)
    mask = (df["timestamp"] >= window_start) & (df["timestamp"] <= window_end)
    windowed = df[mask].copy()

    print(f"{label}: window {window_start} to {window_end}, {len(windowed)} detections")

    if windowed.empty:
        return pd.DataFrame()

    windowed["bucket_start"] = windowed["timestamp"].dt.floor(f"{BUCKET_MINUTES}min")
    bucketed = (
        windowed.groupby(["station_id", "station_name", "lat", "lon", "bucket_start"])
        .size()
        .reset_index(name="detection_count")
    )
    bucketed["window_label"] = label
    return bucketed


if __name__ == "__main__":
    df = pd.read_csv("data/crow_detections.csv", parse_dates=["timestamp"])

    unique_dates = sorted(df["timestamp"].dt.strftime("%Y-%m-%d").unique())
    print(f"Found {len(unique_dates)} unique dates in dataset: {unique_dates}")

    all_windows = []

    for date_str in unique_dates:
        print(f"\nLooking up sun times for {date_str}...")
        try:
            sunrise, sunset = get_sun_times(date_str)
        except Exception as e:
            print(f"  failed to get sun times for {date_str}: {e}, skipping")
            continue

        sunrise_local = sunrise.tz_convert(df["timestamp"].dt.tz)
        sunset_local = sunset.tz_convert(df["timestamp"].dt.tz)

        print(f"  Sunrise: {sunrise_local}")
        print(f"  Sunset: {sunset_local}")

        sunrise_bucketed = build_focus_window(df, sunrise_local, f"{date_str}_sunrise")
        sunset_bucketed = build_focus_window(df, sunset_local, f"{date_str}_sunset")

        all_windows.append(sunrise_bucketed)
        all_windows.append(sunset_bucketed)

        time.sleep(0.5)  # be polite to the free sunrise-sunset.org API too

    combined = pd.concat(all_windows, ignore_index=True)
    combined.to_csv("data/crow_focus_window.csv", index=False)
    print(f"\nSaved {len(combined)} rows across {len(unique_dates)} days to crow_focus_window.csv")