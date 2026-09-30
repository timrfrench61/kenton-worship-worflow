"""Download one verified channel recording; never upload or change YouTube."""
import argparse
import json
import re
import shutil
from datetime import date
from pathlib import Path

from .audio_repair import ROOT, WORK, digest, probe, save
from .youtube_config import configured_channel


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id", help="ID from data/youtube-videos.json")
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--service", required=True, choices=("morning", "evening"))
    parser.add_argument("--cookies-from-browser", choices=("chrome", "edge", "firefox"),
                        help="Optional: explicitly read this browser's signed-in cookies")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", args.video_id):
            raise ValueError("Supply an 11-character video ID, not a URL.")
        channel = configured_channel()
        catalog = json.loads((ROOT / "data/youtube-videos.json").read_text(encoding="utf-8-sig"))
        entry = catalog["videos"].get(args.video_id)
        if entry is None:
            raise ValueError("Video not in inventory. Run scripts/inventory-youtube.py sync first.")
        recorded_date = entry.get("local", {}).get("service_date") or entry["youtube"].get("event_local_date")
        if recorded_date != args.date.isoformat():
            raise ValueError(f"Inventory date is {recorded_date}; check the selected recording/date.")
        labelled_service = entry.get("local", {}).get("service")
        if labelled_service and labelled_service != args.service:
            raise ValueError(f"Inventory labels this recording {labelled_service}; check --service.")
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            raise ValueError("FFmpeg and ffprobe must be on PATH.")
        folder = WORK / "source"
        stem = f"{args.date:%Y%m%d}-{args.service}"
        output = folder / f"{stem}.mp4"
        receipt = folder / f"{stem}.download.json"
        staging = folder / f"{stem}.download"
        if output.exists() or receipt.exists():
            raise ValueError(f"Source/receipt already exists: {output}. Nothing overwritten.")
        try:
            from yt_dlp import YoutubeDL
        except ImportError:
            raise ValueError("Install download dependencies: python -m pip install -r requirements-download.txt") from None

        def check(info, *, incomplete=False):
            if incomplete:
                return None
            if info.get("id") != args.video_id or info.get("channel_id") != channel:
                raise ValueError("Download rejected: video/channel does not match configured Kenton channel.")
            if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
                raise ValueError("Wait until the livestream has finished processing.")
            return None

        options = {
            "noplaylist": True, "match_filter": check,
            "format": "bv[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc1]",
            "merge_output_format": "mp4", "ffmpeg_location": str(Path(ffmpeg).parent),
            "outtmpl": str(staging / "recording.%(ext)s"),
            "overwrites": False,
        }
        if args.cookies_from_browser:
            options["cookiesfrombrowser"] = (args.cookies_from_browser,)
        # Refuse an existing staging directory: partial runs remain for diagnosis.
        staging.mkdir(parents=True, exist_ok=False)
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(f"https://www.youtube.com/watch?v={args.video_id}", download=True)
        check(info)
        downloaded = staging / "recording.mp4"
        media = probe(downloaded, ffprobe)
        types = {stream.get("codec_type") for stream in media["streams"]}
        if not {"audio", "video"} <= types or float(media["format"]["duration"]) <= 0:
            raise ValueError("Downloaded file must contain video and audio with positive duration.")
        record = {"video_id": args.video_id, "channel_id": channel,
                  "service_date": args.date.isoformat(), "service": args.service,
                  "source": str(output), "sha256": digest(downloaded),
                  "duration": media["format"]["duration"], "title": info.get("title")}
        downloaded.rename(output)
        save(receipt, record)
        if not any(staging.iterdir()):
            staging.rmdir()
        print(f"Downloaded: {output}\nNext: run scripts/repair-audio.py on this file.")
        return 0
    except Exception as exc:
        print(f"ATTENTION: {exc}")
        print("No upload performed. Preserve any .download folder for diagnosis; do not use partial media for repair.")
        return 1
