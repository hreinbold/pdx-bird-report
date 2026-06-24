import os
import json
import requests
import time

token = os.environ.get("BIRDWEATHER_TOKEN")
if not token:
    raise SystemExit("BIRDWEATHER_TOKEN environment variable not set")

url = f"https://app.birdweather.com/api/v1/stations/{token}/detections"

all_detections = []
cursor = None

while True:
    params = {"limit": 100, "order": "asc"}
    if cursor:
        params["cursor"] = cursor

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    batch = data.get('detections', [])
    if not batch:
        break

    all_detections.extend(batch)
    print(f"Pulled {len(batch)} detections, total so far: {len(all_detections)}")

    if len(batch) < 100:
        break  # last page, fewer than full limit means we're done

    cursor = batch[-1]['id']
    time.sleep(1)  # be polite to the API between requests

print(f"Total detections pulled: {len(all_detections)}")

os.makedirs('data', exist_ok=True)
with open('data/detections.json', 'w') as f:
    json.dump(all_detections, f, indent=2)

print("Saved to data/detections.json")
