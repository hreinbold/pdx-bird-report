"""
Collapse raw crow detections into per-station, per-time-bucket presence counts.

Why: detections at a single sustained calling event re-trigger every few
seconds (median gap ~6s at the busiest station in initial data). Counting
raw detections would make one noisy/long event dominate a map. Instead we
ask a simpler question per bucket: "was crow activity present at this
station during this window?" -- and optionally how many separate
detections fired, as a secondary intensity signal.

Input:  crow_detections.csv (detection_id, timestamp, station_id, station_name, lat, lon)
Output: crow_buckets.csv (station_id, station_name, lat, lon, bucket_start, detection_count)
"""

import pandas as pd

BUCKET_MINUTES = 15

df = pd.read_csv("crow_detections.csv", parse_dates=["timestamp"])

# floor each timestamp down to its bucket start, e.g. 18:52 -> 18:30 for a 30-min bucket
df["bucket_start"] = df["timestamp"].dt.floor(f"{BUCKET_MINUTES}min")

# group by station + bucket, count raw detections in that window
# (this count is now bounded by "how many 30-min windows have activity",
#  not by how chatty the classifier was within a single window)
bucketed = (
    df.groupby(["station_id", "station_name", "lat", "lon", "bucket_start"])
    .size()
    .reset_index(name="detection_count")
)

print(f"Raw detections: {len(df)}")
print(f"Bucketed rows (station x time-window combos with activity): {len(bucketed)}")
print(f"Stations represented: {bucketed['station_name'].nunique()}")
print(f"Time buckets spanned: {bucketed['bucket_start'].nunique()}")
print()
print(bucketed.sort_values("detection_count", ascending=False).head(10))

bucketed.to_csv("crow_buckets.csv", index=False)
print("\nSaved to crow_buckets.csv")