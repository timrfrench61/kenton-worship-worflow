"""Shared target for Kenton's YouTube commands; never infer it from a login."""
import json
import re
from .audio_repair import ROOT

CONFIG = ROOT / "youtube.json"


def configured_channel(requested=None):
    config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    channel_id = config.get("channel_id")
    if not isinstance(channel_id, str) or not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id):
        raise ValueError(f"Set a valid channel_id in {CONFIG}.")
    if requested is not None and requested != channel_id:
        raise ValueError(f"Requested channel differs from youtube.json. Target is {config.get('channel_name', '')} ({channel_id}).")
    return channel_id
