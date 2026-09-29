"""Read-only YouTube inventory with durable local editorial labels."""
from __future__ import annotations

import argparse
import copy
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .audio_repair import ROOT, WORK
from .youtube_audio import service
from .youtube_config import configured_channel

CATALOG = ROOT / "data" / "youtube-videos.json"


def load(path):
    content = path.read_bytes()
    catalog = json.loads(content.decode("utf-8-sig"))
    if catalog.get("schema") != 1 or not isinstance(catalog.get("videos"), dict):
        raise ValueError("Unsupported catalog; expected schema 1 and a videos object.")
    for key, row in catalog["videos"].items():
        if not isinstance(row, dict) or not isinstance(row.get("local", {}), dict):
            raise ValueError(f"Invalid catalog entry: {key}")
    return catalog, content


def write_catalog(path, catalog, previous):
    # Fetch/merge completes before writing; preserve a recovery copy outside Git.
    if path.read_bytes() != previous:
        raise ValueError("Catalog changed during this operation. Rerun to preserve concurrent edits.")
    backup_dir = ROOT / "work" / "youtube-inventory" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=backup_dir, suffix=".json", delete=False) as backup:
        backup.write(previous)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write((json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        if path.read_bytes() != previous:
            raise ValueError("Catalog changed before replacement; rerun the operation.")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def pages(resource, **kwargs):
    token = None
    seen = set()
    while True:
        response = resource.list(**kwargs, **({"pageToken": token} if token else {})).execute()
        yield from response.get("items", [])
        token = response.get("nextPageToken")
        if not token:
            return
        if token in seen:
            raise ValueError("YouTube repeated a pagination token; catalog was not changed.")
        seen.add(token)


def local_time(stamp, zone):
    if not stamp:
        return None
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("YouTube returned a timestamp without a time zone.")
    return parsed.astimezone(zone).isoformat()


def collect(api, old, channel_id=None):
    name = old.get("timezone", "America/Los_Angeles")
    try:
        zone = timezone.utc if name == "UTC" else ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone data missing. Install requirements-youtube.txt in the YouTube virtual environment.") from exc
    channels = list(pages(api.channels(), part="snippet,contentDetails", mine=True, maxResults=50))
    expected = channel_id or (old.get("channel") or {}).get("id")
    selected = [c for c in channels if c["id"] == expected] if expected else channels
    if len(selected) != 1:
        choices = ", ".join(c["id"] + " (" + c["snippet"]["title"] + ")" for c in channels)
        raise ValueError(f"Select an authorized channel matching the configured target {expected}. Run auth read again and select Kenton Church EPC. Available: {choices or '(none)'}")
    channel = selected[0]
    if old.get("channel") and old["channel"]["id"] != channel["id"]:
        raise ValueError("Catalog belongs to another channel; do not merge channel inventories.")
    playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = list(dict.fromkeys(row["contentDetails"]["videoId"] for row in pages(
        api.playlistItems(), part="contentDetails", playlistId=playlist, maxResults=50)))
    result = copy.deepcopy(old)
    rows = result["videos"]
    for row in rows.values():
        row["seen_in_public_inventory"] = False
    public_count = 0
    for start in range(0, len(ids), 50):
        response = api.videos().list(part="snippet,status,contentDetails,liveStreamingDetails", id=",".join(ids[start:start + 50])).execute()
        for item in response.get("items", []):
            snippet, status = item["snippet"], item["status"]
            if snippet["channelId"] != channel["id"]:
                raise ValueError("Unexpected video owner in API response; catalog not changed.")
            if status.get("privacyStatus") != "public":
                continue
            live = item.get("liveStreamingDetails", {})
            stamp = live.get("actualStartTime") or live.get("scheduledStartTime") or snippet.get("publishedAt")
            local = local_time(stamp, zone)
            row = rows.setdefault(item["id"], {"local": {"service_date": None, "service": None,
                "proposed_title": None, "repair_status": "unassessed", "replacement_video_id": None}})
            row.update(seen_in_public_inventory=True, youtube={
                "title": snippet["title"], "url": "https://www.youtube.com/watch?v=" + item["id"],
                "published_at": snippet.get("publishedAt"), "privacy": "public",
                "duration": item.get("contentDetails", {}).get("duration"),
                "live_broadcast_content": snippet.get("liveBroadcastContent"),
                "has_live_details": bool(live),
                "actual_start": live.get("actualStartTime"), "actual_end": live.get("actualEndTime"),
                "scheduled_start": live.get("scheduledStartTime"), "event_local_time": local,
                "event_local_date": local[:10] if local else None,
                "date_basis": "actual_start" if live.get("actualStartTime") else "scheduled_start" if live.get("scheduledStartTime") else "published_at"})
            public_count += 1
    result.update(channel={"id": channel["id"], "title": channel["snippet"]["title"]},
                  last_synced_at=datetime.now(timezone.utc).isoformat(),
                  inventory_scope="Public videos returned by the authorized channel uploads playlist",
                  videos=dict(sorted(rows.items())))
    return result, public_count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="Read the complete uploads playlist and refresh public metadata")
    sync.add_argument("--channel-id")
    sync.add_argument("--credentials-dir", type=Path, default=WORK / "credentials")
    listing = sub.add_parser("list", help="List saved videos without accessing Google")
    listing.add_argument("--date", type=date.fromisoformat)
    listing.add_argument("--live-only", action="store_true")
    label = sub.add_parser("label", help="Edit local service/repair labels; does not rename on YouTube")
    label.add_argument("video_id")
    label.add_argument("--date", type=date.fromisoformat)
    label.add_argument("--service", choices=("morning", "evening", "other"))
    label.add_argument("--title")
    label.add_argument("--repair-status", choices=("unassessed", "planned", "rendered", "reviewed", "uploaded"))
    label.add_argument("--replacement-id")
    args = parser.parse_args(argv)
    try:
        catalog, previous = load(args.catalog)
        target = configured_channel(getattr(args, "channel_id", None))
        if catalog.get("channel") and catalog["channel"]["id"] != target:
            raise ValueError("Catalog channel differs from youtube.json; no changes made.")
        if args.command == "sync":
            updated, count = collect(service("read", args.credentials_dir), catalog, target)
            write_catalog(args.catalog, updated, previous)
            print(f"Saved {count} current public videos to {args.catalog.resolve()}. Local labels preserved.")
        elif args.command == "list":
            found = 0
            for video_id, row in sorted(catalog["videos"].items(), key=lambda pair: pair[1].get("youtube", {}).get("event_local_time") or "", reverse=True):
                remote, local = row.get("youtube", {}), row.get("local", {})
                day = local.get("service_date") or remote.get("event_local_date")
                if args.date and day != args.date.isoformat():
                    continue
                if args.live_only and not remote.get("has_live_details"):
                    continue
                found += 1
                print(f"{video_id} | {day or 'unknown date'} | {local.get('service') or 'unlabeled'} | {remote.get('title', '')}")
                print(f"  {remote.get('url', '')} | local time: {remote.get('event_local_time')} | date basis: {remote.get('date_basis')} | current: {row.get('seen_in_public_inventory')}")
                if local.get("proposed_title"):
                    print(f"  Proposed: {local['proposed_title']}")
            print(f"{found} matching videos. Last sync: {catalog.get('last_synced_at') or 'not yet fetched'}")
        else:
            if args.video_id not in catalog["videos"]:
                raise ValueError("Video is not in the catalog. Sync and list it first.")
            if args.title is not None and (not args.title.strip() or len(args.title) > 100):
                raise ValueError("Proposed title must contain 1..100 characters.")
            changes = {"service_date": args.date.isoformat() if args.date else None, "service": args.service,
                       "proposed_title": args.title, "repair_status": args.repair_status, "replacement_video_id": args.replacement_id}
            changes = {k: v for k, v in changes.items() if v is not None}
            if not changes:
                raise ValueError("Supply at least one label field to update.")
            catalog["videos"][args.video_id].setdefault("local", {}).update(changes)
            write_catalog(args.catalog, catalog, previous)
            print("Local labels saved. YouTube is unchanged.")
        return 0
    except Exception as exc:
        if isinstance(exc, (ValueError, OSError, KeyError)):
            print(f"ATTENTION: {exc}")
        else:
            print(f"ATTENTION: {type(exc).__name__}; check read authorization and API access. Catalog was not refreshed.")
        return 1
