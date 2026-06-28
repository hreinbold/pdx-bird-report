"""
Bucket ALL-SPECIES detections into 15-min absolute time buckets per
station, and emit a flat JSON structure for the generic multi-species
map (species selector + date-range picker, unlike the crow focus-window
view which is locked to one fixed window per night).

Reads data/detections_all_species.csv, writes data/species_buckets.json.

Design choice: this does NOT pre-aggregate by time-of-day or pick a
fixed window the way the crow focus-window script does. It keeps one
row per (station, species, 15-min bucket) and lets the map's JS filter
by date range and species at view time - more flexible for a map that
needs both selectors, at the cost of a larger file than a pre-summed
version would be. Revisit if file size becomes a problem.
"""

import pandas as pd

INPUT_FILE = "data/detections_all_species.csv"
OUTPUT_FILE = "data/species_buckets.json"
BUCKET_MINUTES = 15

df = pd.read_csv(INPUT_FILE, parse_dates=["timestamp"])
print(f"Loaded {len(df)} total detections across {df['species'].nunique()} species")

df["bucket_start"] = df["timestamp"].dt.floor(f"{BUCKET_MINUTES}min")

bucketed = (
    df.groupby(["station_id", "station_name", "lat", "lon", "species", "bucket_start"])
    .size()
    .reset_index(name="detection_count")
)
print(f"Bucketed into {len(bucketed)} station/species/bucket rows")

stations = (
    df[["station_id", "station_name", "lat", "lon"]]
    .drop_duplicates()
    .to_dict(orient="records")
)

species_list = sorted(df["species"].unique().tolist())

# species -> hex color lookup, using BirdWeather's own assigned color per
# species where available (the same color field BirdWeather shows in its
# own UI), rather than hand-picking colors per species like the original
# single-station dashboard did. Falls back to None for species pulled
# before the color field was added to the query - the chart code on the
# JS side should handle a missing color gracefully (default Plotly color).
species_colors = {}
if "species_color" in df.columns:
    color_lookup = df.dropna(subset=["species_color"]).drop_duplicates("species")
    species_colors = dict(zip(color_lookup["species"], color_lookup["species_color"]))

# flat record list - station_id and species as indices into the lookups
# above keeps the JSON smaller than repeating full station/species info
# on every row
records = [
    {
        "station_id": row["station_id"],
        "species": row["species"],
        "bucket_start": row["bucket_start"].isoformat(),
        "count": int(row["detection_count"]),
    }
    for _, row in bucketed.iterrows()
]

output = {
    "stations": stations,
    "species_list": species_list,
    "species_colors": species_colors,
    "bucket_minutes": BUCKET_MINUTES,
    "date_range": {
        "from": str(df["timestamp"].min().date()),
        "to": str(df["timestamp"].max().date()),
    },
    "records": records,
}

import json
with open(OUTPUT_FILE, "w") as f:
    json.dump(output, f)

print(f"Stations: {len(stations)}")
print(f"Species: {len(species_list)}")
print(f"Date range: {output['date_range']['from']} to {output['date_range']['to']}")
print(f"Records: {len(records)}")
print(f"Saved to {OUTPUT_FILE}")