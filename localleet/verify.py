"""Verify published shard integrity and sampled ranks against independent source arrays."""

import argparse
from bisect import bisect_left
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import zlib

from .build import shard_for
from .collect import utcnow
from .source import Client


def check_profile_freshness(client, node):
    username = node['user']['username']
    query = ('query { userContestRanking(username: ' + json.dumps(username)
             + ') { globalRanking rating } }')
    profile = (client.request(query).get('data') or {}).get('userContestRanking')
    if (not profile or profile.get('globalRanking') != node['currentGlobalRanking']
            or abs(Decimal(str(profile.get('rating'))) - Decimal(str(node['currentRating']))) > Decimal('0.000001')):
        raise ValueError(f'Profile and ranking snapshot disagree for {username}; refusing stale publication')
    return {'username': username, 'matches': True}


def verify(database_path, root, live=False):
    start = time.perf_counter()
    root = Path(root)
    pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
    manifest_path = root / pointer["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    folder = manifest_path.parent
    total_entries = 0
    cache = {}
    shard_sizes = []
    for shard, descriptor in manifest["shards"].items():
        raw = (folder / f"{shard}.json").read_bytes()
        if len(raw) != descriptor["bytes"] or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise ValueError(f"Shard integrity failed: {shard}")
        entries = json.loads(raw)
        if len(entries) != descriptor["entries"]:
            raise ValueError(f"Entry count failed: {shard}")
        if any(shard_for(key) != shard for key in entries):
            raise ValueError(f"Misplaced key in shard: {shard}")
        total_entries += len(entries)
        shard_sizes.append(len(raw))
    database = sqlite3.connect(f"{Path(database_path).resolve().as_uri()}?mode=ro", uri=True)
    country_positions = defaultdict(list)
    country_ratings = defaultdict(list)
    samples = []
    rows = 0
    for number, blob in database.execute("SELECT number,payload FROM pages ORDER BY number"):
        for node in json.loads(zlib.decompress(blob))["rankingNodes"]:
            rows += 1
            country = node["user"]["profile"].get("countryCode")
            if country:
                country_positions[country].append(node["currentGlobalRanking"])
                country_ratings[country].append(-Decimal(str(node["currentRating"])))
            if ((rows % 10007 == 1 or node["user"]["username"] == "Adham0X1Star")
                    and node["user"].get("username") not in (None, "", "deleted_user")):
                samples.append(node)
    if rows != manifest["sourceRows"]:
        raise ValueError("Source row count mismatch")
    if {k: len(v) for k, v in country_positions.items()} != manifest["countries"]:
        raise ValueError("Country totals mismatch")
    example = None
    for node in samples:
        region = node["dataRegion"]
        username = node["user"]["username"]
        key = f"{region}:{username}"
        shard = shard_for(key)
        if shard not in cache:
            cache[shard] = json.loads((folder / f"{shard}.json").read_text(encoding="utf-8"))
        record = cache[shard][key]
        country = node["user"]["profile"].get("countryCode")
        expected = None if not country else bisect_left(
            country_positions[country], node["currentGlobalRanking"]) + 1
        expected_rating_rank = None if not country else bisect_left(
            country_ratings[country], -Decimal(str(node["currentRating"]))) + 1
        if (record["localRank"] != expected or record["localRatingRank"] != expected_rating_rank
                or record["globalRank"] != node["currentGlobalRanking"]):
            raise ValueError(f"Independent source comparison failed: {key}")
        if username == "Adham0X1Star":
            example = record
    sentinels = []
    profiles = []
    if live:
        client = Client(1.0)
        page_count = manifest["sourceMetadata"]["totalPages"]
        numbers = [1, (page_count + 1) // 2, page_count]
        fetched = client.pages(numbers)
        for number in numbers:
            old = database.execute("SELECT payload FROM pages WHERE number=?", (number,)).fetchone()
            old = json.loads(zlib.decompress(old[0]))
            if fetched[number] != old:
                raise ValueError(f"Source sentinel changed: page {number}; snapshot is stale")
            sentinels.append({"page": number, "matches": True})
        candidates = [n for n in samples if n['dataRegion'] == 'US']
        chosen = candidates[:1] + candidates[len(candidates)//2:len(candidates)//2+1]
        chosen += [n for n in candidates if n['user']['username'] == 'Adham0X1Star']
        checked = set()
        for node in chosen:
            if node['user']['username'] not in checked:
                profiles.append(check_profile_freshness(client, node))
                checked.add(node['user']['username'])
    database.close()
    result = {"verifiedAt": utcnow(), "snapshotId": manifest["snapshotId"],
              "sourceRows": rows, "shardsVerified": len(shard_sizes),
              "lookupEntries": total_entries, "independentRankSamples": len(samples),
              "shardBytes": {"min": min(shard_sizes), "max": max(shard_sizes),
                             "total": sum(shard_sizes)},
              "liveSentinels": sentinels, "liveProfiles": profiles, "example": example,
              "elapsedSeconds": round(time.perf_counter() - start, 3),
              "limitation": "Sampled live checks do not prove an atomic source snapshot."}
    (root / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/raw/rankings.sqlite3")
    parser.add_argument("--data", default="data")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    verify(args.database, args.data, args.live)
