"""
Convert crow_focus_window.csv into a JSON structure keyed by window_label
(e.g. '2026-06-24_sunset'), each containing its own sequence of 2-min
bucket frames - ready for a day-selector dropdown on the map page.
"""

import pandas as pd
import json

df = pd.read_csv("crow_focus_window.csv", parse_dates=["bucket_start"])

stations = (
    df[["station_id", "station_name", "lat", "lon"]]
    .drop_duplicates()
    .to_dict(orient="records")
)

windows = {}
for label, group in df.groupby("window_label"):
    # build the full sequence of 2-min buckets actually present for this
    # window, in chronological order
    bucket_times = sorted(group["bucket_start"].unique())

    lookup = {
        (row["station_id"], row["bucket_start"]): row["detection_count"]
        for _, row in group.iterrows()
    }

    frames = []
    for bt in bucket_times:
        counts = {
            s["station_id"]: lookup.get((s["station_id"], bt), 0)
            for s in stations
        }
        frames.append({
            "time": pd.Timestamp(bt).strftime("%H:%M"),
            "counts": counts
        })

    windows[label] = frames

output = {
    "stations": stations,
    "windows": windows,
    "window_labels": sorted(windows.keys())
}

with open("crow_focus_window.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"Stations: {len(stations)}")
print(f"Window labels: {output['window_labels']}")
for label in output["window_labels"]:
    print(f"  {label}: {len(windows[label])} frames")
print("Saved to crow_focus_window.json")