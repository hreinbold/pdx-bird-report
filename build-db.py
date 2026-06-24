import os
import json
import requests
import time

token = os.environ.get("BIRDWEATHER_TOKEN")
if not token:
    raise SystemExit("BIRDWEATHER_TOKEN environment variable not set")

DATA_FILE = 'data/detections.json'

# --- Load existing data ---
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as f:
        existing_detections = json.load(f)
    print(f"Loaded {len(existing_detections)} existing detections")
else:
    existing_detections = []
    print("No existing file found, starting fresh")

existing_ids = set(d['id'] for d in existing_detections)

# --- Determine where to start fetching from ---
if existing_detections:
    last_timestamp = max(d['timestamp'] for d in existing_detections)
    print(f"Fetching new detections from {last_timestamp} onward")
else:
    last_timestamp = None
    print("No prior timestamp found, fetching all available history")

# --- Fetch new detections, paginating in case there's more than 100 ---
url = f"https://app.birdweather.com/api/v1/stations/{token}/detections"
new_detections = []
cursor = None

while True:
    params = {"limit": 100, "order": "asc"}
    if last_timestamp:
        params["from"] = last_timestamp
    if cursor:
        params["cursor"] = cursor

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    batch = data.get('detections', [])
    if not batch:
        break

    new_detections.extend(batch)
    print(f"Pulled {len(batch)} detections, total new so far: {len(new_detections)}")

    if len(batch) < 100:
        break

    cursor = batch[-1]['id']
    time.sleep(1)

print(f"Total new detections fetched: {len(new_detections)}")

# --- Dedupe and merge ---
added = 0
for d in new_detections:
    if d['id'] not in existing_ids:
        existing_detections.append(d)
        existing_ids.add(d['id'])
        added += 1

print(f"Added {added} genuinely new detections (skipped {len(new_detections) - added} duplicates)")

# --- Save merged dataset ---
os.makedirs('data', exist_ok=True)
with open(DATA_FILE, 'w') as f:
    json.dump(existing_detections, f, indent=2)

print(f"Saved {len(existing_detections)} total detections to {DATA_FILE}")