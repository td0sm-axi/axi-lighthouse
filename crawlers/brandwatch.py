import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BW_USERNAME = os.getenv("BW_USERNAME")
BW_PASSWORD = os.getenv("BW_PASSWORD")
PROJECT_ID  = os.getenv("BW_PROJECT_ID")
QUERY_ID    = os.getenv("BW_QUERY_ID")

BASE_URL = "https://api.brandwatch.com"

now        = datetime.now(timezone.utc)
end_date   = (now - timedelta(days=1)).strftime("%Y-%m-%d")
start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")


def authenticate():
    resp = requests.post(
        f"{BASE_URL}/oauth/token",
        params={
            "grant_type": "api-password",
            "client_id":  "brandwatch-api-client",
        },
        data={
            "username": BW_USERNAME,
            "password": BW_PASSWORD,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_mentions(token):
    headers = {"Authorization": f"Bearer {token}"}
    all_mentions = []
    cursor = None
    page = 1

    while True:
        params = {
            "queryId":   QUERY_ID,
            "startDate": start_date,
            "endDate":   end_date,
            "pageSize":  5000,
        }
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(
            f"{BASE_URL}/projects/{PROJECT_ID}/data/mentions",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        all_mentions.extend(results)
        print(f"  Page {page}: {len(results)} mentions (total so far: {len(all_mentions)})")

        cursor = data.get("nextCursor") or data.get("cursor")
        if not results or not cursor:
            break
        page += 1

    return all_mentions


def main():
    print(f"Authenticating as {BW_USERNAME}...")
    token = authenticate()
    print(f"Auth OK.")

    print(f"Fetching mentions for query {QUERY_ID} | {start_date} → {end_date}")
    mentions = fetch_mentions(token)

    output_file = f"brandwatch_mentions_{start_date}_to_{end_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(mentions, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(mentions)} mentions saved to {output_file}")


if __name__ == "__main__":
    main()
