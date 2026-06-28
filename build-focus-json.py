"""
Convert crow_focus_window.csv into a JSON structure keyed by window_label
(e.g. '2026-06-24_sunset'), each containing its own sequence of 2-min
bucket frames - ready for a day-selector dropdown on the map page.
"""

import pandas as pd
import json

df = pd.read_csv("data/crow_focus_window.csv", parse_dates=["bucket_start"])

stations = (
    df[["station_id", "station_name", "lat", "lon"]]
    .drop_duplicates()
    .to_dict(orient="records")
)

windows = {}
for label, group in df.groupby("window_label"):
    # build a COMPLETE, evenly-spaced grid of 2-min buckets spanning this
    # window's actual min-to-max timestamps - NOT just the bucket times that
    # happened to have a detection. Without this, sparse windows silently
    # skip empty slots, making consecutive frames represent wildly uneven
    # amounts of real time (looks like "bigger bins" on a quiet night).
    window_start = group["bucket_start"].min()
    window_end = group["bucket_start"].max()
    full_grid = pd.date_range(start=window_start, end=window_end, freq="2min")

    lookup = {
        (row["station_id"], row["bucket_start"]): row["detection_count"]
        for _, row in group.iterrows()
    }

    frames = []
    for bt in full_grid:
        counts = {
            s["station_id"]: lookup.get((s["station_id"], bt), 0)
            for s in stations
        }
        frames.append({
            "time": bt.strftime("%H:%M"),
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