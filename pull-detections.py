"""
Pull ALL-SPECIES detections across all active BirdWeather stations in the
Portland metro bounding box, via the GraphQL API.

This replaces the species-specific pull_crow_detections.py as the shared
base dataset: species filtering now happens downstream in pandas (one
line: df[df['species'] == 'American Crow']), so the same raw pull can
feed the generic multi-species map AND any species-specific deep-dive
(crows today, swallows later) without separate API pulls per species.

Two-pass design:
  Pass 1: get_active_stations() -> list of station dicts (id, name, coords, latestDetectionAt)
  Pass 2: get_all_detections(station_ids, from_dt, to_dt) -> list of detection dicts

Then join detections -> stations on stationId to attach coords, and
write out a flat dataframe/CSV ready for downstream bucketing/mapping.
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

GRAPHQL_URL = "https://app.birdweather.com/graphql"

BBOX = {
    "ne": {"lat": 45.65, "lon": -122.40},
    "sw": {"lat": 45.40, "lon": -122.85},
}

ACTIVE_WINDOW_DAYS = 7  # station must have a detection within this many days to count as "active"
DATA_FILE = "data/detections_all_species.csv"


def graphql_query(query, variables=None, max_retries=4):
    """POST a GraphQL query, raise on HTTP error or GraphQL-level errors.
    Retries with exponential backoff on connection-level failures (resets,
    timeouts) - distinct from a clean HTTP 429, which we have not seen so
    far. Either way, backing off and retrying is the right response.
    """
    for attempt in range(max_retries):
        try:
            resp = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables or {}}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(data["errors"])
            return data["data"]
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            wait = 2 ** attempt * 5  # 5s, 10s, 20s, 40s
            print(f"  connection error ({e}), retrying in {wait}s (attempt {attempt+1}/{max_retries})...")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {max_retries} retries")


def get_active_stations():
    """
    Pull all stations in the PDX bbox, paginating past the 100-result cap,
    then filter client-side to those with a detection in the last ACTIVE_WINDOW_DAYS.
    """
    query = """
    query($first: Int, $after: String) {
      stations(
        ne: { lat: %f, lon: %f }
        sw: { lat: %f, lon: %f }
        first: $first
        after: $after
      ) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          name
          coords { lat lon }
          latestDetectionAt
        }
      }
    }
    """ % (BBOX["ne"]["lat"], BBOX["ne"]["lon"], BBOX["sw"]["lat"], BBOX["sw"]["lon"])

    all_stations = []
    after = None
    while True:
        data = graphql_query(query, {"first": 100, "after": after})
        block = data["stations"]
        all_stations.extend(block["nodes"])
        print(f"  pulled {len(block['nodes'])} stations, total so far: {len(all_stations)} / {block['totalCount']}")
        if not block["pageInfo"]["hasNextPage"]:
            break
        after = block["pageInfo"]["endCursor"]
        time.sleep(0.5)

    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WINDOW_DAYS)
    active = []
    for s in all_stations:
        if not s["latestDetectionAt"]:
            continue
        last_seen = datetime.fromisoformat(s["latestDetectionAt"])
        if last_seen > cutoff:
            active.append(s)

    print(f"Active stations (detection within {ACTIVE_WINDOW_DAYS} days): {len(active)} / {len(all_stations)}")
    return active


def get_all_detections(station_ids, from_dt, to_dt):
    """
    Pull ALL-SPECIES detections for the given station IDs, paginating.
    No speciesIds filter - that's the key change from the crow-only version.

    station_ids: list of station id strings/ints (GraphQL coerces either)
    from_dt, to_dt: ISO 8601 datetime strings (with offset), confirmed
                    working against the live API on 2026-06-26.
    """
    query = """
    query($stationIds: [ID!], $period: InputDuration, $first: Int, $after: String) {
      detections(
        stationIds: $stationIds
        period: $period
        first: $first
        after: $after
      ) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          timestamp
          station { id }
          species { commonName color }
        }
      }
    }
    """

    all_detections = []
    after = None
    page = 0
    while True:
        variables = {
            "stationIds": station_ids,
            "period": {"from": from_dt, "to": to_dt},
            "first": 1000,  # server appears to clamp this to 500 - confirmed 2026-06-26
            "after": after,
        }
        data = graphql_query(query, variables)
        block = data["detections"]
        all_detections.extend(block["nodes"])
        page += 1
        print(f"  pulled {len(block['nodes'])} detections, total so far: {len(all_detections)} / {block['totalCount']}")

        # checkpoint every 20 pages so a crash doesn't lose everything pulled so far
        if page % 20 == 0:
            import json
            with open("detections_checkpoint.json", "w") as f:
                json.dump(all_detections, f)
            print(f"  [checkpoint saved at page {page}]")

        if not block["pageInfo"]["hasNextPage"]:
            break
        after = block["pageInfo"]["endCursor"]
        time.sleep(1.5)

    return all_detections


def build_dataframe(stations, detections):
    """Join detections to station coords/names on stationId, return a tidy dataframe."""
    station_lookup = {
        str(s["id"]): {"name": s["name"], "lat": s["coords"]["lat"], "lon": s["coords"]["lon"]}
        for s in stations
        if s["coords"] is not None
    }

    rows = []
    skipped_no_coords = 0
    for d in detections:
        sid = str(d["station"]["id"])
        station_info = station_lookup.get(sid)
        if station_info is None:
            skipped_no_coords += 1
            continue
        rows.append({
            "detection_id": d["id"],
            "timestamp": d["timestamp"],
            "species": d["species"]["commonName"],
            "species_color": d["species"].get("color"),
            "station_id": sid,
            "station_name": station_info["name"],
            "lat": station_info["lat"],
            "lon": station_info["lon"],
        })

    if skipped_no_coords:
        print(f"Skipped {skipped_no_coords} detections with no matching/coordless station")

    df = pd.DataFrame(rows)
    if not df.empty:
        # parse as UTC first, then convert to a single named timezone -
        # raw API timestamps can come back with inconsistent fixed-offset
        # representations (caught here as pandas' "mixed timezones" error),
        # and normalizing through UTC sidesteps that while still correctly
        # handling any DST transition automatically going forward
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/Los_Angeles")
    return df


if __name__ == "__main__":
    # --- Load existing data, same dedupe-by-id pattern as the original REST updater ---
    if os.path.exists(DATA_FILE):
        existing_df = pd.read_csv(DATA_FILE)
        existing_df["timestamp"] = pd.to_datetime(existing_df["timestamp"], utc=True).dt.tz_convert("America/Los_Angeles")
        print(f"Loaded {len(existing_df)} existing detections")
    else:
        existing_df = pd.DataFrame(columns=["detection_id", "timestamp", "species", "species_color", "station_id", "station_name", "lat", "lon"])
        print("No existing file found, starting fresh")

    existing_ids = set(existing_df["detection_id"]) if not existing_df.empty else set()

    # pull from the last known timestamp onward - small safety overlap of 10
    # minutes in case the last run ended mid-detection-burst, dedupe handles
    # any resulting repeats
    if not existing_df.empty:
        last_timestamp = existing_df["timestamp"].max()
        from_dt = (last_timestamp - timedelta(minutes=10)).isoformat()
    else:
        # no existing data at all - today's dry run: just the last 24 hours
        from_dt = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    to_dt = datetime.now().astimezone().isoformat()  # now, in local tz with offset

    print(f"Pulling from {from_dt} to {to_dt}")

    print("Pulling active stations in PDX bbox...")
    stations = get_active_stations()

    if not stations:
        raise SystemExit("No active stations found -- check bbox/active window before continuing.")

    station_ids = [s["id"] for s in stations]

    print(f"\nPulling ALL-SPECIES detections across {len(station_ids)} stations...")
    detections = get_all_detections(station_ids, from_dt, to_dt)

    print(f"\nBuilding dataframe...")
    new_df = build_dataframe(stations, detections)

    # --- Dedupe: keep only genuinely new detection ids ---
    if not new_df.empty:
        new_df = new_df[~new_df["detection_id"].isin(existing_ids)]
    print(f"Genuinely new detections (after dedupe): {len(new_df)}")

    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    combined_df = combined_df.sort_values("timestamp").reset_index(drop=True)

    # --- Prune: keep a rolling 1-week window on disk. Long-term analysis
    # is a separate concern (a dedicated multi-year pull), not something
    # this operational file needs to carry. Downstream scripts (focus
    # window, species buckets) read this file directly, so trimming here
    # is the single source of truth - no separate trim step needed there. ---
    cutoff = pd.Timestamp.now(tz=combined_df["timestamp"].dt.tz) - timedelta(days=7)
    before_prune = len(combined_df)
    combined_df = combined_df[combined_df["timestamp"] >= cutoff].reset_index(drop=True)
    pruned = before_prune - len(combined_df)
    if pruned:
        print(f"Pruned {pruned} detections older than 7 days")

    combined_df.to_csv(DATA_FILE, index=False)
    print(f"Saved {len(combined_df)} total detections to {DATA_FILE}")

    if not new_df.empty:
        print("\nSpecies breakdown of new detections:")
        print(new_df["species"].value_counts().head(20))