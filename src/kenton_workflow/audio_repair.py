"""Measured local audio repair; no network calls or changes to source recordings."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work" / "audio-repair"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(command: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} failed:\n{result.stderr[-5000:]}")
    return result


def probe(path: Path, ffprobe: str) -> dict:
    return json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def measure(path: Path, ffmpeg: str, track: int, settings: str) -> dict:
    result = run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", f"0:a:{track}",
                  "-af", settings + ":print_format=json", "-f", "null", "-"])
    start = result.stderr.rfind('{')
    if start < 0:
        raise ValueError("FFmpeg returned no loudness measurements.")
    values = json.JSONDecoder().raw_decode(result.stderr[start:])[0]
    for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
        if not math.isfinite(float(values[key])):
            raise ValueError("Audio is silent or cannot be measured reliably; inspect the selected audio track.")
    return values


def repair(args: argparse.Namespace) -> Path:
    source = args.source.resolve()
    if not source.is_file():
        raise ValueError(f"Recording not found: {source}")
    ffmpeg, ffprobe = shutil.which(args.ffmpeg), shutil.which(args.ffprobe)
    if not ffmpeg or not ffprobe:
        raise ValueError("Install FFmpeg and ffprobe or pass --ffmpeg and --ffprobe with their full paths.")
    info = probe(source, ffprobe)
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    video = [s for s in info["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")]
    if not video or not 0 <= args.audio_track < len(audio):
        raise ValueError(f"Need video and a valid audio track; found {len(video)} video / {len(audio)} audio tracks.")
    if len(audio) > 1 and not args.track_selected:
        raise ValueError("Multiple audio tracks found. Select the board/program mix explicitly with --audio-track (zero based).")
    output_dir = (args.output_dir or WORK / datetime.now().strftime("repair-%Y%m%d-%H%M%S-%f")).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    output = output_dir / "repaired.mp4"
    partial = output_dir / "repaired.partial.mp4"
    report_path = output_dir / "repair.json"
    report = {"schema": 1, "state": "incomplete", "source": str(source), "output": str(output),
              "created": datetime.now(timezone.utc).isoformat(), "audio_track": args.audio_track,
              "target_lufs": args.lufs, "true_peak_ceiling": args.true_peak, "lra": args.lra,
              "source_sha256": digest(source)}
    save(report_path, report)
    log = output_dir / "repair.log"
    def note(message: str) -> None:
        print(message, flush=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")
    try:
        note(f"Source: {source}\nOutput: {output}\nMeasuring selected audio...")
        settings = f"loudnorm=I={args.lufs}:TP={args.true_peak}:LRA={args.lra}"
        before = measure(source, ffmpeg, args.audio_track, settings)
        report["before"] = before
        save(report_path, report)
        measured = ":".join(f"{name}={before[key]}" for name, key in (
            ("measured_I", "input_i"), ("measured_TP", "input_tp"),
            ("measured_LRA", "input_lra"), ("measured_thresh", "input_thresh"), ("offset", "target_offset")))
        note("Rendering corrected audio; copying video unless --transcode-video was selected...")
        codec = ["-c:v", "libx264", "-crf", "18", "-preset", "medium"] if args.transcode_video else ["-c:v", "copy"]
        run([ffmpeg, "-hide_banner", "-nostdin", "-n", "-i", str(source),
             "-map", f"0:{video[0]['index']}", "-map", f"0:a:{args.audio_track}", *codec,
             "-af", settings + ":" + measured + ":linear=true", "-c:a", "aac", "-b:a", "192k",
             "-ar", "48000", "-movflags", "+faststart", str(partial)])
        note("Measuring the encoded MP4...")
        after = measure(partial, ffmpeg, 0, settings)
        result_info = probe(partial, ffprobe)
        duration = float(info["format"]["duration"])
        output_duration = float(result_info["format"]["duration"])
        checks = {"loudness": abs(float(after["input_i"]) - args.lufs) <= 1.0,
                  "peak": float(after["input_tp"]) <= args.true_peak + 0.3,
                  "duration": abs(output_duration - duration) <= 1.0,
                  "source_unchanged": digest(source) == report["source_sha256"]}
        report.update(after=after, checks=checks, duration=duration, output_duration=output_duration)
        if not all(checks.values()):
            raise ValueError(f"Output checks failed: {checks}. Partial MP4 retained for diagnosis; do not upload it.")
        partial.rename(output)
        report.update(state="complete", output_sha256=digest(output))
        save(report_path, report)
        note(f"Complete: {before['input_i']} to {after['input_i']} LUFS; peak {after['input_tp']} dBTP.\nListen before upload. Report: {report_path}")
    except Exception as exc:
        report["error"] = str(exc)
        save(report_path, report)
        note(f"FAILED: {exc}")
        raise
    return report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, help="New directory; existing directories are never overwritten")
    parser.add_argument("--audio-track", type=int, default=None)
    parser.add_argument("--lufs", type=float, default=-18)
    parser.add_argument("--true-peak", type=float, default=-2)
    parser.add_argument("--lra", type=float, default=11)
    parser.add_argument("--transcode-video", action="store_true", help="Encode H.264 if source video cannot be copied into MP4")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args(argv)
    args.track_selected = args.audio_track is not None
    args.audio_track = args.audio_track if args.track_selected else 0
    if not (-70 <= args.lufs <= -5 and -9 <= args.true_peak <= 0 and 1 <= args.lra <= 50):
        parser.error("Targets must be finite: LUFS -70..-5, true peak -9..0, LRA 1..50.")
    try:
        repair(args)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ATTENTION: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
