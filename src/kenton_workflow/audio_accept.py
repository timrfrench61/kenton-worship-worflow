"""Explicit listening acceptance of a completed render with a peak exception."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .audio_repair import digest, save


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        report_path = args.report.resolve()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        checks = report.get("checks", {})
        required = {"loudness", "peak", "duration", "source_unchanged"}
        if set(checks) != required or any(type(v) is not bool for v in checks.values()):
            raise ValueError("The render must have completed its measurements before acceptance.")
        if not all(checks[k] for k in required - {"peak"}):
            raise ValueError("Only the peak check can be accepted by listening; other checks must pass.")
        if digest(Path(report["source"])) != report["source_sha256"]:
            raise ValueError("Source changed since repair.")
        media = Path(report["output"])
        if report.get("state") == "complete":
            if digest(media) != report.get("output_sha256"):
                raise ValueError("Repaired file changed since verification.")
        else:
            media = report_path.parent / "repaired.partial.mp4"
        if not media.is_file() or not media.stat().st_size:
            raise ValueError("Rendered MP4 is missing or empty.")
        accepted = report_path.parent / "accepted.json"
        if accepted.exists():
            raise ValueError(f"Already accepted: {accepted}")
        report.update(state="accepted", output=str(media), output_sha256=digest(media),
                      acceptance={"listening_approved": True,
                                  "accepted_at": datetime.now(timezone.utc).isoformat(),
                                  "waived_checks": [k for k, value in checks.items() if not value],
                                  "original_report": str(report_path),
                                  "original_report_sha256": digest(report_path)})
        save(accepted, report)
        print(f"Accepted: {accepted}\nUse this report with youtube-audio.py upload.")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ATTENTION: {exc}")
        return 1
