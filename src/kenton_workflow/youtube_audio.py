"""Explicit read, private-upload, and old-video actions for repaired recordings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio_repair import WORK, digest, save
from .youtube_config import configured_channel

BASE = "https://www.googleapis.com/auth/"
SCOPES = {"read": [BASE + "youtube.readonly"],
          "upload": [BASE + "youtube.upload", BASE + "youtube.readonly"],
          "manage": [BASE + "youtube.force-ssl"]}


def dependencies():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise ValueError("YouTube dependencies missing. Install requirements-youtube.txt in a local virtual environment; see docs/01-kenton-audio-repair-001.md.") from exc
    return Request, Credentials, InstalledAppFlow, build, MediaFileUpload


def service(role: str, directory: Path, authorize: bool = False):
    Request, Credentials, Flow, build, _ = dependencies()
    directory.mkdir(parents=True, exist_ok=True)
    token = directory / f"token-{role}.json"
    if authorize:
        client = directory / f"credentials-{role}.json"
        if not client.is_file():
            raise ValueError(f"Save the {role} Desktop OAuth client JSON at {client}")
        flow = Flow.from_client_secrets_file(str(client), SCOPES[role], autogenerate_code_verifier=True)
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent", include_granted_scopes="false")
    else:
        if not token.is_file():
            raise ValueError(f"Missing {role} grant. Run auth {role} first; expected {token}")
        raw = json.loads(token.read_text(encoding="utf-8"))
        if set(raw.get("scopes", [])) != set(SCOPES[role]):
            raise ValueError(f"Unexpected scopes in {token.name}; authorize this role again.")
        credentials = Credentials.from_authorized_user_file(str(token), SCOPES[role])
        if not credentials.valid:
            if not credentials.refresh_token:
                raise ValueError(f"Expired {role} grant; authorize again.")
            credentials.refresh(Request())
    granted = credentials.granted_scopes
    if granted is not None and set(granted) != set(SCOPES[role]):
        raise ValueError("Google returned different scopes. Use separate OAuth projects for these roles and authorize again.")
    api = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    channel_check(api, configured_channel())
    token.write_text(credentials.to_json(), encoding="utf-8")
    return api


def channel_check(api, expected: str) -> None:
    channels = api.channels().list(part="id", mine=True).execute().get("items", [])
    if [item["id"] for item in channels] != [expected]:
        raise ValueError(f"Authorization does not provide configured channel {expected}. Run auth again and select Kenton Church EPC, not your personal channel or Kenton Session. No video changes made.")


def video(api, video_id: str, channel: str) -> dict:
    items = api.videos().list(part="snippet,status,processingDetails", id=video_id).execute().get("items", [])
    if len(items) != 1 or items[0]["snippet"]["channelId"] != channel:
        raise ValueError(f"Video {video_id} is unavailable or belongs to another channel.")
    return items[0]


def repair_file(report_path: Path) -> tuple[dict, Path]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("state") != "complete" or not report.get("checks") or not all(report["checks"].values()):
        raise ValueError("Repair is incomplete or failed measurement checks.")
    path = Path(report["output"])
    if not path.is_file() or digest(path) != report["output_sha256"]:
        raise ValueError("Repaired MP4 is missing or changed; run repair again and review the new result.")
    return report, path


def upload(args, api, media_factory) -> dict:
    if not args.reviewed:
        raise ValueError("Listen to the repaired file, then pass --reviewed to upload privately.")
    report, path = repair_file(args.report)
    receipt = args.report.parent / "upload.json"
    if receipt.exists():
        raise ValueError(f"Upload already attempted. Inspect {receipt} and YouTube Studio before another upload; automatic retries could duplicate it.")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    for key in ("title", "description", "categoryId", "madeForKids"):
        if key not in metadata:
            raise ValueError(f"Upload metadata is missing {key}.")
    if not isinstance(metadata["title"], str) or not metadata["title"].strip() or len(metadata["title"]) > 100:
        raise ValueError("Supply a nonempty title of at most 100 characters.")
    if not isinstance(metadata["description"], str) or type(metadata["madeForKids"]) is not bool:
        raise ValueError("Description must be text; madeForKids must be true or false.")
    if not str(metadata["categoryId"]).isdigit():
        raise ValueError("categoryId must be a YouTube numeric category ID.")
    channel_check(api, args.channel_id)
    old = video(api, args.original_id, args.channel_id)
    if old["snippet"].get("liveBroadcastContent") in ("live", "upcoming"):
        raise ValueError("Original must be a completed recording, not a live or scheduled broadcast.")
    body = {"snippet": {"title": metadata["title"], "description": metadata["description"],
                        "categoryId": str(metadata["categoryId"])},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": metadata["madeForKids"]}}
    record = {"state": "started", "original_id": args.original_id, "channel_id": args.channel_id,
              "output_sha256": report["output_sha256"], "request": body}
    save(receipt, record)
    request = api.videos().insert(part="snippet,status", body=body, notifySubscribers=False,
                                 media_body=media_factory(str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True))
    response = None
    while response is None:
        progress, response = request.next_chunk(num_retries=0)
        if progress:
            print(f"Upload {progress.progress():.0%}", flush=True)
    record.update(state="uploaded", video_id=response["id"], url=f"https://www.youtube.com/watch?v={response['id']}")
    save(receipt, record)  # Keep the returned ID even if verification fails.
    created = video(api, response["id"], args.channel_id)
    if created["status"]["privacyStatus"] != "private":
        raise ValueError(f"Unexpected upload privacy. Inspect {record['url']} immediately.")
    record.update(state="private-verified", response=created)
    save(receipt, record)
    return record


def mark_original(args, api) -> dict:
    if not args.reviewed:
        raise ValueError("Review the replacement on YouTube, then pass --reviewed for the selected old-video action.")
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if receipt.get("state") != "private-verified" or receipt.get("channel_id") != args.channel_id:
        raise ValueError("Need a verified upload receipt for this channel.")
    original_id, replacement_id = receipt["original_id"], receipt["video_id"]
    if original_id == replacement_id:
        raise ValueError("Original and replacement must differ.")
    journal = args.receipt.parent / f"original-{args.action}.json"
    if journal.exists():
        raise ValueError(f"Action previously attempted; inspect {journal} and YouTube before retrying.")
    channel_check(api, args.channel_id)
    old = video(api, original_id, args.channel_id)
    replacement = video(api, replacement_id, args.channel_id)
    if old["snippet"].get("liveBroadcastContent") in ("live", "upcoming"):
        raise ValueError("Cannot mark a live or upcoming broadcast.")
    record = {"action": args.action, "original_id": original_id, "replacement_id": replacement_id, "before": old,
              "state": "documented" if args.action == "document" else "started"}
    if args.action == "document":
        save(journal, record)
        return record
    if replacement["status"]["privacyStatus"] != "public" or replacement.get("processingDetails", {}).get("processingStatus") != "succeeded":
        raise ValueError("Replacement must be processed, reviewed, and made public in YouTube Studio before changing the old video.")
    if args.action == "notice":
        snippet = {key: value for key, value in old["snippet"].items()
                   if key in ("title", "description", "tags", "categoryId", "defaultLanguage")}
        notice = f"Audio-corrected recording: https://www.youtube.com/watch?v={replacement_id}"
        snippet["description"] = notice + "\n\n" + snippet.get("description", "")
        if len(snippet["description"].encode("utf-8")) > 5000:
            raise ValueError("Correction notice would exceed the description limit; edit manually in Studio.")
        body, part = {"id": original_id, "snippet": snippet}, "snippet"
    else:
        status = {key: value for key, value in old["status"].items() if key in (
            "embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia")}
        if old["status"].get("publishAt"):
            raise ValueError("Original has a publication schedule; manage it manually in Studio.")
        status["privacyStatus"] = args.action
        body, part = {"id": original_id, "status": status}, "status"
    record["request"] = body
    save(journal, record)  # Persist snapshot before any remote mutation.
    api.videos().update(part=part, body=body).execute()
    updated = video(api, original_id, args.channel_id)
    if any(updated[part].get(key) != value for key, value in body[part].items()):
        raise ValueError(f"Change could not be verified. Inspect YouTube and {journal} before retrying.")
    record.update(state="verified", after=updated)
    save(journal, record)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-dir", type=Path, default=WORK / "credentials")
    sub = parser.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth", help="Authorize one role interactively")
    auth.add_argument("role", choices=SCOPES)
    read = sub.add_parser("read", help="Save video metadata, not video/audio bytes")
    read.add_argument("video_id")
    read.add_argument("--output", type=Path, required=True)
    up = sub.add_parser("upload", help="Upload a measured, reviewed MP4 privately")
    up.add_argument("report", type=Path)
    up.add_argument("--metadata", type=Path, required=True)
    up.add_argument("--original-id", required=True)
    up.add_argument("--reviewed", action="store_true")
    mark = sub.add_parser("mark-original", help="Explicitly choose how to mark the previous video")
    mark.add_argument("receipt", type=Path)
    mark.add_argument("--action", choices=("document", "notice", "private", "unlisted"), required=True)
    mark.add_argument("--reviewed", action="store_true")
    for command in (read, up, mark):
        command.add_argument("--channel-id", help="Optional assertion; must match youtube.json")
    args = parser.parse_args(argv)
    try:
        # Fail before OAuth/network access when the user has not indicated review.
        if args.command in ("upload", "mark-original") and not args.reviewed:
            raise ValueError("Review the file/replacement first, then pass --reviewed.")
        args.channel_id = configured_channel(getattr(args, "channel_id", None))
        if args.command == "auth":
            service(args.role, args.credentials_dir, authorize=True)
            print(f"Authorized {args.role}.")
        elif args.command == "read":
            if args.output.exists():
                raise ValueError(f"Output exists; choose a new metadata path: {args.output}")
            api = service("read", args.credentials_dir)
            channel_check(api, args.channel_id)
            result = video(api, args.video_id, args.channel_id)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            save(args.output, result)
            print(f"Saved metadata: {args.output.resolve()}")
        elif args.command == "upload":
            repair_file(args.report)
            result = upload(args, service("upload", args.credentials_dir), dependencies()[-1])
            print(f"Private upload: {result['url']}\nOriginal unchanged. Review processing and playback in YouTube Studio.")
        else:
            role = "read" if args.action == "document" else "manage"
            result = mark_original(args, service(role, args.credentials_dir))
            print(f"Original-video action: {result['state']}")
        return 0
    except Exception as exc:
        # OAuth/HTTP exceptions can contain tokens or request URLs; do not dump them.
        if isinstance(exc, (ValueError, OSError, KeyError)):
            print(f"ATTENTION: {exc}")
        else:
            print(f"ATTENTION: {type(exc).__name__}. Check authorization, API access/quota and saved action receipt. Do not blindly repeat an upload.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
