"""
Pull American Crow detections across all active BirdWeather stations
in the Portland metro bounding box, via the GraphQL API.

Two-pass design:
  Pass 1: get_active_stations() -> list of station dicts (id, name, coords, latestDetectionAt)
  Pass 2: get_crow_detections(station_ids) -> list of detection dicts (id, timestamp, stationId)

Then join detections -> stations on stationId to attach coords, and
write out a flat dataframe/CSV ready for mapping.
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

GRAPHQL_URL = "https://app.birdweather.com/graphql"

BBOX = {
    "ne": {"lat": 45.65, "lon": -122.40},
    "sw": {"lat": 45.40, "lon": -122.85},
}

AMERICAN_CROW_ID = 108
ACTIVE_WINDOW_DAYS = 7  # station must have a detection within this many days to count as "active"


def graphql_query(query, variables=None):
    """POST a GraphQL query, raise on HTTP error or GraphQL-level errors."""
    resp = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables or {}})
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def get_active_stations():
    """
    Pull all stations in the PDX bbox, paginating past the 100-result cap,
    then filter client-side to those with a detection in the last ACTIVE_WINDOW_DAYS.

    NOTE: we are assuming the 'stations' field supports Relay-style cursor
    pagination (pageInfo.hasNextPage / endCursor). If this errors, the error
    message will tell us the real field names -- paste it back rather than
    guessing further.
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


def get_crow_detections(station_ids, period_days=1):
    """
    Pull American Crow detections for the given station IDs, paginating.

    station_ids: list of station id strings/ints (GraphQL coerces either)
    period_days: how many days back to pull (the API defaults to 1 day
                 if no 'period' arg is sent at all - this was happening
                 silently before this fix)
    """
    query = """
    query($stationIds: [ID!], $speciesIds: [ID!], $period: InputDuration, $first: Int, $after: String) {
      detections(
        stationIds: $stationIds
        speciesIds: $speciesIds
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
        }
      }
    }
    """

    all_detections = []
    after = None
    while True:
        variables = {
            "stationIds": station_ids,
            "speciesIds": [AMERICAN_CROW_ID],
            "period": {"count": period_days, "unit": "day"},
            "first": 100,
            "after": after,
        }
        data = graphql_query(query, variables)
        block = data["detections"]
        all_detections.extend(block["nodes"])
        print(f"  pulled {len(block['nodes'])} detections, total so far: {len(all_detections)} / {block['totalCount']}")
        if not block["pageInfo"]["hasNextPage"]:
            break
        after = block["pageInfo"]["endCursor"]
        time.sleep(0.5)

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
            "station_id": sid,
            "station_name": station_info["name"],
            "lat": station_info["lat"],
            "lon": station_info["lon"],
        })

    if skipped_no_coords:
        print(f"Skipped {skipped_no_coords} detections with no matching/coordless station")

    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


if __name__ == "__main__":
    print("Pulling active stations in PDX bbox...")
    stations = get_active_stations()

    if not stations:
        raise SystemExit("No active stations found -- check bbox/active window before continuing.")

    station_ids = [s["id"] for s in stations]

    print(f"\nPulling American Crow detections across {len(station_ids)} stations (last 7 days)...")
    detections = get_crow_detections(station_ids, period_days=7)

    print(f"\nBuilding dataframe...")
    df = build_dataframe(stations, detections)
    print(df.head())
    print(f"\nTotal crow detections with coordinates: {len(df)}")

    out_path = "crow_detections.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved to {out_path}")