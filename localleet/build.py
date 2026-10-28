"""Validate coverage and atomically publish immutable, sharded lookup data."""

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
import zlib

from .collect import utcnow


def identity(region, username):
    if region not in {"US", "CN"} or not username:
        raise ValueError("A source region (US/CN) and username are required")
    return f"{region}:{username}"


def shard_for(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:2]


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def validate_and_index(pages, emit):
    countries = Counter()
    country_ties = {}
    seen = set()
    digest = hashlib.sha256()
    previous_rank = 0
    previous_rating = Decimal("Infinity")
    unknown = 0
    count = 0
    lookup_users = 0
    deleted_rows = 0
    unnamed_rows = 0
    metadata = None
    for expected_page, (number, page) in enumerate(pages, 1):
        if number != expected_page:
            raise ValueError(f"Missing page {expected_page}")
        current_metadata = {k: page[k] for k in ("totalUsers", "userPerPage", "totalPages")}
        if metadata is None:
            metadata = current_metadata
        elif metadata != current_metadata:
            raise ValueError(f"Metadata changed on page {number}")
        nodes = page["rankingNodes"]
        expected_size = metadata["userPerPage"]
        if not nodes or len(nodes) > expected_size:
            raise ValueError(f"Invalid size on page {number}")
        if number < metadata["totalPages"] and len(nodes) != expected_size:
            raise ValueError(f"Short intermediate page {number}")
        for node in nodes:
            count += 1
            rank = node["currentGlobalRanking"]
            rating = Decimal(str(node["currentRating"]))
            if rank != previous_rank + 1:
                raise ValueError(f"Global rank gap/duplicate: expected {previous_rank + 1}, got {rank}")
            if not rating.is_finite() or rating > previous_rating:
                raise ValueError(f"Invalid rating order at rank {rank}")
            previous_rank, previous_rating = rank, rating
            region = node["dataRegion"]
            user = node["user"]
            profile = user["profile"]
            username = user.get("username") or ""
            available = bool(username) and username != "deleted_user"
            canonical = identity(region, username) if available else None
            if canonical:
                if canonical in seen:
                    raise ValueError(f"Duplicate source account: {canonical}")
                seen.add(canonical)
            elif username == "deleted_user":
                deleted_rows += 1
            else:
                unnamed_rows += 1
            country = profile.get("countryCode") or None
            if country and (len(country) != 2 or not country.isascii() or not country.isalpha()
                            or country != country.upper()):
                raise ValueError(f"Invalid country code for {canonical}")
            local_position = None
            local_rating_rank = None
            if country:
                countries[country] += 1
                local_position = countries[country]
                # Competition rank: equally rated players share a rank (1, 2, 2, 4).
                last_rating, tie_rank = country_ties.get(country, (None, None))
                local_rating_rank = tie_rank if rating == last_rating else local_position
                country_ties[country] = (rating, local_rating_rank)
            else:
                unknown += 1
            record = {
                "username": user["username"], "region": region,
                "userSlug": profile.get("userSlug") or None,
                "country": country, "globalRank": rank,
                "rating": str(node["currentRating"]),
                "localRank": local_position, "localRatingRank": local_rating_rank,
            }
            digest.update((encode(record) + "\n").encode())
            if canonical:
                lookup_users += 1
                emit(canonical, record)
    if metadata is None or expected_page != metadata["totalPages"]:
        raise ValueError("Not all advertised pages have been collected")
    return {
        "sourceMetadata": metadata, "sourceRows": count,
        "indexedUsers": lookup_users, "deletedAccountRows": deleted_rows,
        "unnamedAccountRows": unnamed_rows,
        "reportedMinusSourceRows": metadata["totalUsers"] - count,
        "unknownCountryUsers": unknown, "countries": dict(sorted(countries.items())),
        "contentSha256": digest.hexdigest(),
    }


def build(database_path, output_root):
    database_path = Path(database_path).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(database_path)
    database = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
    metadata = dict(database.execute("SELECT key, value FROM metadata"))
    if metadata.get("status") != "collected":
        database.close()
        raise ValueError("Collection is not complete; refusing to publish a partial index")
    root = Path(output_root)
    snapshot_id = utcnow().replace(":", "").replace("+", "-") + "-" + uuid.uuid4().hex[:8]
    folder = root / "snapshots" / snapshot_id
    folder.mkdir(parents=True)
    shard_files = {}
    alias_seen = set()
    entry_counts = Counter()

    def write_entry(key, record):
        if key in alias_seen:
            raise ValueError(f"Duplicate lookup key: {key}")
        alias_seen.add(key)
        shard = shard_for(key)
        if shard not in shard_files:
            shard_files[shard] = (folder / f"{shard}.json").open("w", encoding="utf-8", newline="\n")
            shard_files[shard].write("{")
        stream = shard_files[shard]
        if entry_counts[shard]:
            stream.write(",")
        stream.write(encode(key) + ":" + encode(record))
        entry_counts[shard] += 1

    def emit(key, record):
        write_entry(key, record)
        slug = record["userSlug"]
        if record["region"] == "CN" and slug:
            write_entry(f"CN-SLUG:{slug}", record)

    try:
        pages = ((n, json.loads(zlib.decompress(blob))) for n, blob in database.execute(
            "SELECT number, payload FROM pages ORDER BY number"))
        summary = validate_and_index(pages, emit)
    finally:
        for stream in shard_files.values():
            stream.write("}\n")
            stream.close()
        database.close()
    shards = {}
    for shard in sorted(shard_files):
        path = folder / f"{shard}.json"
        raw = path.read_bytes()
        shards[shard] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                         "entries": entry_counts[shard]}
    manifest = {
        "schemaVersion": 1, "snapshotId": snapshot_id,
        "source": "https://leetcode.com/contest/globalranking/?tab=global",
        "endpoint": "https://leetcode.com/graphql/", "builtAt": utcnow(),
        "collectionStartedAt": metadata.get("startedAt"),
        "collectionFinishedAt": metadata.get("lastRunAt"),
        "coverage": "all-advertised-pages", "sourceAtomicSnapshot": False,
        "rankDefinition": "1-based country row position in source global order; declared countries only",
        "ratingRankDefinition": "1 + number of same-country users with strictly higher source rating",
        "limitations": [
            "Source provides no verified atomic snapshot or revision token.",
            "Reported totalUsers may exceed the entries exposed by advertised pages; cause unverified.",
            "Country is self-declared; missing country remains null, including CN-region accounts.",
            "Ranks describe this collected dataset, not guaranteed live standings.",
        ],
        **summary, "shards": shards,
    }
    (folder / "manifest.json").write_text(encode(manifest) + "\n", encoding="utf-8")
    pointer = root / "current.json.tmp"
    pointer.write_text(encode({"snapshotId": snapshot_id,
                              "manifest": f"snapshots/{snapshot_id}/manifest.json"}) + "\n",
                       encoding="utf-8")
    pointer.replace(root / "current.json")
    print(json.dumps({k: v for k, v in manifest.items() if k != "shards"}, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/raw/rankings.sqlite3")
    parser.add_argument("--output", default="data")
    arguments = parser.parse_args()
    build(arguments.database, arguments.output)
