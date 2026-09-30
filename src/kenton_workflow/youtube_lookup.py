"""Resolve an original livestream from local event date/time in the inventory."""
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from .audio_repair import ROOT, WORK
from .youtube_config import configured_channel


def resolve_video(day, service, catalog_path=None, log_path=None):
    catalog_path = catalog_path or ROOT / "data/youtube-videos.json"
    log_path = log_path or WORK / "youtube-lookup.log"

    def log(message):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now().astimezone().isoformat()} {day} {service}: {message}\n")

    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
        if catalog.get("channel", {}).get("id") != configured_channel():
            raise ValueError("Inventory channel differs from youtube.json.")
        matches = []
        for video_id, entry in catalog["videos"].items():
            item = entry.get("youtube", {})
            if item.get("event_local_date") != day.isoformat():
                continue
            # Upload publication time is not the service time. Only originals
            # with actual livestream start timestamps qualify.
            if item.get("date_basis") != "actual_start":
                continue
            try:
                local = datetime.fromisoformat(item["event_local_time"])
                if local.date() != day or local.utcoffset() is None:
                    raise ValueError("inconsistent date or missing timezone")
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid event_local_time for {video_id}: {exc}") from exc
            if ("morning" if local.hour < 12 else "evening") == service:
                matches.append((video_id, item["event_local_time"]))
        if not matches:
            raise ValueError("No matching livestream found. Refresh with scripts/inventory-youtube.py sync and check the date/service.")
        if len(matches) > 1:
            raise ValueError("Duplicate matches; no video selected: " + "; ".join(f"{i} ({t})" for i, t in matches))
        video_id, timestamp = matches[0]
        log(f"Selected {video_id} ({timestamp})")
        return video_id
    except (OSError, ValueError, KeyError) as exc:
        log(f"ATTENTION: {exc}")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--service", required=True, choices=("morning", "evening"))
    args = parser.parse_args(argv)
    try:
        print(resolve_video(args.date, args.service))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ATTENTION: {exc}")
        return 1
